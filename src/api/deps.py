# src/api/deps.py (zaktualizowany)
import uuid
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from supabase import AsyncClient
from gotrue.errors import AuthApiError
from pydantic import UUID4
from fastapi.templating import Jinja2Templates  # <<< Dodano import
from pathlib import Path  # <<< Dodano import
from functools import lru_cache  # <<< Dodano import

# Import modeli i schem
from src.schemas.auth import UserInfo
from src.schemas.pagination import PaginationParams

# Import funkcji tworzących klientów Supabase z dedykowanego modułu
from src.db.supabase_client import (
    get_supabase_user_client,
    get_supabase_service_client,
)

# Import serwisów
from src.services.link_service import LinkService
from src.services.rule_service import RuleService
from src.services.auth_service import AuthService
from src.services.redirection_service import RedirectionService

# --- Schemat OAuth2 ---
# Poprawiono tokenUrl, aby wskazywał na poprawny endpoint API
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# --- Zależności Klientów Supabase ---
def supabase_service_dependency() -> AsyncClient:
    return get_supabase_service_client()


def supabase_user_dependency() -> AsyncClient:
    return get_supabase_user_client()


def supabase_auth_dependency() -> AsyncClient:
    return get_supabase_user_client()


# --- Zależność dla Jinja2 Templates ---
# Upewnij się, że ścieżka BASE_DIR jest poprawna względem lokalizacji tego pliku
# Zakładając, że deps.py jest w src/api/, a templates w src/
BASE_DIR = (
    Path(__file__).resolve().parent.parent.parent
)  # Przejdź 3 poziomy wyżej: api -> v1 -> src


@lru_cache()  # Cache'ujemy instancję templates dla wydajności
def get_templates() -> Jinja2Templates:
    """Dependency function that returns the Jinja2Templates instance."""
    templates_dir = str(Path(BASE_DIR, "src", "templates"))  # Poprawiona ścieżka
    print(
        f"Initializing Jinja2Templates with directory: {templates_dir}"
    )  # Logowanie MVP
    return Jinja2Templates(directory=templates_dir)


# --- Zależności Uwierzytelniania ---
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    supabase: AsyncClient = Depends(supabase_auth_dependency),
) -> UserInfo:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        response = await supabase.auth.get_user(token)
        if response is None or response.user is None:
            print("Token verification failed or user not found.")
            raise credentials_exception
        user = response.user
        if user.id is None:
            print("Token verified but user data is incomplete (missing ID).")
            raise credentials_exception
        # Użycie model_validate zamiast from_orm/parse_obj
        return UserInfo.model_validate(user.model_dump())
    except AuthApiError as e:
        print(f"Auth API error verifying token: {e}")
        raise credentials_exception
    except Exception as e:
        print(f"Unexpected error in get_current_user: {e}")
        raise credentials_exception


async def get_current_user_id(
    current_user: UserInfo = Depends(get_current_user),
) -> uuid.UUID:
    if not isinstance(current_user.id, uuid.UUID):
        print(
            f"Error: User ID '{current_user.id}' is not a valid UUID object after validation."
        )
        raise HTTPException(
            status_code=500, detail="Internal error: Invalid user ID type."
        )
    return current_user.id


# --- Zależność Paginacji ---
async def pagination_dependency(
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
) -> PaginationParams:
    try:
        return PaginationParams(page=page, page_size=page_size)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid pagination parameters: {e}",
        )


# --- Zależności Serwisów ---
def get_link_service(
    supabase: AsyncClient = Depends(supabase_user_dependency),
) -> LinkService:
    return LinkService(supabase_client=supabase)


def get_rule_service(
    supabase: AsyncClient = Depends(supabase_user_dependency),
) -> RuleService:
    return RuleService(supabase_client=supabase)


def get_auth_service(
    supabase: AsyncClient = Depends(supabase_auth_dependency),
) -> AuthService:
    return AuthService(supabase_client=supabase)


def get_redirection_service(
    supabase: AsyncClient = Depends(supabase_service_dependency),
) -> RedirectionService:
    return RedirectionService(supabase_client=supabase)
