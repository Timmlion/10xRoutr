# src/api/v1/endpoints/links.py

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
    Request,  # Potrzebne dla HTMX
    Path,
    Response,  # Potrzebne dla 204 No Content
)
from uuid import UUID
from typing import List, Union, Optional  # Dodano Optional
import traceback  # Dla logowania błędów

# Import modeli Pydantic (DTOs)
from src.schemas.link import LinkCreate, LinkUpdate, LinkResponse, PaginatedLinkResponse
from src.schemas.pagination import PaginationParams
from src.schemas.stats import LinkStatsResponse

# Import serwisu i wyjątków
from src.services.link_service import LinkService
from src.services.custom_exceptions import (
    AliasConflictException,
    DatabaseException,
    NotFoundException,
    ValidationException,
    ServiceException,
)

# Import zależności
from src.api.deps import (
    get_current_user_id,
    get_link_service,
    pagination_dependency,
)  # Używamy zależności

# Import szablonów (dla HTMX) - zakładamy, że jest zdefiniowany w main.py
# Lepszym podejściem jest wstrzyknięcie go przez Depends
try:
    from src.main import templates
except ImportError:
    templates = None  # Fallback
    print(
        "[WARNING] Jinja2Templates instance 'templates' not found in main.py. HTMX responses might not work."
    )


router = APIRouter()


# --- Endpoint GET /links ---
@router.get(
    "",
    response_model=PaginatedLinkResponse,  # JSON jest domyślną odpowiedzią
    summary="List User's Links",
    description="Retrieves a paginated list of routr links owned by the authenticated user. Returns HTML fragment if HX-Request header is present.",
    tags=["Links"],
)
async def list_links_endpoint(
    request: Request,  # Potrzebne do sprawdzenia nagłówków HTMX
    pagination: PaginationParams = Depends(
        pagination_dependency
    ),  # Używamy modelu Pydantic
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """
    Retrieves a paginated list of links for the current user.
    Supports pagination via `page` and `page_size` query parameters.
    Can return an HTML fragment for HTMX requests if templates are configured.
    """
    is_htmx_request = request.headers.get("hx-request") == "true"
    print(
        f"Received request to list links for user {current_user_id} with pagination: page={pagination.page}, size={pagination.page_size}. HTMX={is_htmx_request}"
    )

    try:
        paginated_result = await link_service.get_links_paginated(
            user_id=current_user_id,
            page=pagination.page,
            page_size=pagination.page_size,
        )

        if is_htmx_request:
            if templates:
                print(
                    f"Rendering HTMX partial for {len(paginated_result.items)} links."
                )
                # Upewnij się, że ścieżka do szablonu jest poprawna
                return templates.TemplateResponse(
                    "dashboard/links_list_partial.html",  # Zakładany szablon fragmentu
                    {"request": request, "links": paginated_result.items},
                )
            else:
                print(
                    "[ERROR] HTMX request received but templates are not configured or imported."
                )
                # Zwróć błąd lub odpowiedź, którą HTMX potrafi obsłużyć jako błąd
                raise HTTPException(
                    status_code=501,
                    detail="HTML templating for HTMX is not configured on the server.",
                )
        else:
            # Zwróć standardową odpowiedź JSON
            print(f"Returning JSON response for {len(paginated_result.items)} links.")
            return paginated_result

    except DatabaseException as e:
        print(f"[ERROR] Database error in list_links_endpoint: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve links due to a database error.",
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error in list_links_endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint POST /links ---
@router.post(
    "",
    response_model=LinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Routr Link",
    description="Creates a new unique routr link associated with the authenticated user.",
    tags=["Links"],
)
async def create_link_endpoint(
    link_data: LinkCreate,
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """
    Endpoint to create a new routr link.
    Requires a unique alias and an optional default URL.
    """
    print(
        f"Received request to create link with alias '{link_data.alias}' for user {current_user_id}"
    )
    try:
        created_link = await link_service.create_link(
            link_data=link_data, user_id=current_user_id
        )
        return created_link
    except AliasConflictException as e:
        print(f"[CONFLICT] Alias conflict for alias '{link_data.alias}': {e.detail}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    except DatabaseException as e:
        print(f"[ERROR] Database error during link creation: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A database error occurred: {e.detail}",
        )
    except ServiceException as e:
        print(f"[ERROR] Service error during link creation: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  # Lub 400 jeśli to błąd walidacji logiki
            detail=e.detail,
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error in create_link_endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while creating the link.",
        )


# --- Endpoint GET /links/{link_id} ---
@router.get(
    "/{link_id}",
    response_model=LinkResponse,
    summary="Get Link Details",
    description="Retrieves the details of a specific routr link owned by the authenticated user.",
    tags=["Links"],
)
async def get_link_endpoint(
    link_id: UUID = Path(..., description="The ID of the link to retrieve"),
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """
    Retrieves details for a single link identified by its ID.
    Ensures the link belongs to the currently authenticated user.
    """
    print(f"Received request to get link {link_id} for user {current_user_id}")
    try:
        link = await link_service.get_link_by_id(
            link_id=link_id, user_id=current_user_id
        )
        return link
    except NotFoundException as e:
        print(f"[NOT FOUND] {e.detail} for link {link_id}, user {current_user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        print(f"[ERROR] Database error getting link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A database error occurred: {e.detail}",
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error getting link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint PATCH /links/{link_id} ---
@router.patch(
    "/{link_id}",
    response_model=LinkResponse,
    summary="Update Link Details",
    description="Updates the default URL of a specific routr link owned by the authenticated user. Alias cannot be changed.",
    tags=["Links"],
)
async def update_link_endpoint(
    # Reordered: Body parameter first
    update_data: LinkUpdate,
    # Path parameter next
    link_id: UUID = Path(..., description="The ID of the link to update"),
    # Dependencies last
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """
    Updates the default URL for a specific link.
    Only fields provided in the request body will be updated.
    """
    # Użyj .model_dump() (Pydantic v2) zamiast .dict()
    update_payload_info = update_data.model_dump(exclude_unset=True)
    print(
        f"Received request to update link {link_id} for user {current_user_id} with data: {update_payload_info}"
    )
    try:
        updated_link = await link_service.update_link(
            link_id=link_id, update_data=update_data, user_id=current_user_id
        )
        return updated_link
    except NotFoundException as e:
        print(
            f"[NOT FOUND] {e.detail} during update for link {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except ValidationException as e:  # Obsługa błędu walidacji z serwisu
        print(
            f"[BAD REQUEST] Validation error during update for link {link_id}: {e.detail}"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.detail)
    except DatabaseException as e:
        print(f"[ERROR] Database error updating link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A database error occurred during update: {e.detail}",
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error updating link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint DELETE /links/{link_id} ---
@router.delete(
    "/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Link",
    description="Deletes a specific routr link and its associated rules owned by the authenticated user.",
    tags=["Links"],
)
async def delete_link_endpoint(
    link_id: UUID = Path(..., description="The ID of the link to delete"),
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """
    Deletes a link identified by its ID.
    Also deletes all associated rules due to database cascade.
    Returns No Content on success.
    """
    print(f"Received request to delete link {link_id} for user {current_user_id}")
    try:
        await link_service.delete_link(link_id=link_id, user_id=current_user_id)
        # Zwróć pustą odpowiedź z kodem 204
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NotFoundException as e:
        print(
            f"[NOT FOUND] {e.detail} during delete for link {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        print(f"[ERROR] Database error deleting link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A database error occurred during deletion: {e.detail}",
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error deleting link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Endpoint GET /links/{link_id}/stats ---
@router.get(
    "/{link_id}/stats",
    response_model=LinkStatsResponse,
    summary="Get Link Statistics",
    description="Retrieves click statistics for a specific link owned by the authenticated user.",
    tags=["Statistics", "Links"],  # Dodajemy oba tagi
)
async def get_link_statistics_endpoint(
    link_id: UUID = Path(..., description="The ID of the link to get stats for"),
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),  # Używamy LinkService
):
    """
    Retrieves total clicks for the link and current click counts for each associated rule's target.
    """
    print(f"Received request to get stats for link {link_id} by user {current_user_id}")
    try:
        stats_data = await link_service.get_link_statistics(
            link_id=link_id, user_id=current_user_id
        )
        return stats_data
    except NotFoundException as e:
        print(
            f"[NOT FOUND] {e.detail} for link stats {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        print(f"[ERROR] Database error getting stats for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A database error occurred while retrieving statistics: {e.detail}",
        )
    except ServiceException as e:
        print(f"[ERROR] Service error getting stats for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.detail
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error getting stats for link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )
