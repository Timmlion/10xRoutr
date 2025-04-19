# src/api/deps.py (zaktualizowany)
import uuid
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from supabase import AsyncClient  # <<< POPRAWIONY IMPORT
from gotrue.errors import (
    AuthApiError,
)  # Zmieniono import, żeby był zgodny z supabase-py >= 1.0
from pydantic import UUID4

# Import modeli i schem
from src.schemas.auth import UserInfo
from src.schemas.pagination import PaginationParams

# Import funkcji tworzących klientów Supabase z dedykowanego modułu
from src.db.supabase_client import (
    get_supabase_user_client,  # Klient dla operacji użytkownika (z kluczem anon, respektuje RLS+JWT)
    get_supabase_service_client,  # Klient dla operacji serwisowych (z kluczem service_role, omija RLS)
)

# Import serwisów
from src.services.link_service import LinkService
from src.services.rule_service import RuleService
from src.services.auth_service import AuthService
from src.services.redirection_service import RedirectionService

# --- Schemat OAuth2 ---
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)  # Upewnij się, że URL jest poprawny

# --- Zależności Klientów Supabase ---
# Te funkcje są teraz tylko aliasami do funkcji z src.db.supabase_client,
# aby zachować spójność interfejsu zależności w endpointach.
# Alternatywnie można bezpośrednio używać Depends(get_supabase_...) w endpointach.


def supabase_service_dependency() -> AsyncClient:
    """Dependency function that returns the service client."""
    return get_supabase_service_client()


def supabase_user_dependency() -> AsyncClient:
    """Dependency function that returns the user (anon key) client."""
    return get_supabase_user_client()


# Użyjemy klienta użytkownika (anon) do operacji autoryzacji,
# ponieważ to on powinien weryfikować tokeny użytkowników.
def supabase_auth_dependency() -> AsyncClient:
    """Dependency function that returns the client suitable for auth operations."""
    return get_supabase_user_client()


# --- Zależności Uwierzytelniania ---


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    supabase: AsyncClient = Depends(supabase_auth_dependency),
) -> UserInfo:
    """
    Verifies the JWT token using Supabase Auth and returns the user info.
    Raises HTTPException 401 if the token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        response = await supabase.auth.get_user(token)

        # Sprawdź CZY użytkownik został zwrócony W OGÓLE
        if response is None or response.user is None:  # <<< Bezpieczniejsze sprawdzenie
            print("Token verification failed or user not found.")  # Logowanie MVP
            raise credentials_exception

        user = response.user  # Teraz wiemy, że user istnieje

        # Sprawdź, czy użytkownik ma ID (powinien zawsze mieć, ale dla pewności)
        if user.id is None:
            print(
                "Token verified but user data is incomplete (missing ID)."
            )  # Logowanie MVP
            raise credentials_exception

        # Zwracamy obiekt zwalidowany przez Pydantic
        # Użyj model_dump() (Pydantic v2) do serializacji obiektu User z gotrue
        return UserInfo.model_validate(user.model_dump())

    except AuthApiError as e:
        print(f"Auth API error verifying token: {e}")  # Logowanie MVP
        raise credentials_exception
    except Exception as e:
        print(f"Unexpected error in get_current_user: {e}")  # Logowanie MVP
        raise credentials_exception


async def get_current_user_id(
    current_user: UserInfo = Depends(get_current_user),
) -> uuid.UUID:  # <<< Zmień typ zwracany na uuid.UUID
    """Gets the current authenticated user's ID (UUID)."""
    # Pydantic powinien już zapewnić, że current_user.id jest typu uuid.UUID
    # jeśli UserInfo jest poprawnie zdefiniowane z polem id: uuid.UUID lub id: UUID4
    # To sprawdzenie jest głównie zabezpieczeniem.
    if not isinstance(current_user.id, uuid.UUID):  # <<< Sprawdzaj względem uuid.UUID
        print(
            f"Error: User ID '{current_user.id}' is not a valid UUID object after validation."
        )  # Logowanie MVP
        # Można by próbować konwersji, ale jeśli Pydantic przepuścił coś innego, to jest błąd
        raise HTTPException(
            status_code=500, detail="Internal error: Invalid user ID type."
        )

    return current_user.id


# --- Zależność Paginacji ---


async def pagination_dependency(
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
) -> PaginationParams:
    """Parses and validates pagination query parameters."""
    try:
        return PaginationParams(page=page, page_size=page_size)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid pagination parameters: {e}",
        )


# --- Zależności Serwisów ---
# Teraz używamy poprawnych funkcji zależnościowych dla klientów Supabase


def get_link_service(
    supabase: AsyncClient = Depends(
        supabase_user_dependency
    ),  # Używa klienta użytkownika (anon)
) -> LinkService:
    """Dependency to get LinkService instance."""
    return LinkService(supabase_client=supabase)


def get_rule_service(
    supabase: AsyncClient = Depends(
        supabase_user_dependency
    ),  # Używa klienta użytkownika (anon)
) -> RuleService:
    """Dependency to get RuleService instance."""
    return RuleService(supabase_client=supabase)


def get_auth_service(
    supabase: AsyncClient = Depends(
        supabase_auth_dependency
    ),  # Używa klienta użytkownika (anon) dla logowania/rejestracji
) -> AuthService:
    """Dependency to get AuthService instance."""
    return AuthService(supabase_client=supabase)


def get_redirection_service(
    supabase: AsyncClient = Depends(
        supabase_service_dependency
    ),  # Używa klienta SERWISOWEGO
) -> RedirectionService:
    """Dependency to get RedirectionService instance."""
    return RedirectionService(supabase_client=supabase)
