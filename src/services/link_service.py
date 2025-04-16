# src/services/link_service.py

import logging  # Import pozostaje, nawet jeśli używamy print, na przyszłość
import traceback
from uuid import UUID
from typing import List, Optional, Tuple
from supabase_py_async import AsyncClient  # Lub from supabase import Client
from postgrest.exceptions import (
    APIError as PostgrestAPIError,
)  # Sprawdź dokładny import błędu

# Import niestandardowych wyjątków
from src.services.custom_exceptions import (
    AliasConflictException,
    DatabaseException,
    NotFoundException,
    ServiceException,  # Importuj też bazowy, jeśli potrzebny
)

# Import modeli Pydantic (DTOs)
from src.schemas.link import LinkCreate, LinkUpdate, LinkResponse, PaginatedLinkResponse
from src.schemas.stats import LinkStatsResponse, TargetClickStat
from src.schemas.enums import TargetTypeEnum

# logger = logging.getLogger(__name__) # Zakomentowane, używamy print

# Kod błędu PostgreSQL dla naruszenia unikalności
POSTGRES_UNIQUE_VIOLATION_CODE = "23505"


class LinkService:
    """
    Service layer for managing business logic related to Routr Links.
    Operates within the context of an authenticated user (via Supabase client with JWT).
    """

    def __init__(
        self, supabase_client: AsyncClient
    ):  # Oczekuje klienta z kontekstem użytkownika
        """
        Initializes the LinkService.

        Args:
            supabase_client: An instance of the Supabase async client, expected to be
                             initialized with user context (JWT) for RLS enforcement.
        """
        self.supabase = supabase_client
        self.links_table = "routr_links"
        self.rules_table = "routing_rules"  # Nazwa tabeli reguł potrzebna dla statystyk

    async def create_link(self, link_data: LinkCreate, user_id: UUID) -> LinkResponse:
        """
        Creates a new routr_link record in the database for the specified user.
        Relies on RLS WITH CHECK policy and DB UNIQUE constraint for validation.

        Args:
            link_data: Validated data for the new link (LinkCreate schema).
            user_id: The UUID of the user creating the link.

        Returns:
            LinkResponse object representing the newly created link.

        Raises:
            AliasConflictException: If the chosen alias already exists.
            DatabaseException: For other database related errors.
        """
        insert_data = link_data.model_dump()
        insert_data["user_id"] = user_id

        context = f"link creation for alias '{link_data.alias}' by user {user_id}"
        print(f"Attempting {context}")

        try:
            response = (
                await self.supabase.table(self.links_table)
                .insert(insert_data)
                .select("*")
                .single()
                .execute()
            )

            if response.data:
                print(f"Successfully created link with ID: {response.data.get('id')}")
                created_link_dto = LinkResponse.model_validate(response.data)
                return created_link_dto
            else:
                print("[ERROR] Insert successful but no data returned from database.")
                raise DatabaseException(
                    "Failed to retrieve created link data after insert."
                )

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException("Unhandled error during link creation.")  # Fallback

    async def get_link_by_id(self, link_id: UUID, user_id: UUID) -> LinkResponse:
        """
        Retrieves a specific routr_link by its ID, ensuring ownership by the user via RLS.

        Args:
            link_id: The UUID of the link to retrieve.
            user_id: The UUID of the authenticated user (used implicitly by RLS via JWT context).

        Returns:
            LinkResponse object representing the found link.

        Raises:
            NotFoundException: If the link with the given ID is not found or not owned by the user.
            DatabaseException: For other database related errors.
        """
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

            if response.data:
                print(f"Successfully retrieved link with ID: {link_id}")
                link_dto = LinkResponse.model_validate(response.data)
                return link_dto
            else:
                print(f"[WARNING] Link not found or access denied for {context}")
                raise NotFoundException(
                    detail="Link not found or you do not have permission to access it."
                )

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def get_links_paginated(
        self, user_id: UUID, page: int, page_size: int
    ) -> PaginatedLinkResponse:
        """
        Retrieves a paginated list of links owned by the specified user.

        Args:
            user_id: The UUID of the authenticated user (used implicitly by RLS).
            page: The page number (>= 1).
            page_size: The number of items per page.

        Returns:
            PaginatedLinkResponse object containing the list of links and pagination info.

        Raises:
            DatabaseException: For database related errors.
        """
        context = f"paginated link retrieval for user {user_id} (page={page}, size={page_size})"
        print(f"Attempting {context}")

        offset = (page - 1) * page_size
        range_to = offset + page_size - 1

        try:
            response = (
                await self.supabase.table(self.links_table)
                .select("*", count="exact")
                .order("created_at", desc=True)
                .range(offset, range_to)
                .execute()
            )

            items_data = response.data or []
            total_count = response.count if response.count is not None else 0

            print(
                f"Retrieved {len(items_data)} links out of {total_count} total for {context}"
            )

            link_items = [LinkResponse.model_validate(item) for item in items_data]

            paginated_response = PaginatedLinkResponse(
                items=link_items, total=total_count, page=page, page_size=page_size
            )
            return paginated_response

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def update_link(
        self, link_id: UUID, update_data: LinkUpdate, user_id: UUID
    ) -> LinkResponse:
        """
        Updates the mutable fields (currently only default_url) of an existing link owned by the user.

        Args:
            link_id: The UUID of the link to update.
            update_data: LinkUpdate schema containing the fields to update.
            user_id: The UUID of the authenticated user (used implicitly by RLS).

        Returns:
            LinkResponse object representing the updated link.

        Raises:
            NotFoundException: If the link is not found or not owned by the user.
            DatabaseException: For database related errors during update.
        """
        context = f"link update for ID {link_id} by user {user_id}"
        print(f"Attempting {context}")

        db_update_payload = update_data.model_dump(exclude_unset=True)

        if not db_update_payload:
            print(f"No fields to update for {context}. Returning current state.")
            return await self.get_link_by_id(link_id=link_id, user_id=user_id)

        try:
            response = (
                await self.supabase.table(self.links_table)
                .update(db_update_payload)
                .eq("id", str(link_id))
                .select()
                .maybe_single()
                .execute()
            )

            if response.data:
                print(f"Successfully updated link with ID: {link_id}")
                updated_link_dto = LinkResponse.model_validate(response.data)
                return updated_link_dto
            else:
                # If maybe_single returns None after update, it implies the RLS policy failed
                # (or the record didn't exist, which shouldn't happen if RLS is correct)
                print(
                    f"[WARNING] Link not found or access denied during update for {context}"
                )
                raise NotFoundException(
                    detail="Link not found or you do not have permission to update it."
                )

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def delete_link(self, link_id: UUID, user_id: UUID) -> None:
        """
        Deletes a specific link owned by the user.
        Associated rules are deleted automatically by the database CASCADE constraint.

        Args:
            link_id: The UUID of the link to delete.
            user_id: The UUID of the authenticated user (used implicitly by RLS).

        Returns:
            None upon successful deletion.

        Raises:
            NotFoundException: If the link is not found or not owned by the user.
            DatabaseException: For other database related errors.
        """
        context = f"link deletion for ID {link_id} by user {user_id}"
        print(f"Attempting {context}")

        try:
            # Use count='exact' with delete to check if a row was actually deleted
            response = (
                await self.supabase.table(self.links_table)
                .delete(count="exact")
                .eq("id", str(link_id))
                .execute()
            )

            if response.count == 1:
                print(f"Successfully deleted link with ID: {link_id}")
                return
            elif response.count == 0:
                print(
                    f"[WARNING] Link not found or access denied during delete for {context}"
                )
                raise NotFoundException(
                    detail="Link not found or you do not have permission to delete it."
                )
            else:
                print(
                    f"[ERROR] Unexpected delete count ({response.count}) for {context}"
                )
                raise DatabaseException("Unexpected result during link deletion.")

        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    async def get_link_statistics(
        self, link_id: UUID, user_id: UUID
    ) -> LinkStatsResponse:
        """
        Retrieves click statistics for a specific link owned by the user.

        Args:
            link_id: The UUID of the link.
            user_id: The UUID of the authenticated user (used implicitly by RLS).

        Returns:
            LinkStatsResponse object containing link details and target click counts.

        Raises:
            NotFoundException: If the link is not found or not owned by the user.
            DatabaseException: For database related errors.
        """
        context = f"statistics retrieval for link ID {link_id} by user {user_id}"
        print(f"Attempting {context}")

        try:
            # Krok 1: Pobierz link i zweryfikuj własność (RLS zadziała)
            print(f"Fetching base link data for {context}")
            link_response = (
                await self.supabase.table(self.links_table)
                .select("id, alias, total_clicks")
                .eq("id", str(link_id))
                .maybe_single()
                .execute()
            )

            if not link_response.data:
                print(f"[WARNING] Link not found or access denied for {context}")
                raise NotFoundException(
                    "Link not found or you do not have permission to access it."
                )

            link_data = link_response.data
            print(f"Link data found for {context}. Fetching rules.")

            # Krok 2: Pobierz statystyki reguł dla tego linku (RLS na rules też zadziała)
            rules_response = (
                await self.supabase.table(self.rules_table)
                .select("id, target_type, target_value, current_clicks")
                .eq("link_id", str(link_id))
                .order("priority", desc=False)
                .execute()
            )

            rules_stats_data = rules_response.data or []
            print(
                f"Retrieved {len(rules_stats_data)} rules for {context}. Processing stats."
            )

            # Krok 3: Przetwórz dane reguł
            target_clicks_list: List[TargetClickStat] = []
            for rule in rules_stats_data:
                target_value_preview: str
                try:
                    # Używamy .value, aby uzyskać string z Enuma dla mapowania Pydantic
                    target_type = TargetTypeEnum(rule["target_type"])
                except ValueError:
                    print(
                        f"[WARNING] Invalid target_type '{rule['target_type']}' found for rule {rule['id']}"
                    )
                    target_type = None  # Handle invalid enum value gracefully

                target_value = rule["target_value"]
                current_clicks = rule["current_clicks"]
                rule_id = UUID(rule["id"])  # Konwertuj string UUID na obiekt UUID

                if target_type == TargetTypeEnum.URL:
                    target_value_preview = target_value
                elif target_type == TargetTypeEnum.HTML:
                    target_value_preview = "[Custom HTML Content]"  # Placeholder
                else:
                    target_value_preview = "[Unknown Target Type]"

                target_clicks_list.append(
                    TargetClickStat(
                        rule_id=rule_id,
                        # Zwróć wartość stringową enuma, jeśli model Pydantic tego oczekuje
                        target_type=target_type.value if target_type else "unknown",
                        target_value_preview=target_value_preview,
                        current_clicks=current_clicks,
                    )
                )

            # Krok 4: Skonstruuj finalną odpowiedź
            stats_response = LinkStatsResponse(
                link_id=UUID(link_data["id"]),  # Konwertuj string UUID na obiekt UUID
                alias=link_data["alias"],
                total_clicks=link_data["total_clicks"],
                target_clicks=target_clicks_list,
            )

            print(f"Successfully prepared statistics for {context}")
            return stats_response

        except NotFoundException:  # Przechwyć i rzuć dalej z kroku 1
            raise
        except Exception as e:
            self._handle_db_error(e, context=context)
            raise DatabaseException(f"Unhandled error during {context}")

    # Metoda pomocnicza (zdefiniowana wcześniej)
    def _handle_db_error(self, error: Exception, context: str):
        if isinstance(error, PostgrestAPIError):
            print(
                f"[ERROR] PostgrestAPIError during {context}: Status={getattr(error,'status','N/A')}, Message='{getattr(error,'message','Unknown')}'"
            )
            if hasattr(error, "code") and error.code == POSTGRES_UNIQUE_VIOLATION_CODE:
                if "routr_links_alias_key" in getattr(
                    error, "message", ""
                ):  # Dostosuj do nazwy klucza
                    raise AliasConflictException(
                        detail=f"Database error during {context}: Alias conflict."
                    )
                else:
                    # Można dodać sprawdzanie klucza dla priorytetu, jeśli ten serwis miałby go obsługiwać
                    raise DatabaseException(
                        detail=f"Unique constraint violation during {context}: {getattr(error,'message','Unknown')}"
                    )
            # Tutaj można dodać obsługę innych specyficznych kodów błędów DB
            raise DatabaseException(
                detail=f"Database API error during {context}: {getattr(error,'message','Unknown')}"
            )
        else:
            print(f"[ERROR] Unexpected error during {context}: {error}")
            traceback.print_exc()  # Drukuj stacktrace do konsoli dla debugowania
            raise DatabaseException(
                detail=f"An unexpected error occurred during {context}."
            )
