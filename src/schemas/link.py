# src/schemas/link.py
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    ConfigDict,
    UUID4,  # Represents a UUID type
    HttpUrl,  # Represents and validates HTTP/HTTPS URLs
    ValidationInfo,
)
from typing import Optional, List
from datetime import datetime
import re  # Regular expression module for alias validation


# --- Base Model (Potentially for Inheritance) ---
# Defines common fields that might appear in multiple Link schemas.
class LinkBase(BaseModel):
    alias: str
    # Use HttpUrl for input validation; the database typically stores this as a string.
    default_url: Optional[HttpUrl | None] = None


# --- Command Models (Input Schemas) ---
# These models define the expected structure for incoming request data (e.g., request bodies).


class LinkCreate(BaseModel):
    """
    Schema for data required to create a new link.
    Used as the request body structure for POST operations (e.g., /api/v1/links).
    """

    alias: str = Field(
        ...,  # Ellipsis (...) indicates this field is required.
        min_length=3,
        max_length=64,
        # Regex pattern for basic alias format validation (lowercase letters, numbers, hyphens).
        pattern=r"^[a-z0-9-]+$",
        description="Unique path segment for the link URL (e.g., 'my-campaign'). Must be 3-64 chars, lowercase letters, numbers, hyphens only.",
    )
    default_url: Optional[HttpUrl | None] = Field(
        None,  # Default value is None if not provided.
        description="Optional fallback URL. Must be a valid HTTP/HTTPS URL if provided.",
    )

    @field_validator("alias")
    @classmethod
    def validate_alias_format_advanced(cls, v: str) -> str:
        """
        Performs additional validation checks on the alias beyond the basic regex pattern.
        Ensures no consecutive hyphens and no leading/trailing hyphens.
        Note: The basic pattern `^[a-z0-9-]+$` is already checked by Pydantic via the `pattern` argument in `Field`.
        This validator adds more specific constraints.
        """
        # Redundant check for basic format, but ensures it's handled if pattern fails or is removed.
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "Alias must contain only lowercase letters, numbers, and hyphens"
            )
        # Check for disallowed hyphen usage.
        if "--" in v or v.startswith("-") or v.endswith("-"):
            raise ValueError(
                "Alias cannot contain consecutive hyphens or start/end with a hyphen."
            )
        # Potentially add checks against a list of reserved words here.
        return v


class LinkUpdate(BaseModel):
    """
    Schema for data allowed when updating an existing link via PATCH.
    All fields are optional, allowing partial updates.
    Currently, only `default_url` is designed to be mutable in the application logic.
    """

    # Allows setting the default_url to a valid URL or clearing it by providing `null`.
    default_url: Optional[HttpUrl | None] = None


# --- Data Transfer Objects (Output Schemas) ---
# These models define the structure of data returned by the API (e.g., response bodies).


class LinkResponse(BaseModel):
    """
    Schema representing a routr link as returned by the API.
    Includes core link attributes and metadata like IDs and timestamps.
    """

    id: UUID4  # The unique identifier for the link.
    user_id: UUID4  # The identifier of the user who owns the link.
    alias: str  # The unique alias (path segment) for the link.
    # Pydantic attempts to parse the string value from the DB into an HttpUrl object.
    default_url: Optional[HttpUrl | None] = None  # The fallback URL, if set.
    total_clicks: int  # The total number of recorded clicks for this link.
    created_at: datetime  # Timestamp when the link was created.
    updated_at: datetime  # Timestamp when the link was last updated.

    # Enable ORM mode (from_attributes=True in Pydantic v2) to allow creating
    # this schema directly from database model instances (e.g., SQLAlchemy models).
    model_config = ConfigDict(from_attributes=True)


# --- Pagination Schema ---


class PaginatedLinkResponse(BaseModel):
    """
    Schema for responses containing a paginated list of links.
    Includes the list of items for the current page and pagination metadata.
    """

    items: List[LinkResponse]  # The list of link objects for the current page.
    total: int = Field(description="Total number of items available across all pages.")
    page: int = Field(description="Current page number (starts at 1).")
    page_size: int = Field(description="Number of items requested per page.")
