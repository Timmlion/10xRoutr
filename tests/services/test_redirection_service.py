# tests/services/test_redirection_service.py

import pytest

# import pytest_asyncio # Not needed unless using async fixtures
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
from postgrest.exceptions import APIError as PostgrestAPIError

# Import the code to be tested
from src.services.redirection_service import RedirectionService, RedirectionAction
from src.services.custom_exceptions import LinkNotFoundException, DatabaseException
from src.schemas.enums import RuleTypeEnum, TargetTypeEnum
from supabase import AsyncClient

# --- Fixtures ---


@pytest.fixture
def mock_supabase_client():
    """Fixture to create a mock Supabase AsyncClient with improved chaining."""
    mock_client = MagicMock(spec=AsyncClient)
    mock_tables = {}  # Cache for table mocks

    def get_mock_table(table_name):
        if table_name not in mock_tables:
            mock_table = MagicMock(name=f"table({table_name})")
            # Configure chainable methods to return the mock_table itself
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.limit.return_value = mock_table
            mock_table.maybe_single.return_value = mock_table
            mock_table.order.return_value = mock_table
            # The final execute() method is an AsyncMock specific to this table instance
            mock_table.execute = AsyncMock(name=f"table({table_name}).execute")
            mock_tables[table_name] = mock_table
        return mock_tables[table_name]

    mock_rpcs = {}  # Cache for RPC mocks

    def get_mock_rpc(rpc_name, params):
        # Create a unique key for the specific RPC call if needed, or just use rpc_name
        rpc_key = rpc_name
        if rpc_key not in mock_rpcs:
            # This mock represents the object returned by client.rpc(...)
            mock_rpc_intermediate = MagicMock(name=f"rpc({rpc_name})")
            # This is the final execute() mock for this specific RPC call
            mock_rpc_intermediate.execute = AsyncMock(name=f"rpc({rpc_name}).execute")
            mock_rpcs[rpc_key] = mock_rpc_intermediate
        return mock_rpcs[rpc_key]

    # Configure the main client mock methods
    mock_client.table.side_effect = get_mock_table  # Use the factory for table calls
    mock_client.rpc.side_effect = get_mock_rpc  # Use the factory for rpc calls

    return mock_client


@pytest.fixture
def redirection_service(mock_supabase_client: AsyncClient) -> RedirectionService:
    """Fixture providing an instance of RedirectionService."""
    return RedirectionService(supabase_client=mock_supabase_client)


# Helper function
def create_mock_response(data=None, count=None):
    """Creates a MagicMock object mimicking a PostgrestAPIResponse."""
    mock_response = MagicMock()
    mock_response.data = data
    mock_response.count = count
    return mock_response


# --- Test Data Constants ---
TEST_ALIAS = "test-alias"
TEST_LINK_ID = uuid4()
TEST_RULE_ID_TIME = uuid4()
TEST_RULE_ID_CLICKS = uuid4()
TEST_DEFAULT_URL = "https://default.example.com"
TEST_RULE_URL = "https://rule-target.example.com"
TEST_RULE_HTML = "<h1>Hello</h1>"
NOW = datetime.now(timezone.utc)

# Define table names used by the service
LINKS_TABLE_NAME = "routr_links"
RULES_TABLE_NAME = "routing_rules"

# --- Test Cases ---


@pytest.mark.asyncio
async def test_process_redirection_alias_not_found(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection process when the alias does not exist."""
    mock_response = create_mock_response(data=None)
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.return_value = mock_response

    with pytest.raises(LinkNotFoundException):
        await redirection_service.process_redirection(TEST_ALIAS)

    mock_supabase_client.table.assert_called_with(LINKS_TABLE_NAME)
    table_mock = mock_supabase_client.table(LINKS_TABLE_NAME)
    table_mock.select.assert_called_with("id, default_url")
    table_mock.eq.assert_called_with("alias", TEST_ALIAS)
    table_mock.limit.assert_called_with(1)
    table_mock.maybe_single.assert_called_once()
    table_mock.execute.assert_awaited_once()
    mock_supabase_client.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_process_redirection_db_error_fetching_link(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection when a DB error occurs fetching the link."""
    db_error = PostgrestAPIError({"message": "DB Connection Error"})
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.side_effect = db_error

    with pytest.raises(DatabaseException):
        await redirection_service.process_redirection(TEST_ALIAS)

    table_mock = mock_supabase_client.table(LINKS_TABLE_NAME)
    table_mock.select.assert_called_with("id, default_url")
    table_mock.eq.assert_called_with("alias", TEST_ALIAS)
    table_mock.limit.assert_called_with(1)
    table_mock.maybe_single.assert_called_once()
    table_mock.execute.assert_awaited_once()
    mock_supabase_client.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_process_redirection_rule_match_url(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection when a time-based URL rule matches."""
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": TEST_DEFAULT_URL}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.return_value = (
        mock_link_response
    )

    # --- CORRECTION: Remove the manually added "Z" ---
    # .isoformat() on a timezone-aware object already includes the offset (+00:00)
    start_time_iso = (NOW - timedelta(hours=1)).isoformat()
    end_time_iso = (NOW + timedelta(hours=1)).isoformat()
    # ------------------------------------------------

    mock_rule_data = [
        {
            "id": str(TEST_RULE_ID_TIME),
            "priority": 1,
            "rule_type": RuleTypeEnum.TIME.value,
            "target_type": TargetTypeEnum.URL.value,
            "target_value": TEST_RULE_URL,
            "start_time": start_time_iso,  # Use the corrected ISO string
            "end_time": end_time_iso,  # Use the corrected ISO string
            "max_clicks": None,
            "current_clicks": 0,
        }
    ]
    mock_rules_response = create_mock_response(data=mock_rule_data)
    mock_supabase_client.table(RULES_TABLE_NAME).execute.return_value = (
        mock_rules_response
    )

    mock_supabase_client.rpc("increment_link_clicks", ANY).execute.return_value = None
    mock_supabase_client.rpc("increment_rule_clicks", ANY).execute.return_value = None

    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    assert action == RedirectionAction.REDIRECT_URL
    assert value == TEST_RULE_URL

    mock_supabase_client.table(LINKS_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.table(RULES_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    ).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_rule_clicks", {"rule_uuid": str(TEST_RULE_ID_TIME)}
    ).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_redirection_rule_match_html(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection when a click-based HTML rule matches."""
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": None}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.return_value = (
        mock_link_response
    )

    mock_rule_data = [
        {
            "id": str(TEST_RULE_ID_CLICKS),
            "priority": 1,
            "rule_type": RuleTypeEnum.CLICKS.value,
            "target_type": TargetTypeEnum.HTML.value,
            "target_value": TEST_RULE_HTML,
            "start_time": None,
            "end_time": None,
            "max_clicks": 100,
            "current_clicks": 50,
        }
    ]
    mock_rules_response = create_mock_response(data=mock_rule_data)
    mock_supabase_client.table(RULES_TABLE_NAME).execute.return_value = (
        mock_rules_response
    )

    mock_supabase_client.rpc("increment_link_clicks", ANY).execute.return_value = None
    mock_supabase_client.rpc("increment_rule_clicks", ANY).execute.return_value = None

    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    assert action == RedirectionAction.SERVE_HTML
    assert value == TEST_RULE_HTML

    mock_supabase_client.table(LINKS_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.table(RULES_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    ).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_rule_clicks", {"rule_uuid": str(TEST_RULE_ID_CLICKS)}
    ).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_redirection_no_rule_match_with_default(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection falls back to default URL when no rules match."""
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": TEST_DEFAULT_URL}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.return_value = (
        mock_link_response
    )

    # --- CORRECTION: Use valid ISO strings ---
    start_time_iso = (NOW - timedelta(hours=2)).isoformat()
    end_time_iso = (NOW - timedelta(hours=1)).isoformat()
    # -----------------------------------------

    mock_rule_data = [
        {
            "id": str(TEST_RULE_ID_TIME),
            "priority": 1,
            "rule_type": RuleTypeEnum.TIME.value,
            "target_type": TargetTypeEnum.URL.value,
            "target_value": TEST_RULE_URL,
            "start_time": start_time_iso,  # Expired
            "end_time": end_time_iso,  # Expired
            "max_clicks": None,
            "current_clicks": 0,
        }
    ]
    mock_rules_response = create_mock_response(data=mock_rule_data)
    mock_supabase_client.table(RULES_TABLE_NAME).execute.return_value = (
        mock_rules_response
    )

    mock_supabase_client.rpc("increment_link_clicks", ANY).execute.return_value = None
    rule_rpc_mock_execute = mock_supabase_client.rpc(
        "increment_rule_clicks", ANY
    ).execute

    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    assert action == RedirectionAction.REDIRECT_DEFAULT
    assert value == TEST_DEFAULT_URL

    mock_supabase_client.table(LINKS_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.table(RULES_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    ).execute.assert_awaited_once()
    rule_rpc_mock_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_redirection_no_rule_match_no_default(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection falls back to global fallback when no rules match and no default URL."""
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": None}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.return_value = (
        mock_link_response
    )

    mock_rules_response = create_mock_response(data=[])
    mock_supabase_client.table(RULES_TABLE_NAME).execute.return_value = (
        mock_rules_response
    )

    mock_supabase_client.rpc("increment_link_clicks", ANY).execute.return_value = None
    rule_rpc_mock_execute = mock_supabase_client.rpc(
        "increment_rule_clicks", ANY
    ).execute

    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    assert action == RedirectionAction.REDIRECT_GLOBAL_FALLBACK
    assert value is None

    mock_supabase_client.table(LINKS_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.table(RULES_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    ).execute.assert_awaited_once()
    rule_rpc_mock_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_redirection_db_error_fetching_rules(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection when a DB error occurs fetching rules."""
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": TEST_DEFAULT_URL}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.return_value = (
        mock_link_response
    )

    db_error = PostgrestAPIError({"message": "DB Error Fetching Rules"})
    mock_supabase_client.table(RULES_TABLE_NAME).execute.side_effect = db_error

    mock_supabase_client.rpc("increment_link_clicks", ANY).execute.return_value = None
    rule_rpc_mock_execute = mock_supabase_client.rpc(
        "increment_rule_clicks", ANY
    ).execute

    with pytest.raises(DatabaseException, match="Database error fetching rules"):
        await redirection_service.process_redirection(TEST_ALIAS)

    mock_supabase_client.table(LINKS_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.table(RULES_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    ).execute.assert_awaited_once()
    rule_rpc_mock_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_redirection_error_incrementing_link_clicks(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection proceeds even if incrementing link clicks fails."""
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": None}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.return_value = (
        mock_link_response
    )

    mock_rule_data = [
        {
            "id": str(TEST_RULE_ID_CLICKS),
            "rule_type": RuleTypeEnum.CLICKS.value,
            "target_type": TargetTypeEnum.URL.value,
            "target_value": TEST_RULE_URL,
            "max_clicks": 10,
            "current_clicks": 5,
        }
    ]
    mock_rules_response = create_mock_response(data=mock_rule_data)
    mock_supabase_client.table(RULES_TABLE_NAME).execute.return_value = (
        mock_rules_response
    )

    link_rpc_error = PostgrestAPIError({"message": "Link RPC Failed"})
    mock_supabase_client.rpc("increment_link_clicks", ANY).execute.side_effect = (
        link_rpc_error
    )
    mock_supabase_client.rpc("increment_rule_clicks", ANY).execute.return_value = None

    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    assert action == RedirectionAction.REDIRECT_URL
    assert value == TEST_RULE_URL

    mock_supabase_client.table(LINKS_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.table(RULES_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    ).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_rule_clicks", {"rule_uuid": str(TEST_RULE_ID_CLICKS)}
    ).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_redirection_error_incrementing_rule_clicks(
    redirection_service: RedirectionService, mock_supabase_client: MagicMock
):
    """Test redirection proceeds even if incrementing rule clicks fails."""
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": None}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(LINKS_TABLE_NAME).execute.return_value = (
        mock_link_response
    )

    mock_rule_data = [
        {
            "id": str(TEST_RULE_ID_CLICKS),
            "rule_type": RuleTypeEnum.CLICKS.value,
            "target_type": TargetTypeEnum.URL.value,
            "target_value": TEST_RULE_URL,
            "max_clicks": 10,
            "current_clicks": 5,
        }
    ]
    mock_rules_response = create_mock_response(data=mock_rule_data)
    mock_supabase_client.table(RULES_TABLE_NAME).execute.return_value = (
        mock_rules_response
    )

    rule_rpc_error = PostgrestAPIError({"message": "Rule RPC Failed"})
    mock_supabase_client.rpc("increment_link_clicks", ANY).execute.return_value = None
    mock_supabase_client.rpc("increment_rule_clicks", ANY).execute.side_effect = (
        rule_rpc_error
    )

    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    assert action == RedirectionAction.REDIRECT_URL
    assert value == TEST_RULE_URL

    mock_supabase_client.table(LINKS_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.table(RULES_TABLE_NAME).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    ).execute.assert_awaited_once()
    mock_supabase_client.rpc(
        "increment_rule_clicks", {"rule_uuid": str(TEST_RULE_ID_CLICKS)}
    ).execute.assert_awaited_once()
