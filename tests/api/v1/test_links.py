# tests/api/v1/test_links.py (Corrected for Form Data)

import pytest
from fastapi.testclient import TestClient
from httpx import Headers  # Needed to set headers for form data
from uuid import uuid4, UUID
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, AsyncMock  # Import AsyncMock

# Importuj główną aplikację FastAPI z src.main
from src.main import app

# Importuj ZALEŻNOŚCI, które będziemy nadpisywać
from src.api.deps import get_current_user_id, get_link_service

# Importuj serwis i modele dla type hinting i specyfikacji mocka
from src.services.link_service import LinkService
from src.schemas.link import LinkResponse

# Fikcyjne ID użytkownika dla testów
TEST_USER_ID = uuid4()

# --- Fixtures ---


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create a TestClient instance for the FastAPI app with overridden dependencies."""

    original_get_user_id = app.dependency_overrides.get(get_current_user_id)
    original_get_link_service = app.dependency_overrides.get(get_link_service)

    def override_get_current_user_id():
        # print(f"Overriding get_current_user_id to return: {TEST_USER_ID}") # Uncomment for debug
        return TEST_USER_ID

    # --- Mock LinkService dla tego modułu ---
    # Mock musi być zdefiniowany przed jego użyciem w override
    mock_link_service = MagicMock(spec=LinkService)
    # Kluczowe: Definiujemy mocki dla metod asynchronicznych
    mock_link_service.create_link = AsyncMock()
    mock_link_service.get_links_paginated = AsyncMock()
    mock_link_service.get_link_by_id = AsyncMock()
    mock_link_service.update_link = AsyncMock()
    mock_link_service.delete_link = AsyncMock()
    mock_link_service.get_link_statistics = AsyncMock()
    # ---------------------------------------

    def override_get_link_service():
        # print(f"Overriding get_link_service with mock: {mock_link_service}") # Uncomment for debug
        return mock_link_service

    app.dependency_overrides[get_current_user_id] = override_get_current_user_id
    app.dependency_overrides[get_link_service] = override_get_link_service

    with TestClient(app) as test_client:
        yield test_client

    # Wyczyść nadpisania
    # print("Clearing dependency overrides.") # Uncomment for debug
    if original_get_user_id:
        app.dependency_overrides[get_current_user_id] = original_get_user_id
    else:
        if get_current_user_id in app.dependency_overrides:
            del app.dependency_overrides[get_current_user_id]

    if original_get_link_service:
        app.dependency_overrides[get_link_service] = original_get_link_service
    else:
        if get_link_service in app.dependency_overrides:
            del app.dependency_overrides[get_link_service]


# --- Test Cases ---


@pytest.mark.asyncio  # Mark test as async
async def test_create_link_success(
    client: TestClient,
    # Mock jest teraz zarządzany przez fixture `client` przez `app.dependency_overrides`
):
    """Tests successful link creation using form data."""
    unique_alias = f"test-success-{uuid4()}"
    # <<< ZMIANA: Przygotowujemy dane jako słownik dla `data=` >>>
    payload_data = {"alias": unique_alias, "default_url": "https://success.example.com"}

    # Arrange: Pobierz mocka skonfigurowanego w fixture `client`
    mock_service = app.dependency_overrides[get_link_service]()

    # Konfigurujemy, co mock `create_link` ma zwrócić (obiekt LinkResponse)
    # Tworzymy 'prawdziwy' obiekt LinkResponse, który zostanie zwrócony i zserializowany przez FastAPI
    fake_created_time = datetime.now(timezone.utc)
    mock_return_value = LinkResponse(
        id=uuid4(),
        user_id=TEST_USER_ID,
        alias=unique_alias,
        default_url="https://success.example.com",
        total_clicks=0,
        created_at=fake_created_time,
        updated_at=fake_created_time,
    )
    mock_service.create_link.return_value = mock_return_value

    # Act: Wyślij żądanie POST z danymi formularza (`data=`)
    # Musimy dodać nagłówek Content-Type, TestClient nie zrobi tego sam dla 'data'
    headers = Headers({"Content-Type": "application/x-www-form-urlencoded"})
    response = client.post(
        "/api/v1/links",
        data=payload_data,  # <<< ZMIANA: Używamy `data=` zamiast `json=`
        headers=headers,  # <<< DODANO: Nagłówek dla danych formularza
        # Nie potrzebujemy nagłówka Authorization, bo get_current_user_id jest nadpisane
    )

    # Assert: Sprawdź status code
    assert (
        response.status_code == 201
    ), f"Expected 201, got {response.status_code}. Response: {response.text}"

    # Assert: Sprawdź, czy mock serwisu został wywołany z poprawnymi argumentami
    mock_service.create_link.assert_awaited_once()
    call_args, call_kwargs = mock_service.create_link.call_args
    # Sprawdzamy argumenty pozycyjne lub nazwane, zależnie jak serwis był wywołany
    # W naszym przypadku serwis `create_link` przyjmuje `link_data` i `user_id` jako kwargs
    assert call_kwargs["user_id"] == TEST_USER_ID
    # Sprawdzamy, czy przekazany obiekt `link_data` ma poprawne atrybuty
    assert call_kwargs["link_data"].alias == unique_alias
    assert (
        str(call_kwargs["link_data"].default_url) == "https://success.example.com/"
    )  # Pydantic HttpUrl dodaje '/'

    # Assert: Sprawdź strukturę odpowiedzi JSON
    response_data = response.json()
    assert response_data["alias"] == unique_alias
    assert (
        response_data["default_url"] == "https://success.example.com/"
    )  # Pydantic serializuje HttpUrl
    assert response_data["user_id"] == str(TEST_USER_ID)
    assert response_data["id"] is not None
    assert response_data["total_clicks"] == 0


@pytest.mark.asyncio
async def test_create_link_missing_alias(client: TestClient):
    """Tests creation attempt without the required 'alias' field using form data."""
    # Dane formularza bez pola 'alias'
    payload_data = {"default_url": "https://missing-alias.com"}
    headers = Headers({"Content-Type": "application/x-www-form-urlencoded"})
    response = client.post("/api/v1/links", data=payload_data, headers=headers)
    # Oczekujemy 422, bo FastAPI/Pydantic wykryje brak wymaganego pola 'alias' w Form(...)
    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}. Response: {response.text}"
    # Sprawdź szczegóły błędu walidacji
    error_details = response.json().get("detail", [])
    assert any(
        d.get("loc") == ["body", "alias"] and d.get("type") == "missing"
        for d in error_details
    )


@pytest.mark.asyncio
async def test_create_link_invalid_alias_format(client: TestClient):
    """Tests creation attempt with an invalid alias format using form data."""
    payload_data = {"alias": "Invalid Alias", "default_url": "https://valid.com"}
    headers = Headers({"Content-Type": "application/x-www-form-urlencoded"})
    response = client.post("/api/v1/links", data=payload_data, headers=headers)
    # Oczekujemy 422, bo walidacja Pydantic wewnątrz endpointu (LinkCreate.model_validate)
    # powinna odrzucić alias niezgodny z patternem.
    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}. Response: {response.text}"
    # Można dodać asercję sprawdzającą treść błędu, jeśli walidacja Pydantic zwraca szczegóły
    error_detail = response.json().get("detail", "")
    assert (
        "Invalid form data" in error_detail
    )  # Sprawdź ogólny komunikat lub bardziej szczegółowy błąd Pydantic
