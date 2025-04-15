# src/schemas/pagination.py
# (Separate file for pagination related schemas if desired)
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Schema for pagination query parameters, used as a dependency."""

    page: int = Field(1, ge=1, description="Page number to retrieve (starts at 1).")
    page_size: int = Field(
        20, ge=1, le=100, description="Number of items per page (between 1 and 100)."
    )


# Note: PaginatedLinkResponse is defined within schemas/link.py in this example,
# but could also be moved here if preferred.
