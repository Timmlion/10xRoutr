# src/api/v1/endpoints/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

# Import modeli Pydantic (DTOs)
from src.schemas.auth import (
    TokenResponse,
    UserRegister,
    UserRegistrationResponse,
    UserLogin,
)  # <<< DODAJ UserLogin

# Import serwisu i wyjątków
from src.services.auth_service import AuthService
from src.services.custom_exceptions import (
    AuthenticationFailedException,
    EmailExistsException,
    PasswordPolicyException,
    AuthServiceException,
)

# Import zależności
from src.api.deps import get_auth_service
import traceback  # <<< Dodaj, jeśli chcesz używać print_exc()

router = APIRouter()


# --- Endpoint POST /auth/login ---
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login for Access Token",
    description="Authenticates a user with email and password and returns an access token.",
    tags=["Authentication"],
)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Handles user login using OAuth2 password flow.
    Accepts form data: username (mapped to email) and password.
    """
    print(f"Received login attempt for user: {form_data.username}")
    try:
        # <<< POPRAWKA: Utwórz instancję UserLogin
        login_credentials = UserLogin(
            email=form_data.username, password=form_data.password
        )
        # Przekaż instancję modelu Pydantic do serwisu
        token_response = await auth_service.login_user(login_data=login_credentials)
        return token_response
    except AuthenticationFailedException as e:
        print(f"[AUTH FAILED] Login failed for {form_data.username}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except AuthServiceException as e:
        print(
            f"[AUTH ERROR] Service error during login for {form_data.username}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication service error: {e.detail}",
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error during login for {form_data.username}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred during login.",
        )


# --- Endpoint POST /auth/register (Opcjonalny, ale przydatny) ---
@router.post(
    "/register",
    response_model=UserRegistrationResponse,  # Zwraca ID i email użytkownika
    status_code=status.HTTP_201_CREATED,
    summary="Register New User",
    description="Creates a new user account.",
    tags=["Authentication"],
)
async def register_new_user(
    user_data: UserRegister,  # Oczekuje JSON z email i password
    auth_service: AuthService = Depends(get_auth_service),
):
    """Handles new user registration."""
    print(f"Received registration request for email: {user_data.email}")
    try:
        registration_response = await auth_service.register_user(user_data)
        return registration_response
    except EmailExistsException as e:
        print(f"[CONFLICT] Registration failed, email exists: {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.detail,  # Użyj komunikatu z wyjątku
        )
    except PasswordPolicyException as e:
        print(
            f"[BAD REQUEST] Registration failed, password policy violation: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,  # Lub 422 Unprocessable Entity
            detail=e.detail,
        )
    except AuthServiceException as e:
        print(
            f"[AUTH ERROR] Service error during registration for {user_data.email}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication service error: {e.detail}",
        )
    except Exception as e:
        print(
            f"[ERROR] Unexpected error during registration for {user_data.email}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred during registration.",
        )
