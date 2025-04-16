# src/api/deps.py (zaktualizowany)

from fastapi import Depends, HTTPException, status, Query  # Dodano Query
from fastapi.security import OAuth2PasswordBearer
from supabase_py_async import AsyncClient
from gotrue.errors import AuthApiError
from pydantic import UUID4

# Import modeli i schem
from src.schemas.auth import UserInfo
from src.schemas.pagination import PaginationParams  # Import schemy paginacji

# Import klientów Supabase (załóżmy, że istnieją funkcje zwracające odpowiednie instancje)
# WAŻNE: Rozróżnienie między klientem użytkownika (z JWT) a klientem serwisowym (z service_role key)
from src.db.supabase_client import (
    get_supabase_user_client,
    get_supabase_service_client,
)  # Przykładowe nazwy

# Import serwisów
from src.services.link_service import LinkService
from src.services.rule_service import RuleService  # Przygotowanie na przyszłość
from src.services.auth_service import AuthService  # Przygotowanie na przyszłość
from src.services.redirection_service import (
    RedirectionService,
)  # Przygotowanie na przyszłość


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# --- Zależności Uwierzytelniania ---


async def get_supabase_auth_client() -> AsyncClient:
    """Dependency to get Supabase client suitable for auth operations (usually anon key)."""
    # Ta funkcja powinna zwracać klienta, którego AuthService może używać do sign_in/sign_up
    # Może to być ten sam co user_client lub osobny anonimowy. Dla uproszczenia użyjmy service_client
    # ALE w rzeczywistej aplikacji lepiej mieć dedykowanego klienta anon lub użyć biblioteki JS na froncie.
    # W tym przykładzie użyjemy service_client, ale to wymaga uwagi.
    return (
        get_supabase_service_client()
    )  # Użycie service klienta tutaj może być uproszczeniem!


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    # Do weryfikacji tokenu użyjemy klienta, który może to zrobić - zazwyczaj anon/service
    supabase: AsyncClient = Depends(
        get_supabase_auth_client
    ),  # Zmieniono zależność na klienta do auth
) -> UserInfo:
    """Gets the current authenticated user from JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Używamy metody get_user do weryfikacji tokenu
        response = await supabase.auth.get_user(token)
        user = response.user
        if user is None or user.id is None:  # Sprawdźmy czy ID istnieje
            raise credentials_exception
        # Zwracamy obiekt zwalidowany przez Pydantic
        return UserInfo.model_validate(user.dict())
    except AuthApiError as e:
        print(f"Auth error verifying token: {e}")
        raise credentials_exception
    except Exception as e:
        print(f"Unexpected error in get_current_user: {e}")
        raise credentials_exception


async def get_current_user_id(
    current_user: UserInfo = Depends(get_current_user),
) -> UUID4:
    """Gets the current authenticated user's ID."""
    return current_user.id


# --- Zależność Paginacji ---


async def pagination_dependency(
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
) -> PaginationParams:
    """Parses and validates pagination query parameters using Pydantic model."""
    try:
        return PaginationParams(page=page, page_size=page_size)
    except (
        ValueError
    ) as e:  # Przechwycenie błędów walidacji Pydantic (choć Query powinno je obsłużyć)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid pagination parameters: {e}",
        )


# --- Zależności Serwisów ---

# WAŻNE: Rozróżnienie klienta dla operacji użytkownika (RLS) i klienta dla przekierowań (service_role)
# Ta funkcja powinna zwracać klienta zainicjalizowanego z JWT użytkownika, jeśli to możliwe,
# lub klienta anon/service, a RLS będzie polegać na `auth.uid()` w politykach.
# Klient przekazywany do serwisów LinkService, RuleService MUSI działać w kontekście użytkownika dla RLS.
# Klient przekazywany do RedirectionService MUSI być klientem service_role.

# Zakładając, że mamy funkcję get_supabase_user_client zwracającą klienta z kontekstem użytkownika
# (Może wymagać przekazania tokenu lub sesji - upraszczamy na razie)
# W praktyce, klient Supabase może być współdzielony i automatycznie używać kontekstu auth.uid()


def get_link_service(
    supabase: AsyncClient = Depends(get_supabase_user_client),
) -> LinkService:
    """Dependency to get LinkService instance with user-context client."""
    return LinkService(supabase_client=supabase)


def get_rule_service(
    supabase: AsyncClient = Depends(get_supabase_user_client),
) -> RuleService:
    """Dependency to get RuleService instance with user-context client."""
    return RuleService(supabase_client=supabase)


def get_auth_service(
    supabase: AsyncClient = Depends(get_supabase_auth_client),
) -> AuthService:
    """Dependency to get AuthService instance with appropriate client."""
    return AuthService(supabase_client=supabase)


def get_redirection_service(
    supabase: AsyncClient = Depends(get_supabase_service_client),
) -> RedirectionService:
    """Dependency to get RedirectionService instance with service_role client."""
    return RedirectionService(supabase_client=supabase)
