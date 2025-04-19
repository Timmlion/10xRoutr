# src/schemas/link.py
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    ConfigDict,
    UUID4,
    HttpUrl,
    ValidationInfo,  # Zmieniono z FieldValidationInfo
)
from typing import Optional, List
from datetime import datetime
import re


# --- Base Model ---
# Contains fields common across different Link operations, but might not be directly used
# if create/update/response schemas diverge significantly.
class LinkBase(BaseModel):
    alias: str
    # Użycie typu HttpUrl jest dobre dla walidacji przychodzących danych,
    # ale pamiętaj, że do bazy danych zapisujemy string (jak w LinkService)
    default_url: Optional[HttpUrl | None] = None


# --- Command Models (Input) ---
class LinkCreate(BaseModel):
    """
    Schema for data required to create a new link.
    Used as request body for POST /links.
    """

    alias: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9-]+$",  # Dodano pattern dla prostszej walidacji
        description="Unique path segment for the link URL (e.g., 'my-campaign'). Must be 3-64 chars, lowercase letters, numbers, hyphens only.",
    )
    default_url: Optional[HttpUrl | None] = Field(
        None,
        description="Optional fallback URL (must be a valid HTTP/HTTPS URL) if no rules match.",
    )

    # Walidator dla aliasu jest teraz mniej potrzebny dzięki `pattern` w Field,
    # ale zostawiamy go jako przykład lub jeśli chcemy dodać bardziej złożoną logikę.
    @field_validator("alias")
    @classmethod  # Ten walidator nie potrzebuje 'self' ani 'info'
    def validate_alias_format(cls, v: str) -> str:
        """Ensure alias matches the required format."""
        # Walidacja pattern jest już robiona przez Pydantic, ale można dodać inne reguły
        if not re.match(r"^[a-z0-9-]+$", v):  # Redundantne, jeśli pattern działa
            raise ValueError(
                "Alias must contain only lowercase letters, numbers, and hyphens"
            )
        if "--" in v or v.startswith("-") or v.endswith("-"):
            raise ValueError(
                "Alias cannot contain consecutive hyphens or start/end with a hyphen."
            )
        # Można dodać sprawdzanie listy zastrzeżonych słów itp.
        return v


class LinkUpdate(BaseModel):
    """
    Schema for data allowed when updating a link.
    Used as request body for PATCH /links/{link_id}.
    Only default_url is mutable in MVP. All fields optional for PATCH.
    """

    # Pamiętaj, że do DB i tak zapisujemy string
    default_url: Optional[HttpUrl | None] = Field(
        None,  # Zmieniono opis - default=None oznacza, że pole jest opcjonalne
        description="Optional fallback URL (must be a valid HTTP/HTTPS URL or null to clear).",
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
    # Dane z DB przychodzą jako string, Pydantic spróbuje sparsować do HttpUrl
    default_url: Optional[HttpUrl | None] = None
    total_clicks: int
    created_at: datetime
    updated_at: datetime

    # Konfiguracja Pydantic v2+ dla trybu ORM (from_attributes)
    model_config = ConfigDict(from_attributes=True)


# --- Pagination Schema ---
class PaginatedLinkResponse(BaseModel):
    """
    Schema for paginated list responses for links.
    Used as response body for GET /links.
    """

    items: List[LinkResponse]
    total: int = Field(description="Total number of items available across all pages.")
    page: int = Field(description="Current page number.")
    page_size: int = Field(description="Number of items per page.")
