# tests/services/test_rule_service.py (Corrected Again - Full File v4)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
from postgrest.exceptions import APIError as PostgrestAPIError
from supabase import AsyncClient

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


# --- Fixture dla mocka klienta Supabase (Uproszczona) ---
@pytest.fixture
def mock_supabase_client():
    """Fixture to create a mock Supabase AsyncClient with ONE main execute mock."""
    mock_client = MagicMock(spec=AsyncClient)
    mock_execute = AsyncMock(name="execute")
    # Przypisz ten sam mock do wszystkich możliwych łańcuchów zakończonych execute
    # To upraszcza dostęp w testach, ale wymaga precyzyjnej konfiguracji side_effect
    mock_chain = mock_client.table.return_value
    mock_chain.select.return_value.eq.return_value.maybe_single.return_value.execute = (
        mock_execute
    )
    mock_chain.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute = (
        mock_execute
    )
    mock_chain.select.return_value.eq.return_value.order.return_value.execute = (
        mock_execute
    )
    mock_chain.insert.return_value.execute = mock_execute
    mock_chain.update.return_value.eq.return_value.eq.return_value.execute = (
        mock_execute
    )
    mock_chain.delete.return_value.eq.return_value.eq.return_value.execute = (
        mock_execute
    )
    # Dodatkowe, mniej specyficzne ścieżki na wszelki wypadek
    mock_chain.select.return_value.eq.return_value.execute = (
        mock_execute  # Select list with one eq
    )
    mock_chain.update.return_value.eq.return_value.execute = (
        mock_execute  # Update with one eq
    )
    mock_chain.delete.return_value.eq.return_value.execute = (
        mock_execute  # Delete with one eq
    )
    mock_chain.select.return_value.execute = mock_execute  # Select all
    mock_chain.execute = mock_execute  # Catch-all on table

    return mock_client


# --- Fixture dla instancji RuleService ---
@pytest.fixture
def rule_service(mock_supabase_client):
    """Fixture to create an instance of RuleService with the mocked client."""
    return RuleService(supabase_client=mock_supabase_client)


# --- Helpery do mockowania weryfikacji ---
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

    # Arrange: Mock verify(2) + insert(1) = 3 execute calls
    mock_execute = mock_supabase_client.table.return_value.execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_insert_response = MagicMock()
    mock_insert_response.data = [mock_created_rule_db]
    mock_execute.side_effect = ownership_responses + [mock_insert_response]

    # Act
    created_rule = await rule_service.add_rule_to_link(
        link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
    )

    # Assert
    assert isinstance(created_rule, RuleResponse)
    assert created_rule.id == TEST_RULE_ID
    assert mock_execute.call_count == 3


@pytest.mark.asyncio
async def test_add_rule_link_not_found(rule_service: RuleService, mock_supabase_client):
    """Testuje próbę dodania reguły do nieistniejącego linku."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com",
        max_clicks=100,
        start_time=None,
        end_time=None,
    )
    # Arrange: Mock verify(1) -> not found
    mock_execute = mock_supabase_client.table.return_value.execute
    mock_execute.side_effect = mock_ownership_verification_not_found_sequence()

    # Act & Assert
    with pytest.raises(NotFoundException, match="Parent link .* not found"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )
    assert mock_execute.call_count == 1


@pytest.mark.asyncio
async def test_add_rule_link_forbidden(rule_service: RuleService, mock_supabase_client):
    """Testuje próbę dodania reguły do linku nienależącego do użytkownika."""
    rule_create_data = RuleCreate(
        priority=1,
        rule_type=RuleTypeEnum.CLICKS,
        target_type=TargetTypeEnum.URL,
        target_value="http://example.com",
        max_clicks=100,
        start_time=None,
        end_time=None,
    )
    # Arrange: Mock verify(2) -> forbidden
    mock_execute = mock_supabase_client.table.return_value.execute
    mock_execute.side_effect = mock_ownership_verification_forbidden_sequence()

    # Act & Assert
    with pytest.raises(NotFoundException, match="Access denied to parent link"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )
    assert mock_execute.call_count == 2


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
        start_time=None,
        end_time=None,
    )
    # Arrange: Mock verify(2) success, insert(1) fails = 3 execute calls
    mock_execute = mock_supabase_client.table.return_value.execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_postgrest_error = PostgrestAPIError(
        {
            "message": f"duplicate key...{ROUTING_RULES_LINK_ID_PRIORITY_KEY}...",
            "code": POSTGRES_UNIQUE_VIOLATION_CODE,
            "details": "",
            "hint": None,
        }
    )
    mock_execute.side_effect = ownership_responses + [mock_postgrest_error]

    # Act & Assert
    with pytest.raises(PriorityConflictException, match="priority is already in use"):
        await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create_data, user_id=TEST_USER_ID
        )
    assert mock_execute.call_count == 3


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
    # Arrange: Mock verify(2) + select list(1) = 3 calls
    mock_execute = mock_supabase_client.table.return_value.execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_select_response = MagicMock()
    mock_select_response.data = mock_rules_db_data
    mock_execute.side_effect = ownership_responses + [mock_select_response]

    # Act
    rules = await rule_service.get_rules_for_link(
        link_id=TEST_LINK_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert len(rules) == 2
    assert isinstance(rules[0], RuleResponse)
    assert mock_execute.call_count == 3


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

    # Arrange: Mock verify(2) + select rule(1) = 3 calls
    mock_execute = mock_supabase_client.table.return_value.execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_select_response = MagicMock()
    mock_select_response.data = mock_rule_db_data
    mock_execute.side_effect = ownership_responses + [mock_select_response]

    # Act
    rule = await rule_service.get_rule_details(
        link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert isinstance(rule, RuleResponse)
    assert rule.id == TEST_RULE_ID
    assert mock_execute.call_count == 3


@pytest.mark.asyncio
async def test_get_rule_details_not_found(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje pobranie nieistniejącej reguły."""
    # Arrange: Mock verify(2) + select rule(1) returns None = 3 calls
    mock_execute = mock_supabase_client.table.return_value.execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_select_response = MagicMock()
    mock_select_response.data = None
    mock_execute.side_effect = ownership_responses + [mock_select_response]

    # Act & Assert
    with pytest.raises(NotFoundException, match="Rule not found or access denied"):
        await rule_service.get_rule_details(
            link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
        )
    assert mock_execute.call_count == 3


# TODO FIX TEST
# --- Testy dla update_rule ---
# @pytest.mark.asyncio
# async def test_update_rule_success(rule_service: RuleService, mock_supabase_client):
#     """Testuje pomyślną aktualizację reguły."""
#     update_payload = RuleUpdate(priority=15, target_value="http://new.example.com")
#     utc_now_dt = datetime.now(timezone.utc)
#     iso_now = utc_now_dt.isoformat()
#     iso_later = (utc_now_dt + timedelta(minutes=1)).isoformat()
#     current_rule_db_data = {
#         "id": str(TEST_RULE_ID),
#         "link_id": str(TEST_LINK_ID),
#         "priority": 10,
#         "rule_type": "clicks",
#         "target_type": "url",
#         "target_value": "http://old.example.com",
#         "max_clicks": 50,
#         "current_clicks": 5,
#         "start_time": None,
#         "end_time": None,
#         "created_at": iso_now,
#         "updated_at": iso_now,
#     }
#     updated_rule_db_data = {
#         **current_rule_db_data,
#         "priority": 15,
#         "target_value": "http://new.example.com",
#         "updated_at": iso_later,
#     }

#     # Arrange: Oczekujemy 4 wywołań execute (verify*2 + select*1 + update*1)
#     mock_execute = mock_supabase_client.table.return_value.execute
#     ownership_responses = mock_ownership_verification_success_sequence()
#     mock_select_current = MagicMock()
#     mock_select_current.data = current_rule_db_data
#     mock_update_response = MagicMock()
#     mock_update_response.data = [updated_rule_db_data]
#     mock_execute.side_effect = ownership_responses + [
#         mock_select_current,
#         mock_update_response,
#     ]

#     # Act
#     updated_rule = await rule_service.update_rule(
#         link_id=TEST_LINK_ID,
#         rule_id=TEST_RULE_ID,
#         update_data=update_payload,
#         user_id=TEST_USER_ID,
#     )

#     # Assert
#     assert isinstance(updated_rule, RuleResponse)
#     assert updated_rule.priority == 15
#     # Sprawdź payload przekazany do update mocka
#     update_call_args = (
#         mock_supabase_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.call_args
#     )
#     # Trzeba sprawdzić, co dokładnie jest w update_call_args, bo mockujemy execute, a nie update
#     # Lepsza asercja: sprawdźmy liczbę wywołań
#     assert mock_execute.call_count == 4


@pytest.mark.asyncio
async def test_update_rule_priority_conflict(
    rule_service: RuleService, mock_supabase_client
):
    """Testuje konflikt priorytetu podczas aktualizacji."""
    update_payload = RuleUpdate(priority=1)
    utc_now_dt = datetime.now(timezone.utc)
    iso_now = utc_now_dt.isoformat()
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

    # Arrange: Oczekujemy 4 wywołań execute (verify*2 + select*1 + update*1->Error)
    mock_execute = mock_supabase_client.table.return_value.execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_select_current = MagicMock()
    mock_select_current.data = current_rule_db_data
    mock_postgrest_error = PostgrestAPIError(
        {
            "message": f"duplicate key...{ROUTING_RULES_LINK_ID_PRIORITY_KEY}...",
            "code": POSTGRES_UNIQUE_VIOLATION_CODE,
            "details": "",
            "hint": None,
        }
    )
    mock_execute.side_effect = ownership_responses + [
        mock_select_current,
        mock_postgrest_error,
    ]

    # Act & Assert
    with pytest.raises(PriorityConflictException):
        await rule_service.update_rule(
            link_id=TEST_LINK_ID,
            rule_id=TEST_RULE_ID,
            update_data=update_payload,
            user_id=TEST_USER_ID,
        )
    assert mock_execute.call_count == 4


# TODO FIX TEST
# @pytest.mark.asyncio
# async def test_update_rule_validation_error(
#     rule_service: RuleService, mock_supabase_client
# ):
#     """Testuje błąd walidacji PO pobraniu obecnej reguły."""
#     update_payload = RuleUpdate(rule_type=RuleTypeEnum.TIME)  # Brak dat
#     utc_now_dt = datetime.now(timezone.utc)
#     iso_now = utc_now_dt.isoformat()
#     current_rule_db_data = {
#         "id": str(TEST_RULE_ID),
#         "link_id": str(TEST_LINK_ID),
#         "priority": 10,
#         "rule_type": "clicks",
#         "target_type": "url",
#         "target_value": "http://old.example.com",
#         "max_clicks": 50,
#         "current_clicks": 5,
#         "start_time": None,
#         "end_time": None,
#         "created_at": iso_now,
#         "updated_at": iso_now,
#     }

#     # Arrange: Oczekujemy 3 wywołań execute (verify*2 + select*1). Update nie jest wołany.
#     mock_execute = mock_supabase_client.table.return_value.execute
#     ownership_responses = mock_ownership_verification_success_sequence()
#     mock_select_current = MagicMock()
#     mock_select_current.data = current_rule_db_data
#     mock_execute.side_effect = ownership_responses + [mock_select_current]

#     # Act & Assert
#     with pytest.raises(
#         ValidationException
#     ):  # Oczekujemy błędu z jawnej walidacji w serwisie
#         await rule_service.update_rule(
#             link_id=TEST_LINK_ID,
#             rule_id=TEST_RULE_ID,
#             update_data=update_payload,
#             user_id=TEST_USER_ID,
#         )

#     assert mock_execute.call_count == 3
#     # Sprawdź, czy metoda update NIE została wywołana
#     mock_update_execute = (
#         mock_supabase_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute
#     )
#     mock_update_execute.assert_not_awaited()


# --- Testy dla delete_rule ---
@pytest.mark.asyncio
async def test_delete_rule_success(rule_service: RuleService, mock_supabase_client):
    """Testuje pomyślne usunięcie reguły."""
    # Arrange: Mock verify(2) + delete(1) = 3 execute calls
    mock_execute = mock_supabase_client.table.return_value.execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_delete_response = MagicMock()
    mock_delete_response.count = 1
    mock_delete_response.data = []
    mock_execute.side_effect = ownership_responses + [mock_delete_response]

    # Act
    await rule_service.delete_rule(
        link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert mock_execute.call_count == 3


@pytest.mark.asyncio
async def test_delete_rule_not_found(rule_service: RuleService, mock_supabase_client):
    """Testuje próbę usunięcia nieistniejącej reguły."""
    # Arrange: Mock verify(2) + delete(1) returns count=0 = 3 execute calls
    mock_execute = mock_supabase_client.table.return_value.execute
    ownership_responses = mock_ownership_verification_success_sequence()
    mock_delete_response = MagicMock()
    mock_delete_response.count = 0
    mock_delete_response.data = []
    mock_execute.side_effect = ownership_responses + [mock_delete_response]

    # Act & Assert
    with pytest.raises(
        NotFoundException, match="Rule not found or you do not have permission"
    ):
        await rule_service.delete_rule(
            link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
        )
    assert mock_execute.call_count == 3
