# tests/conftest.py (minimalny przykład)
import pytest
from fastapi.testclient import TestClient
from src.main import app  # Importuj swoją aplikację FastAPI


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Provides a FastAPI TestClient instance."""
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers() -> dict:
    """Provides mock authentication headers. Replace with actual token generation if needed."""
    # UWAGA: To jest mock! W prawdziwym teście musisz uzyskać/wygenerować ważny token JWT
    # dla testowego użytkownika, który istnieje w testowej bazie danych lub mocku Supabase.
    return {"Authorization": "Bearer FAKE_TEST_TOKEN"}


# Można dodać fixture do mockowania klienta Supabase lub tworzenia testowego użytkownika
