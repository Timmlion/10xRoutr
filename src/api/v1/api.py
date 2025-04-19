# src/api/v1/api.py

from fastapi import APIRouter

# Importuj moduły links i rules z pakietu endpoints
from src.api.v1.endpoints import links
from src.api.v1.endpoints import rules
from src.api.v1.endpoints import auth  # <<< ODKOMENTOWANO IMPORT

# Główny router dla wersji v1 API
api_v1_router = APIRouter()

# Dołącz router dla linków
api_v1_router.include_router(links.router, prefix="/links", tags=["Links"])

# Dołącz router dla reguł
api_v1_router.include_router(
    rules.router, prefix="/links/{link_id}/rules", tags=["Rules"]
)

# Dołącz router dla autentykacji
api_v1_router.include_router(
    auth.router, prefix="/auth", tags=["Authentication"]
)  # <<< ODKOMENTOWANO INCLUDE

# Endpointy statystyk są w links.router
