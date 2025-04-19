# tests/services/test_rule_service.py

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, ANY, patch
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta

# Importy z Twojego kodu
from supabase import AsyncClient
from postgrest.exceptions import APIError as PostgrestAPIError
from postgrest.types import CountMethod
from src.services.rule_service import RuleService
from src.services.custom_exceptions import (
    DatabaseException,
    NotFoundException,
    ParentLinkNotFoundException,
    PriorityConflictException,
    ValidationException,
)
from src.schemas.rule import RuleCreate, RuleUpdate, RuleResponse
from src.schemas.enums import RuleTypeEnum, TargetTypeEnum

# --- Fixtures ---


@pytest.fixture
def mock_supabase_client(mocker):
    """Fixture to create a mock Supabase AsyncClient."""
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
            mock_table.execute = AsyncMock(name=f"table({table_name}).execute")
            mock_tables[table_name] = mock_table
        return mock_tables[table_name]

    mock_client.table.side_effect = get_mock_table
    return mock_client


@pytest.fixture
def rule_service(mock_supabase_client):
    """Fixture to create an instance of RuleService with the mocked client."""
    return RuleService(supabase_client=mock_supabase_client)


# Helper function to create mock DB response objects
def create_mock_response(data=None, count=None):
    mock_response = MagicMock()
    mock_response.data = data
    mock_response.count = count
    return mock_response


# --- Test Data ---
TEST_USER_ID = uuid4()
TEST_LINK_ID = uuid4()
TEST_RULE_ID = uuid4()
NOW = datetime.now(timezone.utc)

VALID_RULE_CREATE_TIME_DATA = {
    "priority": 10,
    "rule_type": RuleTypeEnum.TIME,
    "target_type": TargetTypeEnum.URL,
    "target_value": "https://time-rule.com",
    "start_time": NOW,
    "end_time": NOW + timedelta(days=1),
}

VALID_RULE_CREATE_CLICKS_DATA = {
    "priority": 20,
    "rule_type": RuleTypeEnum.CLICKS,
    "target_type": TargetTypeEnum.HTML,
    "target_value": "<h1>Clicks Rule</h1>",
    "max_clicks": 1000,
}

# --- Test Cases ---

# === Testy dla _verify_link_ownership === (metoda prywatna, testowana pośrednio)

# === Testy dla add_rule_to_link ===


@pytest.mark.asyncio
async def test_add_rule_success(rule_service, mock_supabase_client):
    """Test successfully adding a new rule."""
    rule_create = RuleCreate(**VALID_RULE_CREATE_TIME_DATA)
    # Mock _verify_link_ownership (zamiast mockować DB call, mockujemy metodę serwisu)
    # Tutaj zakładamy, że chcemy testować add_rule_to_link niezależnie od _verify...
    with patch.object(
        rule_service, "_verify_link_ownership", return_value=None
    ) as mock_verify:

        # Mock insert response
        expected_db_data = {
            "id": str(TEST_RULE_ID),
            "link_id": str(TEST_LINK_ID),
            "priority": 10,
            "rule_type": "time",
            "target_type": "url",
            "target_value": "https://time-rule.com",
            "start_time": NOW.isoformat(),
            "end_time": (NOW + timedelta(days=1)).isoformat(),
            "max_clicks": None,
            "current_clicks": 0,
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
        }
        mock_response = create_mock_response(data=[expected_db_data])
        mock_supabase_client.table(rule_service.rules_table).execute.return_value = (
            mock_response
        )

        # Act
        result = await rule_service.add_rule_to_link(
            link_id=TEST_LINK_ID, rule_data=rule_create, user_id=TEST_USER_ID
        )

        # Assert
        mock_verify.assert_awaited_once_with(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)
        mock_supabase_client.table(rule_service.rules_table).insert.assert_called_once()
        # Sprawdźmy kluczowe pola w insercie
        insert_call_args = mock_supabase_client.table(
            rule_service.rules_table
        ).insert.call_args[0][0]
        assert insert_call_args["link_id"] == str(TEST_LINK_ID)
        assert insert_call_args["priority"] == 10
        assert (
            insert_call_args["rule_type"] == RuleTypeEnum.TIME
        )  # Sprawdź enum lub .value
        mock_supabase_client.table(
            rule_service.rules_table
        ).execute.assert_awaited_once()

        assert isinstance(result, RuleResponse)
        assert result.id == TEST_RULE_ID
        assert result.priority == 10


@pytest.mark.asyncio
async def test_add_rule_link_not_found(rule_service, mock_supabase_client):
    """Test adding a rule when the parent link is not found or owned."""
    rule_create = RuleCreate(**VALID_RULE_CREATE_TIME_DATA)
    # Mock _verify_link_ownership to raise the exception
    with patch.object(
        rule_service,
        "_verify_link_ownership",
        side_effect=ParentLinkNotFoundException(detail="Link not found"),
    ) as mock_verify:

        # Act & Assert
        with pytest.raises(ParentLinkNotFoundException):
            await rule_service.add_rule_to_link(
                link_id=TEST_LINK_ID, rule_data=rule_create, user_id=TEST_USER_ID
            )

        mock_verify.assert_awaited_once_with(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)
        # Assert insert was NOT called
        mock_supabase_client.table(rule_service.rules_table).insert.assert_not_called()


@pytest.mark.asyncio
async def test_add_rule_priority_conflict(rule_service, mock_supabase_client):
    """Test adding a rule when the priority conflicts."""
    rule_create = RuleCreate(**VALID_RULE_CREATE_TIME_DATA)
    with patch.object(
        rule_service, "_verify_link_ownership", return_value=None
    ):  # Mock verify success
        # Mock insert to raise priority conflict error
        db_error = PostgrestAPIError(
            {
                "message": 'duplicate key value violates unique constraint "routing_rules_link_id_priority_key"',
                "code": "23505",
                "details": "Key (link_id, priority)=(..., 10) already exists.",
            }
        )
        mock_supabase_client.table(rule_service.rules_table).execute.side_effect = (
            db_error
        )

        # Act & Assert
        with pytest.raises(PriorityConflictException):
            await rule_service.add_rule_to_link(
                link_id=TEST_LINK_ID, rule_data=rule_create, user_id=TEST_USER_ID
            )
        mock_supabase_client.table(
            rule_service.rules_table
        ).execute.assert_awaited_once()


# === Testy dla get_rules_for_link ===


@pytest.mark.asyncio
async def test_get_rules_for_link_success(rule_service, mock_supabase_client):
    """Test retrieving rules for a link."""
    with patch.object(
        rule_service, "_verify_link_ownership", return_value=None
    ) as mock_verify:
        # Mock select response
        db_rule1 = {
            "id": str(uuid4()),
            "link_id": str(TEST_LINK_ID),
            "priority": 10,
            "rule_type": "time",
            "target_type": "url",
            "target_value": "url1",
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
            "current_clicks": 0,
        }
        db_rule2 = {
            "id": str(uuid4()),
            "link_id": str(TEST_LINK_ID),
            "priority": 20,
            "rule_type": "clicks",
            "target_type": "html",
            "target_value": "html",
            "max_clicks": 100,
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
            "current_clicks": 5,
        }
        mock_response = create_mock_response(data=[db_rule1, db_rule2])
        mock_supabase_client.table(rule_service.rules_table).execute.return_value = (
            mock_response
        )

        # Act
        results = await rule_service.get_rules_for_link(
            link_id=TEST_LINK_ID, user_id=TEST_USER_ID
        )

        # Assert
        mock_verify.assert_awaited_once_with(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)
        mock_supabase_client.table(rule_service.rules_table).select.assert_called_with(
            "*"
        )
        mock_supabase_client.table(rule_service.rules_table).eq.assert_called_with(
            "link_id", str(TEST_LINK_ID)
        )
        mock_supabase_client.table(rule_service.rules_table).order.assert_called_with(
            "priority", desc=False
        )
        mock_supabase_client.table(
            rule_service.rules_table
        ).execute.assert_awaited_once()

        assert isinstance(results, list)
        assert len(results) == 2
        assert isinstance(results[0], RuleResponse)
        assert results[0].priority == 10
        assert results[1].priority == 20


@pytest.mark.asyncio
async def test_get_rules_for_link_not_found(rule_service, mock_supabase_client):
    """Test retrieving rules for a non-existent/unowned link."""
    with patch.object(
        rule_service, "_verify_link_ownership", side_effect=ParentLinkNotFoundException
    ) as mock_verify:

        # Act & Assert
        with pytest.raises(ParentLinkNotFoundException):
            await rule_service.get_rules_for_link(
                link_id=TEST_LINK_ID, user_id=TEST_USER_ID
            )

        mock_verify.assert_awaited_once_with(link_id=TEST_LINK_ID, user_id=TEST_USER_ID)
        # Assert select was NOT called
        mock_supabase_client.table(rule_service.rules_table).select.assert_not_called()


# === Testy dla get_rule_details ===


@pytest.mark.asyncio
async def test_get_rule_details_success(rule_service, mock_supabase_client):
    """Test retrieving details for a specific rule."""
    expected_db_data = {
        "id": str(TEST_RULE_ID),
        "link_id": str(TEST_LINK_ID),
        "priority": 10,
        "rule_type": "time",
        "target_type": "url",
        "target_value": "url1",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "current_clicks": 0,
    }
    mock_response = create_mock_response(data=expected_db_data)
    mock_supabase_client.table(rule_service.rules_table).execute.return_value = (
        mock_response
    )

    # Act
    result = await rule_service.get_rule_details(
        link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
    )

    # Assert
    assert isinstance(result, RuleResponse)
    assert result.id == TEST_RULE_ID
    assert result.priority == 10
    # Sprawdź wywołanie Supabase
    mock_supabase_client.table(rule_service.rules_table).select.assert_called_with("*")
    # Sprawdź oba eq calls - kolejność może być różna, użyj assert_any_call lub sprawdź call_args_list
    mock_supabase_client.table(rule_service.rules_table).eq.assert_any_call(
        "id", str(TEST_RULE_ID)
    )
    mock_supabase_client.table(rule_service.rules_table).eq.assert_any_call(
        "link_id", str(TEST_LINK_ID)
    )
    mock_supabase_client.table(
        rule_service.rules_table
    ).maybe_single.assert_called_once()
    mock_supabase_client.table(rule_service.rules_table).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_rule_details_not_found(rule_service, mock_supabase_client):
    """Test retrieving details for a non-existent rule."""
    mock_response = create_mock_response(data=None)
    mock_supabase_client.table(rule_service.rules_table).execute.return_value = (
        mock_response
    )

    # Act & Assert
    with pytest.raises(NotFoundException):
        await rule_service.get_rule_details(
            link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
        )

    mock_supabase_client.table(rule_service.rules_table).execute.assert_awaited_once()


# === Testy dla update_rule ===


@pytest.mark.asyncio
async def test_update_rule_success(rule_service, mock_supabase_client):
    """Test successfully updating a rule."""
    update_data = RuleUpdate(priority=5, target_value="https://new-target.com")
    current_db_rule = {
        "id": str(TEST_RULE_ID),
        "link_id": str(TEST_LINK_ID),
        "priority": 10,
        "rule_type": "time",
        "target_type": "url",
        "target_value": "https://old.com",
        "start_time": NOW.isoformat(),
        "end_time": (NOW + timedelta(days=1)).isoformat(),
        "max_clicks": None,
        "current_clicks": 0,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    expected_db_payload = {"priority": 5, "target_value": "https://new-target.com"}
    updated_db_rule = {**current_db_rule, **expected_db_payload}

    # Mock verify link ownership
    with patch.object(rule_service, "_verify_link_ownership", return_value=None):
        # Mock get current rule state
        mock_get_response = create_mock_response(data=current_db_rule)
        # Mock update response
        mock_update_response = create_mock_response(
            data=[updated_db_rule]
        )  # update zwraca listę

        # Konfiguracja execute dla różnych kroków
        mock_execute = AsyncMock()
        mock_execute.side_effect = [mock_get_response, mock_update_response]
        mock_supabase_client.table(rule_service.rules_table).execute = mock_execute

        # Act
        result = await rule_service.update_rule(
            link_id=TEST_LINK_ID,
            rule_id=TEST_RULE_ID,
            update_data=update_data,
            user_id=TEST_USER_ID,
        )

        # Assert
        assert isinstance(result, RuleResponse)
        assert result.id == TEST_RULE_ID
        assert result.priority == 5
        assert result.target_value == "https://new-target.com"

        # Sprawdź wywołania
        assert mock_execute.await_count == 2
        # Sprawdź wywołanie update
        mock_supabase_client.table(
            rule_service.rules_table
        ).update.assert_called_once_with(expected_db_payload)


@pytest.mark.asyncio
async def test_update_rule_validation_error(rule_service, mock_supabase_client):
    """Test update fails due to inconsistent data after merge."""
    # Np. zmieniamy typ na 'clicks', ale nie podajemy max_clicks
    update_data = RuleUpdate(rule_type=RuleTypeEnum.CLICKS)
    current_db_rule = {  # Obecnie reguła czasowa
        "id": str(TEST_RULE_ID),
        "link_id": str(TEST_LINK_ID),
        "priority": 10,
        "rule_type": "time",
        "target_type": "url",
        "target_value": "https://old.com",
        "start_time": NOW.isoformat(),
        "end_time": (NOW + timedelta(days=1)).isoformat(),
        "max_clicks": None,
        "current_clicks": 0,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    # Mock verify link ownership i get current rule
    with patch.object(rule_service, "_verify_link_ownership", return_value=None):
        mock_get_response = create_mock_response(data=current_db_rule)
        mock_supabase_client.table(rule_service.rules_table).execute.return_value = (
            mock_get_response
        )

        # Act & Assert
        with pytest.raises(
            ValidationException, match='max_clicks is required for rule_type "clicks"'
        ):
            await rule_service.update_rule(
                link_id=TEST_LINK_ID,
                rule_id=TEST_RULE_ID,
                update_data=update_data,
                user_id=TEST_USER_ID,
            )
        # Sprawdź, że update nie został wywołany
        mock_supabase_client.table(rule_service.rules_table).update.assert_not_called()


@pytest.mark.asyncio
async def test_update_rule_priority_conflict(rule_service, mock_supabase_client):
    """Test update fails due to priority conflict."""
    update_data = RuleUpdate(priority=5)  # Tylko priorytet jest w update
    # Mock obecnego stanu reguły z poprawnymi danymi
    current_db_rule = {
        "id": str(TEST_RULE_ID),
        "link_id": str(TEST_LINK_ID),
        "priority": 10,  # Obecny priorytet
        "rule_type": "time",
        "target_type": "url",
        "target_value": "https://correct-current-url.com",  # <<< POPRAWIONY URL
        "start_time": NOW.isoformat(),  # Wymagane dla typu 'time' przez RuleCreate
        "end_time": (NOW + timedelta(days=1)).isoformat(),  # Wymagane dla typu 'time'
        "max_clicks": None,  # Oczekiwane None dla typu 'time' przez RuleCreate
        "current_clicks": 0,  # Wymagane przez RuleResponse (choć nie przez RuleCreate)
        "created_at": NOW.isoformat(),  # Wymagane przez RuleResponse
        "updated_at": NOW.isoformat(),  # Wymagane przez RuleResponse
    }
    # Mock verify i get
    with patch.object(rule_service, "_verify_link_ownership", return_value=None):
        mock_get_response = create_mock_response(data=current_db_rule)
        # Mock update to raise priority conflict
        db_error = PostgrestAPIError(
            {
                "message": 'duplicate key value violates unique constraint "routing_rules_link_id_priority_key"',
                "code": "23505",
                "details": "Key (link_id, priority)=(..., 5) already exists.",
            }
        )
        # Konfiguracja side_effect dla execute
        mock_execute = AsyncMock()
        # Pierwsze wywołanie (get) zwraca dane, drugie (update) rzuca błąd
        mock_execute.side_effect = [mock_get_response, db_error]
        mock_supabase_client.table(rule_service.rules_table).execute = mock_execute

        # Act & Assert - Oczekujemy teraz PriorityConflictException
        with pytest.raises(PriorityConflictException):
            await rule_service.update_rule(
                link_id=TEST_LINK_ID,
                rule_id=TEST_RULE_ID,
                update_data=update_data,  # update_data zawiera tylko priority=5
                user_id=TEST_USER_ID,
            )
        # Sprawdź, czy execute zostało wywołane dwa razy
        assert mock_execute.await_count == 2
        # Sprawdź, czy próbowano wykonać update z poprawnym payloadem (tylko priority)
        mock_supabase_client.table(
            rule_service.rules_table
        ).update.assert_called_once_with({"priority": 5})


# === Testy dla delete_rule ===


@pytest.mark.asyncio
async def test_delete_rule_success(rule_service, mock_supabase_client):
    """Test successful rule deletion."""
    with patch.object(
        rule_service, "_verify_link_ownership", return_value=None
    ) as mock_verify:
        mock_response = create_mock_response(count=1)
        mock_supabase_client.table(rule_service.rules_table).execute.return_value = (
            mock_response
        )

        # Act
        await rule_service.delete_rule(
            link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
        )

        # Assert
        mock_verify.assert_awaited_once()
        mock_supabase_client.table(
            rule_service.rules_table
        ).delete.assert_called_once_with(count=CountMethod.exact)
        # Sprawdź oba eq
        mock_supabase_client.table(rule_service.rules_table).eq.assert_any_call(
            "id", str(TEST_RULE_ID)
        )
        mock_supabase_client.table(rule_service.rules_table).eq.assert_any_call(
            "link_id", str(TEST_LINK_ID)
        )
        mock_supabase_client.table(
            rule_service.rules_table
        ).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_rule_not_found(rule_service, mock_supabase_client):
    """Test deleting a non-existent rule."""
    with patch.object(rule_service, "_verify_link_ownership", return_value=None):
        mock_response = create_mock_response(count=0)
        mock_supabase_client.table(rule_service.rules_table).execute.return_value = (
            mock_response
        )

        # Act & Assert
        with pytest.raises(NotFoundException):
            await rule_service.delete_rule(
                link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
            )

        mock_supabase_client.table(
            rule_service.rules_table
        ).execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_rule_link_not_found(rule_service, mock_supabase_client):
    """Test deleting a rule when parent link verification fails."""
    with patch.object(
        rule_service, "_verify_link_ownership", side_effect=ParentLinkNotFoundException
    ) as mock_verify:

        # Act & Assert
        with pytest.raises(ParentLinkNotFoundException):
            await rule_service.delete_rule(
                link_id=TEST_LINK_ID, rule_id=TEST_RULE_ID, user_id=TEST_USER_ID
            )

        mock_verify.assert_awaited_once()
        # Delete nie powinno być wywołane
        mock_supabase_client.table(rule_service.rules_table).delete.assert_not_called()
