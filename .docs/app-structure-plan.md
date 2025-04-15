# Application Skeleton - routr (MVP)

This document outlines the proposed file and directory structure for the _routr_ MVP application, designed to be clear, scalable, and aligned with the chosen technology stack (Python, FastAPI, Supabase, HTMX).

## 1. Folder Structure

```
routr-app/
├── .dockerignore             # Specifies files to ignore when building Docker image
├── .env.example              # Example environment variables file
├── .gitignore                # Specifies intentionally untracked files that Git should ignore
├── Dockerfile                # Defines the Docker image for the application
├── LICENSE                   # Project license file (e.g., MIT)
├── README.md                 # Project overview, setup, and usage instructions
├── pyproject.toml            # Python project configuration (dependencies, tools like Ruff/Black)
├── requirements.txt          # Python dependencies list (can be generated from pyproject.toml)
├── src/                      # Main source code directory
│   ├── api/                  # API related modules
│   │   ├── deps.py           # FastAPI dependency injection functions (e.g., get_db, get_current_user)
│   │   └── v1/               # API version 1
│   │       ├── __init__.py
│   │       ├── api.py        # Main API router combining endpoint routers
│   │       └── endpoints/    # Specific resource endpoints
│   │           ├── __init__.py
│   │           ├── auth.py     # Authentication endpoints (/auth/login, /auth/register)
│   │           ├── links.py    # Link CRUD endpoints (/links, /links/{id})
│   │           ├── rules.py    # Rule CRUD endpoints (/links/{id}/rules, ...)
│   │           └── stats.py    # Statistics endpoint (/links/{id}/stats)
│   ├── core/                 # Core application configuration and utilities
│   │   ├── __init__.py
│   │   ├── config.py         # Configuration loading (from environment variables) using Pydantic Settings
│   │   └── security.py       # Security related utilities (e.g., password hashing if needed, JWT handling - though Supabase handles JWTs)
│   ├── db/                   # Database interaction layer (optional abstraction over client)
│   │   ├── __init__.py
│   │   └── supabase_client.py # Initializes and provides the Supabase client instance
│   ├── models/               # Pydantic models representing database table structures (optional but good practice)
│   │   ├── __init__.py
│   │   ├── link.py
│   │   └── rule.py
│   ├── schemas/              # Pydantic models for API request/response validation (DTOs)
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── link.py
│   │   ├── pagination.py
│   │   ├── rule.py
│   │   └── stats.py
│   │   └── token.py # Added for clarity on token response structure
│   ├── services/             # Business logic layer
│   │   ├── __init__.py
│   │   ├── auth_service.py   # Handles interaction with Supabase Auth
│   │   ├── link_service.py   # Business logic for links
│   │   ├── redirection_service.py # Logic for the public /{alias} endpoint
│   │   └── rule_service.py   # Business logic for rules
│   ├── static/               # Static files (CSS, JS, images) - if not using CDN exclusively
│   │   └── custom.css        # Example custom CSS
│   ├── templates/            # Jinja2 HTML templates
│   │   ├── base.html         # Base template with common structure (incl. CDN links)
│   │   ├── auth/             # Auth related templates
│   │   │   └── login.html
│   │   ├── dashboard/        # User dashboard templates
│   │   │   ├── links_list_partial.html # Example partial for HTMX
│   │   │   └── index.html
│   │   └── index.html        # Public landing page (if any)
│   │   └── partials/         # Reusable HTML fragments / partials
│   │       └── _link_item.html
│   ├── __init__.py
│   └── main.py               # Main FastAPI application instance, router registration, middleware
├── supabase/                 # Supabase CLI generated files (managed by Supabase CLI)
│   └── migrations/
│       └── 20240815103000_create_initial_routr_schema.sql # Example migration file
└── tests/                    # Application tests
    ├── __init__.py
    ├── conftest.py           # Pytest fixtures (e.g., test client, mock db)
    ├── api/
    │   └── v1/
    │       └── test_links.py # Example API tests for links
    └── services/
        └── test_link_service.py # Example service layer tests
```

## 2. Configuration & Dependencies

- **Dependencies:** Defined in `pyproject.toml` (preferred for modern Python projects using tools like Poetry or PDM) or `requirements.txt` (for pip). Key dependencies: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `supabase-py`, `jinja2`, `python-dotenv`.
- **Environment Variables:** Managed via a `.env` file (loaded by `python-dotenv` locally or directly by the deployment environment). The `src/core/config.py` module uses Pydantic's `BaseSettings` to load and validate these variables (e.g., `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GLOBAL_FALLBACK_URL`). `.env.example` provides a template.
- **Database Connection:** The Supabase client is initialized in `src/db/supabase_client.py` using credentials loaded from the configuration (`src/core/config.py`). This client instance is then typically injected into service layers or API endpoints using FastAPI's dependency injection system defined in `src/api/deps.py`.

  ```python
  # Example src/core/config.py
  from pydantic_settings import BaseSettings

  class Settings(BaseSettings):
      SUPABASE_URL: str
      SUPABASE_KEY: str # Anon key (usually for client-side/user context)
      SUPABASE_SERVICE_ROLE_KEY: str # Service role key (for backend operations bypassing RLS)
      GLOBAL_FALLBACK_URL: str = "http://example.com/link-not-found" # Default fallback

      class Config:
          env_file = '.env'
          env_file_encoding = 'utf-8'

  settings = Settings()

  # Example src/db/supabase_client.py
  from supabase import create_client, Client
  from src.core.config import settings

  # Client using anon key (for user context operations)
  # Note: For backend API handling user requests, you might initialize
  # the client with the user's JWT instead of the static anon key.
  # supabase_anon: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

  # Client using service role key (for admin/backend tasks bypassing RLS)
  supabase_service: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

  # Dependency function to get the service client
  def get_supabase_service_client() -> Client:
      return supabase_service
  ```

- **API Configuration:** API endpoint definitions reside in `src/api/v1/endpoints/`. They import and use services from `src/services/` and schemas from `src/schemas/`. Routers are combined in `src/api/v1/api.py` and included in the main app instance in `src/main.py`.

## 3. Core Modules

- **`src/main.py`:**

  - Initializes the FastAPI application instance.
  - Includes API routers (e.g., from `src/api/v1/api.py`).
  - Registers middleware (CORS, potentially rate limiting, logging).
  - Configures Jinja2 templating.
  - Defines the root redirection endpoint `/{alias_path:path}`.

  ```python
  # Example src/main.py
  from fastapi import FastAPI, Request, Depends, HTTPException
  from fastapi.responses import RedirectResponse, HTMLResponse, Response
  from fastapi.staticfiles import StaticFiles
  from fastapi.templating import Jinja2Templates
  from contextlib import asynccontextmanager

  from src.api.v1.api import api_router as api_v1_router
  from src.core.config import settings
  from src.services.redirection_service import RedirectionService, RedirectionAction
  # Assuming service instance can be created or injected
  # from src.api.deps import get_redirection_service # Example dependency

  # --- Lifespan (e.g., for DB connection pool setup/teardown, not strictly needed for Supabase client init) ---
  # @asynccontextmanager
  # async def lifespan(app: FastAPI):
  #     # Startup code here
  #     yield
  #     # Shutdown code here

  # app = FastAPI(title="routr API", lifespan=lifespan)
  app = FastAPI(title="routr API")


  # --- Mount Static Files (if needed) ---
  # app.mount("/static", StaticFiles(directory="src/static"), name="static")

  # --- Configure Templates ---
  templates = Jinja2Templates(directory="src/templates")

  # --- Include API Routers ---
  app.include_router(api_v1_router, prefix="/api/v1") # Management API

  # --- Public Redirection Endpoint ---
  # This needs careful implementation of service injection/creation
  # Using a simple instantiation here for brevity
  redirection_service = RedirectionService() # Ideally use Depends if within a request context

  @app.get("/{alias_path:path}", include_in_schema=False)
  async def handle_redirection(alias_path: str):
      try:
          action, value = await redirection_service.process_redirection(alias_path) # Make service async if DB calls are async

          if action == RedirectionAction.REDIRECT_URL or action == RedirectionAction.REDIRECT_DEFAULT:
              return RedirectResponse(url=value, status_code=302)
          elif action == RedirectionAction.SERVE_HTML:
              return HTMLResponse(content=value, status_code=200)
          elif action == RedirectionAction.REDIRECT_GLOBAL_FALLBACK:
              return RedirectResponse(url=settings.GLOBAL_FALLBACK_URL, status_code=302)
          else:
               # Should not happen with proper service implementation
               raise HTTPException(status_code=500, detail="Invalid redirection action")

      except redirection_service.NotFoundException: # Assuming custom exception
          raise HTTPException(status_code=404, detail="Link alias not found")
      except Exception as e:
          # Log the error properly here
          print(f"Error during redirection: {e}") # Replace with proper logging
          raise HTTPException(status_code=500, detail="Internal server error")

  # --- Optional Root Endpoint for Web UI / Info ---
  @app.get("/", response_class=HTMLResponse, include_in_schema=False)
  async def read_root(request: Request):
      # Example: Render a landing page or redirect to login/dashboard
      return templates.TemplateResponse("index.html", {"request": request})

  ```

- **Services (`src/services/`)**: Contain the core business logic, interacting with the database client (`src/db/supabase_client.py`) and processing data. They are designed to be called by the API endpoints.
- **Schemas (`src/schemas/`)**: Define data structures for API input and output using Pydantic, ensuring validation.

## 4. Integration Points

- **API Endpoints (`src/api/v1/endpoints/`)**: These modules directly implement the REST API plan. Each function corresponds to an endpoint defined in the plan (e.g., `create_link` function in `links.py` handles `POST /links`).
- **Service Calls**: API endpoint handlers delegate business logic processing and database interactions to methods within the corresponding service modules (e.g., `links.py` calls methods in `link_service.py`).
- **Database Client**: Services use the initialized Supabase client instance (from `src/db/supabase_client.py`) to interact with the database, respecting the RLS rules defined in the DB schema by using either the user's JWT context or the service role key as appropriate.
- **Redirection Endpoint (`src/main.py`)**: The `/{alias_path:path}` endpoint specifically uses the `RedirectionService` to handle the core link resolution and redirection logic.

## 5. Sample Tests

- **Framework:** `pytest` is recommended.
- **Location:** `/tests` directory, mirroring the `src` structure.
- **Fixtures (`tests/conftest.py`):** Define reusable fixtures, such as:
  - A FastAPI `TestClient` instance.
  - A mock Supabase client or setup for an isolated test database.
  - Fixture for creating authenticated test users and obtaining JWT tokens.
- **Test Files:**
  - `tests/api/v1/test_links.py`: Contains tests for the `/links` endpoints, mocking service layer responses or interacting with a test database.
  - `tests/services/test_link_service.py`: Contains unit tests for the `LinkService` logic, mocking the database client interaction.

```python
# Example tests/api/v1/test_links.py
from fastapi.testclient import TestClient
from uuid import uuid4

# Assuming 'client' is a pytest fixture providing TestClient(app)
# Assuming 'auth_headers' is a fixture providing {'Authorization': 'Bearer ...'}

def test_create_link_success(client, auth_headers):
    response = client.post(
        "/api/v1/links",
        headers=auth_headers,
        json={"alias": f"test-alias-{uuid4()}", "default_url": "https://example.com"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["alias"].startswith("test-alias-")
    assert data["default_url"] == "https://example.com"
    assert "id" in data

def test_create_link_conflict(client, auth_headers):
    # Create a link first
    alias = f"conflict-alias-{uuid4()}"
    client.post("/api/v1/links", headers=auth_headers, json={"alias": alias})
    # Attempt to create again
    response = client.post("/api/v1/links", headers=auth_headers, json={"alias": alias})
    assert response.status_code == 409

def test_get_link_not_found(client, auth_headers):
    non_existent_id = uuid4()
    response = client.get(f"/api/v1/links/{non_existent_id}", headers=auth_headers)
    assert response.status_code == 404

# ... more tests for list, get, patch, delete ...
```

## 6. Getting Started

1.  **Clone/Setup:** Clone the repository and navigate into the `routr-app` directory.
2.  **Environment:** Create a `.env` file from `.env.example` and fill in your `SUPABASE_URL`, `SUPABASE_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`.
3.  **Virtual Env:** Create and activate a Python virtual environment (e.g., `python -m venv .venv && source .venv/bin/activate`).
4.  **Install Dependencies:** Install requirements: `pip install -r requirements.txt` (or using `pyproject.toml` with Poetry/PDM).
5.  **Run Migrations (if needed):** Use Supabase CLI to apply database migrations: `supabase db push` (assuming CLI is configured).
6.  **Run Development Server:** Start the FastAPI application using Uvicorn:
    ```bash
    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    ```
7.  **Access:**
    - Management API Docs (Swagger UI): `http://localhost:8000/docs`
    - Application Frontend (if served): `http://localhost:8000/`
    - Redirection Endpoint: Access via `http://localhost:8000/{your_alias}`
