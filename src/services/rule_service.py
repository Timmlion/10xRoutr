# src/services/rule_service.py

import traceback
from uuid import UUID
from typing import List, Optional, Tuple, Dict, Any
from supabase import AsyncClient
from postgrest.exceptions import APIError as PostgrestAPIError
from postgrest.types import CountMethod
from datetime import datetime
from enum import Enum  # <<<=== ADDED THIS IMPORT

# Import custom application exceptions
from src.services.custom_exceptions import (
    DatabaseException,
    NotFoundException,
    ParentLinkNotFoundException,  # Specific type of NotFoundException
    PriorityConflictException,
    ValidationException,
    ServiceException,  # Base class
)

# Import Pydantic models and Enums
from src.schemas.rule import RuleCreate, RuleUpdate, RuleResponse
from src.schemas.enums import RuleTypeEnum, TargetTypeEnum  # Keep specific Enum imports

# --- Constants ---
# PostgreSQL error code for unique constraint violations
POSTGRES_UNIQUE_VIOLATION_CODE = "23505"
# Specific unique constraint name for rule priority within a link
ROUTING_RULES_LINK_ID_PRIORITY_KEY = "routing_rules_link_id_priority_key"


class RuleService:
    """
    Manages the business logic for creating, retrieving, updating, and deleting Routing Rules
    associated with a specific Routr Link. Ensures operations are performed by the link owner.
    """

    def __init__(self, supabase_client: AsyncClient):
        """
        Initializes the RuleService.

        Args:
            supabase_client: An initialized asynchronous Supabase client instance.
                             RLS policies are expected to enforce user ownership based on the
                             client's authentication state (JWT).
        """
        self.supabase = supabase_client
        self.rules_table = "routing_rules"
        self.links_table = "routr_links"  # Needed for ownership verification

    def _handle_db_error(self, error: Exception, context: str):
        """
        Centralized error handler for database operations within RuleService.
        Maps low-level database errors (like PostgrestAPIError) to specific
        custom business exceptions (PriorityConflictException, DatabaseException).
        Re-raises known business exceptions directly.

        Args:
            error: The exception caught during a database operation.
            context: A string describing the operation context for logging/debugging.

        Raises:
            NotFoundException / ParentLinkNotFoundException / PriorityConflictException / ValidationException: Re-raised if caught.
            PriorityConflictException: If a unique constraint violation on rule priority occurs.
            DatabaseException: For other database-related errors.
        """
        # Re-raise known business exceptions immediately
        if isinstance(
            error,
            (
                NotFoundException,
                ParentLinkNotFoundException,
                PriorityConflictException,
                ValidationException,
            ),
        ):
            print(
                f"[INFO] Business logic exception from {context}: {type(error).__name__}. Re-raising."
            )  # MVP Log
            raise error

        # Handle specific errors from the Supabase client library (PostgREST)
        if isinstance(error, PostgrestAPIError):
            error_code = getattr(error, "code", None)
            error_message = getattr(error, "message", "") or ""
            error_details = getattr(error, "details", "") or ""
            error_status = getattr(error, "status", "N/A")

            print(
                f"[ERROR] PostgrestAPIError during {context}: Status={error_status}, Code={error_code}, Message='{error_message}' Details='{error_details}'"
            )  # MVP Log

            # Check specifically for unique constraint violations
            if error_code == POSTGRES_UNIQUE_VIOLATION_CODE:
                # Check if the violation message/details mention the specific priority constraint name
                is_priority_conflict = (
                    ROUTING_RULES_LINK_ID_PRIORITY_KEY in error_message
                )
                if is_priority_conflict:
                    print(
                        f"[CONFLICT] Priority conflict detected during {context}."
                    )  # MVP Log
                    # Raise the specific business exception for priority conflicts
                    raise PriorityConflictException(
                        detail="This priority is already in use for this link."
                    ) from error
                else:
                    # Handle other (unexpected in this service) unique constraint violations
                    print(
                        f"[ERROR] Unique constraint violation (other) during {context}: {error_details or error_message}"
                    )  # MVP Log
                    raise DatabaseException(
                        detail=f"Unique constraint violation during {context}: {error_details or error_message}"
                    ) from error

            # For other PostgREST errors, raise a generic DatabaseException
            raise DatabaseException(
                detail=f"Database API error during {context}: {error_message or 'Unknown PostgREST error'}"
            ) from error
        else:
            # Handle any other unexpected exceptions
            print(f"[ERROR] Unexpected error during {context}:")  # MVP Log
            traceback.print_exc()
            raise DatabaseException(
                detail=f"An unexpected error occurred during {context}."
            ) from error

    async def _verify_link_ownership(self, link_id: UUID, user_id: UUID):
        """
        Checks if a link exists and is accessible by the specified user.
        Uses two checks: one for existence and one for explicit ownership match.
        Relies on RLS for the primary security, but provides clearer error messages.

        Args:
            link_id: The UUID of the link to check.
            user_id: The UUID of the user attempting the operation.

        Raises:
            NotFoundException: If the link does not exist or the user does not own it.
            DatabaseException: For underlying database errors during the check.
        """
        context = f"link ownership verification for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")  # MVP Log
        try:
            # Check 1: Does the link exist at all? (Using count)
            # We use maybe_single() here, expecting 0 or 1 result based on ID.
            existence_check = (
                await self.supabase.table(self.links_table)
                .select(
                    "id", count=CountMethod.exact
                )  # Request count for existence check
                .eq("id", str(link_id))
                .maybe_single()  # Returns None if ID doesn't exist
                .execute()
            )

            # If maybe_single returned None or count is 0, the link doesn't exist
            if not (
                existence_check
                and existence_check.count is not None
                and existence_check.count > 0
            ):
                print(f"[WARNING] {context}: Link not found.")  # MVP Log
                raise NotFoundException(
                    detail=f"Parent link with ID '{link_id}' not found."
                )

            # Check 2: Does the link belong to *this* specific user?
            # This adds an explicit layer over RLS, useful if RLS isn't fully trusted or for clearer errors.
            owner_check = (
                await self.supabase.table(self.links_table)
                .select(
                    "id"
                )  # Only need to select something to confirm the row matches filters
                .eq("id", str(link_id))
                .eq("user_id", str(user_id))  # Explicitly check user_id ownership
                .maybe_single()  # Expect 0 or 1 result
                .execute()
            )

            # If the second query (with user_id filter) returned no data, the user doesn't own it.
            if not (owner_check and owner_check.data):
                print(
                    f"[FORBIDDEN] {context}: Link found but not owned by user."
                )  # MVP Log
                # Raise NotFoundException for consistency, as the user shouldn't know the link exists if they don't own it.
                raise NotFoundException(
                    detail=f"Access denied to parent link with ID '{link_id}'."
                )

            print(f"Link ownership verified for {context}.")  # MVP Log
        except NotFoundException:
            raise  # Re-raise the specific NotFoundException we raised above
        except Exception as e:
            # Handle any other errors during verification
            self._handle_db_error(e, context=context)
            # Fallback exception if handler somehow doesn't raise
            raise DatabaseException(f"Unhandled error during {context}")

    def _prepare_rule_data_for_db(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepares rule data dictionary for database insertion/update.
        Converts Enum members to their string values and formats datetime objects
        to ISO 8601 strings suitable for PostgreSQL 'timestamptz'.

        Args:
            data: The dictionary containing rule data (potentially from Pydantic model dump).

        Returns:
            A new dictionary with values formatted for the database.
        """
        prepared_data = data.copy()

        # Convert Enums to their string values using isinstance check with the imported Enum base class
        if "rule_type" in prepared_data and isinstance(
            prepared_data["rule_type"], Enum
        ):  # Checks if it's *any* kind of Enum
            prepared_data["rule_type"] = prepared_data["rule_type"].value
        if "target_type" in prepared_data and isinstance(
            prepared_data["target_type"], Enum
        ):  # Checks if it's *any* kind of Enum
            prepared_data["target_type"] = prepared_data["target_type"].value

        # Convert aware/naive datetimes to ISO 8601 strings (PostgREST prefers ISO format)
        # Appending 'Z' for naive datetimes might not be strictly necessary if DB column is timestamptz,
        # but ensures clarity that it represents UTC if it was naive.
        if "start_time" in prepared_data and isinstance(
            prepared_data["start_time"], datetime
        ):
            dt_obj = prepared_data["start_time"]
            iso_str = dt_obj.isoformat()
            # Add 'Z' suffix if datetime object was naive (no timezone info)
            prepared_data["start_time"] = iso_str + (
                "Z" if dt_obj.tzinfo is None else ""
            )
        elif "start_time" in prepared_data and prepared_data["start_time"] is None:
            # Ensure None is preserved if explicitly set
            pass  # Value is already None or handled correctly

        if "end_time" in prepared_data and isinstance(
            prepared_data["end_time"], datetime
        ):
            dt_obj = prepared_data["end_time"]
            iso_str = dt_obj.isoformat()
            prepared_data["end_time"] = iso_str + ("Z" if dt_obj.tzinfo is None else "")
        elif "end_time" in prepared_data and prepared_data["end_time"] is None:
            pass

        return prepared_data

    async def add_rule_to_link(
        self, link_id: UUID, rule_data: RuleCreate, user_id: UUID
    ) -> RuleResponse:
        """
        Adds a new routing rule to an existing link, ensuring the user owns the link.

        Args:
            link_id: The UUID of the parent link.
            rule_data: A RuleCreate object containing validated rule data.
            user_id: The UUID of the user performing the action.

        Returns:
            A RuleResponse object representing the newly created rule.

        Raises:
            NotFoundException (via ParentLinkNotFoundException): If the parent link doesn't exist or isn't owned by the user.
            PriorityConflictException: If the chosen priority already exists for this link.
            DatabaseException: For other database errors.
        """
        # Step 1: Verify the user owns the parent link
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rule creation for link ID {link_id} by user {user_id}"
        print(f"Attempting {context} with priority {rule_data.priority}")  # MVP Log

        # Step 2: Prepare data for insertion
        insert_dict = rule_data.model_dump(
            exclude_unset=True
        )  # Get validated data from Pydantic model
        insert_dict["link_id"] = str(link_id)  # Add the foreign key
        prepared_insert_data = self._prepare_rule_data_for_db(
            insert_dict
        )  # Format enums/datetimes
        print(
            f"Attempting {context} with prepared data: {prepared_insert_data}"
        )  # MVP Log

        # Step 3: Execute insert operation
        try:
            response = (
                await self.supabase.table(self.rules_table)
                .insert(prepared_insert_data)
                .execute()
            )

            # Step 4: Validate response and return created object
            if (
                response
                and response.data
                and isinstance(response.data, list)
                and len(response.data) == 1
            ):
                created_data = response.data[0]
                print(
                    f"Successfully created rule with ID: {created_data.get('id')} for link {link_id}"
                )  # MVP Log
                created_rule_dto = RuleResponse.model_validate(
                    created_data
                )  # Validate DB response against schema
                return created_rule_dto
            else:
                print(
                    f"[ERROR] Insert successful but no data returned. Response: {response}"
                )  # MVP Log
                raise DatabaseException(
                    "Failed to retrieve created rule data after insert."
                )

        except (NotFoundException, PriorityConflictException, ValidationException) as e:
            # Re-raise specific business logic exceptions caught during the process
            print(
                f"Re-raising known business exception from {context}: {type(e).__name__}"
            )  # MVP Log
            raise
        except Exception as e:
            # Handle other exceptions using the centralized handler
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback

    async def get_rules_for_link(
        self, link_id: UUID, user_id: UUID
    ) -> List[RuleResponse]:
        """
        Retrieves all rules associated with a specific link, ensuring user ownership.
        Rules are ordered by priority (ascending).

        Args:
            link_id: The UUID of the parent link.
            user_id: The UUID of the user performing the action.

        Returns:
            A list of RuleResponse objects.

        Raises:
            NotFoundException (via ParentLinkNotFoundException): If the parent link doesn't exist or isn't owned by the user.
            DatabaseException: For database errors.
        """
        # Step 1: Verify user owns the parent link
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rules retrieval for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")  # MVP Log
        try:
            # Step 2: Fetch rules for the link, ordered by priority
            response = (
                await self.supabase.table(self.rules_table)
                .select("*")  # Select all columns for RuleResponse
                .eq("link_id", str(link_id))  # Filter by parent link ID
                .order("priority", desc=False)  # Order by priority, lowest first
                .execute()
            )
            # Step 3: Process and validate the response
            rules_data = response.data if response and response.data else []
            print(f"Retrieved {len(rules_data)} rules for {context}")  # MVP Log
            # Validate each rule against the RuleResponse schema
            rule_list = [RuleResponse.model_validate(item) for item in rules_data]
            return rule_list
        except NotFoundException:  # Can be raised by _verify_link_ownership
            raise
        except Exception as e:
            # Handle other exceptions
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback

    async def get_rule_details(
        self, link_id: UUID, rule_id: UUID, user_id: UUID
    ) -> RuleResponse:
        """
        Retrieves the details of a single rule, verifying parent link ownership.

        Args:
            link_id: The UUID of the parent link.
            rule_id: The UUID of the rule to retrieve.
            user_id: The UUID of the user performing the action.

        Returns:
            A RuleResponse object for the specified rule.

        Raises:
            NotFoundException: If the link or rule doesn't exist, or access is denied.
            DatabaseException: For database errors.
        """
        # Step 1: Verify parent link ownership first
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rule details retrieval for rule ID {rule_id} on link {link_id} by user {user_id}"
        print(f"Attempting {context}")  # MVP Log
        try:
            # Step 2: Fetch the specific rule, ensuring it belongs to the correct link
            response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("id", str(rule_id))  # Filter by rule ID
                .eq("link_id", str(link_id))  # Filter by parent link ID
                .maybe_single()  # Expect 0 or 1 result
                .execute()
            )
            # Step 3: Validate response and return DTO
            if response and response.data:
                print(
                    f"Successfully retrieved rule details for rule ID: {rule_id}"
                )  # MVP Log
                rule_dto = RuleResponse.model_validate(response.data)
                return rule_dto
            else:
                # Rule not found for this link (or maybe RLS denied access even if link owned)
                print(
                    f"[WARNING] Rule not found or access denied for {context}"
                )  # MVP Log
                raise NotFoundException(detail="Rule not found or access denied.")
        except NotFoundException:
            raise  # Re-raise NotFoundException (from above or _verify_link_ownership)
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback

    async def update_rule(
        self, link_id: UUID, rule_id: UUID, update_data: RuleUpdate, user_id: UUID
    ) -> RuleResponse:
        """
        Updates an existing routing rule, verifying ownership.

        Args:
            link_id: The UUID of the parent link.
            rule_id: The UUID of the rule to update.
            update_data: A RuleUpdate object containing validated fields to update.
            user_id: The UUID of the user performing the action.

        Returns:
            A RuleResponse object representing the updated rule state.

        Raises:
            NotFoundException: If the link or rule doesn't exist, or access is denied.
            PriorityConflictException: If the update causes a priority conflict.
            DatabaseException: For other database errors.
        """
        update_context = (
            f"rule update for ID {rule_id} on link {link_id} by user {user_id}"
        )
        print(f"Attempting {update_context}")  # MVP Log

        # Step 1: Verify parent link ownership
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        # Step 2: Prepare update payload
        # Get only the fields explicitly set in the update request model
        update_dict = update_data.model_dump(exclude_unset=True)
        # Format enums/datetimes for the database
        db_update_payload = self._prepare_rule_data_for_db(update_dict)

        # If the payload is empty after preparation (no changes requested), return current state.
        if not db_update_payload:
            print(f"No fields to update provided for {update_context}.")  # MVP Log
            # Fetch and return the current rule details (also re-verifies existence)
            return await self.get_rule_details(
                link_id=link_id, rule_id=rule_id, user_id=user_id
            )

        print(
            f"Attempting database update for {update_context} with payload: {db_update_payload}"
        )  # MVP Log
        try:
            # Step 3: Execute the update operation
            response = (
                await self.supabase.table(self.rules_table)
                .update(db_update_payload)
                .eq("id", str(rule_id))  # Target specific rule
                .eq("link_id", str(link_id))  # Ensure it belongs to the correct link
                .execute()
            )

            # Step 4: Validate response and return updated DTO
            if (
                response
                and response.data
                and isinstance(response.data, list)
                and len(response.data) == 1
            ):
                updated_data = response.data[0]
                print(f"Successfully updated rule ID: {rule_id}")  # MVP Log
                updated_rule_dto = RuleResponse.model_validate(updated_data)
                return updated_rule_dto
            else:
                # If update succeeded but returned no data, the rule likely didn't match the filters (ID + link_id)
                print(
                    f"[NOT FOUND/ERROR] Update failed for rule {rule_id}. Might not exist for this link. Response: {response}"
                )  # MVP Log
                # Explicitly check if the rule exists for this link to give a better error
                try:
                    await self.get_rule_details(link_id, rule_id, user_id)
                    # If it exists, something else went wrong during update (should be caught by _handle_db_error ideally)
                    raise DatabaseException(
                        "Rule found but update failed unexpectedly."
                    )
                except NotFoundException:
                    # If it doesn't exist, raise NotFound
                    raise NotFoundException("Rule to update not found for this link.")

        except (NotFoundException, PriorityConflictException, ValidationException) as e:
            # Re-raise specific business logic exceptions
            print(
                f"Re-raising known business exception from {update_context}: {type(e).__name__}"
            )  # MVP Log
            raise
        except Exception as e:
            # Handle other errors
            self._handle_db_error(e, context=update_context)
            raise DatabaseException(
                f"Unhandled error after handler in {update_context}"
            )  # Fallback

    async def delete_rule(self, link_id: UUID, rule_id: UUID, user_id: UUID) -> None:
        """
        Deletes a specific routing rule, verifying parent link ownership.

        Args:
            link_id: The UUID of the parent link.
            rule_id: The UUID of the rule to delete.
            user_id: The UUID of the user performing the action.

        Raises:
            NotFoundException: If the link or rule doesn't exist, or access is denied.
            DatabaseException: For database errors.
        """
        # Step 1: Verify parent link ownership
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = (
            f"rule deletion for rule ID {rule_id} on link {link_id} by user {user_id}"
        )
        print(f"Attempting {context}")  # MVP Log
        try:
            # Step 2: Execute delete operation, requesting count
            response = (
                await self.supabase.table(self.rules_table)
                .delete(count=CountMethod.exact)  # Request count of deleted rows
                .eq("id", str(rule_id))  # Target specific rule
                .eq("link_id", str(link_id))  # Ensure it belongs to the correct link
                .execute()
            )
            # Step 3: Check response count
            if response and response.count == 1:
                print(f"Successfully deleted rule with ID: {rule_id}")  # MVP Log
                return  # Success, return None
            elif response and response.count == 0:
                # Rule didn't exist for this link (or RLS prevented deletion)
                print(
                    f"[WARNING] Rule not found or access denied during delete for {context}"
                )  # MVP Log
                raise NotFoundException(
                    detail="Rule not found or you do not have permission to delete it."
                )
            else:
                # Unexpected count or response structure
                count_val = response.count if response else "N/A"
                print(
                    f"[ERROR] Unexpected delete count ({count_val}) or invalid response for {context}"
                )  # MVP Log
                raise DatabaseException("Unexpected result during rule deletion.")
        except NotFoundException:
            raise  # Re-raise NotFoundException raised above or by _verify_link_ownership
        except Exception as e:
            # Handle other errors
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error after handler in {context}"
            )  # Fallback
