# tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from src.main import app  # Import the main FastAPI application instance


@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Pytest fixture providing a FastAPI TestClient instance for making requests to the application.
    The scope is 'module', meaning one client instance is created per test module.
    """
    # Create a TestClient instance using the imported FastAPI app
    with TestClient(app) as test_client:
        yield test_client  # Yield the client to the tests


@pytest.fixture(scope="module")
def auth_headers() -> dict:
    """
    Pytest fixture providing mock authentication headers.

    NOTE: This uses a **FAKE** token. It will only work for tests where
    the authentication dependency (e.g., `get_current_user_id` in `src.api.deps`)
    is overridden/mocked to bypass actual token validation.
    For integration tests that require real token validation, you would need
    to replace this with logic to generate or retrieve a valid JWT
    for a test user existing in your test database or mocked Supabase instance.
    """
    return {"Authorization": "Bearer FAKE_TEST_TOKEN"}


# Other potential fixtures could be added here, for example:
# - Mocking the Supabase client globally if needed across multiple test modules.
# - Setting up and tearing down test database state.
# - Creating a test user and obtaining a real token for integration tests.
