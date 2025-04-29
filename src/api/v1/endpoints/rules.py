# src/api/v1/endpoints/rules.py (Corrected - Removed Path parameter for link_id where appropriate)

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    status,
    Request,
    Response,
    Form,
)
from fastapi.templating import Jinja2Templates
from uuid import UUID
from typing import List, Optional
import traceback
from datetime import datetime
from fastapi import Form
from typing import Optional
from datetime import datetime

# Import modeli Pydantic (DTOs)
from src.schemas.rule import RuleCreate, RuleUpdate, RuleResponse

# Import serwisu i wyjątków
from src.services.rule_service import RuleService
from src.services.custom_exceptions import (
    DatabaseException,
    NotFoundException,
    PriorityConflictException,
    ValidationException,
    ServiceException,
)

# Import zależności
from src.api.deps import get_current_user_id, get_rule_service, get_templates

router = APIRouter()


# --- Endpoint zwracający PUSTY formularz tworzenia reguły ---
@router.get(
    "/create-form-partial",
    summary="Get Rule Creation Form HTML Partial",
    description="Returns an HTML fragment containing an empty form for creating a new rule.",
    tags=["Rules UI Partials"],
    include_in_schema=False,
)
async def get_rule_create_form_partial(
    request: Request,
    link_id: UUID,  # <<< Usunięto Path(...), wartość pobierana z prefiksu montowania routera
    templates: Jinja2Templates = Depends(get_templates),
):
    """Renders the partial template for the rule form (empty)."""
    print(f"Fetching create form partial for link {link_id}")
    return templates.TemplateResponse(
        "partials/rule_form.html",
        {
            "request": request,
            "link_id": link_id,
            "rule": None,
            "now": datetime.utcnow(),
        },
    )


# --- Endpoint zwracający WYPEŁNIONY formularz edycji reguły ---
@router.get(
    "/{rule_id}/edit-form-partial",
    summary="Get Rule Edit Form HTML Partial",
    description="Returns an HTML fragment containing a pre-filled form for editing an existing rule.",
    tags=["Rules UI Partials"],
    include_in_schema=False,
)
async def get_rule_edit_form_partial(
    request: Request,
    link_id: UUID,  # <<< Usunięto Path(...)
    rule_id: UUID = Path(
        ..., description="The ID of the rule to edit"
    ),  # rule_id jest częścią ścieżki względnej
    user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Fetches rule data and renders the rule form partial template pre-filled."""
    print(
        f"Fetching edit form partial for rule {rule_id} on link {link_id} by user {user_id}"
    )
    try:
        rule = await rule_service.get_rule_details(
            link_id=link_id, rule_id=rule_id, user_id=user_id
        )
        return templates.TemplateResponse(
            "partials/rule_form.html",
            {
                "request": request,
                "link_id": link_id,
                "rule": rule,
                "now": datetime.utcnow(),
            },
        )
    except NotFoundException as e:
        print(
            f"[NOT FOUND] Rule {rule_id} or Link {link_id} not found for edit form, user {user_id}: {e.detail}"
        )
        return templates.TemplateResponse(
            "partials/modal_error.html",
            {
                "request": request,
                "error_title": "Błąd Ładowania Formularza",
                "error_message": e.detail,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        print(f"Error fetching rule for edit form partial (rule {rule_id}): {e}")
        return templates.TemplateResponse(
            "partials/modal_error.html",
            {
                "request": request,
                "error_title": "Błąd Serwera",
                "error_message": "Nie udało się załadować formularza edycji.",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# --- Endpoint zwracający fragment HTML dla listy reguł ---
@router.get(
    "/list-partial",
    summary="Get Rules List HTML Partial",
    description="Returns an HTML fragment containing table rows for the rules of a specific link.",
    tags=["Rules UI Partials"],
    include_in_schema=False,
)
async def get_rules_list_partial(
    request: Request,
    link_id: UUID,  # <<< Usunięto Path(...)
    user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Fetches rules for a link and renders them as HTML table rows."""
    print(f"Fetching rules list partial for link {link_id} by user {user_id}")
    try:
        rules = await rule_service.get_rules_for_link(link_id=link_id, user_id=user_id)
        return templates.TemplateResponse(
            "partials/rule_rows.html",
            {"request": request, "rules": rules, "link_id": link_id},
        )
    except NotFoundException as e:
        print(
            f"[NOT FOUND] Link {link_id} not found for rules partial, user {user_id}: {e.detail}"
        )
        return templates.TemplateResponse(
            "partials/rule_row_error.html",
            {
                "request": request,
                "error_message": "Link nie został znaleziony lub nie masz uprawnień.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        print(f"Error fetching rules for partial rendering (link {link_id}): {e}")
        return templates.TemplateResponse(
            "partials/rule_row_error.html",
            {"request": request, "error_message": "Nie udało się załadować reguł."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# --- Endpoint POST / (tworzenie reguły) ---
@router.post(
    "/create",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Rule from Form Data",
    description="Adds a new routing rule using form data.",
    tags=["Rules"],
)
async def create_rule_endpoint(
    link_id: UUID,
    # --- Przyjmowanie danych formularza ---
    priority: int = Form(...),
    rule_type: str = Form(...),  # Enumy odbieramy jako stringi
    target_type: str = Form(...),
    target_value: str = Form(...),
    start_time: Optional[str] = Form(None),  # Odbieramy daty jako stringi
    end_time: Optional[str] = Form(None),
    max_clicks: Optional[str] = Form(
        None
    ),  # <<< ZMIANA: Odbieramy jako Optional[str], bo może przyjść ""
    # --------------------------------------
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """Creates a new routing rule for the specified link from form data."""
    print(
        f"Received request to create rule via form for link {link_id} by user {current_user_id}"
    )
    print(
        f"Raw form data: priority={priority}, rule_type={rule_type}, target_type={target_type}, target_value={target_value}, start={start_time}, end={end_time}, max_clicks={max_clicks}"
    )

    # Ręcznie stwórz słownik i skonwertuj/waliduj
    rule_data_dict: Dict[str, Any] = {  # Używamy Any dla elastyczności przed walidacją
        "priority": priority,
        "rule_type": rule_type,
        "target_type": target_type,
        "target_value": target_value,
    }

    # --- POPRAWKA: Obsługa pustych stringów dla pól opcjonalnych ---
    parsed_start_time = None
    if (
        start_time and start_time.strip()
    ):  # Sprawdź czy nie jest None i nie jest pusty/białe znaki
        try:
            parsed_start_time = datetime.strptime(start_time.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid format for start_time: '{start_time}'. Use YYYY-MM-DD HH:MM.",
            )
    rule_data_dict["start_time"] = (
        parsed_start_time  # Przypisz sparsowaną datę lub None
    )

    parsed_end_time = None
    if end_time and end_time.strip():
        try:
            parsed_end_time = datetime.strptime(end_time.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid format for end_time: '{end_time}'. Use YYYY-MM-DD HH:MM.",
            )
    rule_data_dict["end_time"] = parsed_end_time

    parsed_max_clicks = None
    if (
        max_clicks and max_clicks.strip()
    ):  # Sprawdź czy nie jest None i nie jest pusty/białe znaki
        try:
            parsed_max_clicks = int(max_clicks.strip())
            if parsed_max_clicks < 1:  # Dodatkowa walidacja wartości
                raise ValueError("max_clicks must be positive")
        except ValueError:
            # Złapie zarówno błąd konwersji int(), jak i nasz ValueError
            raise HTTPException(
                status_code=422,
                detail=f"Invalid value for max_clicks: '{max_clicks}'. Must be a positive integer.",
            )
    rule_data_dict["max_clicks"] = parsed_max_clicks
    # ---------------------------------------------------------------

    try:
        # Walidacja Pydantic - teraz powinna otrzymać None zamiast "" dla max_clicks
        print(f"Data prepared for Pydantic validation: {rule_data_dict}")
        rule_data = RuleCreate.model_validate(rule_data_dict)
        print("RuleCreate DTO validated:", rule_data.model_dump())
    except Exception as validation_error:
        print(f"Validation error creating RuleCreate DTO: {validation_error}")
        # Formatowanie błędu Pydantic
        error_details = getattr(
            validation_error, "errors", lambda: [{"msg": str(validation_error)}]
        )()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_details,  # Przekaż szczegóły błędu walidacji
        )

    # Kontynuuj z logiką serwisu
    try:
        created_rule = await rule_service.add_rule_to_link(
            link_id=link_id, rule_data=rule_data, user_id=current_user_id
        )
        return created_rule
    # ... (reszta obsługi błędów serwisu bez zmian) ...
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent link not found or access denied.",
        )
    except (PriorityConflictException, ValidationException) as e:
        status_code = (
            status.HTTP_409_CONFLICT
            if isinstance(e, PriorityConflictException)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=e.detail)
    except (DatabaseException, ServiceException) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {e.detail}",
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint GET / (pobieranie listy reguł JSON) ---
@router.get(
    "/",
    response_model=List[RuleResponse],
    summary="List Rules for Link",
    description="Retrieves a list of all routing rules...",
    tags=["Rules"],
)
async def list_rules_endpoint(
    link_id: UUID,  # <<< Usunięto Path(...)
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """Retrieves all rules for a specific link (JSON response)..."""
    print(
        f"Received request to list rules (JSON) for link {link_id} by user {current_user_id}"
    )
    try:
        rules = await rule_service.get_rules_for_link(
            link_id=link_id, user_id=current_user_id
        )
        print(f"Returning JSON response for {len(rules)} rules.")
        return rules
    except NotFoundException as e:
        print(
            f"[NOT FOUND] Parent link {link_id} not found or access denied: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent link not found or access denied.",
        )
    except DatabaseException as e:
        print(f"[ERROR] Database error listing rules for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e.detail}",
        )
    except Exception as e:
        print(
            f"[ERROR] Unexpected error in list_rules_endpoint for link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint GET /{rule_id} (pobieranie pojedynczej reguły) ---
@router.get(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Get Rule Details",
    description="Retrieves details of a specific routing rule...",
    tags=["Rules"],
)
async def get_rule_endpoint(
    link_id: UUID,  # <<< Usunięto Path(...)
    rule_id: UUID = Path(
        ..., description="The ID of the rule to retrieve"
    ),  # rule_id jest OK jako Path
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """Retrieves details for a single rule (JSON response)."""
    print(
        f"Received request to get rule {rule_id} for link {link_id} by user {current_user_id} (JSON)"
    )
    try:
        rule = await rule_service.get_rule_details(
            link_id=link_id, rule_id=rule_id, user_id=current_user_id
        )
        return rule
    except NotFoundException as e:
        print(
            f"[NOT FOUND] {e.detail} for rule {rule_id} on link {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        print(
            f"[ERROR] Database error getting rule {rule_id} for link {link_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e.detail}",
        )
    except Exception as e:
        print(
            f"[ERROR] Unexpected error getting rule {rule_id} for link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint PATCH /{rule_id} (aktualizacja reguły) ---
@router.patch(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Update Rule from Form Data",  # Zmieniono summary
    description="Updates details of a specific routing rule using form data.",
    tags=["Rules"],
)
async def update_rule_endpoint(
    link_id: UUID,  # Z prefiksu
    rule_id: UUID = Path(..., description="The ID of the rule to update"),
    # --- Przyjmowanie danych formularza ---
    # Odbieramy WSZYSTKIE potencjalne pola jako Optional[str/int],
    # bo PATCH może wysłać tylko zmienione pola (chociaż nasz formularz wyśle wszystkie widoczne).
    # Używamy `Form(None)` jako wartości domyślnej, aby odróżnić brak pola od pustego stringa.
    priority: Optional[int] = Form(None),
    rule_type: Optional[str] = Form(None),
    target_type: Optional[str] = Form(None),
    target_value: Optional[str] = Form(
        None
    ),  # Pusty string jest ważny dla usunięcia HTML/URL
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
    max_clicks: Optional[str] = Form(None),  # Odbieramy jako string na wypadek ""
    # --------------------------------------
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """Updates specific fields of a routing rule using form data."""
    print(
        f"Received request to update rule {rule_id} via form for link {link_id} by user {current_user_id}"
    )

    # Zbuduj słownik tylko z tymi polami, które zostały faktycznie przesłane w formularzu
    # (Form(...) zwróci None, jeśli pole nie zostało wysłane lub było puste i nie ma default)
    update_data_dict: Dict[str, Any] = {}
    if priority is not None:
        update_data_dict["priority"] = priority
    if rule_type is not None:
        update_data_dict["rule_type"] = rule_type
    if target_type is not None:
        update_data_dict["target_type"] = target_type

    # Dla target_value, start_time, end_time, max_clicks - pozwalamy na pusty string/None
    # Konwersja i walidacja odbędzie się w Pydantic lub serwisie
    if target_value is not None:  # Przekaż nawet pusty string
        update_data_dict["target_value"] = target_value

    parsed_start_time = None
    if start_time is not None and start_time.strip():  # Konwertuj tylko jeśli niepuste
        try:
            parsed_start_time = datetime.strptime(start_time.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid format for start_time: '{start_time}'. Use YYYY-MM-DD HH:MM.",
            )
    # Przekaż None, jeśli start_time było puste lub None
    if start_time is not None:  # Przekazujemy klucz tylko, jeśli pole było w formularzu
        update_data_dict["start_time"] = parsed_start_time

    parsed_end_time = None
    if end_time is not None and end_time.strip():
        try:
            parsed_end_time = datetime.strptime(end_time.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid format for end_time: '{end_time}'. Use YYYY-MM-DD HH:MM.",
            )
    if end_time is not None:
        update_data_dict["end_time"] = parsed_end_time

    parsed_max_clicks = None
    if max_clicks is not None and max_clicks.strip():
        try:
            parsed_max_clicks = int(max_clicks.strip())
            if parsed_max_clicks < 1:
                raise ValueError("max_clicks must be positive")
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid value for max_clicks: '{max_clicks}'. Must be a positive integer.",
            )
    if max_clicks is not None:
        update_data_dict["max_clicks"] = parsed_max_clicks

    # Jeśli słownik jest pusty (żadne pole nie zostało zmienione/przesłane),
    # możemy od razu zwrócić błąd lub obecny stan.
    if not update_data_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided."
        )

    try:
        # Walidacja Pydantic dla modelu Update (sprawdzi typy i logikę warunkową pól)
        # Przekazujemy tylko te pola, które przyszły z formularza
        print(f"Data prepared for Pydantic validation (Update): {update_data_dict}")
        update_data = RuleUpdate.model_validate(update_data_dict)
        print("RuleUpdate DTO validated:", update_data.model_dump(exclude_unset=True))
    except Exception as validation_error:
        print(f"Validation error creating RuleUpdate DTO: {validation_error}")
        error_details = getattr(
            validation_error, "errors", lambda: [{"msg": str(validation_error)}]
        )()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_details,
        )

    # Kontynuuj z logiką serwisu
    try:
        updated_rule = await rule_service.update_rule(
            link_id=link_id,
            rule_id=rule_id,
            update_data=update_data,
            user_id=current_user_id,
        )
        # Zwracamy JSON (HTMX odświeży listę przez hx-target na formularzu w modalu)
        return updated_rule
    # ... (Obsługa wyjątków NotFound, PriorityConflict, Validation z serwisu, Database, etc. jak poprzednio) ...
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except (ValidationException, PriorityConflictException) as e:
        status_code = (
            status.HTTP_409_CONFLICT
            if isinstance(e, PriorityConflictException)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=e.detail)
    except (DatabaseException, ServiceException) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {e.detail}",
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint DELETE /{rule_id} (usuwanie reguły) ---
@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Rule",
    description="Deletes a specific routing rule...",
    tags=["Rules"],
)
async def delete_rule_endpoint(
    link_id: UUID,  # <<< Usunięto Path(...)
    rule_id: UUID = Path(
        ..., description="The ID of the rule to delete"
    ),  # rule_id jest OK jako Path
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """Deletes a specific rule identified by its ID and parent link ID."""
    print(
        f"Received request to delete rule {rule_id} for link {link_id} by user {current_user_id}"
    )
    try:
        await rule_service.delete_rule(
            link_id=link_id, rule_id=rule_id, user_id=current_user_id
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NotFoundException as e:
        print(
            f"[NOT FOUND] {e.detail} during delete for rule {rule_id} on link {link_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        print(
            f"[ERROR] Database error deleting rule {rule_id} for link {link_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e.detail}",
        )
    except Exception as e:
        print(
            f"[ERROR] Unexpected error deleting rule {rule_id} for link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Koniec pliku ---
