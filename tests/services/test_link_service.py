# tests/services/test_link_service.py

import pytest

# import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, ANY
from uuid import uuid4, UUID
from datetime import datetime, timezone

from pydantic import HttpUrl

# Imports from the application code
from supabase import AsyncClient
from postgrest.exceptions import APIError as PostgrestAPIError
from postgrest.types import CountMethod
from src.services.link_service import LinkService
from src.services.link_service import POSTGRES_UNIQUE_VIOLATION_CODE

# Import custom exceptions
from src.services.custom_exceptions import (
    AliasConflictException,
    DatabaseException,
    NotFoundException,
    ValidationException,
    ServiceException,
    LinkNotFoundException,
)

# Import Pydantic schemas
from src.schemas.link import LinkCreate, LinkUpdate, LinkResponse, PaginatedLinkResponse
from src.schemas.stats import LinkStatsResponse, TargetClickStat
from src.schemas.enums import TargetTypeEnum


# --- Fixtures ---


@pytest.fixture
def mock_supabase_client():
    """Fixture providing a MagicMock instance simulating the Supabase AsyncClient."""
    mock_client = MagicMock(spec=AsyncClient)
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
            mock_table.execute = AsyncMock(name=f"table({table_name}).execute")
            mock_tables[table_name] = mock_table
        return mock_tables[table_name]

    mock_client.table.side_effect = get_mock_table
    mock_client.rpc.return_value.execute = AsyncMock(name="rpc.execute")
    return mock_client


@pytest.fixture
def link_service(mock_supabase_client: AsyncClient) -> LinkService:
    """Fixture providing an instance of LinkService."""
    return LinkService(supabase_client=mock_supabase_client)


# Helper function
def create_mock_response(data=None, count=None):
    """Creates a MagicMock object mimicking a PostgrestAPIResponse."""
    mock_response = MagicMock()
    mock_response.data = data
    mock_response.count = count
    return mock_response


# --- Test Data Constants ---
TEST_USER_ID = uuid4()
TEST_LINK_ID = uuid4()
TEST_ALIAS = "my-cool-link"
TEST_DEFAULT_URL_STR = "https://example.com/default"
TEST_DEFAULT_URL_HTTPURL = HttpUrl(TEST_DEFAULT_URL_STR)
# String representation *as likely stored/returned from DB*
TEST_DEFAULT_URL_DB_STR = TEST_DEFAULT_URL_STR + "/"
# HttpUrl matching the DB string representation
TEST_DEFAULT_URL_DB_HTTPURL = HttpUrl(TEST_DEFAULT_URL_DB_STR)
NOW = datetime.now(timezone.utc)
NOW_ISO = NOW.isoformat()

# --- Test Cases ---

# === Test Cases for create_link ===


@pytest.mark.asyncio
async def test_create_link_success(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test successful link creation."""
    link_create_data = LinkCreate(
        alias=TEST_ALIAS, default_url=TEST_DEFAULT_URL_HTTPURL
    )

    # --- THIS IS THE CORRECTION ---
    # Expected payload *as passed to the insert method* (before potential DB-side changes)
    # Based on the ACTUAL call shown in the error log.
    expected_insert_payload = {
        "alias": TEST_ALIAS,
        "default_url": TEST_DEFAULT_URL_STR,  # Expect the string WITHOUT the trailing slash here
        "user_id": str(TEST_USER_ID),
    }
    # -------------------------------

    # Expected data structure returned *from* the mocked DB after insertion
    expected_db_return_data = {
        "id": str(TEST_LINK_ID),
        "user_id": str(TEST_USER_ID),
        "alias": TEST_ALIAS,
        "default_url": TEST_DEFAULT_URL_DB_STR,  # Mock DB returns the string WITH the slash
        "total_clicks": 0,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }
    mock_insert_response = create_mock_response(data=[expected_db_return_data])
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_insert_response
    )

    result = await link_service.create_link(
        link_data=link_create_data, user_id=TEST_USER_ID
    )

    assert isinstance(result, LinkResponse)
    assert result.id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    # The result parsed from the DB mock (with slash) should match the HttpUrl with slash
    assert result.default_url == TEST_DEFAULT_URL_DB_HTTPURL
    assert result.user_id == TEST_USER_ID
    assert result.total_clicks == 0

    # Assert the insert call matches the corrected payload (without trailing slash on URL)
    mock_supabase_client.table(link_service.links_table).insert.assert_called_once_with(
        expected_insert_payload
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_link_alias_conflict(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test link creation fails correctly when the alias causes a unique constraint violation."""
    link_create_data = LinkCreate(alias=TEST_ALIAS)
    db_error = PostgrestAPIError(
        {
            "message": f'duplicate key value violates unique constraint "{link_service.links_table}_alias_key"',
            "code": POSTGRES_UNIQUE_VIOLATION_CODE,
            "details": f"Key (alias)=({TEST_ALIAS}) already exists.",
            "hint": None,
        }
    )
    mock_supabase_client.table(link_service.links_table).execute.side_effect = db_error

    with pytest.raises(AliasConflictException):
        await link_service.create_link(link_data=link_create_data, user_id=TEST_USER_ID)

    mock_supabase_client.table(link_service.links_table).insert.assert_called_once()
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


# ... (rest of the tests remain the same as the previous corrected version) ...


@pytest.mark.asyncio
async def test_create_link_other_db_error(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test link creation handling for generic database errors."""
    link_create_data = LinkCreate(alias=TEST_ALIAS)
    db_error = PostgrestAPIError(
        {"message": "Some other internal DB error", "code": "XX000"}
    )
    mock_supabase_client.table(link_service.links_table).execute.side_effect = db_error

    with pytest.raises(DatabaseException, match="Database API error"):
        await link_service.create_link(link_data=link_create_data, user_id=TEST_USER_ID)


# === Test Cases for get_link_by_id ===


@pytest.mark.asyncio
async def test_get_link_by_id_success(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test retrieving an existing link successfully."""
    expected_db_data = {
        "id": str(TEST_LINK_ID),
        "user_id": str(TEST_USER_ID),
        "alias": TEST_ALIAS,
        "default_url": TEST_DEFAULT_URL_DB_STR,  # DB returns string with slash
        "total_clicks": 10,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }
    mock_response = create_mock_response(data=expected_db_data)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    result = await link_service.get_link_by_id(
        link_id=TEST_LINK_ID, user_id=TEST_USER_ID
    )

    assert isinstance(result, LinkResponse)
    assert result.id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    # Compare against the HttpUrl WITH the trailing slash
    assert result.default_url == TEST_DEFAULT_URL_DB_HTTPURL

    mock_supabase_client.table.assert_called_with(link_service.links_table)
    mock_supabase_client.table(link_service.links_table).select.assert_called_with("*")
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(
        link_service.links_table
    ).maybe_single.assert_called_once()
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_link_by_id_not_found(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test retrieving a link that does not exist or is not accessible."""
    mock_response = create_mock_response(data=None)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    with pytest.raises(
        NotFoundException, match="Link not found or you do not have permission"
    ):
        await link_service.get_link_by_id(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)

    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


# === Test Cases for get_links_paginated ===


@pytest.mark.asyncio
async def test_get_links_paginated_success(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test retrieving a paginated list of links."""
    page, page_size = 1, 10
    offset, range_to = 0, 9
    db_item = {
        "id": str(TEST_LINK_ID),
        "alias": TEST_ALIAS,
        "user_id": str(TEST_USER_ID),
        "total_clicks": 5,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
        "default_url": None,
    }
    mock_response = create_mock_response(data=[db_item], count=1)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    result = await link_service.get_links_paginated(
        user_id=TEST_USER_ID, page=page, page_size=page_size
    )

    assert isinstance(result, PaginatedLinkResponse)
    assert result.page == page
    assert result.page_size == page_size
    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].id == TEST_LINK_ID
    assert result.items[0].alias == TEST_ALIAS

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
async def test_get_links_paginated_empty(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test retrieving paginated links when the user has none."""
    page, page_size = 1, 10
    mock_response = create_mock_response(data=[], count=0)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    result = await link_service.get_links_paginated(
        user_id=TEST_USER_ID, page=page, page_size=page_size
    )

    assert isinstance(result, PaginatedLinkResponse)
    assert result.total == 0
    assert len(result.items) == 0
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


# === Test Cases for update_link ===


@pytest.mark.asyncio
async def test_update_link_success(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test successfully updating a link's default_url."""
    new_url_str = "https://new-default.example.com"
    new_url_httpurl = HttpUrl(new_url_str)
    new_url_db_str = new_url_str + "/"

    update_data = LinkUpdate(default_url=new_url_httpurl)
    expected_db_payload = {"default_url": new_url_db_str}
    expected_db_response_data = {
        "id": str(TEST_LINK_ID),
        "user_id": str(TEST_USER_ID),
        "alias": TEST_ALIAS,
        "default_url": new_url_db_str,
        "total_clicks": 0,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }
    mock_update_response = create_mock_response(data=[expected_db_response_data])
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_update_response
    )

    result = await link_service.update_link(
        link_id=TEST_LINK_ID, update_data=update_data, user_id=TEST_USER_ID
    )

    assert isinstance(result, LinkResponse)
    assert result.id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    assert result.default_url == HttpUrl(
        new_url_db_str
    )  # Compare against HttpUrl with slash

    mock_supabase_client.table(link_service.links_table).update.assert_called_once_with(
        expected_db_payload
    )
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_link_clear_default_url(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test successfully clearing a link's default_url by setting it to None."""
    update_data = LinkUpdate(default_url=None)
    expected_db_payload = {"default_url": None}
    expected_db_response_data = {
        "id": str(TEST_LINK_ID),
        "user_id": str(TEST_USER_ID),
        "alias": TEST_ALIAS,
        "default_url": None,
        "total_clicks": 0,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }
    mock_update_response = create_mock_response(data=[expected_db_response_data])
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_update_response
    )

    result = await link_service.update_link(
        link_id=TEST_LINK_ID, update_data=update_data, user_id=TEST_USER_ID
    )

    assert isinstance(result, LinkResponse)
    assert result.id == TEST_LINK_ID
    assert result.default_url is None

    mock_supabase_client.table(link_service.links_table).update.assert_called_once_with(
        expected_db_payload
    )
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_link_not_found(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test attempting to update a link that does not exist or is inaccessible."""
    update_url_str = "https://some-url.com"
    update_url_httpurl = HttpUrl(update_url_str)
    update_data = LinkUpdate(default_url=update_url_httpurl)
    expected_db_payload = {"default_url": update_url_str + "/"}

    mock_update_response = create_mock_response(data=[])
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_update_response
    )

    with pytest.raises(
        NotFoundException,
        match="Link not found or you do not have permission to update it",
    ):
        await link_service.update_link(
            link_id=TEST_LINK_ID, update_data=update_data, user_id=TEST_USER_ID
        )

    mock_supabase_client.table(link_service.links_table).update.assert_called_once_with(
        expected_db_payload
    )
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_link_no_changes(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test updating a link when the provided update data is empty."""
    update_data = LinkUpdate()
    expected_db_data_for_get = {
        "id": str(TEST_LINK_ID),
        "alias": TEST_ALIAS,
        "user_id": str(TEST_USER_ID),
        "default_url": TEST_DEFAULT_URL_DB_STR,
        "total_clicks": 5,
        "created_at": NOW_ISO,
        "updated_at": NOW_ISO,
    }
    mock_get_response = create_mock_response(data=expected_db_data_for_get)
    mock_table_instance = mock_supabase_client.table(link_service.links_table)
    mock_table_instance.reset_mock()
    mock_table_instance.select.return_value = mock_table_instance
    mock_table_instance.eq.return_value = mock_table_instance
    mock_table_instance.maybe_single.return_value = mock_table_instance
    mock_table_instance.execute = AsyncMock(return_value=mock_get_response)

    result = await link_service.update_link(
        link_id=TEST_LINK_ID, update_data=update_data, user_id=TEST_USER_ID
    )

    assert result.id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    # Compare against the HttpUrl WITH the trailing slash
    assert result.default_url == TEST_DEFAULT_URL_DB_HTTPURL

    mock_table_instance.update.assert_not_called()
    mock_table_instance.select.assert_called_with("*")
    mock_table_instance.eq.assert_called_with("id", str(TEST_LINK_ID))
    mock_table_instance.maybe_single.assert_called_once()
    mock_table_instance.execute.assert_awaited_once()


# === Test Cases for delete_link ===


@pytest.mark.asyncio
async def test_delete_link_success(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test successful deletion of a link."""
    mock_response = create_mock_response(count=1)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    await link_service.delete_link(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)

    mock_supabase_client.table(link_service.links_table).delete.assert_called_once_with(
        count=CountMethod.exact
    )
    mock_supabase_client.table(link_service.links_table).eq.assert_called_with(
        "id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_link_not_found(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test attempting to delete a link that does not exist or is inaccessible."""
    mock_response = create_mock_response(count=0)
    mock_supabase_client.table(link_service.links_table).execute.return_value = (
        mock_response
    )

    with pytest.raises(
        NotFoundException,
        match="Link not found or you do not have permission to delete it",
    ):
        await link_service.delete_link(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)

    mock_supabase_client.table(link_service.links_table).execute.assert_awaited_once()


# === Test Cases for get_link_statistics ===


@pytest.mark.asyncio
async def test_get_link_statistics_success(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test retrieving statistics for a link with associated rules."""
    mock_link_data = {"id": str(TEST_LINK_ID), "alias": TEST_ALIAS, "total_clicks": 150}
    mock_link_response = create_mock_response(data=mock_link_data)
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
            "current_clicks": 45,
        },
    ]
    mock_rules_response = create_mock_response(data=mock_rules_data)
    mock_link_execute = AsyncMock(return_value=mock_link_response)
    mock_rules_execute = AsyncMock(return_value=mock_rules_response)
    mock_supabase_client.table(link_service.links_table).execute = mock_link_execute
    mock_supabase_client.table(link_service.rules_table).execute = mock_rules_execute

    result = await link_service.get_link_statistics(
        link_id=TEST_LINK_ID, user_id=TEST_USER_ID
    )

    assert isinstance(result, LinkStatsResponse)
    assert result.link_id == TEST_LINK_ID
    assert result.alias == TEST_ALIAS
    assert result.total_clicks == 150
    assert len(result.target_clicks) == 2
    assert result.target_clicks[0].rule_id == rule1_id
    assert result.target_clicks[0].target_type == TargetTypeEnum.URL
    assert result.target_clicks[0].target_value_preview == "http://rule1.com"
    assert result.target_clicks[0].current_clicks == 100
    assert result.target_clicks[1].rule_id == rule2_id
    assert result.target_clicks[1].target_type == TargetTypeEnum.HTML
    assert result.target_clicks[1].target_value_preview == "[Custom HTML Content]"
    assert result.target_clicks[1].current_clicks == 45

    mock_supabase_client.table(link_service.links_table).select.assert_called_with(
        "id, alias, total_clicks"
    )
    mock_link_execute.assert_awaited_once()
    mock_supabase_client.table(link_service.rules_table).select.assert_called_with(
        "id, target_type, target_value, current_clicks"
    )
    mock_supabase_client.table(link_service.rules_table).eq.assert_called_with(
        "link_id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(link_service.rules_table).order.assert_called_with(
        "priority", desc=False
    )
    mock_rules_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_link_statistics_link_not_found(
    link_service: LinkService, mock_supabase_client: MagicMock
):
    """Test retrieving statistics when the parent link is not found."""
    mock_link_response = create_mock_response(data=None)
    mock_link_execute = AsyncMock(return_value=mock_link_response)
    mock_supabase_client.table(link_service.links_table).execute = mock_link_execute
    mock_rules_execute = AsyncMock()
    mock_supabase_client.table(link_service.rules_table).execute = mock_rules_execute

    with pytest.raises(
        NotFoundException, match="Link not found or you do not have permission"
    ):
        await link_service.get_link_statistics(
            link_id=TEST_LINK_ID, user_id=TEST_USER_ID
        )

    mock_link_execute.assert_awaited_once()
    mock_rules_execute.assert_not_awaited()
