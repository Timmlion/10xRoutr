# src/main.py
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
from typing import List, Optional
from uuid import UUID

# Import application configuration
from src.core.config import settings

# Import the main API router
from src.api.v1.api import api_v1_router

# Import services and custom exceptions
from src.services.redirection_service import (
    RedirectionService,
    RedirectionAction,
    LinkNotFoundException,
)
from src.services.custom_exceptions import (
    LinkNotFoundException as CustomLinkNotFoundException,  # Alias to avoid name clash if needed later
)

# Import Supabase initialization function
from src.db.supabase_client import init_supabase_clients

# Import dependencies
from supabase import AsyncClient
from src.api.deps import (
    get_redirection_service,
    get_templates,
    get_link_service,
    # Dependencies for server-side UI auth checks were removed
)

from src.services.link_service import LinkService
from src.schemas.link import LinkResponse
from src.schemas.pagination import PaginationParams


# --- Application Lifespan Management ---
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """
    Asynchronous context manager to handle application startup and shutdown events.
    Initializes resources like database connections on startup and cleans them up on shutdown.
    """
    print("Application startup: Initializing resources...")
    await init_supabase_clients()  # Initialize Supabase clients
    print("Application startup: Resources initialized.")
    yield  # Application runs here
    print("Application shutdown: Cleaning up resources...")
    # Add any cleanup logic here if needed in the future
    print("Application shutdown: Cleanup complete.")


# --- FastAPI Application Initialization ---
app = FastAPI(
    title="routr UI & API - MVP",
    version="0.1.0",
    description="Application for managing dynamic redirection links with a web interface.",
    lifespan=lifespan,  # Register the lifespan context manager
)

# --- Static Files Mounting (Example - currently commented out) ---
# base_dir = Path(__file__).resolve().parent
# app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

# --- API Router Inclusion ---
# Include routes defined in the v1 API router, prefixed with /api/v1
app.include_router(api_v1_router, prefix="/api/v1")

# --- UI Router Definition ---
# Router for handling HTML page rendering for the web interface
ui_router = APIRouter()


# --- UI Endpoints ---
# These endpoints render HTML templates. Authentication is expected to be handled client-side via JavaScript.


@ui_router.get(
    "/", response_class=HTMLResponse, name="render_landing_page", tags=["UI"]
)
async def render_landing_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    """Renders the public landing page."""
    print("Rendering Landing Page")
    return templates.TemplateResponse(
        "landing_page.html", {"request": request, "now": datetime.utcnow()}
    )


@ui_router.get(
    "/login", response_class=HTMLResponse, name="render_login_page", tags=["UI"]
)
async def render_login_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    """Renders the login page."""
    print("Rendering Login Page")
    return templates.TemplateResponse(
        "login.html", {"request": request, "now": datetime.utcnow()}
    )


@ui_router.get(
    "/register", response_class=HTMLResponse, name="render_register_page", tags=["UI"]
)
async def render_register_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    """Renders the registration page."""
    print("Rendering Register Page")
    return templates.TemplateResponse(
        "register.html", {"request": request, "now": datetime.utcnow()}
    )


@ui_router.get(
    "/links", response_class=HTMLResponse, name="render_dashboard", tags=["UI"]
)
async def render_dashboard(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    """
    Renders the main dashboard shell.
    Actual link data is loaded dynamically client-side (e.g., via HTMX or JavaScript).
    Authentication is checked client-side.
    """
    print(f"Rendering dashboard shell (auth checked client-side)")
    return templates.TemplateResponse(
        "links_list.html",
        {
            "request": request,
            "links": [],
            "now": datetime.utcnow(),
        },  # Pass empty list initially
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
    """
    Renders the form for creating a new link.
    Authentication is checked client-side.
    """
    print("Rendering create link form (auth checked client-side)")
    return templates.TemplateResponse(
        "links_create.html", {"request": request, "now": datetime.utcnow()}
    )


@ui_router.get(
    "/links/{link_id}/edit",
    response_class=HTMLResponse,
    name="render_edit_link_form",
    tags=["UI"],
)
async def render_edit_link_form(
    request: Request,
    link_id: UUID,  # Extract link_id from the URL path
    templates: Jinja2Templates = Depends(get_templates),
    # Link data is not fetched here; it will be loaded client-side (e.g., via HTMX)
):
    """
    Renders the shell page for editing an existing link.
    The form fields will be populated dynamically client-side using the link_id.
    Authentication is checked client-side.
    """
    print(
        f"Rendering edit form shell for link_id: {link_id} (auth checked client-side)"
    )
    # Pass link_id to the template so client-side code knows which link to fetch
    return templates.TemplateResponse(
        "links_edit.html",
        {
            "request": request,
            "link_id": link_id,  # ID needed for client-side fetch
            "link": None,  # Placeholder, data loaded by HTMX/JS
            "now": datetime.utcnow(),
        },
    )


# --- UI Router Inclusion ---
# IMPORTANT: Include the UI router *before* the catch-all redirection endpoint
# to ensure UI paths like /app/links are matched correctly.
app.include_router(ui_router, prefix="/app")


# --- Public Redirection Endpoint ---
@app.get(
    "/{alias_path:path}",
    summary="Handle Link Redirection",
    description="Public endpoint that processes a routr link alias, determines the appropriate action (e.g., redirect, serve HTML), and executes it.",
    tags=["Public Redirection"],
    include_in_schema=False,  # Hide from OpenAPI docs as it's a catch-all
)
async def handle_public_redirection(
    alias_path: str,  # The path requested by the user, treated as a potential link alias
    request: Request,
    redirection_service: RedirectionService = Depends(get_redirection_service),
):
    """
    Handles incoming requests that don't match any other specific API or UI routes.
    It attempts to find a matching link alias and perform the configured action.
    """
    print(f"Processing redirection request for alias: {alias_path}")
    try:
        # Determine the action based on the alias and defined rules
        action, value = await redirection_service.process_redirection(alias_path)

        if (
            action == RedirectionAction.REDIRECT_URL
            or action == RedirectionAction.REDIRECT_DEFAULT
        ):
            # Redirect to the target URL found for the alias or its default
            print(f"Redirecting '{alias_path}' to URL: {value}")
            return RedirectResponse(url=str(value), status_code=status.HTTP_302_FOUND)
        elif action == RedirectionAction.SERVE_HTML:
            # Serve HTML content directly (e.g., for tracking pixels or simple pages)
            print(f"Serving HTML content for alias: {alias_path}")
            return HTMLResponse(content=value, status_code=status.HTTP_200_OK)
        elif action == RedirectionAction.REDIRECT_GLOBAL_FALLBACK:
            # No specific rule or default found, redirect to the main application UI
            print(
                f"No matching rule or default URL for alias '{alias_path}'. Redirecting to global fallback."
            )
            # Redirects to the UI landing/dashboard page
            return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)
        else:
            # Fallback for unexpected actions, redirecting to the UI
            print(
                f"ERROR: Unexpected redirection action '{action}' for alias: {alias_path}"
            )
            return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)

    except LinkNotFoundException:
        # Alias explicitly not found in the database
        print(f"Link alias not found: {alias_path}. Redirecting to global fallback.")
        return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        # Catch any other unexpected errors during redirection processing
        print(f"ERROR processing redirection for alias '{alias_path}': {e}")
        # Redirect to the UI as a safe fallback
        return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)


# --- Root Endpoint Redirect ---
@app.get(
    "/", summary="Root Endpoint Redirect", tags=["General"], include_in_schema=False
)
async def read_root_redirect():
    """Redirects requests to the server root ('/') to the main UI application path ('/app/')."""
    return RedirectResponse(url="/app/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


# --- Debug: Print Registered Routes ---
# Useful for verifying that routes are registered as expected, especially the catch-all.
print("\n--- Registered Routes ---")
for route in app.routes:
    if hasattr(route, "path") and hasattr(route, "methods"):
        print(f"Path: {route.path}, Methods: {route.methods}")
    # Can be extended to introspect routes within APIRouters if needed
print("-------------------------\n")

# --- Server Execution ---
if __name__ == "__main__":
    # Starts the Uvicorn server for local development.
    # `reload=True` enables auto-reloading when code changes are detected.
    print("Starting Uvicorn server for local development...")
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
