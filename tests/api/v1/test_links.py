# tests/api/v1/test_links.py

import pytest
from fastapi.testclient import TestClient
from uuid import uuid4, UUID
from datetime import datetime, timezone  # Dodano import
from typing import Generator


# Importuj główną aplikację FastAPI z src.main
from src.main import app

# Importuj ZALEŻNOŚCI, które będziemy nadpisywać
from src.api.deps import get_current_user_id, get_link_service  # <<< Zmieniono import

# Importuj serwis, który będziemy mockować (dla specyfikacji)
from src.services.link_service import LinkService

# Fikcyjne ID użytkownika dla testów
TEST_USER_ID = uuid4()

# --- Fixtures ---


@pytest.fixture(scope="module")
# <<< POPRAWKA: Zmień typowanie na Generator
def client() -> Generator[TestClient, None, None]:
    """Create a TestClient instance for the FastAPI app with overridden dependencies."""

    # Override the dependency to return a fixed user ID without checking token
    def override_get_current_user_id():
        print(f"Overriding get_current_user_id to return: {TEST_USER_ID}")
        return TEST_USER_ID

    original_dependency = app.dependency_overrides.get(
        get_current_user_id
    )  # Zapisz oryginalną, jeśli istnieje
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id

    # Utwórz klienta testowego w kontekście `with`, aby zapewnić cleanup
    with TestClient(app) as test_client:
        yield test_client  # Udostępnij klienta testom

    # Wyczyść nadpisanie po zakończeniu testów w module
    print("Clearing get_current_user_id override.")
    if original_dependency:
        app.dependency_overrides[get_current_user_id] = original_dependency
    else:
        del app.dependency_overrides[get_current_user_id]


@pytest.fixture
def mock_link_service(mocker):
    """Mocks the LinkService."""
    mock = mocker.MagicMock(spec=LinkService)
    # Definiujemy AsyncMock dla metod asynchronicznych
    mock.create_link = mocker.AsyncMock()
    # Dodaj inne mockowane metody, jeśli są potrzebne w innych testach
    # mock.get_links_paginated = mocker.AsyncMock()
    # mock.get_link_by_id = mocker.AsyncMock()
    # mock.update_link = mocker.AsyncMock()
    # mock.delete_link = mocker.AsyncMock()
    return mock


@pytest.fixture(autouse=True)
def override_link_service_dependency(mock_link_service):
    """Overrides the get_link_service dependency for all tests in this file."""
    print(f"Overriding get_link_service with mock: {mock_link_service}")  # Dodajmy log
    # <<< POPRAWKA: Nadpisz funkcję zależności, a nie klasę
    app.dependency_overrides[get_link_service] = lambda: mock_link_service
    yield  # Testy działają
    # Wyczyść nadpisanie po teście
    print(f"Clearing get_link_service override.")  # Dodajmy log
    if get_link_service in app.dependency_overrides:
        del app.dependency_overrides[get_link_service]


# --- Test Cases ---


def test_create_link_success(
    client: TestClient,
    mock_link_service,  # Zależność mocka jest wstrzykiwana przez pytest
):
    """Tests successful link creation."""
    unique_alias = f"test-success-{uuid4()}"
    payload = {"alias": unique_alias, "default_url": "https://success.example.com"}

    # Arrange: Skonfiguruj mock serwisu, aby zwracał **obiekt zgodny z LinkResponse**
    # Zamiast słownika, użyjmy MagicMock, aby uniknąć problemów z atrybutami
    mock_response_obj = mock_link_service.create_link.return_value
    mock_response_obj.id = uuid4()
    mock_response_obj.user_id = TEST_USER_ID
    mock_response_obj.alias = unique_alias
    mock_response_obj.default_url = "https://success.example.com"
    mock_response_obj.total_clicks = 0
    # Możemy mockować datetime jako stringi dla uproszczenia
    mock_response_obj.created_at = datetime.now(timezone.utc).isoformat()
    mock_response_obj.updated_at = datetime.now(timezone.utc).isoformat()
    # Ważne: mock musi mieć metodę .model_dump(), której FastAPI użyje do serializacji
    mock_response_obj.model_dump.return_value = {
        "id": mock_response_obj.id,
        "user_id": mock_response_obj.user_id,
        "alias": mock_response_obj.alias,
        "default_url": mock_response_obj.default_url,
        "total_clicks": mock_response_obj.total_clicks,
        "created_at": mock_response_obj.created_at,
        "updated_at": mock_response_obj.updated_at,
    }

    # Act: Wyślij żądanie
    response = client.post("/api/v1/links", json=payload)

    # Assert: Sprawdź status code
    assert (
        response.status_code == 201
    ), f"Expected 201, got {response.status_code}. Response: {response.text}"

    # Assert: Sprawdź, czy mock serwisu został wywołany
    mock_link_service.create_link.assert_awaited_once()  # Sprawdź await
    call_args = mock_link_service.create_link.call_args
    assert call_args.kwargs["user_id"] == TEST_USER_ID
    assert (
        call_args.kwargs["link_data"].alias == unique_alias
    )  # Sprawdź przekazane dane

    # Assert: Sprawdź strukturę odpowiedzi JSON
    response_data = response.json()
    assert response_data["alias"] == unique_alias
    assert response_data["default_url"].startswith("https://success.example.com")

    # UUID będzie serializowane do stringa w JSON
    assert response_data["user_id"] == str(TEST_USER_ID)
    assert response_data["id"] is not None


def test_create_link_missing_alias(client: TestClient):
    """Tests creation attempt without the required 'alias' field."""
    payload = {"default_url": "https://missing-alias.com"}
    response = client.post("/api/v1/links", json=payload)
    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}. Response: {response.text}"


def test_create_link_invalid_alias_format(client: TestClient):
    """Tests creation attempt with an invalid alias format."""
    payload = {"alias": "Invalid Alias With Spaces", "default_url": "https://valid.com"}
    response = client.post("/api/v1/links", json=payload)
    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}. Response: {response.text}"
