# src/schemas/link.py
from pydantic import BaseModel, Field, field_validator, ConfigDict, UUID4, HttpUrl
from typing import Optional, List
from datetime import datetime
import re


# --- Base Model ---
# Contains fields common across different Link operations, but might not be directly used
# if create/update/response schemas diverge significantly.
class LinkBase(BaseModel):
    alias: str
    default_url: Optional[HttpUrl | None] = (
        None  # Use Pydantic's HttpUrl for validation
    )


# --- Command Models (Input) ---


class LinkCreate(BaseModel):
    """
    Schema for data required to create a new link.
    Used as request body for POST /links.
    """

    alias: str = Field(
        ...,  # Ellipsis indicates required field
        min_length=3,
        max_length=64,
        description="Unique path segment for the link URL (e.g., 'my-campaign'). Must be 3-64 chars, lowercase letters, numbers, hyphens only.",
    )
    default_url: Optional[HttpUrl | None] = Field(
        None,
        description="Optional fallback URL (must be a valid HTTP/HTTPS URL) if no rules match.",
    )

    @field_validator("alias")
    def validate_alias_format(cls, v: str) -> str:
        """Validate alias format against database CHECK constraint."""
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "Alias must contain only lowercase letters, numbers, and hyphens"
            )
        return v


class LinkUpdate(BaseModel):
    """
    Schema for data allowed when updating a link.
    Used as request body for PATCH /links/{link_id}.
    Only default_url is mutable in MVP. All fields optional for PATCH.
    """

    default_url: Optional[HttpUrl | None] = Field(
        # No default ellipsis means it's optional. Explicit None can be sent to clear the field.
        description="Optional fallback URL (must be a valid HTTP/HTTPS URL or null to clear)."
    )
    # Alias is intentionally omitted as it's immutable post-creation.


# --- Data Transfer Objects (Output) ---


class LinkResponse(BaseModel):
    """
    Schema for representing a link when returned by the API.
    Used as response body for GET /links/{link_id}, POST /links, PATCH /links/{link_id}.
    """

    id: UUID4
    user_id: UUID4
    alias: str
    default_url: Optional[HttpUrl | None] = None
    total_clicks: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)  # Enable ORM mode (Pydantic v2+)
    # Pydantic v1 equivalent:
    # class Config:
    #     orm_mode = True


# --- Pagination Schema (used by List Links) ---
# Often placed in a separate pagination.py or directly here if only used for links


class PaginatedLinkResponse(BaseModel):
    """
    Schema for paginated list responses for links.
    Used as response body for GET /links.
    """

    items: List[LinkResponse]
    total: int = Field(description="Total number of items available across all pages.")
    page: int = Field(description="Current page number.")
    page_size: int = Field(description="Number of items per page.")
