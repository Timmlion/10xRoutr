# tests/services/test_redirection_service.py

import pytest
import pytest_asyncio  # Import the asyncio plugin
from unittest.mock import AsyncMock, MagicMock, patch, ANY  # Import mocking tools
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
def mock_supabase_client(mocker):
    """Fixture to create a mock Supabase AsyncClient."""
    # We need to mock the chained calls. We'll mock the final execute() method.
    # Use AsyncMock for awaitable methods/return values.
    mock_client = MagicMock(
        spec=AsyncClient
    )  # Use MagicMock to mimic AsyncClient structure

    # Mock the .table() method chain for links
    mock_links_table = MagicMock()
    mock_client.table.return_value = mock_links_table  # Default return for table()
    mock_links_table.select.return_value.eq.return_value.limit.return_value.maybe_single.return_value.execute = (
        AsyncMock()
    )

    # Mock the .table() method chain for rules
    mock_rules_table = MagicMock()

    # We need to handle different return values for table based on table name
    def table_side_effect(table_name):
        if table_name == "routr_links":
            return mock_links_table
        elif table_name == "routing_rules":
            return mock_rules_table
        else:
            return MagicMock()  # Default mock for other tables if needed

    mock_client.table.side_effect = table_side_effect

    mock_rules_table.select.return_value.eq.return_value.order.return_value.execute = (
        AsyncMock()
    )

    # Mock the .rpc() method chain
    mock_client.rpc.return_value.execute = AsyncMock()

    return mock_client


@pytest.fixture
def redirection_service(mock_supabase_client):
    """Fixture to create an instance of RedirectionService with the mocked client."""
    return RedirectionService(supabase_client=mock_supabase_client)


# Helper function to create mock DB response objects
def create_mock_response(data=None, count=None):
    mock_response = MagicMock()
    mock_response.data = data
    mock_response.count = count
    return mock_response


# --- Test Data ---
TEST_ALIAS = "test-alias"
TEST_LINK_ID = uuid4()
TEST_RULE_ID_TIME = uuid4()
TEST_RULE_ID_CLICKS = uuid4()
TEST_DEFAULT_URL = "https://default.example.com"
TEST_RULE_URL = "https://rule-target.example.com"
TEST_RULE_HTML = "<h1>Hello</h1>"
NOW = datetime.now(timezone.utc)

# --- Test Cases ---


@pytest.mark.asyncio  # Mark test as async
async def test_process_redirection_alias_not_found(
    redirection_service, mock_supabase_client
):
    """Test redirection process when the alias does not exist."""
    # Arrange: Mock DB response for finding the link (returns no data)
    mock_response = create_mock_response(
        data=None
    )  # maybe_single returns None data if not found
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.return_value = mock_response

    # Act & Assert: Expect LinkNotFoundException
    with pytest.raises(LinkNotFoundException):
        await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Check that Supabase client was called correctly to find link
    mock_supabase_client.table("routr_links").select("id", "default_url").eq(
        "alias", TEST_ALIAS
    ).limit(1).maybe_single().execute.assert_awaited_once()
    # Assert: Check that NO RPC calls were made
    mock_supabase_client.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_process_redirection_db_error_fetching_link(
    redirection_service, mock_supabase_client
):
    # ...
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.side_effect = PostgrestAPIError(  # Teraz PostgrestAPIError jest zdefiniowane
        {"message": "DB Connection Error"}
    )

    # Act & Assert: Expect DatabaseException
    with pytest.raises(DatabaseException):
        await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Check that Supabase client was called correctly
    mock_supabase_client.table("routr_links").select("id", "default_url").eq(
        "alias", TEST_ALIAS
    ).limit(1).maybe_single().execute.assert_awaited_once()
    # Assert: Check that NO RPC calls were made
    mock_supabase_client.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_process_redirection_rule_match_url(
    redirection_service, mock_supabase_client
):
    """Test redirection when a time-based URL rule matches."""
    # Arrange: Mock finding the link
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": TEST_DEFAULT_URL}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.return_value = mock_link_response

    # Arrange: Mock fetching rules (one matching time rule)
    mock_rule_data = [
        {
            "id": str(TEST_RULE_ID_TIME),
            "priority": 1,
            "rule_type": RuleTypeEnum.TIME.value,
            "target_type": TargetTypeEnum.URL.value,
            "target_value": TEST_RULE_URL,
            "start_time": (NOW - timedelta(hours=1)).isoformat(),
            "end_time": (NOW + timedelta(hours=1)).isoformat(),
            "max_clicks": None,
            "current_clicks": 0,
        }
    ]
    mock_rules_response = create_mock_response(data=mock_rule_data)
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.return_value = mock_rules_response

    # Arrange: Mock successful RPC calls
    mock_supabase_client.rpc.return_value.execute.return_value = (
        None  # RPC calls might not return significant data
    )

    # Act
    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Correct action and value returned
    assert action == RedirectionAction.REDIRECT_URL
    assert value == TEST_RULE_URL

    # Assert: Check Supabase calls
    mock_supabase_client.table("routr_links").select("id", "default_url").eq(
        "alias", TEST_ALIAS
    ).limit(1).maybe_single().execute.assert_awaited_once()
    mock_supabase_client.table("routing_rules").select(ANY).eq(
        "link_id", str(TEST_LINK_ID)
    ).order("priority", desc=False).execute.assert_awaited_once()
    # Assert: Check RPC calls were made correctly
    mock_supabase_client.rpc.assert_any_call(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    )
    mock_supabase_client.rpc.assert_any_call(
        "increment_rule_clicks", {"rule_uuid": str(TEST_RULE_ID_TIME)}
    )
    assert mock_supabase_client.rpc.call_count == 2  # Ensure exactly two RPC calls


@pytest.mark.asyncio
async def test_process_redirection_rule_match_html(
    redirection_service, mock_supabase_client
):
    """Test redirection when a click-based HTML rule matches."""
    # Arrange: Mock finding the link (no default URL this time)
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": None}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.return_value = mock_link_response

    # Arrange: Mock fetching rules (one matching click rule)
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
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.return_value = mock_rules_response

    # Arrange: Mock successful RPC calls
    mock_supabase_client.rpc.return_value.execute.return_value = None

    # Act
    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Correct action and value returned
    assert action == RedirectionAction.SERVE_HTML
    assert value == TEST_RULE_HTML

    # Assert: Check Supabase calls
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.assert_awaited_once()
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.assert_awaited_once()
    # Assert: Check RPC calls were made correctly
    mock_supabase_client.rpc.assert_any_call(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    )
    mock_supabase_client.rpc.assert_any_call(
        "increment_rule_clicks", {"rule_uuid": str(TEST_RULE_ID_CLICKS)}
    )
    assert mock_supabase_client.rpc.call_count == 2


@pytest.mark.asyncio
async def test_process_redirection_no_rule_match_with_default(
    redirection_service, mock_supabase_client
):
    """Test redirection falls back to default URL when no rules match."""
    # Arrange: Mock finding the link with a default URL
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": TEST_DEFAULT_URL}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.return_value = mock_link_response

    # Arrange: Mock fetching rules (e.g., time rule expired)
    mock_rule_data = [
        {
            "id": str(TEST_RULE_ID_TIME),
            "priority": 1,
            "rule_type": RuleTypeEnum.TIME.value,
            "target_type": TargetTypeEnum.URL.value,
            "target_value": TEST_RULE_URL,
            "start_time": (NOW - timedelta(hours=2)).isoformat(),
            "end_time": (NOW - timedelta(hours=1)).isoformat(),  # Expired
            "max_clicks": None,
            "current_clicks": 0,
        }
    ]
    mock_rules_response = create_mock_response(data=mock_rule_data)
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.return_value = mock_rules_response

    # Arrange: Mock successful link increment RPC call
    mock_supabase_client.rpc.return_value.execute.return_value = None

    # Act
    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Correct action and value returned
    assert action == RedirectionAction.REDIRECT_DEFAULT
    assert value == TEST_DEFAULT_URL

    # Assert: Check Supabase calls
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.assert_awaited_once()
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.assert_awaited_once()
    # Assert: Check ONLY link increment RPC was called
    mock_supabase_client.rpc.assert_called_once_with(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    )


@pytest.mark.asyncio
async def test_process_redirection_no_rule_match_no_default(
    redirection_service, mock_supabase_client
):
    """Test redirection falls back to global fallback when no rules match and no default URL."""
    # Arrange: Mock finding the link without a default URL
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": None}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.return_value = mock_link_response

    # Arrange: Mock fetching no rules
    mock_rules_response = create_mock_response(data=[])  # Empty list
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.return_value = mock_rules_response

    # Arrange: Mock successful link increment RPC call
    mock_supabase_client.rpc.return_value.execute.return_value = None

    # Act
    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Correct action and value returned
    assert action == RedirectionAction.REDIRECT_GLOBAL_FALLBACK
    assert value is None

    # Assert: Check Supabase calls
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.assert_awaited_once()
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.assert_awaited_once()
    # Assert: Check ONLY link increment RPC was called
    mock_supabase_client.rpc.assert_called_once_with(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    )


@pytest.mark.asyncio
async def test_process_redirection_db_error_fetching_rules(
    redirection_service, mock_supabase_client
):
    """Test redirection when a DB error occurs fetching rules."""
    # Arrange: Mock finding the link successfully
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": TEST_DEFAULT_URL}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.return_value = mock_link_response

    # Arrange: Mock successful link increment RPC call
    mock_supabase_client.rpc.return_value.execute.return_value = None

    # Arrange: Mock rules fetch to raise an error
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.side_effect = PostgrestAPIError(  # Teraz PostgrestAPIError jest zdefiniowane
        {"message": "DB Error Fetching Rules"}
    )

    # Act & Assert: Expect DatabaseException
    with pytest.raises(DatabaseException):
        await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Check Supabase calls
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.assert_awaited_once()
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.assert_awaited_once()
    # Assert: Check ONLY link increment RPC was called
    mock_supabase_client.rpc.assert_called_once_with(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    )


@pytest.mark.asyncio
async def test_process_redirection_error_incrementing_link_clicks(
    redirection_service, mock_supabase_client
):
    """Test redirection proceeds even if incrementing link clicks fails."""
    # Arrange: Mock finding the link
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": None}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.return_value = mock_link_response

    # Arrange: Mock fetching a matching rule
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
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.return_value = mock_rules_response

    # Arrange: Mock link increment RPC to FAIL
    # Need to mock based on the specific RPC call
    def rpc_side_effect_link_fail(rpc_name, params):
        if rpc_name == "increment_link_clicks":
            raise PostgrestAPIError({"message": "Link RPC Failed"})
        elif rpc_name == "increment_rule_clicks":
            return None  # Symulacja sukcesu (await None jest OK)
        return None  # Domyślny sukces

    mock_supabase_client.rpc.side_effect = rpc_side_effect_link_fail

    # Act: Should still succeed and return the rule action
    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Correct action and value returned (rule matched despite link increment error)
    assert action == RedirectionAction.REDIRECT_URL
    assert value == TEST_RULE_URL

    # Assert: Check RPC calls (link failed, rule succeeded)
    mock_supabase_client.rpc.assert_any_call(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    )
    mock_supabase_client.rpc.assert_any_call(
        "increment_rule_clicks", {"rule_uuid": str(TEST_RULE_ID_CLICKS)}
    )
    assert mock_supabase_client.rpc.call_count == 2


@pytest.mark.asyncio
async def test_process_redirection_error_incrementing_rule_clicks(
    redirection_service, mock_supabase_client
):
    """Test redirection proceeds even if incrementing rule clicks fails."""
    # Arrange: Mock finding the link
    mock_link_data = {"id": str(TEST_LINK_ID), "default_url": None}
    mock_link_response = create_mock_response(data=mock_link_data)
    mock_supabase_client.table(
        "routr_links"
    ).select().eq().limit().maybe_single().execute.return_value = mock_link_response

    # Arrange: Mock fetching a matching rule
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
    mock_supabase_client.table(
        "routing_rules"
    ).select().eq().order().execute.return_value = mock_rules_response

    # Arrange: Mock RPC calls (link succeeds, rule fails)
    def rpc_side_effect_rule_fail(rpc_name, params):
        if rpc_name == "increment_link_clicks":
            return None  # Symulacja sukcesu
        elif rpc_name == "increment_rule_clicks":
            raise PostgrestAPIError({"message": "Rule RPC Failed"})
        return None  # Domyślny sukces

    mock_supabase_client.rpc.side_effect = rpc_side_effect_rule_fail

    # Act: Should still succeed and return the rule action
    action, value = await redirection_service.process_redirection(TEST_ALIAS)

    # Assert: Correct action and value returned (rule matched despite rule increment error)
    assert action == RedirectionAction.REDIRECT_URL
    assert value == TEST_RULE_URL

    # Assert: Check RPC calls (link succeeded, rule failed)
    mock_supabase_client.rpc.assert_any_call(
        "increment_link_clicks", {"link_uuid": str(TEST_LINK_ID)}
    )
    mock_supabase_client.rpc.assert_any_call(
        "increment_rule_clicks", {"rule_uuid": str(TEST_RULE_ID_CLICKS)}
    )
    assert mock_supabase_client.rpc.call_count == 2
