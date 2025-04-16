# tests/api/v1/test_links.py

from fastapi.testclient import TestClient
from uuid import uuid4
import pytest  # Importuj pytest, jeśli używasz fixture'ów bezpośrednio

# Testy wymagają fixture 'client' i 'auth_headers' z conftest.py


def test_create_link_success(client: TestClient, auth_headers: dict):
    """Tests successful link creation."""
    unique_alias = f"test-success-{uuid4()}"
    payload = {"alias": unique_alias, "default_url": "https://success.example.com"}

    response = client.post("/api/v1/links", headers=auth_headers, json=payload)

    assert (
        response.status_code == 201
    ), f"Expected 201, got {response.status_code}. Response: {response.text}"
    data = response.json()
    assert data["alias"] == unique_alias
    assert data["default_url"] == "https://success.example.com"
    assert data["total_clicks"] == 0
    assert "id" in data
    assert (
        "user_id" in data
    )  # Możesz dodać asercję na ID użytkownika, jeśli fixture go dostarcza
    assert "created_at" in data
    assert "updated_at" in data


def test_create_link_missing_alias(client: TestClient, auth_headers: dict):
    """Tests creation attempt without the required 'alias' field."""
    payload = {"default_url": "https://missing-alias.com"}

    response = client.post("/api/v1/links", headers=auth_headers, json=payload)

    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}. Response: {response.text}"
    # Można dodać sprawdzanie treści błędu walidacji


def test_create_link_invalid_alias_format(client: TestClient, auth_headers: dict):
    """Tests creation attempt with an invalid alias format."""
    payload = {"alias": "Invalid Alias With Spaces", "default_url": "https://valid.com"}

    response = client.post("/api/v1/links", headers=auth_headers, json=payload)

    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}. Response: {response.text}"
    # Sprawdź, czy błąd dotyczy pola alias


def test_create_link_no_auth(client: TestClient):
    """Tests creation attempt without authentication."""
    payload = {"alias": f"no-auth-{uuid4()}", "default_url": "https://no-auth.com"}

    response = client.post("/api/v1/links", json=payload)  # Brak nagłówka Authorization

    assert (
        response.status_code == 401
    ), f"Expected 401, got {response.status_code}. Response: {response.text}"


# UWAGA: Test na 409 Conflict wymaga bardziej złożonego setupu:
# 1. Prawdziwego połączenia z bazą testową LUB
# 2. Mockowania odpowiedzi Supabase klienta w warstwie serwisowej,
#    aby symulować zgłoszenie wyjątku AliasConflictException.

# Przykład z mockowaniem (wymaga `pytest-mock`):
# def test_create_link_conflict_mocked(client: TestClient, auth_headers: dict, mocker):
#     """Tests alias conflict by mocking the service layer."""
#     from src.services.link_service import AliasConflictException
#     # Mockuj metodę create_link w instancji serwisu używanej przez endpoint
#     # To może być skomplikowane w zależności od sposobu wstrzykiwania zależności
#     # Załóżmy, że możemy mockować bezpośrednio importowaną instancję lub przez patch
#     mocker.patch(
#         'src.api.v1.endpoints.links.get_link_service', # Ścieżka do zależności lub serwisu
#         return_value=mocker.Mock( # Zwróć mock serwisu
#             create_link=mocker.Mock(side_effect=AliasConflictException("Alias already exists")) # Mock metody create_link
#         )
#     )
#
#     payload = {"alias": "existing-alias", "default_url": "https://conflict.com"}
#     response = client.post(
#         "/api/v1/links",
#         headers=auth_headers,
#         json=payload
#     )
#     assert response.status_code == 409
#     assert "Alias already exists" in response.json()["detail"]
