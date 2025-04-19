# src/main.py

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

# Usunięto nieużywane: import logging (bo używamy print), logger = logging.getLogger(__name__)
# Usunięto nieużywane: @asynccontextmanager, lifespan

# Import konfiguracji
from src.core.config import settings  # Ten import jest teraz poprawny

# Import głównego routera API
from src.api.v1.api import api_v1_router

# Import serwisu i wyjątków dla endpointu przekierowania
from src.services.redirection_service import (
    RedirectionService,
    RedirectionAction,
    LinkNotFoundException,
)

# Import zależności i poprawiony import AsyncClient
from src.api.deps import (
    get_supabase_service_client,
)  # Ta funkcja MUSI zwracać AsyncClient
from supabase import AsyncClient  # <<< POPRAWIONY IMPORT

# --- Inicjalizacja Aplikacji FastAPI ---
app = FastAPI(
    title="routr API - MVP",
    version="0.1.0",
    description="API for managing dynamic redirection links.",
)

# --- Montowanie Plików Statycznych ---
# app.mount("/static", StaticFiles(directory="src/static"), name="static")

# --- Konfiguracja Szablonów Jinja2 ---
templates = Jinja2Templates(directory="src/templates")

# --- Dołączenie Routerów API ---
app.include_router(api_v1_router, prefix="/api/v1")

# --- Endpoint Publicznego Przekierowania ---


# Zależność wstrzykująca serwis przekierowań
# Typowanie `supabase: AsyncClient` jest teraz poprawne dzięki zmienionemu importowi
def get_redirection_service(
    supabase: AsyncClient = Depends(
        get_supabase_service_client
    ),  # Zależność musi zwrócić poprawny AsyncClient
) -> RedirectionService:
    """Dependency to get RedirectionService instance."""
    # Pamiętaj, że get_supabase_service_client musi faktycznie tworzyć
    # i zwracać instancję AsyncClient z biblioteki supabase
    return RedirectionService(supabase_client=supabase)


@app.get(
    "/{alias_path:path}",
    summary="Handle Link Redirection",
    description="Public endpoint that processes a routr link alias and redirects the user based on defined rules.",
    tags=["Public Redirection"],
    include_in_schema=False,
)
async def handle_redirection(
    alias_path: str,
    request: Request,
    redirection_service: RedirectionService = Depends(get_redirection_service),
):
    """
    Processes the alias path, evaluates rules, and performs redirection or serves HTML.
    Uses the service_role key for database access to bypass RLS.
    """
    print(f"Processing redirection request for alias: {alias_path}")  # Logowanie MVP
    try:
        action, value = await redirection_service.process_redirection(alias_path)

        if (
            action == RedirectionAction.REDIRECT_URL
            or action == RedirectionAction.REDIRECT_DEFAULT
        ):
            print(f"Redirecting '{alias_path}' to URL: {value}")  # Logowanie MVP
            # Używamy str() dla pewności przy konwersji z potencjalnego typu Pydantic
            return RedirectResponse(url=str(value), status_code=status.HTTP_302_FOUND)
        elif action == RedirectionAction.SERVE_HTML:
            print(f"Serving HTML content for alias: {alias_path}")  # Logowanie MVP
            return HTMLResponse(content=value, status_code=status.HTTP_200_OK)
        elif action == RedirectionAction.REDIRECT_GLOBAL_FALLBACK:
            print(  # Logowanie MVP
                f"No matching rule or default URL for alias '{alias_path}'. Redirecting to global fallback."
            )
            # <<< POPRAWIONA LINIA: Konwersja HttpUrl na string
            return RedirectResponse(
                url=str(settings.GLOBAL_FALLBACK_URL), status_code=status.HTTP_302_FOUND
            )
        else:
            print(  # Logowanie MVP
                f"ERROR: Invalid redirection action '{action}' returned for alias: {alias_path}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal configuration error in redirection logic.",
            )

    except LinkNotFoundException:
        print(f"Link alias not found: {alias_path}")  # Logowanie MVP
        # Zwracamy 404 zgodnie z planem
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested link alias was not found.",
        )
    except Exception as e:
        # Logujemy błąd i zwracamy 500
        print(
            f"ERROR processing redirection for alias '{alias_path}': {e}"
        )  # Logowanie MVP
        # W produkcji tu byłby logger.exception(e) dla stack trace
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing the link.",
        )


# --- Opcjonalny Endpoint Główny (/) ---
@app.get(
    "/",
    summary="Root Endpoint",
    description="Provides a landing page or redirects to the main application interface.",
    tags=["General"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def read_root(request: Request):
    """Serves the main landing page or redirects."""
    return HTMLResponse(
        "<html><body><h1>Welcome to routr!</h1><p>API Docs at <a href='/docs'>/docs</a></p></body></html>"
    )


# --- Uruchomienie (dla lokalnego developmentu) ---
if __name__ == "__main__":
    import uvicorn

    print("Starting Uvicorn server for local development...")  # Logowanie MVP
    # <<< POPRAWKA: Podaj pełną ścieżkę importu do aplikacji
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
