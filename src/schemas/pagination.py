# src/schemas/pagination.py
# This module defines Pydantic models related to pagination parameters.

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """
    Represents and validates pagination query parameters.

    This model is typically used as a FastAPI dependency to automatically parse,
    validate, and provide default values for 'page' and 'page_size' query parameters
    in list endpoints.
    """

    # The requested page number. Defaults to 1 if not provided. Must be 1 or greater.
    page: int = Field(
        default=1,
        ge=1,  # ge=1 means "greater than or equal to 1"
        description="Page number to retrieve (starts at 1).",
    )

    # The number of items requested per page. Defaults to 20. Must be between 1 and 100 (inclusive).
    page_size: int = Field(
        default=20,
        ge=1,  # Minimum items per page
        le=100,  # Maximum items per page (adjust as needed for performance/policy)
        description="Number of items per page (between 1 and 100).",
    )


# Note: Response models that include pagination results (like a 'PaginatedLinkResponse'
# containing 'items', 'total', 'page', 'page_size') might be defined in their
# respective feature schema files (e.g., schemas/link.py) or grouped together elsewhere.
