# tests/services/test_link_service.py

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, ANY  # Importuj ANY
from uuid import uuid4, UUID
from datetime import datetime, timezone

from pydantic import HttpUrl  # Potrzebne do porównania URL

# Importy z Twojego kodu
from supabase import AsyncClient  # Importuj AsyncClient do specyfikacji mocka
from postgrest.exceptions import APIError as PostgrestAPIError
from postgrest.types import CountMethod  # Importuj CountMethod
from src.services.link_service import LinkService

# Importuj WSZYSTKIE wyjątki biznesowe, które mogą być rzucone i łapane
from src.services.custom_exceptions import (
    AliasConflictException,
    DatabaseException,
    NotFoundException,
    ParentLinkNotFoundException,  # Dodaj, jeśli jest używany (choć nie w LinkService)
    PriorityConflictException,  # Dodaj, jeśli jest używany
    ValidationException,  # Dodaj, jeśli jest używany
    ServiceException,
)
from src.schemas.link import LinkCreate, LinkUpdate, LinkResponse, PaginatedLinkResponse
from src.schemas.stats import LinkStatsResponse, TargetClickStat
from src.schemas.enums import TargetTypeEnum


# --- Fixtures ---


@pytest.fixture
def mock_supabase_client(mocker):
    """Fixture to create a mock Supabase AsyncClient."""
    mock_client = MagicMock(spec=AsyncClient)

    # --- Precyzyjniejsze mockowanie łańcuchów ---
    mock_tables = {}

    def get_mock_table(table_name):
        if table_name not in mock_tables:
            mock_table = MagicMock(name=f"table({table_name})")
            mock_table.select.return_value = mock_table
            mock_table.insert.return_value = mock_table
            mock_table.update.return_value = mock_table
            mock_table.delete.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.maybe_single.return_value = mock_table
            mock_table.order.return_value = mock_table
            mock_table.range.return_value = mock_table
            # Na końcu łańcucha jest execute, które jest AsyncMock
            mock_table.execute = AsyncMock(name=f"table({table_name}).execute")
            mock_tables[table_name] = mock_table
        return mock_tables[table_name]

    mock_client.table.side_effect = get_mock_table
    mock_client.rpc.return_value.execute = AsyncMock(name="rpc.execute")

    return mock_client


@pytest.fixture
def link_service(mock_supabase_client):
    """Fixture to create an instance of LinkService with the mocked client."""
    return LinkService(supabase_client=mock_supabase_client)


# Helper function to create mock DB response objects
def create_mock_response(data=None, count=None):
    mock_response = MagicMock()
    mock_response.data = data
    mock_response.count = count
    return mock_response


# --- Test Data ---
TEST_USER_ID = uuid4()
TEST_LINK_ID = uuid4()
TEST_ALIAS = "my-cool-link"
TEST_DEFAULT_URL = "https://example.com/default"
NOW = datetime.now(timezone.utc)

# --- Test Cases ---

# === Testy dla create_link ===


@pytest.mark.asyncio
async def test_create_link_success(link_service, mock_supabase_client):
    """Test successful link creation."""
    link_create_data = LinkCreate(alias=TEST_ALIAS, default_url=TEST_DEFAULT_URL)
    expected_db_data = {
        "id": str(TEST_LINK_ID),
        "user_id": str(TEST_USER_ID),
        "alias": TEST_ALIAS,
        "default_url": TEST_DEFAULT_URL,
        "total_clicks": 0,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    mock_response = create_mock_response(data=[expected_db_data])  # Insert zwraca listę
    # Konfigurujemy mock dla konkretnej tabeli i metody execute
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act
    result = await link_service.create_link(
        link_data=link_create_data, user_id=TEST_USER_ID
    )

    # Assert
    assert isinstance(result, LinkResponse)
    assert result.id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    assert result.default_url == HttpUrl(
        TEST_DEFAULT_URL
    )  # Pydantic powinien sparsować
    assert result.user_id == TEST_USER_ID
    # Sprawdzamy, czy metoda insert została wywołana na mocku tabeli z poprawnymi danymi
    mock_supabase_client.table(link_service.links_table).insert.assert_called_once_with(
        {
            "alias": TEST_ALIAS,
            "default_url": TEST_DEFAULT_URL,  # Serwis konwertuje HttpUrl na string
            "user_id": str(TEST_USER_ID),
        }
    )
    # Sprawdzamy, czy metoda execute została wywołana na końcu łańcucha insert
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_link_alias_conflict(link_service, mock_supabase_client):
    """Test link creation when alias already exists."""
    link_create_data = LinkCreate(alias=TEST_ALIAS)
    db_error = PostgrestAPIError(
        {
            "message": 'duplicate key value violates unique constraint "routr_links_alias_key"',
            # Użyj stringa "23505" lub zaimportuj stałą
            "code": "23505",
            "details": "Key (alias)=(my-cool-link) already exists.",
        }
    )
    # Ustaw side_effect na mocku execute dla tabeli linków
    mock_supabase_client.table(link_service.links_table).execute.side_effect = db_error

    # Act & Assert
    with pytest.raises(AliasConflictException):
        await link_service.create_link(link_data=link_create_data, user_id=TEST_USER_ID)

    # Sprawdź, czy próbowano wykonać insert
    mock_supabase_client.table(link_service.links_table).insert.assert_called_once()
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_link_other_db_error(link_service, mock_supabase_client):
    """Test link creation with a generic DB error."""
    link_create_data = LinkCreate(alias=TEST_ALIAS)
    db_error = PostgrestAPIError({"message": "Some other DB error"})
    mock_supabase_client.table(link_service.links_table).execute.side_effect = db_error

    # Act & Assert
    with pytest.raises(DatabaseException, match="Database API error"):
        await link_service.create_link(link_data=link_create_data, user_id=TEST_USER_ID)


# === Testy dla get_link_by_id ===


@pytest.mark.asyncio
async def test_get_link_by_id_success(link_service, mock_supabase_client):
    """Test retrieving an existing link."""
    expected_db_data = {
        "id": str(TEST_LINK_ID),
        "user_id": str(TEST_USER_ID),
        "alias": TEST_ALIAS,
        "default_url": TEST_DEFAULT_URL,
        "total_clicks": 10,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    mock_response = create_mock_response(data=expected_db_data)
    # Ustaw return_value na mocku execute dla tabeli linków
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act
    result = await link_service.get_link_by_id(
        link_id=TEST_LINK_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert isinstance(result, LinkResponse)
    assert result.id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    # Sprawdź wywołanie Supabase (łańcuch select -> eq -> maybe_single -> execute)
    mock_supabase_client.table(link_service.links_table).select.assert_called_with("*")
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(
        link_service.links_table
    ).maybe_single.assert_called_once()
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_link_by_id_not_found(link_service, mock_supabase_client):
    """Test retrieving a non-existent link or one not owned by user."""
    mock_response = create_mock_response(data=None)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act & Assert
    with pytest.raises(NotFoundException):
        await link_service.get_link_by_id(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)

    # Sprawdź wywołanie Supabase
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


# === Testy dla get_links_paginated ===


@pytest.mark.asyncio
async def test_get_links_paginated_success(link_service, mock_supabase_client):
    """Test retrieving a paginated list of links."""
    page, page_size = 1, 10
    offset, range_to = 0, 9
    db_item = {
        "id": str(TEST_LINK_ID),
        "alias": TEST_ALIAS,
        "user_id": str(TEST_USER_ID),
        "total_clicks": 5,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "default_url": None,
    }
    mock_response = create_mock_response(data=[db_item], count=1)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act
    result = await link_service.get_links_paginated(
        user_id=TEST_USER_ID, page=page, page_size=page_size
    )

    # Assert
    assert isinstance(result, PaginatedLinkResponse)
    assert result.page == page
    assert result.page_size == page_size
    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].id == TEST_LINK_ID
    # Sprawdź wywołanie Supabase
    mock_supabase_client.table(link_service.links_table).select.assert_called_with(
        "*", count=CountMethod.exact
    )
    mock_supabase_client.table(link_service.links_table).order.assert_called_with(
        "created_at", desc=True
    )
    mock_supabase_client.table(link_service.links_table).range.assert_called_with(
        offset, range_to
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_links_paginated_empty(link_service, mock_supabase_client):
    """Test retrieving paginated links when user has none."""
    page, page_size = 1, 10
    mock_response = create_mock_response(data=[], count=0)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act
    result = await link_service.get_links_paginated(
        user_id=TEST_USER_ID, page=page, page_size=page_size
    )

    # Assert
    assert isinstance(result, PaginatedLinkResponse)
    assert result.total == 0
    assert len(result.items) == 0
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


# === Testy dla update_link ===


@pytest.mark.asyncio
async def test_update_link_success(link_service, mock_supabase_client):
    """Test successfully updating a link's default_url."""
    new_url = "https://new-default.example.com"
    # W teście tworzymy obiekt Pydantic, jakby przyszedł z API
    update_data = LinkUpdate(default_url=HttpUrl(new_url))

    # <<< POPRAWKA: Oczekiwany payload do DB powinien mieć URL z ukośnikiem,
    # bo tak prawdopodobnie konwertuje go str(HttpUrl(...)) w serwisie
    expected_db_payload = {"default_url": new_url + "/"}

    # Arrange: Mock DB response after update
    # Dane zwracane z DB po update
    expected_db_response_data = {
        "id": str(TEST_LINK_ID),
        "user_id": str(TEST_USER_ID),
        "alias": TEST_ALIAS,
        "default_url": new_url
        + "/",  # Baza danych zwróci zaktualizowany string (z ukośnikiem)
        "total_clicks": 0,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),  # W rzeczywistości DB by to zaktualizowało
    }
    mock_response = create_mock_response(
        data=[expected_db_response_data]
    )  # Update zwraca listę
    # Konfigurujemy mock dla metody execute tabeli linków
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act
    result = await link_service.update_link(
        link_id=TEST_LINK_ID, update_data=update_data, user_id=TEST_USER_ID
    )

    # Assert: Sprawdź typ i podstawowe pola zwróconego obiektu
    assert isinstance(result, LinkResponse)
    assert result.id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    # Assert: Sprawdź URL - Pydantic w LinkResponse sparsuje string z DB do HttpUrl
    # Porównujemy obiekty HttpUrl, które powinny być równe mimo różnicy w ukośniku
    assert result.default_url == HttpUrl(new_url)

    # Assert: Sprawdź, czy wywołano metody mocka Supabase z poprawnymi argumentami
    mock_supabase_client.table(link_service.links_table).update.assert_called_once_with(
        expected_db_payload  # Sprawdź, czy do update przekazano string z ukośnikiem
    )
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_link_not_found(link_service, mock_supabase_client):
    """Test updating a non-existent link."""
    update_data = LinkUpdate(default_url=HttpUrl("https://some-url.com"))
    mock_response = create_mock_response(data=[])  # Update nic nie zwraca w .data
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act & Assert
    with pytest.raises(NotFoundException):
        await link_service.update_link(
            link_id=TEST_LINK_ID, update_data=update_data, user_id=TEST_USER_ID
        )

    # Sprawdź wywołanie Supabase
    mock_supabase_client.table(link_service.links_table).update.assert_called_once_with(
        {"default_url": "https://some-url.com/"}
    )  # Pydantic może dodać /
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_link_no_changes(link_service, mock_supabase_client):
    """Test updating a link with no actual changes (empty payload)."""
    update_data = LinkUpdate()  # Pusty obiekt update

    # Mock the get_link_by_id call
    expected_db_data = {
        "id": str(TEST_LINK_ID),
        "alias": TEST_ALIAS,
        "user_id": str(TEST_USER_ID),
        "total_clicks": 5,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    mock_get_response = create_mock_response(data=expected_db_data)
    # Konfigurujemy mock dla wywołania get_link_by_id
    # Musimy to zrobić bardziej precyzyjnie, bo execute jest używane wielokrotnie
    mock_get_execute = AsyncMock(return_value=mock_get_response)
    mock_supabase_client.table(link_service.links_table).execute = (
        mock_get_execute  # Ustawiamy na mocku tabeli
    )

    # Act
    result = await link_service.update_link(
        link_id=TEST_LINK_ID, update_data=update_data, user_id=TEST_USER_ID
    )

    # Assert: Should return the current state
    assert result.id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    # Assert: Update NIE został wywołany
    mock_supabase_client.table(link_service.links_table).update.assert_not_called()
    # Assert: Get ZOSTAŁ wywołany
    mock_supabase_client.table(link_service.links_table).select.assert_called_with("*")
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(
        link_service.links_table
    ).maybe_single.assert_called_once()
    mock_get_execute.assert_awaited_once()  # Sprawdzamy wywołanie execute skonfigurowanego dla get


# === Testy dla delete_link ===


@pytest.mark.asyncio
async def test_delete_link_success(link_service, mock_supabase_client):
    """Test successful link deletion."""
    mock_response = create_mock_response(count=1)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act
    await link_service.delete_link(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)

    # Assert
    mock_supabase_client.table(link_service.links_table).delete.assert_called_once_with(
        count=CountMethod.exact
    )
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_link_not_found(link_service, mock_supabase_client):
    """Test deleting a non-existent link."""
    mock_response = create_mock_response(count=0)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    # Act & Assert
    with pytest.raises(NotFoundException):
        await link_service.delete_link(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)

    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


# === Testy dla get_link_statistics ===


@pytest.mark.asyncio
async def test_get_link_statistics_success(link_service, mock_supabase_client):
    """Test retrieving link statistics."""
    # Arrange: Mock link data fetch
    mock_link_data = {"id": str(TEST_LINK_ID), "alias": TEST_ALIAS, "total_clicks": 150}
    mock_link_response = create_mock_response(data=mock_link_data)

    # Arrange: Mock rules data fetch
    rule1_id = uuid4()
    rule2_id = uuid4()
    mock_rules_data = [
        {
            "id": str(rule1_id),
            "target_type": TargetTypeEnum.URL.value,
            "target_value": "http://rule1.com",
            "current_clicks": 100,
        },
        {
            "id": str(rule2_id),
            "target_type": TargetTypeEnum.HTML.value,
            "target_value": "<h1>Hi</h1>",
            "current_clicks": 50,
        },
    ]
    mock_rules_response = create_mock_response(data=mock_rules_data)

    # Konfiguracja mock execute dla różnych tabel
    mock_link_execute = AsyncMock(return_value=mock_link_response)
    mock_rules_execute = AsyncMock(return_value=mock_rules_response)

    def execute_side_effect(*args, **kwargs):
        # Rozpoznajemy wywołanie na podstawie obiektu 'self' w łańcuchu mocka
        # To jest trochę skomplikowane, może być prostszy sposób zależy od mock frameworka
        if mock_supabase_client.table.return_value == mock_supabase_client.table(
            link_service.links_table
        ):
            return mock_link_execute(*args, **kwargs)
        elif mock_supabase_client.table.return_value == mock_supabase_client.table(
            link_service.rules_table
        ):
            return mock_rules_execute(*args, **kwargs)
        raise Exception("Unexpected table for execute mock")

    # Używamy side_effect do rozróżnienia wywołań (prostsze może być mockowanie `execute` na mockach tabel)
    mock_supabase_client.table(link_service.links_table).execute = mock_link_execute
    mock_supabase_client.table(link_service.rules_table).execute = mock_rules_execute

    # Act
    result = await link_service.get_link_statistics(
        link_id=TEST_LINK_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert isinstance(result, LinkStatsResponse)
    assert result.link_id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    assert result.total_clicks == 150
    assert len(result.target_clicks) == 2
    assert result.target_clicks[0].rule_id == rule1_id
    assert result.target_clicks[0].target_type == TargetTypeEnum.URL
    assert result.target_clicks[1].rule_id == rule2_id
    assert result.target_clicks[1].target_type == TargetTypeEnum.HTML

    # Sprawdź wywołania Supabase
    mock_link_execute.assert_awaited_once()
    mock_rules_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_link_statistics_link_not_found(link_service, mock_supabase_client):
    """Test retrieving statistics for a non-existent link."""
    mock_link_response = create_mock_response(data=None)
    # Konfigurujemy mock execute dla tabeli linków
    mock_link_execute = AsyncMock(return_value=mock_link_response)
    mock_supabase_client.table(link_service.links_table).execute = mock_link_execute

    # Act & Assert
    with pytest.raises(NotFoundException):
        await link_service.get_link_statistics(
            link_id=TEST_LINK_ID, user_id=TEST_USER_ID
        )

    # Assert that link fetch was attempted
    mock_link_execute.assert_awaited_once()
    # Assert that the rules table mock's execute method was never awaited
    mock_supabase_client.table(link_service.rules_table).execute.assert_not_awaited()
