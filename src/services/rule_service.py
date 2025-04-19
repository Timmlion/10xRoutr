# src/services/rule_service.py

import traceback
from uuid import UUID
from typing import List, Optional, Tuple, Dict, Any
from supabase import AsyncClient
from postgrest.exceptions import APIError as PostgrestAPIError
from postgrest.types import CountMethod  # <<< DODANO IMPORT

# Importuj WSZYSTKIE wyjątki biznesowe, które mogą być rzucane lub łapane
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
# Upewnij się, że ta nazwa klucza jest poprawna
ROUTING_RULES_LINK_ID_PRIORITY_KEY = "routing_rules_link_id_priority_key"


class RuleService:
    """
    Service layer for managing business logic related to Routing Rules.
    Operates within the context of an authenticated user.
    Requires verification of parent link ownership for most operations.
    """

    def __init__(self, supabase_client: AsyncClient):
        self.supabase = supabase_client
        self.rules_table = "routing_rules"
        self.links_table = "routr_links"  # Potrzebne do weryfikacji

    def _handle_db_error(self, error: Exception, context: str):
        """Handles database errors and raises appropriate service exceptions."""
        # Sprawdź najpierw wyjątki biznesowe RELEWANTNE DLA RULESERVICE
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
                f"[INFO] Business logic exception caught in handler: {type(error).__name__}. Re-raising."
            )
            raise error  # Rzuć ponownie ten sam wyjątek biznesowy

        # Następnie sprawdź błędy Postgrest/DB
        if isinstance(error, PostgrestAPIError):
            error_code = getattr(error, "code", None)
            error_message = getattr(error, "message", "")
            error_details = getattr(error, "details", "")
            error_status = getattr(error, "status", "N/A")

            print(
                f"[ERROR] PostgrestAPIError during {context}: Status={error_status}, Code={error_code}, Message='{error_message}' Details='{error_details}'"
            )

            if error_code == POSTGRES_UNIQUE_VIOLATION_CODE:
                error_full_msg = error_details or error_message
                # Sprawdź konflikt priorytetu
                if ROUTING_RULES_LINK_ID_PRIORITY_KEY in error_message:
                    print(f"[CONFLICT] Priority conflict detected during {context}.")
                    raise PriorityConflictException(
                        detail="This priority is already in use for this link."
                    ) from error
                else:
                    print(
                        f"[ERROR] Unique constraint violation (other) during {context}: {error_details or error_message}"
                    )
                    raise DatabaseException(...) from error
        else:
            # Inne, nieoczekiwane błędy
            print(f"[ERROR] Unexpected error during {context}:")
            traceback.print_exc()
            raise DatabaseException(
                detail=f"An unexpected error occurred during {context}."
            ) from error

    async def _verify_link_ownership(self, link_id: UUID, user_id: UUID):
        """
        Verifies if a link exists and belongs to the user. Raises ParentLinkNotFoundException if not.
        """
        context = f"link ownership verification for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.links_table)
                .select("id", count=CountMethod.exact)
                .eq("id", str(link_id))
                .maybe_single()
                .execute()
            )

            if not (response and response.data):
                print(f"[WARNING] {context}: Link not found or access denied.")
                # <<< POPRAWKA: Przekaż link_id w komunikacie 'detail' >>>
                raise ParentLinkNotFoundException(
                    detail=f"Parent link with ID '{link_id}' not found or access denied."
                )
            else:
                print(f"Link ownership verified for {context}.")
        except ParentLinkNotFoundException:
            raise
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def add_rule_to_link(
        self, link_id: UUID, rule_data: RuleCreate, user_id: UUID
    ) -> RuleResponse:
        """Adds a new rule to an existing link owned by the user."""
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rule creation for link ID {link_id} by user {user_id}"
        print(f"Attempting {context} with priority {rule_data.priority}")

        insert_data = rule_data.model_dump()
        insert_data["link_id"] = str(link_id)

        try:
            response = (
                await self.supabase.table(self.rules_table).insert(insert_data)
                # <<< USUNIĘTO .select("*").single() >>>
                .execute()
            )

            # Sprawdź, czy insert zwrócił dane (domyślnie zwraca listę)
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
                    f"[ERROR] Insert successful but no data returned from database. Response: {response}"
                )
                raise DatabaseException(
                    "Failed to retrieve created rule data after insert."
                )

        except ParentLinkNotFoundException:  # Przechwyć z _verify_link_ownership
            raise
        except PriorityConflictException:  # Przechwyć z _handle_db_error
            raise
        except Exception as e:  # Pozostałe idą do handlera
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

        except ParentLinkNotFoundException:  # Przechwyć z _verify_link_ownership
            raise
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def get_rule_details(
        self, link_id: UUID, rule_id: UUID, user_id: UUID
    ) -> RuleResponse:
        """Retrieves details of a specific rule, verifying ownership via RLS."""
        # Weryfikacja linku nadrzędnego nie jest tu konieczna, bo RLS na tabeli reguł użyje link_id
        context = f"rule details retrieval for rule ID {rule_id} on link {link_id} by user {user_id}"
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))  # Dodatkowe zabezpieczenie
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

        except NotFoundException:  # Jawnie łap i rzucaj dalej
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

        # Krok 0: Weryfikacja własności linku nadrzędnego (dobra praktyka przed próbą update)
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        try:
            # Krok 1: Pobierz bieżący stan reguły (weryfikuje istnienie reguły)
            print(f"Fetching current rule state for {update_context}")
            current_rule_response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("id", str(rule_id))
                .eq(
                    "link_id", str(link_id)
                )  # Upewnij się, że należy do właściwego linku
                .maybe_single()
                .execute()
            )

            if not (current_rule_response and current_rule_response.data):
                print(
                    f"[WARNING] Rule not found during update check for {update_context}"
                )
                # Rzuć NotFoundException specyficzny dla reguły
                raise NotFoundException("Rule to update not found.")

            current_rule_dict = current_rule_response.data
            print("Rule exists. Preparing update.")

            # Krok 2 i 3: Połącz dane i Walidacja spójności
            final_state_dict = current_rule_dict.copy()
            update_payload_dict = update_data.model_dump(exclude_unset=True)
            final_state_dict.update(update_payload_dict)

            try:
                validated_final_state = RuleCreate.model_validate(final_state_dict)
            except ValueError as val_error:
                print(
                    f"[VALIDATION ERROR] Inconsistent data after merging update for {update_context}: {val_error}"
                )
                raise ValidationException(detail=str(val_error))

            # Krok 4: Przygotuj payload do update
            db_update_payload = update_payload_dict
            final_rule_type = RuleTypeEnum(validated_final_state.rule_type)
            if "rule_type" in db_update_payload:
                if final_rule_type == RuleTypeEnum.TIME:
                    db_update_payload["max_clicks"] = None
                elif final_rule_type == RuleTypeEnum.CLICKS:
                    db_update_payload["start_time"] = None
                    db_update_payload["end_time"] = None

            # Krok 5: Wykonaj Update
            if not db_update_payload:
                print(
                    f"No actual changes detected for {update_context}. Returning current state."
                )
                return RuleResponse.model_validate(current_rule_dict)

            print(
                f"Attempting database update for {update_context} with payload: {db_update_payload}"
            )
            response = (
                await self.supabase.table(self.rules_table)
                .update(db_update_payload)
                .eq("id", str(rule_id))
                # <<< USUNIĘTO .single() >>>
                .execute()
            )

            # Sprawdź, czy update zwrócił dane (lista z jednym elementem)
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
                # Jeśli update nic nie zwrócił, mimo że weryfikacja istnienia przeszła, to dziwne
                print(
                    f"[ERROR] Update query executed but did not return expected data for {update_context}. Response: {response}"
                )
                raise DatabaseException(
                    "Failed to retrieve updated rule data after update (unexpected response format)."
                )

        # Jawnie łap wyjątki, które mogą wystąpić w tej metodzie
        except ParentLinkNotFoundException:  # Z _verify_link_ownership
            raise
        except NotFoundException:  # Z weryfikacji istnienia reguły lub z handlera
            raise
        except ValidationException:  # Z walidacji Pydantic
            raise
        except PriorityConflictException:  # Z _handle_db_error
            raise
        except Exception as e:  # Pozostałe idą do handlera
            self._handle_db_error(e, context=update_context)
            raise DatabaseException(
                f"Unhandled error after handler in {update_context}"
            )

    async def delete_rule(self, link_id: UUID, rule_id: UUID, user_id: UUID) -> None:
        """Deletes a specific routing rule owned by the user."""
        # Weryfikacja własności linku nadrzędnego przed próbą usunięcia reguły
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = (
            f"rule deletion for rule ID {rule_id} on link {link_id} by user {user_id}"
        )
        print(f"Attempting {context}")

        try:
            response = (
                await self.supabase.table(self.rules_table)
                # <<< POPRAWKA: Użyj CountMethod.exact >>>
                .delete(count=CountMethod.exact)
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))  # Dodatkowe zabezpieczenie
                .execute()
            )

            if response and response.count == 1:
                print(f"Successfully deleted rule with ID: {rule_id}")
                return
            elif response and response.count == 0:
                print(
                    f"[WARNING] Rule not found or access denied during delete for {context}"
                )
                # Rzuć NotFoundException specyficzny dla reguły
                raise NotFoundException(
                    detail="Rule not found or you do not have permission to delete it."
                )
            else:
                count_val = response.count if response else "N/A"
                print(
                    f"[ERROR] Unexpected delete count ({count_val}) or invalid response for {context}"
                )
                raise DatabaseException("Unexpected result during rule deletion.")

        except ParentLinkNotFoundException:  # Z _verify_link_ownership
            raise
        except NotFoundException:  # Z tego bloku try lub z handlera
            raise
        except Exception as e:  # Pozostałe idą do handlera
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")
