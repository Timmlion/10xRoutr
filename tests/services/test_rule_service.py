# tests/services/test_rule_service.py

import pytest  # <<< --- ADDED THIS IMPORT ---
from unittest.mock import AsyncMock, MagicMock, ANY
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
from postgrest.exceptions import APIError as PostgrestAPIError
from supabase import AsyncClient
from postgrest.types import CountMethod

# Import the service under test, custom exceptions, and constants
from src.services.rule_service import (
    RuleService,
    ROUTING_RULES_LINK_ID_PRIORITY_KEY,
    POSTGRES_UNIQUE_VIOLATION_CODE,
)
from src.services.custom_exceptions import (
    DatabaseException,
    NotFoundException,
    ParentLinkNotFoundException,
    PriorityConflictException,
    ValidationException,
    ServiceException,
)

# Import DTOs and Enums used in the service
from src.schemas.rule import RuleCreate, RuleUpdate, RuleResponse
from src.schemas.enums import RuleTypeEnum, TargetTypeEnum

# --- Test Constants ---
TEST_LINK_ID = uuid4()
TEST_USER_ID = uuid4()
TEST_RULE_ID = uuid4()
TEST_OTHER_RULE_ID = uuid4()


# --- Fixtures ---


@pytest.fixture
def mock_supabase_client():
    """
    Provides a MagicMock simulating Supabase AsyncClient with distinct mocks
    for different table operations and RPC calls.
    """
    mock_client = MagicMock(spec=AsyncClient)
    mock_tables = {}  # Cache for table-specific mocks

    def get_mock_table(table_name):
        """Factory to get or create table mocks with chainable methods."""
        if table_name not in mock_tables:
            mock_table = MagicMock(name=f"table({table_name})")
            # Mock chainable methods needed by the service
            mock_table.select.return_value = mock_table
            mock_table.insert.return_value = mock_table
            mock_table.update.return_value = mock_table
            mock_table.delete.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.maybe_single.return_value = mock_table
            mock_table.order.return_value = mock_table
            # Each table mock gets its own distinct AsyncMock for execute
            mock_table.execute = AsyncMock(name=f"table({table_name}).execute")
            mock_tables[table_name] = mock_table
        return mock_tables[table_name]

    mock_client.table.side_effect = get_mock_table
    # Note: RPC calls are not directly used by RuleService, so no need to mock here.

    return mock_client


@pytest.fixture
def rule_service(mock_supabase_client: AsyncClient) -> RuleService:
    """Provides a RuleService instance initialized with the mocked client."""
    return RuleService(supabase_client=mock_supabase_client)


# --- Helper Functions ---


def create_mock_response(data=None, count=None):
    """Creates a MagicMock object mimicking a PostgrestAPIResponse."""
    mock_response = MagicMock()
    mock_response.data = data
    mock_response.count = count
    return mock_response


def mock_ownership_verification_success_sequence():
    """Returns a sequence of mock responses simulating successful link ownership verification."""
    mock_link_exists = create_mock_response(count=1, data=[{"id": str(TEST_LINK_ID)}])
    mock_owner_check = create_mock_response(data=[{"id": str(TEST_LINK_ID)}])
    return [mock_link_exists, mock_owner_check]


def mock_ownership_verification_not_found_sequence():
    """Returns a sequence for link verification where the link is not found."""
    mock_link_exists = create_mock_response(count=0, data=[])
    return [mock_link_exists]


def mock_ownership_verification_forbidden_sequence():
    """Returns a sequence for link verification where the link exists but is not owned by the user."""
    mock_link_exists = create_mock_response(count=1, data=[{"id": str(TEST_LINK_ID)}])
    mock_owner_check = create_mock_response(data=None)
    return [mock_link_exists, mock_owner_check]


# --- Test Cases ---

# === Tests for add_rule_to_link ===


@pytest.mark.asyncio
async def test_add_rule_to_link_success(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests successful addition of a new rule to a link."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com/click",
        max_clicks=100,
    )
    expected_db_insert_data = {
        "link_id": str(TEST_LINK_ID),
        "priority": 1,
        "rule_type": "clicks",
        "target_type": "url",
        "target_value": "http://example.com/click",
        "start_time": None,
        "end_time": None,
        "max_clicks": 100,
    }
    utc_now_dt = datetime.now(timezone.utc)
    mock_created_at_str = utc_now_dt.isoformat()
    mock_updated_at_str = utc_now_dt.isoformat()
    mock_created_rule_db = {
        **expected_db_insert_data,
        "id": str(TEST_RULE_ID),
        "current_clicks": 0,
        "created_at": mock_created_at_str,
        "updated_at": mock_updated_at_str,
    }

    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_insert_response = create_mock_response(data=[mock_created_rule_db])
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.return_value = mock_insert_response

    created_rule = await rule_service.add_rule_to_link(
        link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
    )

    assert isinstance(created_rule, RuleResponse)
    assert created_rule.id == TEST_RULE_ID
    assert created_rule.priority == 1
    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()
    mock_supabase_client.table(rule_service.rules_table).insert.assert_called_once_with(
        expected_db_insert_data
    )


@pytest.mark.asyncio
async def test_add_rule_link_not_found(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests adding a rule when the parent link is not found."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com",
        max_clicks=100,
    )
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_links_execute.side_effect = mock_ownership_verification_not_found_sequence()
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute

    with pytest.raises(NotFoundException, match="Parent link .* not found"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )

    assert mock_links_execute.await_count == 1
    mock_rules_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_rule_link_forbidden(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests adding a rule when the user does not own the parent link."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com",
        max_clicks=100,
    )
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_links_execute.side_effect = mock_ownership_verification_forbidden_sequence()
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute

    with pytest.raises(NotFoundException, match="Access denied to parent link"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )

    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_rule_priority_conflict(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests adding a rule when the priority conflicts with an existing rule."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com",
        max_clicks=100,
    )
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_postgrest_error = PostgrestAPIError(
        {
            "message": f"duplicate key...{ROUTING_RULES_LINK_ID_PRIORITY_KEY}...",
            "code": POSTGRES_UNIQUE_VIOLATION_CODE,
            "details": "",
            "hint": None,
        }
    )
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.side_effect = mock_postgrest_error

    with pytest.raises(PriorityConflictException, match="priority is already in use"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )

    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()


# === Tests for get_rules_for_link ===


@pytest.mark.asyncio
async def test_get_rules_for_link_success(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests retrieving the list of rules for a link successfully."""
    iso_now = datetime.now(timezone.utc).isoformat()
    mock_rules_db_data = [
        {
            "id": str(uuid4()),
            "link_id": str(TEST_LINK_ID),
            "priority": 1,
            "rule_type": "clicks",
            "target_type": "url",
            "target_value": "url1",
            "max_clicks": 100,
            "current_clicks": 10,
            "start_time": None,
            "end_time": None,
            "created_at": iso_now,
            "updated_at": iso_now,
        },
        {
            "id": str(uuid4()),
            "link_id": str(TEST_LINK_ID),
            "priority": 2,
            "rule_type": "time",
            "target_type": "html",
            "target_value": "html2",
            "max_clicks": None,
            "current_clicks": 5,
            "start_time": iso_now,
            "end_time": iso_now,
            "created_at": iso_now,
            "updated_at": iso_now,
        },
    ]
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_select_response = create_mock_response(data=mock_rules_db_data)
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.return_value = mock_select_response

    rules = await rule_service.get_rules_for_link(
        link_id=TEST_LINK_ID, user_id=TEST_USER_ID
    )

    assert len(rules) == 2
    assert isinstance(rules[0], RuleResponse)
    assert isinstance(rules[1], RuleResponse)
    assert rules[0].priority == 1
    assert rules[1].priority == 2
    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()
    mock_supabase_client.table(rule_service.rules_table).select.assert_called_with("*")
    mock_supabase_client.table(rule_service.rules_table).eq.assert_called_with(
        "link_id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(rule_service.rules_table).order.assert_called_with(
        "priority", desc=False
    )


# === Tests for get_rule_details ===


@pytest.mark.asyncio
async def test_get_rule_details_success(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests retrieving details for a specific rule successfully."""
    iso_now = datetime.now(timezone.utc).isoformat()
    mock_rule_db_data = {
        "id": str(TEST_RULE_ID),
        "link_id": str(TEST_LINK_ID),
        "priority": 5,
        "rule_type": "time",
        "target_type": "url",
        "target_value": "url_details",
        "max_clicks": None,
        "current_clicks": 3,
        "start_time": iso_now,
        "end_time": iso_now,
        "created_at": iso_now,
        "updated_at": iso_now,
    }
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_select_response = create_mock_response(data=mock_rule_db_data)
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.return_value = mock_select_response

    rule = await rule_service.get_rule_details(
        link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
    )

    assert isinstance(rule, RuleResponse)
    assert rule.id == TEST_RULE_ID
    assert rule.priority == 5
    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()
    mock_rules_table = mock_supabase_client.table(rule_service.rules_table)
    mock_rules_table.select.assert_called_with("*")
    mock_rules_table.eq.assert_any_call("id", str(TEST_RULE_ID))
    mock_rules_table.eq.assert_any_call("link_id", str(TEST_LINK_ID))
    mock_rules_table.maybe_single.assert_called_once()


@pytest.mark.asyncio
async def test_get_rule_details_not_found(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests retrieving details for a non-existent rule."""
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_select_response = create_mock_response(data=None)
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.return_value = mock_select_response

    with pytest.raises(NotFoundException, match="Rule not found or access denied"):
        await rule_service.get_rule_details(
            link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
        )

    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()


# === Tests for update_rule ===


@pytest.mark.asyncio
async def test_update_rule_success(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests successful update of a rule."""
    update_payload = RuleUpdate(priority=15, target_value="http://new.example.com")
    expected_db_update_payload = {
        "priority": 15,
        "target_value": "http://new.example.com",
    }
    iso_now = datetime.now(timezone.utc).isoformat()
    iso_later = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    updated_rule_db_data = {
        "id": str(TEST_RULE_ID),
        "link_id": str(TEST_LINK_ID),
        "priority": 15,
        "rule_type": "clicks",
        "target_type": "url",
        "target_value": "http://new.example.com",
        "max_clicks": 50,
        "current_clicks": 5,
        "start_time": None,
        "end_time": None,
        "created_at": iso_now,
        "updated_at": iso_later,
    }

    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_update_response = create_mock_response(data=[updated_rule_db_data])
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.return_value = mock_update_response

    updated_rule = await rule_service.update_rule(
        link_id=TEST_LINK_ID,
        rule_id=TEST_RULE_ID,
        update_data=update_payload,
        user_id=TEST_USER_ID,
    )

    assert isinstance(updated_rule, RuleResponse)
    assert updated_rule.priority == 15
    assert updated_rule.target_value == "http://new.example.com"
    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()
    mock_rules_table = mock_supabase_client.table(rule_service.rules_table)
    mock_rules_table.update.assert_called_once_with(expected_db_update_payload)
    mock_rules_table.eq.assert_any_call("id", str(TEST_RULE_ID))
    mock_rules_table.eq.assert_any_call("link_id", str(TEST_LINK_ID))


@pytest.mark.asyncio
async def test_update_rule_no_changes(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests update call when no data fields are provided."""
    update_payload = RuleUpdate()  # Empty update object
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute

    # --- Provide enough responses for BOTH verification calls AND the get_details call ---
    ownership_responses_1 = mock_ownership_verification_success_sequence()
    ownership_responses_2 = mock_ownership_verification_success_sequence()
    mock_links_execute.side_effect = ownership_responses_1 + ownership_responses_2
    # -------------------------------------------------------------------------------------

    iso_now = datetime.now(timezone.utc).isoformat()
    current_rule_db_data = {
        "id": str(TEST_RULE_ID),
        "link_id": str(TEST_LINK_ID),
        "priority": 10,
        "rule_type": "clicks",
        "target_type": "url",
        "target_value": "http://old.example.com",
        "max_clicks": 50,
        "current_clicks": 5,
        "start_time": None,
        "end_time": None,
        "created_at": iso_now,
        "updated_at": iso_now,
    }
    mock_get_details_response = create_mock_response(data=current_rule_db_data)
    mock_rules_execute.return_value = (
        mock_get_details_response  # For get_rule_details call
    )

    result = await rule_service.update_rule(
        link_id=TEST_LINK_ID,
        rule_id=TEST_RULE_ID,
        update_data=update_payload,
        user_id=TEST_USER_ID,
    )

    assert isinstance(result, RuleResponse)
    assert result.id == TEST_RULE_ID
    assert result.priority == 10
    assert (
        mock_links_execute.await_count == 4
    )  # 2 calls for first verify, 2 for second verify
    mock_rules_execute.assert_awaited_once()  # Called once for get_rule_details fetch
    mock_supabase_client.table(rule_service.rules_table).update.assert_not_called()


@pytest.mark.asyncio
async def test_update_rule_priority_conflict(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests priority conflict during rule update."""
    update_payload = RuleUpdate(priority=1)
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_postgrest_error = PostgrestAPIError(
        {
            "message": f"duplicate key...{ROUTING_RULES_LINK_ID_PRIORITY_KEY}...",
            "code": POSTGRES_UNIQUE_VIOLATION_CODE,
            "details": "",
            "hint": None,
        }
    )
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.side_effect = mock_postgrest_error  # Update fails

    with pytest.raises(PriorityConflictException):
        await rule_service.update_rule(
            link_id=TEST_LINK_ID,
            rule_id=TEST_RULE_ID,
            update_data=update_payload,
            user_id=TEST_USER_ID,
        )

    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()
    mock_supabase_client.table(rule_service.rules_table).update.assert_called_once()


# --- Tests for delete_rule ---


@pytest.mark.asyncio
async def test_delete_rule_success(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests successful deletion of a rule."""
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_delete_response = create_mock_response(count=1, data=[])
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.return_value = mock_delete_response

    await rule_service.delete_rule(
        link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
    )

    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()
    mock_rules_table = mock_supabase_client.table(rule_service.rules_table)
    mock_rules_table.delete.assert_called_once_with(count=CountMethod.exact)
    mock_rules_table.eq.assert_any_call("id", str(TEST_RULE_ID))
    mock_rules_table.eq.assert_any_call("link_id", str(TEST_LINK_ID))


@pytest.mark.asyncio
async def test_delete_rule_not_found(
    rule_service: RuleService, mock_supabase_client: MagicMock
):
    """Tests attempting to delete a non-existent rule."""
    mock_links_execute = mock_supabase_client.table(rule_service.links_table).execute
    mock_rules_execute = mock_supabase_client.table(rule_service.rules_table).execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_delete_response = create_mock_response(count=0, data=[])
    mock_links_execute.side_effect = ownership_responses
    mock_rules_execute.return_value = mock_delete_response

    with pytest.raises(
        NotFoundException, match="Rule not found or you do not have permission"
    ):
        await rule_service.delete_rule(
            link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
        )

    assert mock_links_execute.await_count == 2
    mock_rules_execute.assert_awaited_once()
    mock_supabase_client.table(rule_service.rules_table).delete.assert_called_once()
