# src/main.py

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging  # Dodajemy logowanie

# Import konfiguracji
from src.core.config import settings

# Import głównego routera API
from src.api.v1.api import api_v1_router

# Import serwisu i wyjątków dla endpointu przekierowania
from src.services.redirection_service import (
    RedirectionService,
    RedirectionAction,
    LinkNotFoundException,
)  # Załóżmy, że LinkNotFoundException jest zdefiniowane w redirection_service lub custom_exceptions
from src.api.deps import (
    get_supabase_service_client,
)  # Zależność do pobrania klienta Supabase z rolą service
from supabase_py_async import AsyncClient

# --- Konfiguracja Logowania ---
# Prosta konfiguracja logowania, w rzeczywistej aplikacji może być bardziej zaawansowana
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Kontekst Życia Aplikacji (Opcjonalny) ---
# Można tu umieścić inicjalizację/czyszczenie zasobów, np. puli połączeń DB,
# ale dla Supabase klienta inicjalizowanego statycznie, może nie być konieczne.
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     logger.info("Application startup...")
#     # Inicjalizacja zasobów, np. await setup_database_pool()
#     yield
#     logger.info("Application shutdown...")
#     # Czyszczenie zasobów, np. await close_database_pool()

# --- Inicjalizacja Aplikacji FastAPI ---
# app = FastAPI(title="routr API - MVP", version="0.1.0", lifespan=lifespan)
app = FastAPI(
    title="routr API - MVP",
    version="0.1.0",
    description="API for managing dynamic redirection links.",
    # Dodaj kontakt, licencję itp., jeśli potrzebne w dokumentacji OpenAPI
    # contact={"name": "Admin", "email": "admin@example.com"},
    # license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"}
)

# --- Montowanie Plików Statycznych (jeśli nie używasz wyłącznie CDN) ---
# Odkomentuj i dostosuj ścieżkę, jeśli serwujesz własne pliki CSS/JS/obrazy
# app.mount("/static", StaticFiles(directory="src/static"), name="static")

# --- Konfiguracja Szablonów Jinja2 ---
# Zakładamy, że szablony znajdują się w folderze 'src/templates'
templates = Jinja2Templates(directory="src/templates")

# --- Dołączenie Routerów API ---
# Wszystkie endpointy zarządzania będą dostępne pod /api/v1/...
app.include_router(api_v1_router, prefix="/api/v1")

# --- Endpoint Publicznego Przekierowania ---


# Zależność wstrzykująca serwis przekierowań z klientem service_role
# Uwaga: Zależności w FastAPI zazwyczaj działają w kontekście żądania.
# Jeśli RedirectionService nie ma stanu zależnego od żądania, można go
# potencjalnie utworzyć raz przy starcie, ale użycie Depends jest standardem.
def get_redirection_service(
    supabase: AsyncClient = Depends(
        get_supabase_service_client
    ),  # Używa klienta z service_role
) -> RedirectionService:
    """Dependency to get RedirectionService instance."""
    return RedirectionService(supabase_client=supabase)


@app.get(
    "/{alias_path:path}",  # Przechwytuje całą ścieżkę jako alias
    summary="Handle Link Redirection",
    description="Public endpoint that processes a routr link alias and redirects the user based on defined rules.",
    tags=["Public Redirection"],
    include_in_schema=False,  # Zazwyczaj nie chcemy tego w dokumentacji API zarządzania
)
async def handle_redirection(
    alias_path: str,
    request: Request,  # Opcjonalnie: Dostęp do obiektu żądania, np. dla logowania nagłówków
    redirection_service: RedirectionService = Depends(get_redirection_service),
):
    """
    Processes the alias path, evaluates rules, and performs redirection or serves HTML.
    Uses the service_role key for database access to bypass RLS.
    """
    logger.info(f"Processing redirection request for alias: {alias_path}")
    try:
        # Przekaż request, jeśli serwis potrzebuje np. User-Agent dla przyszłych reguł
        action, value = await redirection_service.process_redirection(alias_path)

        if (
            action == RedirectionAction.REDIRECT_URL
            or action == RedirectionAction.REDIRECT_DEFAULT
        ):
            logger.info(f"Redirecting '{alias_path}' to URL: {value}")
            return RedirectResponse(
                url=str(value), status_code=status.HTTP_302_FOUND
            )  # Użyj str() dla pewności
        elif action == RedirectionAction.SERVE_HTML:
            logger.info(f"Serving HTML content for alias: {alias_path}")
            return HTMLResponse(content=value, status_code=status.HTTP_200_OK)
        elif action == RedirectionAction.REDIRECT_GLOBAL_FALLBACK:
            logger.warning(
                f"No matching rule or default URL for alias '{alias_path}'. Redirecting to global fallback."
            )
            return RedirectResponse(
                url=settings.GLOBAL_FALLBACK_URL, status_code=status.HTTP_302_FOUND
            )
        else:
            # Ten przypadek nie powinien wystąpić, jeśli serwis jest poprawnie zaimplementowany
            logger.error(
                f"Invalid redirection action '{action}' returned for alias: {alias_path}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal configuration error in redirection logic.",
            )

    except LinkNotFoundException:  # Przechwyć specyficzny wyjątek z serwisu
        logger.warning(f"Link alias not found: {alias_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested link alias was not found.",
        )
    except Exception as e:
        # Przechwyć wszystkie inne błędy (np. błędy bazy danych z serwisu)
        logger.exception(
            f"Error processing redirection for alias '{alias_path}': {e}"
        )  # Użyj logger.exception dla stack trace
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing the link.",
        )


# --- Opcjonalny Endpoint Główny (/) ---
# Może służyć jako strona powitalna, przekierowanie do logowania lub panelu.
@app.get(
    "/",
    summary="Root Endpoint",
    description="Provides a landing page or redirects to the main application interface.",
    tags=["General"],
    response_class=HTMLResponse,
    include_in_schema=False,  # Ukryj w dokumentacji API zarządzania
)
async def read_root(request: Request):
    """Serves the main landing page or redirects."""
    # Przykład: zwrócenie prostej strony powitalnej z szablonu
    # return templates.TemplateResponse("landing.html", {"request": request, "title": "Welcome to routr"})
    # Lub przekierowanie np. do strony logowania
    # return RedirectResponse(url="/path/to/login")
    return HTMLResponse(
        "<html><body><h1>Welcome to routr!</h1><p>API Docs at <a href='/docs'>/docs</a></p></body></html>"
    )


# --- Uruchomienie (dla lokalnego developmentu, jeśli plik jest uruchamiany bezpośrednio) ---
# W produkcji Uvicorn będzie uruchamiany jako osobny proces wskazujący na ten obiekt `app`
if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Uvicorn server for local development...")
    # Użyj host="0.0.0.0", aby serwer był dostępny z zewnątrz kontenera Docker
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
