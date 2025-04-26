# tests/services/test_rule_service.py (Corrected - Full File)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
from postgrest.exceptions import APIError as PostgrestAPIError
from supabase import AsyncClient  # Import AsyncClient

# Import testowanej klasy i wyjątków ORAZ stałych
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
)

# Import modeli DTO
from src.schemas.rule import RuleCreate, RuleUpdate, RuleResponse
from src.schemas.enums import RuleTypeEnum, TargetTypeEnum

# Stałe dla testów
TEST_LINK_ID = uuid4()
TEST_USER_ID = uuid4()
TEST_RULE_ID = uuid4()
TEST_OTHER_RULE_ID = uuid4()


# --- Fixture dla mocka klienta Supabase ---
@pytest.fixture
def mock_supabase_client():
    """Fixture to create a mock Supabase AsyncClient with distinct execute mocks."""
    mock_client = MagicMock(spec=AsyncClient)

    # Define distinct AsyncMock instances for different execute chains
    mock_select_single_execute = AsyncMock(name="select_single_execute")
    mock_select_list_execute = AsyncMock(name="select_list_execute")
    mock_insert_execute = AsyncMock(name="insert_execute")
    mock_update_execute = AsyncMock(name="update_execute")
    mock_delete_execute = AsyncMock(name="delete_execute")

    # Configure chains to return the specific execute mock
    # For maybe_single() calls (ownership checks, get_rule_details, update pre-check)
    mock_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute = (
        mock_select_single_execute
    )
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute = (
        mock_select_single_execute
    )
    # For get_rules_for_link (list)
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute = (
        mock_select_list_execute
    )
    # For add_rule_to_link (insert)
    mock_client.table.return_value.insert.return_value.execute = mock_insert_execute
    # For update_rule (update)
    mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute = (
        mock_update_execute
    )
    # For delete_rule (delete)
    mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute = (
        mock_delete_execute
    )

    return mock_client


# --- Fixture dla instancji RuleService ---
@pytest.fixture
def rule_service(mock_supabase_client):
    """Fixture to create an instance of RuleService with the mocked client."""
    return RuleService(supabase_client=mock_supabase_client)


# --- Helpery do mockowania weryfikacji (zwracają listy odpowiedzi dla side_effect) ---
def mock_ownership_verification_success_sequence():
    mock_link_exists = MagicMock()
    mock_link_exists.count = 1
    mock_link_exists.data = [{"id": str(TEST_LINK_ID)}]
    mock_owner_check = MagicMock()
    mock_owner_check.data = [{"id": str(TEST_LINK_ID)}]
    return [mock_link_exists, mock_owner_check]


def mock_ownership_verification_not_found_sequence():
    mock_link_exists = MagicMock()
    mock_link_exists.count = 0
    mock_link_exists.data = []
    return [mock_link_exists]


def mock_ownership_verification_forbidden_sequence():
    mock_link_exists = MagicMock()
    mock_link_exists.count = 1
    mock_link_exists.data = [{"id": str(TEST_LINK_ID)}]
    mock_owner_check = MagicMock()
    mock_owner_check.data = None
    return [mock_link_exists, mock_owner_check]


# --- Testy ---


@pytest.mark.asyncio
async def test_add_rule_to_link_success(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje pomyślne dodanie reguły."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com/click",
        max_clicks=100,
        start_time=None,
        end_time=None,
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

    # Arrange:
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_insert_execute = (
        mock_supabase_client.table.return_value.insert.return_value.execute
    )

    mock_select_single_execute.side_effect = (
        mock_ownership_verification_success_sequence()
    )
    mock_insert_response = MagicMock()
    mock_insert_response.data = [mock_created_rule_db]
    mock_insert_execute.return_value = mock_insert_response

    # Act
    created_rule = await rule_service.add_rule_to_link(
        link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
    )

    # Assert
    assert isinstance(created_rule, RuleResponse)
    assert created_rule.id == TEST_RULE_ID
    assert mock_select_single_execute.call_count == 2
    mock_insert_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_rule_link_not_found(rule_service: RuleService, mock_supabase_client):
    """Testuje próbę dodania reguły do nieistniejącego linku."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com",
        max_clicks=100,
    )
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_select_single_execute.side_effect = (
        mock_ownership_verification_not_found_sequence()
    )

    with pytest.raises(NotFoundException, match="Parent link .* not found"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )
    assert mock_select_single_execute.call_count == 1


@pytest.mark.asyncio
async def test_add_rule_link_forbidden(rule_service: RuleService, mock_supabase_client):
    """Testuje próbę dodania reguły do linku nienależącego do użytkownika."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com",
        max_clicks=100,
    )
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_select_single_execute.side_effect = (
        mock_ownership_verification_forbidden_sequence()
    )

    with pytest.raises(NotFoundException, match="Access denied to parent link"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )
    assert mock_select_single_execute.call_count == 2


@pytest.mark.asyncio
async def test_add_rule_priority_conflict(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje konflikt priorytetu podczas dodawania reguły."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com",
        max_clicks=100,
    )
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_select_single_execute.side_effect = (
        mock_ownership_verification_success_sequence()
    )

    mock_insert_execute = (
        mock_supabase_client.table.return_value.insert.return_value.execute
    )
    mock_postgrest_error = PostgrestAPIError(
        {
            "message": f'duplicate key value violates unique constraint "{ROUTING_RULES_LINK_ID_PRIORITY_KEY}"',
            "code": POSTGRES_UNIQUE_VIOLATION_CODE,
            "details": "",
        }
    )
    mock_insert_execute.side_effect = mock_postgrest_error

    with pytest.raises(PriorityConflictException, match="priority is already in use"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )
    assert mock_select_single_execute.call_count == 2
    mock_insert_execute.assert_awaited_once()


# --- Testy dla get_rules_for_link ---
@pytest.mark.asyncio
async def test_get_rules_for_link_success(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje pomyślne pobranie listy reguł."""
    utc_now_dt = datetime.now(timezone.utc)
    iso_now = utc_now_dt.isoformat()
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
    # Arrange: Mock verify(2) uses select_single, select list uses select_list
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_select_list_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute
    )

    mock_select_single_execute.side_effect = (
        mock_ownership_verification_success_sequence()
    )
    mock_select_response = MagicMock()
    mock_select_response.data = mock_rules_db_data
    mock_select_list_execute.return_value = mock_select_response

    # Act
    rules = await rule_service.get_rules_for_link(
        link_id=TEST_LINK_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert len(rules) == 2
    assert isinstance(rules[0], RuleResponse)
    assert mock_select_single_execute.call_count == 2
    mock_select_list_execute.assert_awaited_once()


# --- Testy dla get_rule_details ---
@pytest.mark.asyncio
async def test_get_rule_details_success(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje pomyślne pobranie szczegółów reguły."""
    utc_now_dt = datetime.now(timezone.utc)
    iso_now = utc_now_dt.isoformat()
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

    # Arrange: Mock verify(2) and select rule(1) use select_single
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_select_response = MagicMock()
    mock_select_response.data = mock_rule_db_data
    mock_select_single_execute.side_effect = (
        mock_ownership_verification_success_sequence() + [mock_select_response]
    )

    # Act
    rule = await rule_service.get_rule_details(
        link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert isinstance(rule, RuleResponse)
    assert rule.id == TEST_RULE_ID
    assert mock_select_single_execute.call_count == 3


@pytest.mark.asyncio
async def test_get_rule_details_not_found(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje pobranie nieistniejącej reguły."""
    # Arrange: Mock verify(2) success, but select(1) returns None = 3 calls
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_select_response = MagicMock()
    mock_select_response.data = None
    mock_select_single_execute.side_effect = (
        mock_ownership_verification_success_sequence() + [mock_select_response]
    )

    # Act & Assert
    with pytest.raises(NotFoundException, match="Rule not found or access denied"):
        await rule_service.get_rule_details(
            link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
        )
    assert mock_select_single_execute.call_count == 3


# --- Testy dla update_rule ---
@pytest.mark.asyncio
async def test_update_rule_success(rule_service: RuleService, mock_supabase_client):
    """Testuje pomyślną aktualizację reguły."""
    update_payload = RuleUpdate(priority=15, target_value="http://new.example.com")
    utc_now_dt = datetime.now(timezone.utc)
    iso_now = utc_now_dt.isoformat()
    iso_later = (utc_now_dt + timedelta(minutes=1)).isoformat()

    # Define current_rule_db_data here
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
    updated_rule_db_data = {
        **current_rule_db_data,
        "priority": 15,
        "target_value": "http://new.example.com",
        "updated_at": iso_later,
    }

    # Arrange:
    # 1 & 2: _verify_link_ownership (uses mock_select_single_execute for .eq().maybe_single())
    mock_verify_select_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    ownership_responses = mock_ownership_verification_success_sequence()

    # 3: select current rule state (uses mock_select_single_execute for .eq().eq().maybe_single())
    mock_get_current_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_select_current_response = MagicMock()
    mock_select_current_response.data = current_rule_db_data

    # Set side effect for the 3 select calls (2 for verify, 1 for get current)
    # Important: Need to ensure the right mock is configured for the right chain
    # We'll use side_effect on the most specific mock chain expected
    mock_verify_select_execute.side_effect = ownership_responses
    mock_get_current_execute.return_value = (
        mock_select_current_response  # This will be called once
    )

    # 4: update operation success (uses mock_update_execute)
    mock_update_execute = (
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    )
    mock_update_response = MagicMock()
    mock_update_response.data = [updated_rule_db_data]
    mock_update_execute.return_value = mock_update_response

    # Act
    updated_rule = await rule_service.update_rule(
        link_id=TEST_LINK_ID,
        rule_id=TEST_RULE_ID,
        update_data=update_payload,
        user_id=TEST_USER_ID,
    )

    # Assert
    assert isinstance(updated_rule, RuleResponse)
    assert updated_rule.priority == 15
    update_call_args = mock_supabase_client.table.return_value.update.call_args
    called_update_payload = update_call_args[0][0]
    assert called_update_payload == {
        "priority": 15,
        "target_value": "http://new.example.com",
    }
    assert mock_verify_select_execute.call_count == 2  # verify(2)
    mock_get_current_execute.assert_awaited_once()  # select(1)
    mock_update_execute.assert_awaited_once()  # update(1)


@pytest.mark.asyncio
async def test_update_rule_priority_conflict(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje konflikt priorytetu podczas aktualizacji."""
    update_payload = RuleUpdate(priority=1)
    utc_now_dt = datetime.now(timezone.utc)
    iso_now = utc_now_dt.isoformat()

    # Define current_rule_db_data here
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

    # Arrange:
    # 1 & 2: _verify_link_ownership
    mock_verify_select_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_verify_select_execute.side_effect = (
        mock_ownership_verification_success_sequence()
    )

    # 3: select current rule state
    mock_get_current_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_select_current_response = MagicMock()
    mock_select_current_response.data = current_rule_db_data
    mock_get_current_execute.return_value = mock_select_current_response

    # 4: update operation fails
    mock_update_execute = (
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    )
    mock_postgrest_error = PostgrestAPIError(
        {
            "message": f'duplicate key value violates unique constraint "{ROUTING_RULES_LINK_ID_PRIORITY_KEY}"',
            "code": POSTGRES_UNIQUE_VIOLATION_CODE,
            "details": "",
        }
    )
    mock_update_execute.side_effect = mock_postgrest_error

    # Act & Assert
    with pytest.raises(PriorityConflictException, match="priority is already in use"):
        await rule_service.update_rule(
            link_id=TEST_LINK_ID,
            rule_id=TEST_RULE_ID,
            update_data=update_payload,
            user_id=TEST_USER_ID,
        )

    assert mock_verify_select_execute.call_count == 2
    mock_get_current_execute.assert_awaited_once()
    mock_update_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rule_validation_error(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje błąd walidacji (np. brak daty dla typu time) podczas update."""
    update_payload = RuleUpdate(rule_type=RuleTypeEnum.TIME)
    utc_now_dt = datetime.now(timezone.utc)
    iso_now = utc_now_dt.isoformat()

    # Define current_rule_db_data here
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

    # Arrange: Mock verify(2) + select(1) = 3 calls on select_single
    mock_verify_select_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_get_current_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute
    )

    ownership_responses = mock_ownership_verification_success_sequence()
    mock_select_current_response = MagicMock()
    mock_select_current_response.data = current_rule_db_data

    mock_verify_select_execute.side_effect = ownership_responses
    mock_get_current_execute.return_value = mock_select_current_response

    # Act & Assert
    with pytest.raises(ValidationException):
        await rule_service.update_rule(
            link_id=TEST_LINK_ID,
            rule_id=TEST_RULE_ID,
            update_data=update_payload,
            user_id=TEST_USER_ID,
        )

    assert mock_verify_select_execute.call_count == 2
    mock_get_current_execute.assert_awaited_once()
    # Ensure update was not called
    mock_update_execute = (
        mock_supabase_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
    )
    mock_update_execute.assert_not_awaited()


# --- Testy dla delete_rule ---
@pytest.mark.asyncio
async def test_delete_rule_success(rule_service: RuleService, mock_supabase_client):
    """Testuje pomyślne usunięcie reguły."""
    # Arrange: Mock verify(2) uses select_single, delete(1) uses delete_execute
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_delete_execute = (
        mock_supabase_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute
    )

    mock_select_single_execute.side_effect = (
        mock_ownership_verification_success_sequence()
    )
    mock_delete_response = MagicMock()
    mock_delete_response.count = 1
    mock_delete_response.data = []
    mock_delete_execute.return_value = mock_delete_response

    # Act
    await rule_service.delete_rule(
        link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert mock_select_single_execute.call_count == 2
    mock_delete_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_rule_not_found(rule_service: RuleService, mock_supabase_client):
    """Testuje próbę usunięcia nieistniejącej reguły."""
    # Arrange: Mock verify(2) uses select_single, delete(1) uses delete_execute returns count=0
    mock_select_single_execute = (
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute
    )
    mock_delete_execute = (
        mock_supabase_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute
    )

    mock_select_single_execute.side_effect = (
        mock_ownership_verification_success_sequence()
    )
    mock_delete_response = MagicMock()
    mock_delete_response.count = 0
    mock_delete_response.data = []
    mock_delete_execute.return_value = mock_delete_response

    # Act & Assert
    with pytest.raises(
        NotFoundException, match="Rule not found or you do not have permission"
    ):
        await rule_service.delete_rule(
            link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
        )
    assert mock_select_single_execute.call_count == 2
    mock_delete_execute.assert_awaited_once()
