# src/services/link_service.py

import traceback
from uuid import UUID
from typing import List, Optional, Tuple
from supabase import AsyncClient
from postgrest.exceptions import APIError as PostgrestAPIError
from postgrest.types import CountMethod

# Importuj WSZYSTKIE wyjątki biznesowe, które mogą być rzucane przez ten serwis
from src.services.custom_exceptions import (
    AliasConflictException,
    DatabaseException,
    NotFoundException,
    ValidationException,  # Choć nie jest rzucany bezpośrednio tutaj, może być w przyszłości
    ServiceException,  # Bazowy
)

# Importuj wyjątki, które mogą być rzucone przez inne serwisy, jeśli je łapiesz
# (w tym przypadku nie dotyczy)

# Import modeli Pydantic (DTOs)
from src.schemas.link import LinkCreate, LinkUpdate, LinkResponse, PaginatedLinkResponse
from src.schemas.stats import LinkStatsResponse, TargetClickStat
from src.schemas.enums import TargetTypeEnum

POSTGRES_UNIQUE_VIOLATION_CODE = "23505"
ROUTING_RULES_LINK_ID_PRIORITY_KEY = (
    "routing_rules_link_id_priority_key"  # Potencjalnie potrzebne w RuleService
)


class LinkService:
    """
    Service layer for managing business logic related to Routr Links.
    Operates within the context of an authenticated user (via Supabase client with JWT).
    """

    def __init__(self, supabase_client: AsyncClient):
        self.supabase = supabase_client
        self.links_table = "routr_links"
        self.rules_table = "routing_rules"

    def _handle_db_error(self, error: Exception, context: str):
        """
        Handles potential database errors, raising specific custom exceptions.
        It re-raises known business exceptions and wraps others.
        """
        # ... (sprawdzanie wyjątków biznesowych bez zmian) ...

        if isinstance(error, PostgrestAPIError):
            error_code = getattr(error, "code", None)
            error_message = getattr(error, "message", "")
            error_details = getattr(error, "details", "")
            error_status = getattr(error, "status", "N/A")

            print(
                f"[ERROR] PostgrestAPIError during {context}: Status={error_status}, Code={error_code}, Message='{error_message}' Details='{error_details}'"
            )

            if error_code == POSTGRES_UNIQUE_VIOLATION_CODE:
                # <<< POPRAWKA: Uproszczone wykrywanie konfliktu aliasu >>>
                # Jeśli kod to 23505 i komunikat/szczegóły zawierają 'alias',
                # zakładamy, że to konflikt aliasu w tym serwisie.
                mentions_alias = "alias" in error_details or "alias" in error_message
                if mentions_alias:
                    print(
                        f"[CONFLICT] Alias conflict likely detected during {context}."
                    )
                    raise AliasConflictException() from error
                else:
                    # Inne naruszenie unikalności
                    print(
                        f"[ERROR] Unique constraint violation (other) during {context}: {error_details or error_message}"
                    )
                    raise DatabaseException(
                        detail=f"Unique constraint violation during {context}: {error_details or error_message}"
                    ) from error
            # Inne błędy Postgrest
            raise DatabaseException(
                detail=f"Database API error during {context}: {error_message}"
            ) from error
        else:
            # Inne, nieoczekiwane błędy (niebędące wyjątkami biznesowymi ani PostgrestAPIError)
            # np. błędy sieciowe na niższym poziomie, błędy w logice Python itp.
            print(f"[ERROR] Unexpected error during {context}:")
            traceback.print_exc()  # Drukuj pełny traceback dla tych błędów
            # Rzuć ogólny DatabaseException lub ServiceException
            raise DatabaseException(
                detail=f"An unexpected error occurred during {context}."
            ) from error

    async def create_link(self, link_data: LinkCreate, user_id: UUID) -> LinkResponse:
        """
        Creates a new routr_link record in the database for the specified user.
        """
        insert_data = link_data.model_dump()
        insert_data["user_id"] = str(user_id)

        if insert_data.get("default_url") is not None:
            insert_data["default_url"] = str(insert_data["default_url"])

        context = f"link creation for alias '{link_data.alias}' by user {user_id}"
        print(f"Attempting {context} with data: {insert_data}")

        try:
            response = (
                await self.supabase.table(self.links_table)
                .insert(insert_data)
                .execute()
            )

            if (
                response
                and response.data
                and isinstance(response.data, list)
                and len(response.data) == 1
            ):
                created_data = response.data[0]
                print(f"Successfully created link with ID: {created_data.get('id')}")
                created_link_dto = LinkResponse.model_validate(created_data)
                return created_link_dto
            else:
                print(
                    f"[ERROR] Insert query executed but did not return expected data. Response: {response}"
                )
                raise DatabaseException(
                    "Failed to retrieve created link data after insert (unexpected response format)."
                )

        except AliasConflictException:  # Jawnie łap i rzucaj dalej
            print(f"Re-raising AliasConflictException from {context}")
            raise
        except Exception as e:  # Pozostałe idą do handlera
            self._handle_db_error(e, context=context)
            # Jeśli handler nie rzucił, coś jest bardzo źle
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def get_link_by_id(self, link_id: UUID, user_id: UUID) -> LinkResponse:
        context = f"link retrieval for ID {link_id} by user {user_id}"
        print(f"Attempting {context}")
        try:
            response = (
                await self.supabase.table(self.links_table)
                .select("*")
                .eq("id", str(link_id))
                .maybe_single()
                .execute()
            )

            if response and response.data:
                print(f"Successfully retrieved link with ID: {link_id}")
                link_dto = LinkResponse.model_validate(response.data)
                return link_dto
            else:
                print(f"[WARNING] Link not found or access denied for {context}")
                # Rzuć NotFoundException, zostanie złapany i rzucony dalej przez blok except
                raise NotFoundException(
                    detail="Link not found or you do not have permission to access it."
                )

        except NotFoundException:  # Jawnie łap i rzucaj dalej
            print(f"Re-raising NotFoundException from {context}")
            raise
        except Exception as e:  # Pozostałe idą do handlera
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def get_links_paginated(
        self, user_id: UUID, page: int, page_size: int
    ) -> PaginatedLinkResponse:
        context = f"paginated link retrieval for user {user_id} (page={page}, size={page_size})"
        print(f"Attempting {context}")

        offset = (page - 1) * page_size
        range_to = offset + page_size - 1

        try:
            response = (
                await self.supabase.table(self.links_table)
                .select("*", count=CountMethod.exact)
                .order("created_at", desc=True)
                .range(offset, range_to)
                .execute()
            )

            items_data = response.data if response and response.data else []
            total_count = (
                response.count if response and response.count is not None else 0
            )

            print(
                f"Retrieved {len(items_data)} links out of {total_count} total for {context}"
            )

            link_items = [LinkResponse.model_validate(item) for item in items_data]

            paginated_response = PaginatedLinkResponse(
                items=link_items, total=total_count, page=page, page_size=page_size
            )
            return paginated_response

        # Tutaj raczej nie spodziewamy się wyjątków biznesowych, tylko DB lub inne
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def update_link(
        self, link_id: UUID, update_data: LinkUpdate, user_id: UUID
    ) -> LinkResponse:
        context = f"link update for ID {link_id} by user {user_id}"
        print(f"Attempting {context}")

        db_update_payload = update_data.model_dump(exclude_unset=True)

        if (
            "default_url" in db_update_payload
            and db_update_payload["default_url"] is not None
        ):
            db_update_payload["default_url"] = str(db_update_payload["default_url"])

        if not db_update_payload:
            print(f"No fields to update for {context}. Returning current state.")
            # To wywołanie może rzucić NotFoundException, jeśli link nie istnieje
            try:
                return await self.get_link_by_id(link_id=link_id, user_id=user_id)
            except NotFoundException:
                raise  # Rzuć dalej NotFoundException z get_link_by_id
            except Exception as e:  # Obsłuż inne błędy z get_link_by_id
                self._handle_db_error(
                    e, context=f"get_link_by_id during update check for {context}"
                )
                raise DatabaseException(
                    f"Unhandled error during get_link_by_id in update check for {context}"
                )

        try:
            response = (
                await self.supabase.table(self.links_table)
                .update(db_update_payload)
                .eq("id", str(link_id))
                .execute()
            )

            if (
                response
                and response.data
                and isinstance(response.data, list)
                and len(response.data) == 1
            ):
                updated_data = response.data[0]
                print(f"Successfully updated link with ID: {link_id}")
                updated_link_dto = LinkResponse.model_validate(updated_data)
                return updated_link_dto
            else:
                print(
                    f"[WARNING] Link not found or access denied during update for {context}. Response: {response}"
                )
                # Rzuć NotFoundException, zostanie złapany i rzucony dalej przez blok except
                raise NotFoundException(
                    detail="Link not found or you do not have permission to update it."
                )

        except NotFoundException:  # Jawnie łap i rzucaj dalej
            print(f"Re-raising NotFoundException from {context}")
            raise
        except Exception as e:  # Pozostałe idą do handlera
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def delete_link(self, link_id: UUID, user_id: UUID) -> None:
        context = f"link deletion for ID {link_id} by user {user_id}"
        print(f"Attempting {context}")

        try:
            response = (
                await self.supabase.table(self.links_table)
                .delete(count=CountMethod.exact)
                .eq("id", str(link_id))
                .execute()
            )

            if response and response.count == 1:
                print(f"Successfully deleted link with ID: {link_id}")
                return
            elif response and response.count == 0:
                print(
                    f"[WARNING] Link not found or access denied during delete for {context}"
                )
                # Rzuć NotFoundException
                raise NotFoundException(
                    detail="Link not found or you do not have permission to delete it."
                )
            else:
                count_val = response.count if response else "N/A"
                print(
                    f"[ERROR] Unexpected delete count ({count_val}) or invalid response for {context}"
                )
                # To jest błąd bazy danych lub logiki
                raise DatabaseException("Unexpected result during link deletion.")

        except NotFoundException:  # Jawnie łap i rzucaj dalej
            print(f"Re-raising NotFoundException from {context}")
            raise
        except (
            Exception
        ) as e:  # Pozostałe (w tym DatabaseException z bloku else) idą do handlera
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")

    async def get_link_statistics(
        self, link_id: UUID, user_id: UUID
    ) -> LinkStatsResponse:
        context = f"statistics retrieval for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")

        try:
            # Krok 1: Pobierz link
            print(f"Fetching base link data for {context}")
            link_response = (
                await self.supabase.table(self.links_table)
                .select("id, alias, total_clicks")
                .eq("id", str(link_id))
                .maybe_single()
                .execute()
            )

            if not (link_response and link_response.data):
                print(f"[WARNING] Link not found or access denied for {context}")
                # Rzuć NotFoundException
                raise NotFoundException(
                    "Link not found or you do not have permission to access it."
                )

            link_data = link_response.data
            print(f"Link data found for {context}. Fetching rules.")

            # Krok 2: Pobierz statystyki reguł
            rules_response = (
                await self.supabase.table(self.rules_table)
                .select("id, target_type, target_value, current_clicks")
                .eq("link_id", str(link_id))
                .order("priority", desc=False)
                .execute()
            )

            rules_stats_data = (
                rules_response.data if rules_response and rules_response.data else []
            )
            print(
                f"Retrieved {len(rules_stats_data)} rules for {context}. Processing stats."
            )

            # Krok 3: Przetwórz dane reguł
            target_clicks_list: List[TargetClickStat] = []
            for rule in rules_stats_data:
                target_value_preview: str
                try:
                    target_type_enum = TargetTypeEnum(rule["target_type"])
                    target_type_str = target_type_enum.value
                except ValueError:
                    print(
                        f"[WARNING] Invalid target_type '{rule.get('target_type')}' found for rule {rule.get('id','N/A')}"
                    )
                    target_type_str = "unknown"

                target_value = rule["target_value"]
                current_clicks = rule["current_clicks"]
                rule_id = UUID(rule["id"])

                if target_type_str == TargetTypeEnum.URL.value:
                    target_value_preview = target_value
                elif target_type_str == TargetTypeEnum.HTML.value:
                    target_value_preview = "[Custom HTML Content]"
                else:
                    target_value_preview = "[Unknown Target Type]"

                target_stat = TargetClickStat.model_validate(
                    {
                        "rule_id": rule_id,
                        "target_type": target_type_str,
                        "target_value_preview": target_value_preview,
                        "current_clicks": current_clicks,
                    }
                )
                target_clicks_list.append(target_stat)

            # Krok 4: Skonstruuj finalną odpowiedź
            stats_response = LinkStatsResponse.model_validate(
                {
                    "link_id": UUID(link_data["id"]),
                    "alias": link_data["alias"],
                    "total_clicks": link_data["total_clicks"],
                    "target_clicks": target_clicks_list,
                }
            )

            print(f"Successfully prepared statistics for {context}")
            return stats_response

        except NotFoundException:  # Jawnie łap i rzucaj dalej
            print(f"Re-raising NotFoundException from {context}")
            raise
        except Exception as e:  # Pozostałe idą do handlera
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error after handler in {context}")
