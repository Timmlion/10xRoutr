import logging
import traceback
from uuid import UUID
from typing import List, Optional, Tuple, Dict, Any
from supabase_py_async import AsyncClient
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

# Załóżmy, że Pydantic FieldValidationInfo jest dostępne dla validatorów v2
try:
    from pydantic_core import PydanticCustomError
    from pydantic import FieldValidationInfo
except ImportError:  # Fallback dla starszych Pydantic lub jeśli nie używamy v2
    FieldValidationInfo = Any


# print = logging.getLogger(__name__).info # Można przełączyć na logger
# logger = logging.getLogger(__name__)

POSTGRES_UNIQUE_VIOLATION_CODE = "23505"
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
            print(
                f"[ERROR] PostgrestAPIError during {context}: Status={getattr(error,'status','N/A')}, Message='{getattr(error,'message','Unknown')}'"
            )
            if hasattr(error, "code") and error.code == POSTGRES_UNIQUE_VIOLATION_CODE:
                if ROUTING_RULES_LINK_ID_PRIORITY_KEY in getattr(error, "message", ""):
                    raise PriorityConflictException(
                        detail=f"Database error during {context}: Priority conflict."
                    )
                else:
                    raise DatabaseException(
                        detail=f"Unique constraint violation during {context}: {getattr(error,'message','Unknown')}"
                    )
            raise DatabaseException(
                detail=f"Database API error during {context}: {getattr(error,'message','Unknown')}"
            )
        else:
            print(f"[ERROR] Unexpected error during {context}: {error}")
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
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.links_table)
                .select("id", count="exact")
                .eq("id", str(link_id))
                .maybe_single()
                .execute()
            )

            # Sprawdzamy czy cokolwiek znaleziono - RLS odfiltruje, jeśli user_id nie pasuje
            if not response.data:
                print(f"[WARNING] {context}: Link not found or access denied.")
                raise ParentLinkNotFoundException()
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")  # Fallback

    async def add_rule_to_link(
        self, link_id: UUID, rule_data: RuleCreate, user_id: UUID
    ) -> RuleResponse:
        """Adds a new rule to an existing link owned by the user."""
        await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rule creation for link ID {link_id} by user {user_id}"
        print(f"Attempting {context} with priority {rule_data.priority}")

        insert_data = rule_data.model_dump()
        insert_data["link_id"] = str(link_id)  # Przekonwertuj UUID na string dla insert

        try:
            response = (
                await self.supabase.table(self.rules_table)
                .insert(insert_data)
                .select()
                .single()
                .execute()
            )

            if response.data:
                print(
                    f"Successfully created rule with ID: {response.data.get('id')} for link {link_id}"
                )
                created_rule_dto = RuleResponse.model_validate(response.data)
                return created_rule_dto
            else:
                print("[ERROR] Insert successful but no data returned from database.")
                raise DatabaseException(
                    "Failed to retrieve created rule data after insert."
                )

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")  # Fallback

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

            rules_data = response.data or []
            print(f"Retrieved {len(rules_data)} rules for {context}")

            rule_list = [RuleResponse.model_validate(item) for item in rules_data]
            return rule_list

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def get_rule_details(
        self, link_id: UUID, rule_id: UUID, user_id: UUID
    ) -> RuleResponse:
        """Retrieves details of a specific rule, verifying ownership via the parent link."""
        # Weryfikacja własności linku nie jest tu krytyczna, bo RLS na rules to załatwi,
        # ale może dać lepszy komunikat błędu (ParentLinkNotFound vs NotFound)
        # await self._verify_link_ownership(link_id=link_id, user_id=user_id)

        context = f"rule details retrieval for rule ID {rule_id} on link {link_id} by user {user_id}"
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))
                .maybe_single()
                .execute()
            )

            if response.data:
                print(f"Successfully retrieved rule details for rule ID: {rule_id}")
                rule_dto = RuleResponse.model_validate(response.data)
                return rule_dto
            else:
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
        print(f"Attempting {update_context}")

        try:
            # Krok 1: Pobierz bieżący stan reguły (weryfikuje istnienie i własność)
            print(f"Verifying existence and ownership for {update_context}")
            current_rule_response = (
                await self.supabase.table(self.rules_table)
                .select("*")
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))
                .maybe_single()
                .execute()
            )

            if not current_rule_response.data:
                print(
                    f"[WARNING] Rule not found or access denied during update check for {update_context}"
                )
                raise NotFoundException("Rule not found or access denied.")

            current_rule_dict = current_rule_response.data
            print("Ownership verified. Preparing update.")

            # Krok 2 i 3: Połącz dane i Walidacja spójności
            final_state_dict = current_rule_dict.copy()
            update_payload_dict = update_data.model_dump(exclude_unset=True)
            final_state_dict.update(update_payload_dict)

            # Waliduj finalny stan używając logiki z RuleCreate
            try:
                # Upewnij się, że ENUMy są stringami przed walidacją, jeśli RuleCreate ich tak oczekuje
                # (choć model_validate powinien sobie poradzić z enumami)
                # if isinstance(final_state_dict.get('rule_type'), Enum):
                #     final_state_dict['rule_type'] = final_state_dict['rule_type'].value
                # if isinstance(final_state_dict.get('target_type'), Enum):
                #      final_state_dict['target_type'] = final_state_dict['target_type'].value

                # Zwaliduj używając modelu Create, aby sprawdzić spójność pól
                validated_final_state = RuleCreate.model_validate(final_state_dict)
            except ValueError as val_error:
                print(
                    f"[VALIDATION ERROR] Inconsistent data after merging update for {update_context}: {val_error}"
                )
                raise ValidationException(detail=str(val_error))

            # Krok 4: Przygotuj payload do update (tylko zmienione pola)
            db_update_payload = {}
            # Sprawdź, które pola z update_payload_dict faktycznie się różnią od current_rule_dict
            # lub po prostu użyj payloadu z update_data, jeśli walidacja spójności przeszła
            # Użycie payloadu z update_data jest prostsze:
            db_update_payload = update_payload_dict

            # Dodatkowo wyczyść pola, które stały się nieistotne z powodu zmiany typu
            final_rule_type = RuleTypeEnum(
                validated_final_state.rule_type
            )  # Użyj typu zwalidowanego stanu
            if "rule_type" in db_update_payload:  # Jeśli typ był aktualizowany
                if final_rule_type == RuleTypeEnum.TIME:
                    db_update_payload["max_clicks"] = None
                elif final_rule_type == RuleTypeEnum.CLICKS:
                    db_update_payload["start_time"] = None
                    db_update_payload["end_time"] = None

            # Krok 5: Wykonaj Update (jeśli są zmiany)
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
                .select()
                .single()
                .execute()
            )

            if response.data:
                print(f"Successfully updated rule ID: {rule_id}")
                updated_rule_dto = RuleResponse.model_validate(response.data)
                return updated_rule_dto
            else:
                # Update nic nie zwrócił - może RLS, ale weryfikacja była wcześniej
                print(
                    f"[ERROR] Update executed but no data returned for {update_context}"
                )
                raise DatabaseException(
                    "Failed to retrieve updated rule data after update."
                )

        except NotFoundException:
            raise
        except ValidationException:
            raise
        except Exception as e:
            # Krok 6: Obsługa błędów DB (np. konflikt priorytetu)
            self._handle_db_error(e, context=update_context)
            raise DatabaseException(
                f"Unhandled error during {update_context}"
            )  # Fallback

    async def delete_rule(self, link_id: UUID, rule_id: UUID, user_id: UUID) -> None:
        """Deletes a specific routing rule owned by the user."""
        context = (
            f"rule deletion for rule ID {rule_id} on link {link_id} by user {user_id}"
        )
        print(f"Attempting {context}")

        try:
            # Filtruj po obu ID, RLS dodatkowo zabezpieczy przez link_id
            response = (
                await self.supabase.table(self.rules_table)
                .delete(count="exact")
                .eq("id", str(rule_id))
                .eq("link_id", str(link_id))
                .execute()
            )

            if response.count == 1:
                print(f"Successfully deleted rule with ID: {rule_id}")
                return
            elif response.count == 0:
                print(
                    f"[WARNING] Rule not found or access denied during delete for {context}"
                )
                raise NotFoundException(
                    detail="Rule not found or you do not have permission to delete it."
                )
            else:
                print(
                    f"[ERROR] Unexpected delete count ({response.count}) for {context}"
                )
                raise DatabaseException("Unexpected result during rule deletion.")

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")  # Fallback
