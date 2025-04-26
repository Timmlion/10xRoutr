# src/services/rule_service.py

import traceback
from uuid import UUID
from typing import List, Optional, Tuple, Dict, Any
from supabase import AsyncClient
from postgrest.exceptions import APIError as PostgrestAPIError
from postgrest.types import CountMethod
from datetime import datetime  # Added for ISO conversion

from src.services.custom_exceptions import (
    DatabaseException,
    NotFoundException,
    ParentLinkNotFoundException,
    PriorityConflictException,
    ValidationException,
    ServiceException,
)
from src.schemas.rule import RuleCreate, RuleUpdate, RuleResponse
from src.schemas.enums import RuleTypeEnum, TargetTypeEnum

POSTGRES_UNIQUE_VIOLATION_CODE = "23505"
ROUTING_RULES_LINK_ID_PRIORITY_KEY = "routing_rules_link_id_priority_key"


class RuleService:
    """Service layer for managing Routing Rules."""

    def __init__(self, supabase_client: AsyncClient):
        self.supabase = supabase_client
        self.rules_table = "routing_rules"
        self.links_table = "routr_links"

    def _handle_db_error(self, error: Exception, context: str):
        """Handles database errors and raises appropriate service exceptions."""
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
            )
            raise error

        if isinstance(error, PostgrestAPIError):
            error_code = getattr(error, "code", None)
            error_message = getattr(error, "message", "") or ""
            error_details = getattr(error, "details", "") or ""
            error_status = getattr(error, "status", "N/A")

            print(
                f"[ERROR] PostgrestAPIError during {context}: Status={error_status}, Code={error_code}, Message='{error_message}' Details='{error_details}'"
            )

            if error_code == POSTGRES_UNIQUE_VIOLATION_CODE:
                is_priority_conflict = (
                    ROUTING_RULES_LINK_ID_PRIORITY_KEY in error_message
                )
                if is_priority_conflict:
                    print(f"[CONFLICT] Priority conflict detected during {context}.")
                    raise PriorityConflictException(
                        detail="This priority is already in use for this link."
                    ) from error
                else:
                    print(
                        f"[ERROR] Unique constraint violation (other) during {context}: {error_details or error_message}"
                    )
                    raise DatabaseException(
                        detail=f"Unique constraint violation during {context}: {error_details or error_message}"
                    ) from error

            raise DatabaseException(
                detail=f"Database API error during {context}: {error_message or 'Unknown PostgREST error'}"
            ) from error
        else:
            print(f"[ERROR] Unexpected error during {context}:")
            traceback.print_exc()
            raise DatabaseException(
                detail=f"An unexpected error occurred during {context}."
            ) from error

    async def _verify_link_ownership(self, link_id: UUID, user_id: UUID):
        """Verifies if a link exists and belongs to the user. Raises NotFoundException if not."""
        context = f"link ownership verification for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.links_table)
                .select("id", count=CountMethod.exact)
                .eq("id", str(link_id))
                # RLS handles user_id check, but this confirms existence
                .maybe_single()
                .execute()
            )
            # Check if link exists using the count from the response
            if not (response and response.count is not None and response.count > 0):
                print(f"[WARNING] {context}: Link not found.")
                raise NotFoundException(
                    detail=f"Parent link with ID '{link_id}' not found."
                )
            else:
                # Now verify ownership explicitly for clarity and security layer
                owner_check = (
                    await self.supabase.table(self.links_table)
                    .select("id")
                    .eq("id", str(link_id))
                    .eq("user_id", str(user_id))
                    .maybe_single()
                    .execute()
                )
                if not (owner_check and owner_check.data):
                    print(f"[FORBIDDEN] {context}: Link found but not owned by user.")
                    raise NotFoundException(
                        detail=f"Access denied to parent link with ID '{link_id}'."
                    )

            print(f"Link ownership verified for {context}.")
        except NotFoundException:  # Re-raise NotFoundException
            raise
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(
                f"Unhandled error during {context}"
            )  # Should not happen if handler works

    def _prepare_rule_data_for_db(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Converts enums and datetimes in rule data to DB-compatible formats."""
        prepared_data = data.copy()

        # Convert Enums to strings
        if "rule_type" in prepared_data and hasattr(
            prepared_data["rule_type"], "value"
        ):
            prepared_data["rule_type"] = prepared_data["rule_type"].value
        if "target_type" in prepared_data and hasattr(
            prepared_data["target_type"], "value"
        ):
            prepared_data["target_type"] = prepared_data["target_type"].value

        # Convert datetimes to ISO 8601 strings with 'Z' for UTC if naive
        if "start_time" in prepared_data and isinstance(
            prepared_data["start_time"], datetime
        ):
            dt_obj = prepared_data["start_time"]
            prepared_data["start_time"] = dt_obj.isoformat() + (
                "Z" if dt_obj.tzinfo is None else ""
            )
        elif "start_time" in prepared_data and prepared_data["start_time"] is None:
            # Ensure None is passed correctly if allowed
            pass

        if "end_time" in prepared_data and isinstance(
            prepared_data["end_time"], datetime
        ):
            dt_obj = prepared_data["end_time"]
            prepared_data["end_time"] = dt_obj.isoformat() + (
                "Z" if dt_obj.tzinfo is None else ""
            )
        elif "end_time" in prepared_data and prepared_data["end_time"] is None:
            pass

        return prepared_data

    async def add_rule_to_link(
        self, link_id: UUID, rule_data: RuleCreate, user_id: UUID
    ) -> RuleResponse:
        """Adds a new rule to an existing link owned by the user."""
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rule creation for link ID {link_id} by user {user_id}"
        print(f"Attempting {context} with priority {rule_data.priority}")

        insert_dict = rule_data.model_dump(exclude_unset=True)
        insert_dict["link_id"] = str(link_id)

        prepared_insert_data = self._prepare_rule_data_for_db(insert_dict)
        print(f"Attempting {context} with prepared data: {prepared_insert_data}")

        try:
            response = (
                await self.supabase.table(self.rules_table)
                .insert(prepared_insert_data)
                .execute()
            )

            if (
                response
                and response.data
                and isinstance(response.data, list)
                and len(response.data) == 1
            ):
                created_data = response.data[0]
                print(
                    f"Successfully created rule with ID: {created_data.get('id')} for link {link_id}"
                )
                created_rule_dto = RuleResponse.model_validate(created_data)
                return created_rule_dto
            else:
                print(
                    f"[ERROR] Insert successful but no data returned. Response: {response}"
                )
                raise DatabaseException(
                    "Failed to retrieve created rule data after insert."
                )

        except (NotFoundException, PriorityConflictException, ValidationException) as e:
            print(
                f"Re-raising known business exception from {context}: {type(e).__name__}"
            )
            raise
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def get_rules_for_link(
        self, link_id: UUID, user_id: UUID
    ) -> List[RuleResponse]:
        """Retrieves a list of all rules for a given link owned by the user, ordered by priority."""
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)
        context = f"rules retrieval for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("link_id", str(link_id))
                .order("priority", desc=False)
                .execute()
            )
            rules_data = response.data if response and response.data else []
            print(f"Retrieved {len(rules_data)} rules for {context}")
            rule_list = [RuleResponse.model_validate(item) for item in rules_data]
            return rule_list
        except NotFoundException:  # From _verify_link_ownership
            raise
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def get_rule_details(
        self, link_id: UUID, rule_id: UUID, user_id: UUID
    ) -> RuleResponse:
        """Retrieves details of a specific rule, verifying ownership via RLS implicitly and link_id."""
        # Verify parent link ownership first for better error message if link is wrong
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rule details retrieval for rule ID {rule_id} on link {link_id} by user {user_id}"
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))  # Ensure it's for the correct link
                .maybe_single()
                .execute()
            )
            if response and response.data:
                print(f"Successfully retrieved rule details for rule ID: {rule_id}")
                rule_dto = RuleResponse.model_validate(response.data)
                return rule_dto
            else:
                print(f"[WARNING] Rule not found or access denied for {context}")
                raise NotFoundException(detail="Rule not found or access denied.")
        except NotFoundException:
            raise
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def update_rule(
        self, link_id: UUID, rule_id: UUID, update_data: RuleUpdate, user_id: UUID
    ) -> RuleResponse:
        """Updates an existing routing rule owned by the user."""
        update_context = (
            f"rule update for ID {rule_id} on link {link_id} by user {user_id}"
        )
        print(f"Attempting {update_context}")

        # Verify ownership before attempting update
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        # Prepare payload, converting datetime and enums
        db_update_payload = self._prepare_rule_data_for_db(
            update_data.model_dump(exclude_unset=True)
        )

        # If no actual data to update (after potential None conversions), return current state
        if not db_update_payload:
            print(f"No fields to update provided for {update_context}.")
            return await self.get_rule_details(
                link_id=link_id, rule_id=rule_id, user_id=user_id
            )

        print(
            f"Attempting database update for {update_context} with payload: {db_update_payload}"
        )
        try:
            response = (
                await self.supabase.table(self.rules_table)
                .update(db_update_payload)
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))  # Ensure update targets correct link
                .execute()
            )

            if (
                response
                and response.data
                and isinstance(response.data, list)
                and len(response.data) == 1
            ):
                updated_data = response.data[0]
                print(f"Successfully updated rule ID: {rule_id}")
                updated_rule_dto = RuleResponse.model_validate(updated_data)
                return updated_rule_dto
            else:
                # Could be that the rule ID didn't exist or RLS prevented update on a found rule (less likely if ownership verified)
                print(
                    f"[NOT FOUND/ERROR] Update failed for rule {rule_id}. Might not exist or RLS issue. Response: {response}"
                )
                # Check if rule actually exists to differentiate
                try:
                    await self.get_rule_details(link_id, rule_id, user_id)
                    # If it exists, it's likely an unexpected DB state or error
                    raise DatabaseException(
                        "Rule found but update failed unexpectedly."
                    )
                except NotFoundException:
                    # If it doesn't exist, raise NotFound
                    raise NotFoundException("Rule to update not found.")

        except (NotFoundException, PriorityConflictException, ValidationException) as e:
            print(
                f"Re-raising known business exception from {update_context}: {type(e).__name__}"
            )
            raise
        except Exception as e:
            self._handle_db_error(e, context=update_context)
            raise DatabaseException(
                f"Unhandled error after handler in {update_context}"
            )

    async def delete_rule(self, link_id: UUID, rule_id: UUID, user_id: UUID) -> None:
        """Deletes a specific routing rule owned by the user."""
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)
        context = (
            f"rule deletion for rule ID {rule_id} on link {link_id} by user {user_id}"
        )
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.rules_table)
                .delete(count=CountMethod.exact)
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))  # Ensure delete targets correct link
                .execute()
            )
            if response and response.count == 1:
                print(f"Successfully deleted rule with ID: {rule_id}")
                return
            elif response and response.count == 0:
                print(
                    f"[WARNING] Rule not found or access denied during delete for {context}"
                )
                raise NotFoundException(
                    detail="Rule not found or you do not have permission to delete it."
                )
            else:
                count_val = response.count if response else "N/A"
                print(
                    f"[ERROR] Unexpected delete count ({count_val}) or invalid response for {context}"
                )
                raise DatabaseException("Unexpected result during rule deletion.")
        except NotFoundException:
            raise
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")
