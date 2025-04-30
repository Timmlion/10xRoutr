# src/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field, UUID4, ConfigDict
from typing import Optional, Any
from datetime import (
    datetime,
)  # Keep import if using datetime fields in UserInfo/UserInfoMinimal


class UserLogin(BaseModel):
    """Schema defining the expected structure for user login requests."""

    email: EmailStr  # Ensures the email field is a valid email format.
    password: str


class UserRegister(BaseModel):
    """Schema defining the expected structure for user registration requests."""

    email: EmailStr  # Ensures the email field is a valid email format.
    # Field validation ensures password meets minimum length requirement.
    password: str = Field(
        ...,  # ... indicates the field is required
        min_length=8,
        description="Password must be at least 8 characters long.",
    )
    # Custom Pydantic validators can be added here for more complex password rules.


# --- User Information Data Transfer Objects (DTOs) ---
# These models represent user data, typically used in responses.


class UserInfo(BaseModel):
    """
    Represents the structure of user information often returned by
    Supabase after successful authentication or user retrieval.
    Maps relevant fields from the Supabase User object.
    """

    id: UUID4  # User's unique identifier (UUID).
    aud: str  # Audience claim, typically 'authenticated'.
    role: str  # User role, e.g., 'authenticated'.
    email: Optional[EmailStr] = None  # User's email, may not always be present.

    # Add other relevant fields from the Supabase user object if needed for your application.
    # Examples:
    # phone: Optional[str] = None
    # created_at: Optional[datetime] = None
    # confirmed_at: Optional[datetime] = None # Email/Phone confirmation timestamp
    # email_confirmed_at: Optional[datetime] = None
    # last_sign_in_at: Optional[datetime] = None
    # updated_at: Optional[datetime] = None

    # Pydantic v2 configuration to enable creating the model from object attributes (like Supabase user object).
    model_config = ConfigDict(from_attributes=True)


class UserInfoMinimal(BaseModel):
    """
    Represents a potentially minimal set of user information, often returned
    immediately after registration before full details might be available or needed.
    """

    id: UUID4
    # Fields like 'aud' and 'role' might be optional or absent in some Supabase responses,
    # particularly immediately post-registration.
    aud: Optional[str] = None
    role: Optional[str] = None
    email: Optional[EmailStr] = None
    # created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# --- Token and Session Response DTOs ---


class TokenResponse(BaseModel):
    """
    Schema for the response payload after a successful user login,
    typically containing JWT access tokens and user information.
    Follows common OAuth2/JWT patterns.
    """

    access_token: (
        str  # The JWT access token used for authenticating subsequent requests.
    )
    token_type: str = "bearer"  # Standard token type, usually 'bearer'.
    # Optional fields that Supabase might include in its session response.
    expires_in: Optional[int] = None  # Token expiry time in seconds.
    refresh_token: Optional[str] = None  # Token used to obtain a new access token.
    user: UserInfo  # Includes detailed information about the logged-in user.

    # If the actual Supabase response includes extra fields not defined here,
    # you can uncomment the following config to ignore them instead of raising an error.
    # model_config = ConfigDict(extra='ignore')


class UserRegistrationResponse(BaseModel):
    """
    Schema for the response payload after a successful user registration.
    """

    user: UserInfoMinimal  # Contains the basic information of the newly created user.
    # Supabase might return a 'session' object (containing tokens) or null upon registration.
    # Define a detailed Session model if you need to parse it, or use Any/dict for flexibility.
    # session: Optional[Any] = None
