# src/schemas/auth.py
from pydantic import BaseModel, EmailStr, Field, UUID4, ConfigDict
from typing import Optional, Any  # Import Any if using extra='allow'
from datetime import datetime  # Import if needed for UserInfo


class UserLogin(BaseModel):
    """Schema for user login request body."""

    email: EmailStr
    password: str


class UserRegister(BaseModel):
    """Schema for user registration request body."""

    email: EmailStr
    password: str = Field(
        ..., min_length=8, description="Password must be at least 8 characters long."
    )
    # Add more complex password validation rules here if needed using custom validators


# --- User Info DTOs (used in responses) ---
class UserInfo(BaseModel):
    """Represents user information returned by Supabase upon successful login."""

    id: UUID4
    aud: str  # Audience
    role: str  # e.g., 'authenticated'
    email: Optional[EmailStr] = None
    # Add other relevant fields from Supabase user object if needed
    # phone: Optional[str] = None
    # created_at: Optional[datetime] = None
    # confirmed_at: Optional[datetime] = None
    # email_confirmed_at: Optional[datetime] = None
    # last_sign_in_at: Optional[datetime] = None
    # updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserInfoMinimal(BaseModel):
    """Minimal user info returned upon registration (might differ from login)."""

    id: UUID4
    aud: Optional[str] = (
        None  # May not always be present depending on Supabase version/response
    )
    role: Optional[str] = None
    email: Optional[EmailStr] = None
    # created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# --- Token/Session Response DTOs ---
class TokenResponse(BaseModel):
    """Schema for the response after successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None  # Provided by Supabase? Check response.
    refresh_token: Optional[str] = None  # Provided by Supabase? Check response.
    user: UserInfo

    # If Supabase response might contain extra fields you don't map
    # model_config = ConfigDict(
    #     extra='allow'
    # )


class UserRegistrationResponse(BaseModel):
    """Schema for the response after successful registration."""

    user: UserInfoMinimal
    # session: Optional[Any] = None # Supabase might return a session object or null
    # Define a Session model if needed, or use Any/dict
