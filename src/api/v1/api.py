# src/api/v1/api.py

from fastapi import APIRouter

# Import endpoint routers for different API resource types
from src.api.v1.endpoints import links
from src.api.v1.endpoints import rules
from src.api.v1.endpoints import auth

# Create the main router for the v1 version of the API
api_v1_router = APIRouter()

# Include the router for link management endpoints
# All routes defined in 'links.router' will be prefixed with '/links'
# and tagged 'Links' in the OpenAPI documentation.
api_v1_router.include_router(links.router, prefix="/links", tags=["Links"])

# Include the router for rule management endpoints
# These routes are nested under specific links, hence the prefix '/links/{link_id}/rules'
# Tagged as 'Rules' in the OpenAPI documentation.
api_v1_router.include_router(
    rules.router, prefix="/links/{link_id}/rules", tags=["Rules"]
)

# Include the router for authentication-related endpoints (login, register, etc.)
# All routes defined in 'auth.router' will be prefixed with '/auth'
# and tagged 'Authentication' in the OpenAPI documentation.
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Note: Statistics-related endpoints are currently included within the links router (links.router).
