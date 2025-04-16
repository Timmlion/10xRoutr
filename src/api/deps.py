# src/api/deps.py

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    OAuth2PasswordBearer,
)  # Lub HTTPBearer, jeśli token nie jest związany z OAuth2 flow
from supabase_py_async import AsyncClient  # Lub sync Client
from gotrue.errors import AuthApiError  # Sprawdź dokładny typ wyjątku dla sesji
from pydantic import UUID4

# Import klienta Supabase i modelu użytkownika (jeśli Supabase go zwraca)
# Załóżmy, że mamy funkcję do uzyskania klienta, np. z db.supabase_client
# lub wstrzykujemy go inaczej
from src.db.supabase_client import get_supabase_service_client  # Przykład - dostosuj
from src.schemas.auth import UserInfo  # Przykład modelu użytkownika

# Definiujemy schemat Bearer - FastAPI użyje go do znalezienia tokenu w nagłówku Authorization
# Można użyć OAuth2PasswordBearer, jeśli jest przepływ /token, lub prostszego HTTPBearer
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)  # Token URL jest bardziej dla dokumentacji Swaggera


# Zwracany typ może być bardziej generyczny, np. User, jeśli masz własną klasę User
# lub po prostu UUID, jeśli potrzebujesz tylko ID
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    supabase: AsyncClient = Depends(
        get_supabase_service_client
    ),  # Wstrzyknij klienta Supabase
) -> (
    UserInfo
):  # Zmień UserInfo na faktyczny typ zwracany przez Supabase lub tylko UUID4
    """
    Dependency function to get the current authenticated user from the JWT token.
    Verifies the token using Supabase client.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Użyj klienta Supabase do weryfikacji tokenu i pobrania użytkownika
        # Dostosuj do metody w supabase-py (może być get_session lub get_user)
        response = await supabase.auth.get_user(token)
        user = response.user
        if user is None:
            raise credentials_exception
        # Zwróć obiekt użytkownika lub tylko jego ID, jeśli to wystarczy
        # Mapowanie do UserInfo może być konieczne
        # return UserInfo(**user.dict()) # Dostosuj do atrybutów zwracanego obiektu
        return UserInfo.model_validate(user.dict())  # Pydantic v2

    except AuthApiError as e:  # Przechwyć błędy związane z sesją/tokenem Supabase
        print(f"Auth error: {e}")  # Logowanie
        raise credentials_exception
    except Exception as e:  # Inne nieoczekiwane błędy
        print(f"Unexpected error in get_current_user: {e}")  # Logowanie
        raise credentials_exception


# Zależność do uzyskania samego ID użytkownika
async def get_current_user_id(
    current_user: UserInfo = Depends(get_current_user),
) -> UUID4:
    """Dependency to get only the current user's ID."""
    return current_user.id
