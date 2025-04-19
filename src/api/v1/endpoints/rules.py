# src/api/v1/endpoints/rules.py

from fastapi import APIRouter, Depends, HTTPException, Path, status, Request, Response
from uuid import UUID
from typing import List, Union, Optional  # Dodano Optional
import traceback

# Import modeli Pydantic (DTOs)
from src.schemas.rule import RuleCreate, RuleUpdate, RuleResponse

# Import serwisu i wyjątków
from src.services.rule_service import RuleService
from src.services.custom_exceptions import (
    DatabaseException,
    NotFoundException,
    ParentLinkNotFoundException,
    PriorityConflictException,
    ValidationException,
    ServiceException,
)

# Import zależności
from src.api.deps import get_current_user_id, get_rule_service

# Import szablonów (dla HTMX)
try:
    from src.main import templates
except ImportError:
    templates = None
    print(
        "[WARNING] Jinja2Templates instance 'templates' not found in main.py. HTMX responses might not work for List Rules."
    )


router = APIRouter()


# --- Endpoint POST /links/{link_id}/rules ---
@router.post(
    "",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Rule",
    description="Adds a new routing rule to a specific link owned by the authenticated user.",
    tags=["Rules"],
)
async def create_rule_endpoint(
    # Reordered: Body parameter first
    rule_data: RuleCreate,
    # Path parameter next
    link_id: UUID = Path(..., description="The ID of the link to add the rule to"),
    # Dependencies last
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """Creates a new routing rule for the specified link."""
    print(
        f"Received request to create rule for link {link_id} by user {current_user_id}"
    )
    try:
        # ... (rest of the function remains the same)
        created_rule = await rule_service.add_rule_to_link(
            link_id=link_id, rule_data=rule_data, user_id=current_user_id
        )
        return created_rule
    except ParentLinkNotFoundException as e:
        print(
            f"[NOT FOUND] Parent link {link_id} not found or access denied for user {current_user_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent link not found or access denied.",
        )
    except PriorityConflictException as e:
        print(f"[CONFLICT] Priority conflict for link {link_id}: {e.detail}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    except DatabaseException as e:
        print(f"[ERROR] Database error creating rule for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e.detail}",
        )
    except ServiceException as e:
        print(f"[ERROR] Service error creating rule for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail
        )
    except Exception as e:
        print(
            f"[ERROR] Unexpected error in create_rule_endpoint for link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint GET /links/{link_id}/rules ---
@router.get(
    "",
    response_model=List[RuleResponse],
    summary="List Rules for Link",
    description="Retrieves a list of all routing rules for a specific link owned by the authenticated user, ordered by priority.",
    tags=["Rules"],
)
async def list_rules_endpoint(
    request: Request,
    link_id: UUID = Path(..., description="The ID of the link whose rules to retrieve"),
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """Retrieves all rules for a specific link, sorted by priority. Can return HTML fragment for HTMX."""
    is_htmx_request = request.headers.get("hx-request") == "true"
    print(
        f"Received request to list rules for link {link_id} by user {current_user_id}. HTMX={is_htmx_request}"
    )
    try:
        rules = await rule_service.get_rules_for_link(
            link_id=link_id, user_id=current_user_id
        )

        if is_htmx_request:
            if templates:
                print(f"Rendering HTMX partial for {len(rules)} rules.")
                return templates.TemplateResponse(
                    "dashboard/rules_list_partial.html",  # Przykładowa nazwa szablonu
                    {"request": request, "rules": rules, "link_id": link_id},
                )
            else:
                print(
                    "[ERROR] HTMX request received but templates are not configured or imported."
                )
                raise HTTPException(
                    status_code=501,
                    detail="HTML templating for HTMX is not configured.",
                )
        else:
            print(f"Returning JSON response for {len(rules)} rules.")
            return rules

    except ParentLinkNotFoundException as e:
        print(
            f"[NOT FOUND] Parent link {link_id} not found or access denied for user {current_user_id}: {e.detail}"
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


# --- Endpoint GET /links/{link_id}/rules/{rule_id} ---
@router.get(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Get Rule Details",
    description="Retrieves details of a specific routing rule within a link owned by the authenticated user.",
    tags=["Rules"],
)
async def get_rule_endpoint(
    link_id: UUID = Path(..., description="The ID of the parent link"),
    rule_id: UUID = Path(..., description="The ID of the rule to retrieve"),
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """Retrieves details for a single rule, ensuring it belongs to the specified link and user."""
    print(
        f"Received request to get rule {rule_id} for link {link_id} by user {current_user_id}"
    )
    try:
        rule = await rule_service.get_rule_details(
            link_id=link_id, rule_id=rule_id, user_id=current_user_id
        )
        return rule
    except (
        NotFoundException
    ) as e:  # Obejmuje nieznalezienie reguły lub linku nadrzędnego (jeśli serwis tak zgłasza)
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


# --- Endpoint PATCH /links/{link_id}/rules/{rule_id} ---
@router.patch(
    "/{rule_id}",
    response_model=RuleResponse,
    summary="Update Rule",
    description="Updates details of a specific routing rule within a link owned by the authenticated user.",
    tags=["Rules"],
)
async def update_rule_endpoint(
    # Reordered: Body parameter first
    update_data: RuleUpdate,
    # Path parameters next
    link_id: UUID = Path(..., description="The ID of the parent link"),
    rule_id: UUID = Path(..., description="The ID of the rule to update"),
    # Dependencies last
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """
    Updates specific fields of a routing rule.
    Requires ownership of the parent link. Validates data consistency upon update.
    """
    update_payload_info = update_data.model_dump(exclude_unset=True)
    print(
        f"Received request to update rule {rule_id} for link {link_id} by user {current_user_id} with data: {update_payload_info}"
    )
    try:
        # ... (reszta funkcji bez zmian)
        updated_rule = await rule_service.update_rule(
            link_id=link_id,
            rule_id=rule_id,
            update_data=update_data,
            user_id=current_user_id,
        )
        return updated_rule
    except (
        NotFoundException
    ) as e:  # Może być rzucony przez weryfikację własności lub nieznalezienie reguły
        print(
            f"[NOT FOUND] {e.detail} during update for rule {rule_id} on link {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except ValidationException as e:  # Błąd walidacji spójności z serwisu
        print(
            f"[BAD REQUEST] Validation error during update for rule {rule_id}: {e.detail}"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    except PriorityConflictException as e:
        print(
            f"[CONFLICT] Priority conflict during update for rule {rule_id} on link {link_id}: {e.detail}"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    except DatabaseException as e:
        print(
            f"[ERROR] Database error updating rule {rule_id} for link {link_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e.detail}",
        )
    except ServiceException as e:
        print(
            f"[ERROR] Service error updating rule {rule_id} for link {link_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail
        )
    except Exception as e:
        print(
            f"[ERROR] Unexpected error updating rule {rule_id} for link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint DELETE /links/{link_id}/rules/{rule_id} ---
@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Rule",
    description="Deletes a specific routing rule within a link owned by the authenticated user.",
    tags=["Rules"],
)
async def delete_rule_endpoint(
    link_id: UUID = Path(..., description="The ID of the parent link"),
    rule_id: UUID = Path(..., description="The ID of the rule to delete"),
    current_user_id: UUID = Depends(get_current_user_id),
    rule_service: RuleService = Depends(get_rule_service),
):
    """
    Deletes a specific rule identified by its ID and parent link ID.
    Returns No Content on success.
    """
    print(
        f"Received request to delete rule {rule_id} for link {link_id} by user {current_user_id}"
    )
    try:
        await rule_service.delete_rule(
            link_id=link_id, rule_id=rule_id, user_id=current_user_id
        )
        # Zwróć pustą odpowiedź z kodem 204
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except NotFoundException as e:  # Obejmuje nieznalezienie reguły lub linku
        print(
            f"[NOT FOUND] {e.detail} during delete for rule {rule_id} on link {link_id}, user {current_user_id}"
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
