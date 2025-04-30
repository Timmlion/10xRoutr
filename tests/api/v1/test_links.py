# tests/api/v1/test_links.py

import pytest
from fastapi.testclient import TestClient

# httpx.Headers is not strictly needed as TestClient handles dicts, but good practice
from httpx import Headers
from uuid import uuid4, UUID
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, AsyncMock  # AsyncMock for mocking async methods

# Import the FastAPI app instance
from src.main import app

# Import dependencies to override
from src.api.deps import get_current_user_id, get_link_service

# Import services and schemas for type hinting and mock specification
from src.services.link_service import LinkService
from src.schemas.link import (
    LinkResponse,
    LinkCreate,
)  # Import LinkCreate for assertion checking

# Define a consistent test user ID
TEST_USER_ID = uuid4()

# --- Fixtures ---


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """
    Provides a TestClient instance for the FastAPI app with overridden dependencies
    for user authentication and the link service. This fixture ensures dependencies
    are mocked consistently across tests in this module.
    """
    # Store original overrides to restore them later
    original_get_user_id = app.dependency_overrides.get(get_current_user_id)
    original_get_link_service = app.dependency_overrides.get(get_link_service)

    # Override user ID dependency to return a fixed test user ID
    def override_get_current_user_id():
        # print(f"Overriding get_current_user_id to return: {TEST_USER_ID}") # Uncomment for debug
        return TEST_USER_ID

    # --- Mock LinkService Definition ---
    # Create a mock object that mimics the LinkService interface.
    # Specify async methods using AsyncMock.
    mock_link_service = MagicMock(spec=LinkService)
    mock_link_service.create_link = AsyncMock()
    mock_link_service.get_links_paginated = AsyncMock()
    mock_link_service.get_link_by_id = AsyncMock()
    mock_link_service.update_link = AsyncMock()
    mock_link_service.delete_link = AsyncMock()
    mock_link_service.get_link_statistics = AsyncMock()
    # ------------------------------------

    # Override link service dependency to return the mock instance
    def override_get_link_service():
        # print(f"Overriding get_link_service with mock: {mock_link_service}") # Uncomment for debug
        return mock_link_service

    # Apply the overrides to the FastAPI app instance
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id
    app.dependency_overrides[get_link_service] = override_get_link_service

    # Yield the TestClient for use in tests
    with TestClient(app) as test_client:
        yield test_client

    # --- Cleanup ---
    # Restore original dependency overrides after tests in the module have run.
    # print("Clearing dependency overrides.") # Uncomment for debug
    if original_get_user_id:
        app.dependency_overrides[get_current_user_id] = original_get_user_id
    else:
        # Ensure the key is removed if it was added by this fixture
        if get_current_user_id in app.dependency_overrides:
            del app.dependency_overrides[get_current_user_id]

    if original_get_link_service:
        app.dependency_overrides[get_link_service] = original_get_link_service
    else:
        if get_link_service in app.dependency_overrides:
            del app.dependency_overrides[get_link_service]


# --- Test Cases ---


@pytest.mark.asyncio  # Mark test as asynchronous
async def test_create_link_success(client: TestClient):
    """
    Tests successful link creation endpoint (POST /api/v1/links)
    using application/x-www-form-urlencoded data.
    """
    unique_alias = f"test-success-{uuid4()}"
    # Define the payload as a dictionary representing form data.
    payload_data = {"alias": unique_alias, "default_url": "https://success.example.com"}

    # Arrange: Get the mocked service instance configured in the fixture.
    mock_service = app.dependency_overrides[get_link_service]()

    # Configure the mock's `create_link` method to return a valid LinkResponse object.
    fake_created_time = datetime.now(timezone.utc)
    mock_return_value = LinkResponse(
        id=uuid4(),
        user_id=TEST_USER_ID,
        alias=unique_alias,
        default_url="https://success.example.com",  # Simulate DB value before Pydantic serialization
        total_clicks=0,
        created_at=fake_created_time,
        updated_at=fake_created_time,
    )
    mock_service.create_link.return_value = mock_return_value

    # Act: Send the POST request with form data using the `data=` parameter.
    # TestClient typically sets the 'Content-Type' correctly for `data=`.
    # No Authorization header needed as get_current_user_id is mocked.
    response = client.post(
        "/api/v1/links",
        data=payload_data,  # Use `data=` for form data
        # headers={"Content-Type": "application/x-www-form-urlencoded"} # Optional: Be explicit if needed
    )

    # Assert: Check the HTTP status code (201 Created)
    assert (
        response.status_code == 201
    ), f"Expected 201, got {response.status_code}. Response: {response.text}"

    # Assert: Verify the mocked service method was called correctly.
    mock_service.create_link.assert_awaited_once()
    # Extract keyword arguments passed to the mock call.
    call_args, call_kwargs = mock_service.create_link.call_args
    # Check if user_id was passed correctly.
    assert call_kwargs["user_id"] == TEST_USER_ID
    # Check if the `link_data` argument passed to the service was a LinkCreate instance
    # with the correct attributes derived from the form data.
    assert isinstance(call_kwargs["link_data"], LinkCreate)
    assert call_kwargs["link_data"].alias == unique_alias
    # Pydantic HttpUrl adds a trailing slash if path is empty
    assert str(call_kwargs["link_data"].default_url) == "https://success.example.com/"

    # Assert: Check the structure and content of the JSON response body.
    response_data = response.json()
    assert response_data["alias"] == unique_alias
    # The response serializes the HttpUrl object, which includes the trailing slash.
    assert response_data["default_url"] == "https://success.example.com/"
    assert response_data["user_id"] == str(TEST_USER_ID)
    assert "id" in response_data and response_data["id"] is not None
    assert response_data["total_clicks"] == 0
    assert "created_at" in response_data
    assert "updated_at" in response_data


@pytest.mark.asyncio
async def test_create_link_missing_alias(client: TestClient):
    """
    Tests the link creation endpoint when the required 'alias' field
    is missing from the submitted form data. Expects a 422 Validation Error.
    """
    # Form data payload missing the 'alias' field.
    payload_data = {"default_url": "https://missing-alias.com"}
    # headers = {"Content-Type": "application/x-www-form-urlencoded"} # TestClient usually handles this

    # Act: Send the POST request.
    response = client.post(
        "/api/v1/links",
        data=payload_data,
        # headers=headers
    )

    # Assert: Expect 422 Unprocessable Entity status code.
    # FastAPI's Form(...) dependency requires the field, resulting in 422 if missing.
    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}. Response: {response.text}"

    # Assert: Check the validation error details in the response.
    error_details = response.json().get("detail", [])
    assert isinstance(error_details, list)
    # Check if the error detail indicates a missing 'alias' field in the request body (form data).
    assert any(
        d.get("loc") == ["body", "alias"] and d.get("type") == "missing"
        for d in error_details
    ), f"Error details did not indicate missing alias: {error_details}"


@pytest.mark.asyncio
async def test_create_link_invalid_alias_format(client: TestClient):
    """
    Tests the link creation endpoint when the 'alias' field is provided
    but contains characters invalid according to the validation rules
    (defined in the LinkCreate schema and endpoint logic). Expects 422.
    """
    # Form data with an alias containing invalid characters (space).
    payload_data = {"alias": "Invalid Alias", "default_url": "https://valid.com"}
    # headers = {"Content-Type": "application/x-www-form-urlencoded"} # TestClient usually handles this

    # Act: Send the POST request.
    response = client.post(
        "/api/v1/links",
        data=payload_data,
        # headers=headers
    )

    # Assert: Expect 422 Unprocessable Entity status code.
    # The validation happens inside the endpoint when `LinkCreate.model_validate` is called.
    assert (
        response.status_code == 422
    ), f"Expected 422, got {response.status_code}. Response: {response.text}"

    # Assert: Check the error detail message.
    # The exact message depends on how Pydantic validation errors are formatted and returned by the endpoint.
    error_detail_text = response.json().get("detail", "")
    # Check for a generic message indicating invalid data, as specific Pydantic error details might vary.
    assert (
        "Invalid form data provided" in error_detail_text
    ), f"Unexpected error detail: {error_detail_text}"
    # Optionally, check for more specific Pydantic error details if the endpoint returns them:
    # assert "alias" in error_detail_text.lower()
    # assert "pattern" in error_detail_text.lower() # If pattern mismatch is the primary error reported
