# src/services/rule_service.py

# Usunięto import logging
import traceback
from uuid import UUID
from typing import List, Optional, Tuple, Dict, Any
from supabase import AsyncClient  # <<< POPRAWIONY IMPORT
from postgrest.exceptions import APIError as PostgrestAPIError

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

# Usunięto importy i użycie Pydantic FieldValidationInfo, jeśli nie jest potrzebne
# try:
#     from pydantic_core import PydanticCustomError
#     from pydantic import FieldValidationInfo
# except ImportError:
#     FieldValidationInfo = Any

# Usunięto logger

POSTGRES_UNIQUE_VIOLATION_CODE = "23505"
# Upewnij się, że ta nazwa klucza jest DOKŁADNIE taka jak w definicji bazy danych
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
        self.links_table = "routr_links"

    def _handle_db_error(self, error: Exception, context: str):
        """Handles database errors and raises appropriate service exceptions."""
        if isinstance(error, PostgrestAPIError):
            # Zastąpiono logger.error
            print(
                f"[ERROR] PostgrestAPIError during {context}: Status={getattr(error,'status','N/A')}, Code={getattr(error,'code','N/A')}, Message='{getattr(error,'message','Unknown')}'"
            )
            if hasattr(error, "code") and error.code == POSTGRES_UNIQUE_VIOLATION_CODE:
                # Sprawdzamy, czy komunikat błędu zawiera nazwę naszego unikalnego ograniczenia
                if ROUTING_RULES_LINK_ID_PRIORITY_KEY in getattr(
                    error, "details", getattr(error, "message", "")
                ):  # Sprawdzaj 'details' lub 'message'
                    # Zastąpiono logger.warning
                    print(f"[CONFLICT] Priority conflict detected during {context}.")
                    # Użyj wyjątku, który ma domyślny komunikat lub przekaż go
                    raise PriorityConflictException(
                        detail="This priority is already in use for this link."
                    )
                else:
                    # Inne naruszenie unikalności
                    # Zastąpiono logger.error
                    print(
                        f"[ERROR] Unique constraint violation (not priority) during {context}: {getattr(error,'message','Unknown')}"
                    )
                    raise DatabaseException(
                        detail=f"Unique constraint violation during {context}: {getattr(error,'message','Unknown')}"
                    )
            # Inne błędy Postgrest
            raise DatabaseException(
                detail=f"Database API error during {context}: {getattr(error,'message','Unknown')}"
            )
        else:
            # Inne, nieoczekiwane błędy
            # Zastąpiono logger.exception
            print(f"[ERROR] Unexpected error during {context}:")
            traceback.print_exc()
            raise DatabaseException(
                detail=f"An unexpected error occurred during {context}."
            )

    async def _verify_link_ownership(self, link_id: UUID, user_id: UUID):
        """
        Verifies if a link exists and belongs to the user. Raises ParentLinkNotFoundException if not.
        Relies on RLS implicitly checking ownership when querying with user context.
        """
        context = f"link ownership verification for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")  # Zastąpiono logger.info
        try:
            response = (
                await self.supabase.table(self.links_table)
                .select(
                    "id", count="exact"
                )  # Wystarczy ID lub cokolwiek, liczy się count
                .eq("id", str(link_id))
                # RLS zastosuje filtr user_id automatycznie
                .maybe_single()  # Zwróci None jeśli RLS odrzuci
                .execute()
            )

            # <<< POPRAWKA: Sprawdź response ORAZ response.data
            if not (response and response.data):
                # Zastąpiono logger.warning
                print(f"[WARNING] {context}: Link not found or access denied.")
                # Użyj wyjątku z domyślnym komunikatem
                raise ParentLinkNotFoundException()
            else:
                print(f"Link ownership verified for {context}.")  # Logowanie sukcesu
        except Exception as e:
            # Obsługa błędów DB (jeśli wystąpią podczas weryfikacji)
            self._handle_db_error(e, context=context)
            # Jeśli _handle_db_error nie rzuci wyjątku, rzuć ogólny
            raise DatabaseException(f"Unhandled error during {context}")

    async def add_rule_to_link(
        self, link_id: UUID, rule_data: RuleCreate, user_id: UUID
    ) -> RuleResponse:
        """Adds a new rule to an existing link owned by the user."""
        # Weryfikacja własności linku jest teraz ważna, aby zwrócić poprawny błąd 404
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rule creation for link ID {link_id} by user {user_id}"
        print(
            f"Attempting {context} with priority {rule_data.priority}"
        )  # Zastąpiono logger.info

        insert_data = rule_data.model_dump()
        insert_data["link_id"] = str(link_id)

        try:
            response = (
                await self.supabase.table(self.rules_table)
                .insert(insert_data)
                .select("*")  # Zwróć pełny nowo utworzony obiekt
                .single()  # Oczekujemy jednego wyniku
                .execute()
            )

            # <<< POPRAWKA: Sprawdź response ORAZ response.data
            if response and response.data:
                print(
                    f"Successfully created rule with ID: {response.data.get('id')} for link {link_id}"
                )  # Zastąpiono logger.info
                created_rule_dto = RuleResponse.model_validate(response.data)
                return created_rule_dto
            else:
                print(
                    "[ERROR] Insert successful but no data returned from database."
                )  # Zastąpiono logger.error
                raise DatabaseException(
                    "Failed to retrieve created rule data after insert."
                )

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def get_rules_for_link(
        self, link_id: UUID, user_id: UUID
    ) -> List[RuleResponse]:
        """Retrieves a list of all rules for a given link owned by the user, ordered by priority."""
        # Weryfikacja własności linku, aby dać 404 jeśli link nie należy do usera
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rules retrieval for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")  # Zastąpiono logger.info

        try:
            response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("link_id", str(link_id))
                .order("priority", desc=False)
                .execute()
            )

            # Sprawdź czy response istnieje przed dostępem do data
            rules_data = response.data if response and response.data else []
            print(
                f"Retrieved {len(rules_data)} rules for {context}"
            )  # Zastąpiono logger.info

            rule_list = [RuleResponse.model_validate(item) for item in rules_data]
            return rule_list

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def get_rule_details(
        self, link_id: UUID, rule_id: UUID, user_id: UUID
    ) -> RuleResponse:
        """Retrieves details of a specific rule, verifying ownership via the parent link and RLS."""
        context = f"rule details retrieval for rule ID {rule_id} on link {link_id} by user {user_id}"
        print(f"Attempting {context}")  # Zastąpiono logger.info
        try:
            response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))  # RLS i tak sprawdzi user_id przez link_id
                .maybe_single()
                .execute()
            )

            # <<< POPRAWKA: Sprawdź response ORAZ response.data
            if response and response.data:
                print(
                    f"Successfully retrieved rule details for rule ID: {rule_id}"
                )  # Zastąpiono logger.info
                rule_dto = RuleResponse.model_validate(response.data)
                return rule_dto
            else:
                # Zastąpiono logger.warning
                print(f"[WARNING] Rule not found or access denied for {context}")
                raise NotFoundException(detail="Rule not found or access denied.")

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def update_rule(
        self, link_id: UUID, rule_id: UUID, update_data: RuleUpdate, user_id: UUID
    ) -> RuleResponse:
        """Updates an existing routing rule owned by the user."""
        update_context = (
            f"rule update for ID {rule_id} on link {link_id} by user {user_id}"
        )
        print(f"Attempting {update_context}")  # Zastąpiono logger.info

        try:
            # Krok 1: Pobierz bieżący stan reguły (weryfikuje istnienie i własność przez RLS)
            print(
                f"Verifying existence and ownership for {update_context}"
            )  # Zastąpiono logger.debug
            current_rule_response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))
                .maybe_single()
                .execute()
            )

            # <<< POPRAWKA: Sprawdź response ORAZ response.data
            if not (current_rule_response and current_rule_response.data):
                # Zastąpiono logger.warning
                print(
                    f"[WARNING] Rule not found or access denied during update check for {update_context}"
                )
                raise NotFoundException("Rule not found or access denied.")

            current_rule_dict = current_rule_response.data
            print("Ownership verified. Preparing update.")  # Zastąpiono logger.debug

            # Krok 2 i 3: Połącz dane i Walidacja spójności
            final_state_dict = current_rule_dict.copy()
            update_payload_dict = update_data.model_dump(exclude_unset=True)
            final_state_dict.update(update_payload_dict)

            try:
                # Zwaliduj używając modelu Create
                validated_final_state = RuleCreate.model_validate(final_state_dict)
            except ValueError as val_error:
                # Zastąpiono logger.warning
                print(
                    f"[VALIDATION ERROR] Inconsistent data after merging update for {update_context}: {val_error}"
                )
                raise ValidationException(detail=str(val_error))

            # Krok 4: Przygotuj payload do update
            db_update_payload = update_payload_dict

            # Wyczyść nieistotne pola
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
                )  # Zastąpiono logger.info
                return RuleResponse.model_validate(current_rule_dict)

            print(
                f"Attempting database update for {update_context} with payload: {db_update_payload}"
            )  # Zastąpiono logger.debug
            response = (
                await self.supabase.table(self.rules_table)
                .update(db_update_payload)
                .eq("id", str(rule_id))
                .execute()
            )

            # <<< POPRAWKA: Sprawdź response ORAZ response.data
            if response and response.data:
                print(
                    f"Successfully updated rule ID: {rule_id}"
                )  # Zastąpiono logger.info
                updated_rule_dto = RuleResponse.model_validate(response.data)
                return updated_rule_dto
            else:
                # Zastąpiono logger.error
                print(
                    f"[ERROR] Update executed but no data returned for {update_context}"
                )
                # To nie powinno się zdarzyć z .single() po udanym update, ale zabezpieczamy
                raise DatabaseException(
                    "Failed to retrieve updated rule data after update."
                )

        except NotFoundException:  # Przechwyć i rzuć dalej
            raise
        except ValidationException:  # Przechwyć i rzuć dalej
            raise
        except Exception as e:
            # Krok 6: Obsługa błędów DB (np. konflikt priorytetu)
            self._handle_db_error(e, context=update_context)
            # Fallback, jeśli _handle_db_error nie rzuci wyjątku
            raise DatabaseException(f"Unhandled error during {update_context}")

    async def delete_rule(self, link_id: UUID, rule_id: UUID, user_id: UUID) -> None:
        """Deletes a specific routing rule owned by the user."""
        context = (
            f"rule deletion for rule ID {rule_id} on link {link_id} by user {user_id}"
        )
        print(f"Attempting {context}")  # Zastąpiono logger.info

        try:
            # Używamy count='exact'
            response = (
                await self.supabase.table(self.rules_table)
                .delete()
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))  # RLS i tak to wymusi
                .execute()
            )

            if response and response.count == 1:
                print(
                    f"Successfully deleted rule with ID: {rule_id}"
                )  # Zastąpiono logger.info
                return
            elif response and response.count == 0:
                # Zastąpiono logger.warning
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
                )  # Zastąpiono logger.error
                raise DatabaseException("Unexpected result during rule deletion.")

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")  # Fallback
