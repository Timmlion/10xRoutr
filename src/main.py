# src/main.py (Corrected - Removed UI Auth Checks)
import uvicorn
from fastapi import (
    FastAPI,
    Request,
    Depends,
    HTTPException,
    status,
    APIRouter,
)
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

# Usunięto 'import uuid', bo nie jest już potrzebny bezpośrednio tutaj
from typing import List, Optional  # <<< Dodano Optional, jeśli get_user_id_for_ui wróci
from uuid import UUID  # <<< Import UUID dla type hintów

# Import konfiguracji
from src.core.config import settings

# Import głównego routera API
from src.api.v1.api import api_v1_router

# Import serwisu i wyjątków
from src.services.redirection_service import (
    RedirectionService,
    RedirectionAction,
    LinkNotFoundException,
)

# Usunięto drugi import LinkNotFoundException z custom_exceptions
from src.services.custom_exceptions import (
    LinkNotFoundException,  # Zachowano jeden import
)

# Import funkcji inicjalizującej klientów Supabase
from src.db.supabase_client import init_supabase_clients

# Import zależności
from supabase import AsyncClient
from src.api.deps import (
    get_redirection_service,
    get_templates,
    get_link_service,
    # Usunięto nieużywane importy zależności związanych z get_user_id_for_ui
    # get_current_user_id,
    # supabase_auth_dependency,
)

# from src.schemas.auth import UserInfo # Niepotrzebne tutaj
from src.services.link_service import LinkService
from src.schemas.link import LinkResponse
from src.schemas.pagination import PaginationParams


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    print("Application startup: Initializing resources...")
    await init_supabase_clients()
    print("Application startup: Resources initialized.")
    yield
    print("Application shutdown: Cleaning up resources...")
    print("Application shutdown: Cleanup complete.")


# --- Inicjalizacja Aplikacji FastAPI z lifespan ---
app = FastAPI(
    title="routr UI & API - MVP",
    version="0.1.0",
    description="Application for managing dynamic redirection links with a web interface.",
    lifespan=lifespan,
)

# --- Montowanie Plików Statycznych ---
# app.mount("/static", ...)

# --- Dołączenie Routerów API ---
app.include_router(api_v1_router, prefix="/api/v1")

# --- Endpointy Renderujące Strony UI ---
ui_router = APIRouter()

# --- Usunięto funkcję pomocniczą get_user_id_for_ui ---

# --- Endpointy UI (bez sprawdzania auth po stronie serwera - polegamy na JS) ---


@ui_router.get(
    "/", response_class=HTMLResponse, name="render_landing_page", tags=["UI"]
)
async def render_landing_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    print("Rendering Landing Page")
    return templates.TemplateResponse(
        "landing_page.html", {"request": request, "now": datetime.utcnow}
    )


@ui_router.get(
    "/login", response_class=HTMLResponse, name="render_login_page", tags=["UI"]
)
async def render_login_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    print("Rendering Login Page")
    return templates.TemplateResponse(
        "login.html", {"request": request, "now": datetime.utcnow}
    )


@ui_router.get(
    "/register", response_class=HTMLResponse, name="render_register_page", tags=["UI"]
)
async def render_register_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    print("Rendering Register Page")
    return templates.TemplateResponse(
        "register.html", {"request": request, "now": datetime.utcnow}
    )


@ui_router.get(
    "/links", response_class=HTMLResponse, name="render_dashboard", tags=["UI"]
)
async def render_dashboard(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    # Usunięto blok sprawdzający user_id po stronie serwera
    print(f"Rendering dashboard shell (auth checked client-side)")
    # Renderujemy tylko powłokę, JS/HTMX załaduje resztę i sprawdzi token
    return templates.TemplateResponse(
        "links_list.html", {"request": request, "links": [], "now": datetime.utcnow}
    )


@ui_router.get(
    "/links/new",
    response_class=HTMLResponse,
    name="render_create_link_form",
    tags=["UI"],
)
async def render_create_link_form(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    # Usunięto blok sprawdzający user_id po stronie serwera
    print("Rendering create link form (auth checked client-side)")
    return templates.TemplateResponse(
        "links_create.html", {"request": request, "now": datetime.utcnow}
    )


@ui_router.get(
    "/links/{link_id}/edit",
    response_class=HTMLResponse,
    name="render_edit_link_form",
    tags=["UI"],
)
async def render_edit_link_form(
    request: Request,
    link_id: UUID,  # Nadal potrzebujemy link_id ze ścieżki
    templates: Jinja2Templates = Depends(get_templates),
    # Usunięto link_service, bo dane będą ładowane przez HTMX
):
    """Renderuje powłokę strony edycji linku. Dane zostaną załadowane przez HTMX."""
    # Usunięto blok sprawdzający user_id po stronie serwera
    # Usunięto blok try...except pobierający dane linku
    print(
        f"Rendering edit form shell for link_id: {link_id} (auth checked client-side)"
    )
    # Przekazujemy tylko link_id do szablonu, aby HTMX wiedział, jakie dane załadować
    return templates.TemplateResponse(
        "links_edit.html",
        {
            "request": request,
            "link_id": link_id,  # Przekazujemy tylko ID
            "link": None,  # Dane linku załaduje HTMX
            "now": datetime.utcnow,
        },
    )


# <<< Include the UI router BEFORE the catch-all redirection endpoint >>>
app.include_router(ui_router, prefix="/app")


# --- Endpoint Publicznego Przekierowania ---
@app.get(
    "/{alias_path:path}",
    summary="Handle Link Redirection",
    description="Public endpoint that processes a routr link alias...",
    tags=["Public Redirection"],
    include_in_schema=False,
)
async def handle_public_redirection(
    alias_path: str,
    request: Request,
    redirection_service: RedirectionService = Depends(get_redirection_service),
):
    # ... (logika bez zmian) ...
    print(f"Processing redirection request for alias: {alias_path}")
    try:
        action, value = await redirection_service.process_redirection(alias_path)
        if (
            action == RedirectionAction.REDIRECT_URL
            or action == RedirectionAction.REDIRECT_DEFAULT
        ):
            print(f"Redirecting '{alias_path}' to URL: {value}")
            return RedirectResponse(url=str(value), status_code=status.HTTP_302_FOUND)
        elif action == RedirectionAction.SERVE_HTML:
            print(f"Serving HTML content for alias: {alias_path}")
            return HTMLResponse(content=value, status_code=status.HTTP_200_OK)
        elif action == RedirectionAction.REDIRECT_GLOBAL_FALLBACK:
            print(
                f"No matching rule or default URL for alias '{alias_path}'. Redirecting to global fallback."
            )
            return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)
        else:
            print(
                f"ERROR: Unexpected redirection action '{action}' for alias: {alias_path}"
            )
            return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)
    except LinkNotFoundException:
        print(f"Link alias not found: {alias_path}")
        return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        print(f"ERROR processing redirection for alias '{alias_path}': {e}")
        return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)


# --- Endpoint główny (/) ---
@app.get(
    "/", summary="Root Endpoint Redirect", tags=["General"], include_in_schema=False
)
async def read_root_redirect():
    return RedirectResponse(url="/app/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


# --- Uruchomienie ---
if __name__ == "__main__":
    print("Starting Uvicorn server for local development...")
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
