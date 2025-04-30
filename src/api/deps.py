# src/api/deps.py
import uuid
from fastapi import Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer
from supabase import AsyncClient
from gotrue.errors import AuthApiError  # Specific Supabase auth error
from pydantic import UUID4
from fastapi.templating import Jinja2Templates
from pathlib import Path
from functools import lru_cache  # Used for caching template instance

# Import models and schemas used in dependencies
from src.schemas.auth import UserInfo
from src.schemas.pagination import PaginationParams

# Import functions that provide initialized Supabase clients
from src.db.supabase_client import (
    get_supabase_user_client,
    get_supabase_service_client,
)

# Import application services that dependencies will provide
from src.services.link_service import LinkService
from src.services.rule_service import RuleService
from src.services.auth_service import AuthService
from src.services.redirection_service import RedirectionService

# --- OAuth2 Password Bearer Scheme ---
# Defines the security scheme for API endpoints requiring authentication.
# Specifies the URL where clients should send credentials to obtain a token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# --- Supabase Client Dependencies ---
def supabase_service_dependency() -> AsyncClient:
    """Provides an instance of the Supabase client using the service role key."""
    return get_supabase_service_client()


def supabase_user_dependency() -> AsyncClient:
    """
    Provides an instance of the Supabase client using the anonymous/user role key.
    This client is typically used for operations that depend on user authentication context.
    """
    return get_supabase_user_client()


def supabase_auth_dependency() -> AsyncClient:
    """
    Provides an instance of the Supabase client specifically for authentication operations.
    Currently points to the same client as supabase_user_dependency.
    """
    return get_supabase_user_client()


# --- Jinja2 Templates Dependency ---
# Calculate the base directory of the project (assuming deps.py is in src/api/deps)
# Goes up three levels: deps.py -> api -> src -> project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent


@lru_cache()  # Cache the result: Jinja2Templates initialization is relatively expensive
def get_templates() -> Jinja2Templates:
    """
    Dependency function that initializes and returns a Jinja2Templates instance.
    The instance is configured to look for templates in the 'src/templates' directory.
    Uses lru_cache to avoid re-initializing on every request.
    """
    templates_dir = (
        BASE_DIR / "src" / "templates"
    )  # Construct the path to the templates directory
    print(f"Initializing Jinja2Templates with directory: {templates_dir}")
    return Jinja2Templates(directory=str(templates_dir))


# --- Authentication Dependencies ---
async def get_current_user(
    token: str = Depends(
        oauth2_scheme
    ),  # Extracts the token from the Authorization header
    supabase: AsyncClient = Depends(supabase_auth_dependency),  # Gets the auth client
) -> UserInfo:
    """
    Validates the provided Bearer token using Supabase auth and returns user information.
    Raises HTTPException(401) if the token is invalid, expired, or the user is not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer"
        },  # Standard header for bearer auth challenges
    )
    try:
        # Attempt to retrieve user information using the provided token
        response = await supabase.auth.get_user(token)
        if response is None or response.user is None:
            print("Token verification failed or user not found.")
            raise credentials_exception

        user = response.user
        # Ensure the user object retrieved has an ID
        if user.id is None:
            print("Token verified but user data is incomplete (missing ID).")
            raise credentials_exception

        # Validate and parse the user data into the UserInfo schema
        return UserInfo.model_validate(user.model_dump())
    except AuthApiError as e:
        # Handle specific Supabase authentication errors
        print(f"Auth API error verifying token: {e}")
        raise credentials_exception
    except Exception as e:
        # Catch any other unexpected errors during token validation
        print(f"Unexpected error in get_current_user: {e}")
        raise credentials_exception


async def get_current_user_id(
    current_user: UserInfo = Depends(
        get_current_user
    ),  # Depends on the validated user info
) -> uuid.UUID:
    """
    Dependency that simply extracts and returns the UUID user ID from the
    validated UserInfo object obtained from get_current_user.
    Includes a type check for robustness, although Pydantic validation in get_current_user
    should generally ensure this.
    """
    if not isinstance(current_user.id, uuid.UUID):
        # This check acts as a safeguard against unexpected data types
        print(
            f"Error: User ID '{current_user.id}' is not a valid UUID object after validation."
        )
        raise HTTPException(
            status_code=500, detail="Internal error: Invalid user ID type."
        )
    return current_user.id


# --- Pagination Dependency ---
async def pagination_dependency(
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
) -> PaginationParams:
    """
    Parses and validates pagination parameters (page, page_size) from query parameters.
    Provides default values and enforces constraints (min/max values).
    Returns a PaginationParams object or raises HTTPException(422) on validation errors.
    """
    try:
        # Pydantic validation happens implicitly here if PaginationParams uses validators
        # or explicitly via model_validate if needed, but defaults/Query handle basic checks.
        return PaginationParams(page=page, page_size=page_size)
    except (
        ValueError
    ) as e:  # Catch potential Pydantic validation errors if complex validation exists
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid pagination parameters: {e}",
        )


# --- Service Dependencies ---
# These functions instantiate and provide service classes, injecting the required
# Supabase client dependency into them.


def get_link_service(
    supabase: AsyncClient = Depends(supabase_user_dependency),
) -> LinkService:
    """Provides an instance of LinkService, initialized with the user-context Supabase client."""
    return LinkService(supabase_client=supabase)


def get_rule_service(
    supabase: AsyncClient = Depends(supabase_user_dependency),
) -> RuleService:
    """Provides an instance of RuleService, initialized with the user-context Supabase client."""
    return RuleService(supabase_client=supabase)


def get_auth_service(
    supabase: AsyncClient = Depends(supabase_auth_dependency),
) -> AuthService:
    """Provides an instance of AuthService, initialized with the Supabase auth client."""
    return AuthService(supabase_client=supabase)


def get_redirection_service(
    supabase: AsyncClient = Depends(supabase_service_dependency),
) -> RedirectionService:
    """
    Provides an instance of RedirectionService, initialized with the service-role Supabase client.
    This is often used for public-facing redirection logic that shouldn't depend on user auth state.
    """
    return RedirectionService(supabase_client=supabase)
