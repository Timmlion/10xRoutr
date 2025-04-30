# src/api/v1/endpoints/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import (
    OAuth2PasswordRequestForm,
)  # Standard FastAPI class for handling username/password form data

# Import Pydantic models (Data Transfer Objects) for request and response validation/serialization
from src.schemas.auth import (
    TokenResponse,
    UserRegister,
    UserRegistrationResponse,
    UserLogin,
)

# Import the authentication service and custom exceptions
from src.services.auth_service import AuthService
from src.services.custom_exceptions import (
    AuthenticationFailedException,
    EmailExistsException,
    PasswordPolicyException,
    AuthServiceException,
)

# Import dependency injector function
from src.api.deps import get_auth_service
import traceback  # Used for printing detailed exception information for debugging

# Create an API router instance for authentication endpoints
router = APIRouter()


# --- Endpoint POST /auth/login ---
@router.post(
    "/login",
    response_model=TokenResponse,  # Defines the expected response structure (access token)
    summary="Login for Access Token",
    description="Authenticates a user with email and password and returns an access token.",
    tags=["Authentication"],  # Tag for OpenAPI documentation grouping
)
async def login_for_access_token(
    # Depends() injects the form data parsed by OAuth2PasswordRequestForm.
    # Note: OAuth2PasswordRequestForm expects 'username' and 'password' fields in the form data.
    form_data: OAuth2PasswordRequestForm = Depends(),
    # Depends() injects an instance of AuthService using the get_auth_service dependency.
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Handles user login using the standard OAuth2 password flow.
    Accepts 'username' (which is treated as email here) and 'password' via form data.
    Returns a JWT access token upon successful authentication.
    """
    print(f"Received login attempt for user: {form_data.username}")
    try:
        # Create a UserLogin Pydantic model instance from the form data for validation and clear structure.
        login_credentials = UserLogin(
            email=form_data.username,  # Map form's 'username' to 'email' field
            password=form_data.password,
        )
        # Call the authentication service to perform the login logic
        token_response = await auth_service.login_user(login_data=login_credentials)
        return token_response  # Return the TokenResponse containing the access token
    except AuthenticationFailedException as e:
        # Handle specific case where credentials are wrong
        print(f"[AUTH FAILED] Login failed for {form_data.username}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.detail,
            headers={
                "WWW-Authenticate": "Bearer"
            },  # Standard header for 401 bearer auth errors
        )
    except AuthServiceException as e:
        # Handle errors originating from the authentication service itself (e.g., Supabase issues)
        print(
            f"[AUTH ERROR] Service error during login for {form_data.username}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication service error: {e.detail}",
        )
    except Exception as e:
        # Catch any other unexpected errors during the login process
        print(f"[ERROR] Unexpected error during login for {form_data.username}: {e}")
        traceback.print_exc()  # Print full traceback for debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred during login.",
        )


# --- Endpoint POST /auth/register ---
@router.post(
    "/register",
    response_model=UserRegistrationResponse,  # Defines the success response (user ID and email)
    status_code=status.HTTP_201_CREATED,  # Standard HTTP status code for successful resource creation
    summary="Register New User",
    description="Creates a new user account using email and password.",
    tags=["Authentication"],
)
async def register_new_user(
    user_data: UserRegister,  # Expects JSON request body matching the UserRegister schema
    auth_service: AuthService = Depends(
        get_auth_service
    ),  # Inject AuthService instance
):
    """Handles new user registration."""
    print(f"Received registration request for email: {user_data.email}")
    try:
        # Call the authentication service to handle user registration logic
        registration_response = await auth_service.register_user(user_data)
        return registration_response  # Return the UserRegistrationResponse on success
    except EmailExistsException as e:
        # Handle case where the email address is already registered
        print(f"[CONFLICT] Registration failed, email exists: {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,  # Use 409 Conflict for existing resource
            detail=e.detail,  # Use the specific error message from the exception
        )
    except PasswordPolicyException as e:
        # Handle case where the provided password doesn't meet complexity requirements
        print(
            f"[BAD REQUEST] Registration failed, password policy violation: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,  # 400 Bad Request or 422 Unprocessable Entity are appropriate
            detail=e.detail,
        )
    except AuthServiceException as e:
        # Handle errors originating from the authentication service during registration
        print(
            f"[AUTH ERROR] Service error during registration for {user_data.email}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication service error: {e.detail}",
        )
    except Exception as e:
        # Catch any other unexpected errors during registration
        print(
            f"[ERROR] Unexpected error during registration for {user_data.email}: {e}"
        )
        traceback.print_exc()  # Print full traceback for debugging
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred during registration.",
        )
