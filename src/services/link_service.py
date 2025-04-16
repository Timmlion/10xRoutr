# src/services/link_service.py

from uuid import UUID
from supabase_py_async import (
    AsyncClient,
)  # Używamy klienta async, jeśli FastAPI działa asynchronicznie

# Lub: from supabase import Client as SyncClient (jeśli używasz synchronicznego klienta)
from postgrest import (
    APIError as PostgrestAPIError,
)  # Dostosuj import błędu do używanej wersji supabase-py

from src.schemas.link import LinkCreate, LinkResponse
from src.services.custom_exceptions import AliasConflictException, DatabaseException

# Załóżmy, że psycopg2 lub odpowiedni driver bazy danych jest dostępny do sprawdzania kodów błędów
# W praktyce, supabase-py może opakowywać te błędy inaczej.
# Należy sprawdzić dokumentację supabase-py lub eksperymentalnie, jak przechwycić UniqueViolation.
# Tutaj użyjemy ogólnego sprawdzania kodu błędu z PostgrestAPIError, jeśli jest dostępny.
POSTGRES_UNIQUE_VIOLATION_CODE = "23505"


class LinkService:
    def __init__(self, supabase: AsyncClient):  # Oczekujemy wstrzyknięcia klienta async
        # Lub: def __init__(self, supabase: SyncClient):
        self.supabase = supabase
        self.table_name = "routr_links"

    async def create_link(self, link_data: LinkCreate, user_id: UUID) -> LinkResponse:
        """
        Creates a new routr_link in the database for the specified user.

        Args:
            link_data: Validated data for the new link (from LinkCreate schema).
            user_id: The UUID of the user creating the link.

        Returns:
            A LinkResponse object representing the newly created link.

        Raises:
            AliasConflictException: If the chosen alias already exists.
            DatabaseException: For other database related errors.
            Exception: For unexpected errors.
        """
        insert_data = link_data.model_dump()
        insert_data["user_id"] = user_id
        # total_clicks, created_at, updated_at mają wartości domyślne w bazie

        try:
            # .select("*").single() - aby zwrócić wstawiony wiersz (sprawdź składnię dla async)
            response = (
                await self.supabase.table(self.table_name)
                .insert(insert_data)
                .select("*")
                .single()
                .execute()
            )

            # Sprawdzenie, czy dane zostały zwrócone
            if response.data:
                # Użyj **response.data do rozpakowania słownika do modelu Pydantic
                # Pydantic v2 używa model_validate zamiast from_orm
                created_link = LinkResponse.model_validate(response.data)
                return created_link
            else:
                # Jeśli z jakiegoś powodu insert się powiódł, ale nie zwrócił danych
                raise DatabaseException(
                    "Failed to retrieve created link data after insert."
                )

        except PostgrestAPIError as e:
            # Sprawdź, czy błąd jest związany z naruszeniem unikalności
            # Kod błędu '23505' jest standardem PostgreSQL dla unique_violation
            # Dostosuj sprawdzanie na podstawie rzeczywistych błędów zwracanych przez supabase-py
            if hasattr(e, "code") and e.code == POSTGRES_UNIQUE_VIOLATION_CODE:
                # Sprawdzenie, czy naruszenie dotyczy ograniczenia aliasu (może wymagać parsowania e.details)
                # Dla uproszczenia zakładamy, że to naruszenie aliasu
                raise AliasConflictException(
                    detail=f"Alias '{link_data.alias}' already exists."
                )
            else:
                # Inny błąd bazy danych
                # Log the original error e
                print(
                    f"Database error creating link: {e}"
                )  # Zastąp prawdziwym logowaniem
                raise DatabaseException(
                    detail="Failed to create link due to database error."
                )
        except Exception as e:
            # Nieoczekiwany błąd
            # Log the original error e
            print(
                f"Unexpected error creating link: {e}"
            )  # Zastąp prawdziwym logowaniem
            raise DatabaseException(
                detail="An unexpected error occurred while creating the link."
            )
