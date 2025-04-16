# src/api/v1/endpoints/links.py

from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID

from src.schemas.link import LinkCreate, LinkResponse
from src.services.link_service import LinkService
from src.services.custom_exceptions import AliasConflictException, DatabaseException
from src.api.deps import get_current_user_id  # Zależność do pobrania ID użytkownika
from src.db.supabase_client import (
    get_supabase_service_client,
)  # Zależność do pobrania klienta DB
from supabase_py_async import AsyncClient  # Lub Sync Client

# Utworzenie routera dla tego endpointu
router = APIRouter()

# Inicjalizacja serwisu (prosta, dla przykładu - w większej aplikacji można użyć DI frameworka)
# Lub wstrzykiwać serwis jako zależność, jeśli ma stan lub zależności
# link_service = LinkService(supabase=...) # Unikać tworzenia instancji globalnie, jeśli klient jest per-request


# Alternatywa: Wstrzykiwanie serwisu jako zależności
# To lepsze podejście, pozwala na łatwiejsze testowanie i zarządzanie zależnościami klienta DB
def get_link_service(
    supabase: AsyncClient = Depends(get_supabase_service_client),
) -> LinkService:
    """Dependency function to get an instance of LinkService."""
    return LinkService(supabase=supabase)


@router.post(
    "",  # Ścieżka jest pusta, bo prefix "/links" będzie dodany przy rejestracji routera
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Routr Link",
    description="Creates a new unique routr link associated with the authenticated user.",
    tags=["Links"],  # Tagowanie dla dokumentacji Swagger/OpenAPI
)
async def create_link_endpoint(
    link_data: LinkCreate,  # Ciało żądania zwalidowane przez Pydantic
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Pobranie ID zalogowanego użytkownika
    link_service: LinkService = Depends(get_link_service),  # Wstrzyknięcie serwisu
):
    """
    Endpoint to create a new routr link.

    - **alias**: The unique path for the link (e.g., 'my-campaign').
    - **default_url**: Optional fallback URL.
    """
    try:
        created_link = await link_service.create_link(
            link_data=link_data, user_id=current_user_id
        )
        return created_link
    except AliasConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    except DatabaseException as e:
        # Ogólny błąd bazy danych z serwisu
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail
        )
    except Exception as e:
        # Inne nieoczekiwane błędy
        # Log the error e here
        print(f"Unexpected error in create_link_endpoint: {e}")  # Zastąp logowaniem
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )
