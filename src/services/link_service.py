# src/services/link_service.py

import traceback
from uuid import UUID
from typing import List, Optional, Tuple
from supabase import AsyncClient
from postgrest.exceptions import (
    APIError as PostgrestAPIError,
)  # Specific exception from Supabase client library
from postgrest.types import CountMethod  # Type hint for count parameter

# Import custom exceptions relevant to this service
from src.services.custom_exceptions import (
    AliasConflictException,
    DatabaseException,
    NotFoundException,
    ValidationException,
    ServiceException,  # Base service exception
    LinkNotFoundException,  # More specific not found for links
)

# Import Pydantic models (DTOs) used for data validation and structuring
from src.schemas.link import LinkCreate, LinkUpdate, LinkResponse, PaginatedLinkResponse
from src.schemas.stats import LinkStatsResponse, TargetClickStat
from src.schemas.enums import TargetTypeEnum

# --- Constants ---
# PostgreSQL error code for unique constraint violations
POSTGRES_UNIQUE_VIOLATION_CODE = "23505"
# Example constraint name (more relevant if handling multiple unique constraints)
# ROUTING_RULES_LINK_ID_PRIORITY_KEY = "routing_rules_link_id_priority_key"


class LinkService:
    """
    Manages the business logic for creating, retrieving, updating, deleting,
    and getting statistics for Routr Links. Interacts with the Supabase database.
    Assumes operations are performed in the context of an authenticated user,
    whose identity is used implicitly via RLS policies enforced by Supabase
    (unless using the service role client, which is not typical here).
    """

    def __init__(self, supabase_client: AsyncClient):
        """
        Initializes the LinkService.

        Args:
            supabase_client: An initialized asynchronous Supabase client instance.
        """
        self.supabase = supabase_client
        # Define table names for easier maintenance
        self.links_table = "routr_links"
        self.rules_table = "routing_rules"  # Used for statistics

    def _handle_db_error(self, error: Exception, context: str):
        """
        Centralized error handler for database operations within this service.
        Analyzes exceptions (especially PostgrestAPIError) and maps them
        to specific custom business exceptions (e.g., AliasConflictException, DatabaseException).
        Re-raises known business exceptions directly.

        Args:
            error: The exception caught during a database operation.
            context: A string describing the operation context for logging/debugging.

        Raises:
            AliasConflictException: If a unique constraint violation on the alias occurs.
            NotFoundException: If re-raising a NotFoundException caught earlier.
            DatabaseException: For other database-related errors (Postgrest errors, connection issues).
            ServiceException: Potentially as a fallback for truly unexpected errors.
        """
        # Re-raise known business exceptions immediately if they were caught and passed here.
        if isinstance(
            error, (AliasConflictException, NotFoundException, ValidationException)
        ):
            print(
                f"Re-raising known business exception from {context}: {type(error).__name__}"
            )
            raise error

        # Handle specific errors from the Supabase client library (PostgREST)
        if isinstance(error, PostgrestAPIError):
            # Extract error details safely, providing defaults if attributes are missing
            error_code = getattr(error, "code", None)
            error_message = getattr(error, "message", "") or ""
            error_details = getattr(error, "details", "") or ""
            error_status = getattr(error, "status", "N/A")

            print(
                f"[ERROR] PostgrestAPIError during {context}: Status={error_status}, Code={error_code}, Message='{error_message}' Details='{error_details}'"
            )  # MVP Log

            # Check for unique constraint violation error code
            if error_code == POSTGRES_UNIQUE_VIOLATION_CODE:
                # Check if the violation specifically relates to the 'alias' field/constraint
                # This might involve checking the constraint name or keywords in the message/details.
                # Note: Relying on string checks can be fragile if DB messages change.
                is_alias_conflict = (
                    "routr_links_alias_key" in error_message
                    or "routr_links_alias_key" in error_details
                    # Add more general checks as fallback
                    or ("alias" in error_details.lower())
                    or ("alias" in error_message.lower())
                )

                if is_alias_conflict:
                    print(f"[CONFLICT] Alias conflict detected during {context}.")
                    # Raise the specific business exception for alias conflicts.
                    raise AliasConflictException() from error
                else:
                    # Handle other unique constraint violations (e.g., should be in RuleService for priority)
                    print(
                        f"[ERROR] Unique constraint violation (other) during {context}: {error_details or error_message}"
                    )
                    raise DatabaseException(
                        detail=f"Unique constraint violation during {context}: {error_details or error_message}"
                    ) from error

            # For other PostgREST errors, raise a generic DatabaseException
            raise DatabaseException(
                detail=f"Database API error during {context}: {error_message or 'Unknown PostgREST error'}"
            ) from error
        else:
            # Handle any other unexpected exceptions (network errors, programming errors, etc.)
            print(f"[ERROR] Unexpected error during {context}:")  # MVP Log
            traceback.print_exc()  # Log the full traceback for debugging
            # Raise a generic exception indicating an unexpected issue.
            raise DatabaseException(  # Or potentially ServiceException
                detail=f"An unexpected error occurred during {context}."
            ) from error

    async def create_link(self, link_data: LinkCreate, user_id: UUID) -> LinkResponse:
        """
        Creates a new link record in the database.

        Args:
            link_data: A LinkCreate object containing validated alias and optional default_url.
            user_id: The UUID of the user creating the link.

        Returns:
            A LinkResponse object representing the newly created link.

        Raises:
            AliasConflictException: If the chosen alias already exists for the user.
            DatabaseException: For other database-related errors.
        """
        # Prepare data for insertion: dump Pydantic model, add user_id.
        insert_data = link_data.model_dump()
        insert_data["user_id"] = str(
            user_id
        )  # Ensure UUID is converted to string if needed by DB driver

        # Convert HttpUrl back to string for database storage if present
        if insert_data.get("default_url") is not None:
            insert_data["default_url"] = str(insert_data["default_url"])

        context = f"link creation for alias '{link_data.alias}' by user {user_id}"
        print(f"Attempting {context} with data: {insert_data}")  # MVP Log

        try:
            # Execute the insert operation against the links table
            response = (
                await self.supabase.table(self.links_table)
                .insert(insert_data)
                .execute()
            )

            # Validate the response structure and extract the created data
            if (
                response
                and response.data
                and isinstance(response.data, list)
                and len(response.data) == 1
            ):
                created_data = response.data[0]
                print(
                    f"Successfully created link with ID: {created_data.get('id')}"
                )  # MVP Log
                # Validate and structure the response data using LinkResponse schema
                created_link_dto = LinkResponse.model_validate(created_data)
                return created_link_dto
            else:
                # Handle unexpected response format after successful-looking insert
                print(
                    f"[ERROR] Insert query executed but did not return expected data. Response: {response}"
                )  # MVP Log
                raise DatabaseException(
                    "Failed to retrieve created link data after insert (unexpected response format)."
                )

        except AliasConflictException as e:
            # Explicitly catch and re-raise known business exceptions if needed for specific logging/handling here
            print(f"Re-raising AliasConflictException from {context}")  # MVP Log
            raise e
        except Exception as e:
            # Delegate other exceptions to the centralized error handler
            self._handle_db_error(e, context=context)
            # Ensure an exception is always raised if _handle_db_error doesn't (shouldn't happen)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def get_link_by_id(self, link_id: UUID, user_id: UUID) -> LinkResponse:
        """
        Retrieves a specific link by its ID, ensuring the user has access (via RLS).

        Args:
            link_id: The UUID of the link to retrieve.
            user_id: The UUID of the user requesting the link (used implicitly by RLS).

        Returns:
            A LinkResponse object if the link is found and accessible.

        Raises:
            NotFoundException: If the link is not found or the user lacks permission.
            DatabaseException: For other database-related errors.
        """
        context = f"link retrieval for ID {link_id} by user {user_id}"
        print(f"Attempting {context}")  # MVP Log
        try:
            # Query the links table for a single record matching the ID
            response = (
                await self.supabase.table(self.links_table)
                .select("*")  # Select all columns for the LinkResponse model
                .eq("id", str(link_id))  # Filter by primary key
                # .eq("user_id", str(user_id)) # RLS should handle this, but explicit check can be added if needed
                .maybe_single()  # Expect 0 or 1 result; returns None if not found, raises error for multiple
                .execute()
            )

            # Check if data was returned
            if response and response.data:
                print(f"Successfully retrieved link with ID: {link_id}")  # MVP Log
                # Validate and structure the response data
                link_dto = LinkResponse.model_validate(response.data)
                return link_dto
            else:
                # If maybe_single() returned None or response.data is empty
                print(
                    f"[WARNING] Link not found or access denied for {context}"
                )  # MVP Log
                # Raise the specific exception for not found resources
                raise NotFoundException(
                    detail="Link not found or you do not have permission to access it."
                )

        except NotFoundException as e:
            # Re-raise NotFoundException explicitly
            print(f"Re-raising NotFoundException from {context}")  # MVP Log
            raise e
        except Exception as e:
            # Delegate other exceptions to the centralized handler
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback

    async def get_links_paginated(
        self, user_id: UUID, page: int, page_size: int
    ) -> PaginatedLinkResponse:
        """
        Retrieves a paginated list of links owned by the specified user.

        Args:
            user_id: The UUID of the user whose links to retrieve (used implicitly by RLS).
            page: The page number (1-based).
            page_size: The number of items per page.

        Returns:
            A PaginatedLinkResponse object containing the list of links for the page
            and pagination metadata.

        Raises:
            DatabaseException: For database-related errors.
        """
        context = f"paginated link retrieval for user {user_id} (page={page}, size={page_size})"
        print(f"Attempting {context}")  # MVP Log

        # Calculate offset for pagination
        offset = (page - 1) * page_size
        range_to = offset + page_size - 1

        try:
            # Query the links table with pagination, ordering, and count
            response = (
                await self.supabase.table(self.links_table)
                # Request exact total count for pagination metadata
                .select("*", count=CountMethod.exact)
                # .eq("user_id", str(user_id)) # RLS should handle this
                .order("created_at", desc=True)  # Order by creation date, newest first
                .range(offset, range_to)  # Apply pagination range
                .execute()
            )

            # Extract data and count safely
            items_data = response.data if response and response.data else []
            total_count = (
                response.count if response and response.count is not None else 0
            )

            print(
                f"Retrieved {len(items_data)} links out of {total_count} total for {context}"
            )  # MVP Log

            # Validate and structure each item in the list
            link_items = [LinkResponse.model_validate(item) for item in items_data]

            # Construct the final paginated response object
            paginated_response = PaginatedLinkResponse(
                items=link_items, total=total_count, page=page, page_size=page_size
            )
            return paginated_response

        except Exception as e:
            # Handle potential database errors during list retrieval
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback

    async def update_link(
        self, link_id: UUID, update_data: LinkUpdate, user_id: UUID
    ) -> LinkResponse:
        """
        Updates an existing link (currently only default_url).

        Args:
            link_id: The UUID of the link to update.
            update_data: A LinkUpdate object containing the fields to update.
            user_id: The UUID of the user performing the update (used implicitly by RLS).

        Returns:
            A LinkResponse object representing the updated link state.

        Raises:
            NotFoundException: If the link is not found or the user lacks permission.
            DatabaseException: For other database-related errors.
        """
        context = f"link update for ID {link_id} by user {user_id}"
        print(f"Attempting {context}")  # MVP Log

        # Prepare the update payload, excluding fields not provided in the PATCH request
        db_update_payload = update_data.model_dump(exclude_unset=True)

        # Convert HttpUrl back to string if default_url is being updated
        if (
            "default_url" in db_update_payload
            and db_update_payload["default_url"] is not None
        ):
            db_update_payload["default_url"] = str(db_update_payload["default_url"])
        # Note: If default_url is explicitly set to None in update_data, it will be None here,
        # which correctly clears the field in the database.

        # If the update payload is empty (no fields were provided to change),
        # simply return the current state of the link.
        if not db_update_payload:
            print(
                f"No fields to update for {context}. Returning current state."
            )  # MVP Log
            try:
                # Fetch and return the current link data. This also serves as an existence/permission check.
                return await self.get_link_by_id(link_id=link_id, user_id=user_id)
            except NotFoundException:
                print(f"Link {link_id} not found during empty update check.")  # MVP Log
                raise  # Re-raise the NotFoundException from get_link_by_id
            except Exception as e:
                # Handle errors during the existence check
                self._handle_db_error(
                    e, context=f"get_link_by_id during update check for {context}"
                )
                raise DatabaseException(
                    f"Unhandled error during get_link_by_id in update check for {context}"
                )

        # If there are fields to update, execute the update operation
        try:
            response = (
                await self.supabase.table(self.links_table)
                .update(db_update_payload)
                .eq("id", str(link_id))  # Target the specific link
                # .eq("user_id", str(user_id)) # RLS should handle ownership
                .execute()
            )

            # Check if the update was successful and data was returned
            if (
                response
                and response.data
                and isinstance(response.data, list)
                and len(response.data) == 1
            ):
                updated_data = response.data[0]
                print(f"Successfully updated link with ID: {link_id}")  # MVP Log
                # Validate and structure the updated link data
                updated_link_dto = LinkResponse.model_validate(updated_data)
                return updated_link_dto
            else:
                # If update didn't return data, it likely means the row wasn't found or wasn't accessible (RLS)
                print(
                    f"[WARNING] Link not found or update failed for {context}. Response: {response}"
                )  # MVP Log
                raise NotFoundException(
                    detail="Link not found or you do not have permission to update it."
                )

        except NotFoundException as e:
            # Re-raise NotFoundException explicitly
            print(f"Re-raising NotFoundException from {context}")  # MVP Log
            raise e
        except Exception as e:
            # Delegate other exceptions to the centralized handler
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback

    async def delete_link(self, link_id: UUID, user_id: UUID) -> None:
        """
        Deletes a specific link by its ID. RLS policy should ensure only the owner can delete.

        Args:
            link_id: The UUID of the link to delete.
            user_id: The UUID of the user performing the deletion (used implicitly by RLS).

        Raises:
            NotFoundException: If the link is not found or the user lacks permission.
            DatabaseException: For other database-related errors.
        """
        context = f"link deletion for ID {link_id} by user {user_id}"
        print(f"Attempting {context}")  # MVP Log

        try:
            # Execute the delete operation, requesting the count of deleted rows
            response = (
                await self.supabase.table(self.links_table)
                .delete(count=CountMethod.exact)  # Request count of deleted rows
                .eq("id", str(link_id))  # Target the specific link
                # .eq("user_id", str(user_id)) # RLS should handle ownership
                .execute()
            )

            # Check the count of deleted rows
            if response and response.count == 1:
                # Successful deletion
                print(f"Successfully deleted link with ID: {link_id}")  # MVP Log
                return  # Return None on success
            elif response and response.count == 0:
                # No rows were deleted, implies link not found or no permission (RLS)
                print(
                    f"[WARNING] Link not found or access denied during delete for {context}"
                )  # MVP Log
                raise NotFoundException(
                    detail="Link not found or you do not have permission to delete it."
                )
            else:
                # Unexpected response (e.g., count is None, > 1, or response object is missing)
                count_val = response.count if response else "N/A"
                print(
                    f"[ERROR] Unexpected delete count ({count_val}) or invalid response for {context}"
                )  # MVP Log
                raise DatabaseException("Unexpected result during link deletion.")

        except NotFoundException as e:
            # Re-raise NotFoundException explicitly
            print(f"Re-raising NotFoundException from {context}")  # MVP Log
            raise e
        except Exception as e:
            # Delegate other exceptions to the centralized handler
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback

    async def get_link_statistics(
        self, link_id: UUID, user_id: UUID
    ) -> LinkStatsResponse:
        """
        Retrieves click statistics for a specific link, including total clicks
        and a breakdown by rule target.

        Args:
            link_id: The UUID of the link to get statistics for.
            user_id: The UUID of the user requesting statistics (used implicitly by RLS).

        Returns:
            A LinkStatsResponse object containing the aggregated statistics.

        Raises:
            NotFoundException: If the link is not found or the user lacks permission.
            DatabaseException: For database-related errors during data retrieval.
        """
        context = f"statistics retrieval for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")  # MVP Log

        try:
            # Step 1: Fetch the basic link data (ID, alias, total_clicks).
            # This also serves as an existence and permission check via RLS.
            print(f"Fetching base link data for {context}")  # MVP Log
            link_response = (
                await self.supabase.table(self.links_table)
                .select("id, alias, total_clicks")
                .eq("id", str(link_id))
                # .eq("user_id", str(user_id)) # RLS handles ownership
                .maybe_single()
                .execute()
            )

            # Check if link data was found
            if not (link_response and link_response.data):
                print(
                    f"[WARNING] Link not found or access denied for {context}"
                )  # MVP Log
                raise NotFoundException(
                    "Link not found or you do not have permission to access it."
                )

            link_data = link_response.data
            print(f"Link data found for {context}. Fetching rules.")  # MVP Log

            # Step 2: Fetch associated rules to get per-rule click counts.
            rules_response = (
                await self.supabase.table(self.rules_table)
                .select(
                    "id, target_type, target_value, current_clicks"
                )  # Select relevant rule fields
                .eq("link_id", str(link_id))  # Filter by the link ID
                .order(
                    "priority", desc=False
                )  # Order consistently (optional but good practice)
                .execute()
            )

            rules_stats_data = (
                rules_response.data if rules_response and rules_response.data else []
            )
            print(
                f"Retrieved {len(rules_stats_data)} rules for {context}. Processing stats."
            )  # MVP Log

            # Step 3: Process the rule data into TargetClickStat objects.
            target_clicks_list: List[TargetClickStat] = []
            for rule in rules_stats_data:
                target_value_preview: str
                try:
                    # Safely convert target_type string from DB to Enum member
                    target_type_enum = TargetTypeEnum(rule["target_type"])
                    target_type_str = target_type_enum.value
                except ValueError:
                    # Handle unexpected values gracefully
                    print(
                        f"[WARNING] Invalid target_type '{rule.get('target_type')}' found for rule {rule.get('id','N/A')}"
                    )  # MVP Log
                    target_type_str = "unknown"  # Assign a placeholder

                target_value = rule["target_value"]
                current_clicks = rule["current_clicks"]
                rule_id = UUID(rule["id"])  # Convert rule ID string to UUID

                # Create a user-friendly preview for the target value
                if target_type_str == TargetTypeEnum.URL.value:
                    target_value_preview = (
                        target_value  # For URL, preview is the URL itself
                    )
                elif target_type_str == TargetTypeEnum.HTML.value:
                    target_value_preview = (
                        "[Custom HTML Content]"  # For HTML, use a placeholder
                    )
                else:
                    target_value_preview = "[Unknown Target Type]"

                # Validate and structure the per-rule stat data
                target_stat = TargetClickStat.model_validate(
                    {
                        "rule_id": rule_id,
                        "target_type": target_type_str,  # Use the validated string value
                        "target_value_preview": target_value_preview,
                        "current_clicks": current_clicks,
                    }
                )
                target_clicks_list.append(target_stat)

            # Step 4: Construct the final LinkStatsResponse object.
            stats_response = LinkStatsResponse.model_validate(
                {
                    "link_id": UUID(link_data["id"]),  # Convert link ID string to UUID
                    "alias": link_data["alias"],
                    "total_clicks": link_data["total_clicks"],
                    "target_clicks": target_clicks_list,  # Embed the list of per-rule stats
                }
            )

            print(f"Successfully prepared statistics for {context}")  # MVP Log
            return stats_response

        except NotFoundException as e:
            # Re-raise NotFoundException explicitly
            print(f"Re-raising NotFoundException from {context}")  # MVP Log
            raise e
        except Exception as e:
            # Delegate other exceptions to the centralized handler
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback
