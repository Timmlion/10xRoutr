# src/api/v1/api.py

from fastapi import APIRouter

# Importuj routery z poszczególnych plików endpointów
from src.api.v1.endpoints import (
    links,
)  # Załóżmy, że w przyszłości będą inne, np. rules, auth, stats

# Główny router dla wersji v1 API
api_v1_router = APIRouter()

# Dołącz router dla linków pod prefiksem /links
api_v1_router.include_router(links.router, prefix="/links", tags=["Links"])
# Dołącz inne routery w przyszłości
# api_v1_router.include_router(rules.router, prefix="/links/{link_id}/rules", tags=["Rules"])
# api_v1_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
# api_v1_router.include_router(stats.router, prefix="/links/{link_id}/stats", tags=["Statistics"])
