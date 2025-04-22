# src/api/v1/endpoints/links.py (Corrected Order, Imports, and New Endpoint)

# Standard library imports
import traceback

# Usunięto import uuid, bo UUID jest importowane bezpośrednio
from typing import List, Union, Optional

# FastAPI imports
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
    Request,
    Path,
    Response,
    Form,
)
from fastapi.templating import Jinja2Templates
from uuid import UUID  # Import UUID dla type hintów

# Pydantic models (DTOs)
from src.schemas.link import (
    LinkCreate,
    LinkUpdate,
    LinkResponse,
    PaginatedLinkResponse,
)
from src.schemas.pagination import PaginationParams
from src.schemas.stats import LinkStatsResponse

# Services and Custom Exceptions
from src.services.link_service import LinkService
from src.services.custom_exceptions import (
    LinkNotFoundException,
    AliasConflictException,
    DatabaseException,
    ValidationException,
    ServiceException,
)

# Dependencies
from src.api.deps import (
    get_link_service,
    get_current_user_id,
    pagination_dependency,
    get_templates,
)

router = APIRouter()


# --- Endpoint zwracający fragment HTML dla nagłówka edycji linku ---
# <<< NOWY ENDPOINT - Umieszczony PRZED innymi z {link_id} i przed /list-partial >>>
@router.get(
    "/{link_id}/edit-header-partial",
    # Brak response_model, bo zwracamy HTML
    summary="Get Link Edit Header HTML Partial",
    description="Returns an HTML fragment for the header section of the link edit page, including alias display and default URL form.",
    tags=["Links UI Partials"],
    include_in_schema=False,
)
async def get_link_edit_header_partial(
    request: Request,
    link_id: UUID = Path(..., description="The ID of the link"),
    link_service: LinkService = Depends(get_link_service),
    user_id: UUID = Depends(get_current_user_id),  # Wymagany do pobrania linku
    templates: Jinja2Templates = Depends(get_templates),
):
    """Fetches link data and renders the edit page header partial template."""
    print(f"Fetching edit header partial for link {link_id} by user {user_id}")
    try:
        link = await link_service.get_link_by_id(link_id=link_id, user_id=user_id)
        return templates.TemplateResponse(
            "partials/link_edit_header.html",  # Nazwa szablonu częściowego
            {"request": request, "link": link},  # Przekazujemy pełny obiekt linku
        )
    except LinkNotFoundException:
        print(
            f"[NOT FOUND] Link {link_id} not found for header partial, user {user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found or access denied.",
        )
    except Exception as e:
        print(f"Error fetching link for header partial (link {link_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load link data.",
        )


# --- Endpoint zwracający fragment HTML dla listy linków ---
# <<< Umieszczony PO /edit-header-partial, ale PRZED /{link_id} >>>
@router.get(
    "/list-partial",
    summary="Get Links List HTML Partial",
    description="Returns an HTML fragment containing table rows for the user's links.",
    tags=["Links UI Partials"],
    include_in_schema=False,
)
async def get_links_list_partial(
    request: Request,
    link_service: LinkService = Depends(get_link_service),
    user_id: UUID = Depends(get_current_user_id),
    pagination: PaginationParams = Depends(pagination_dependency),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Fetches the user's links and renders them as HTML table rows (tr)."""
    print(
        f"Fetching links partial for user {user_id}, page: {pagination.page}, size: {pagination.page_size}"
    )
    try:
        paginated_response = await link_service.get_links_paginated(
            user_id=user_id, page=pagination.page, page_size=pagination.page_size
        )
        links = paginated_response.items
    except Exception as e:
        print(f"Error fetching links for partial rendering (user {user_id}): {e}")
        return templates.TemplateResponse(
            "partials/link_row_error.html",
            {"request": request, "error_message": "Nie udało się załadować linków."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return templates.TemplateResponse(
        "partials/link_rows.html", {"request": request, "links": links}
    )


@router.get(
    "/{link_id}/stats-partial",
    summary="Get Link Statistics HTML Partial",
    description="Returns an HTML fragment displaying statistics for a specific link.",
    tags=["Statistics", "Links UI Partials"],  # Dodajemy obie tagi
    include_in_schema=False,
)
async def get_link_stats_partial(
    request: Request,
    link_id: UUID = Path(..., description="The ID of the link to get stats for"),
    user_id: UUID = Depends(get_current_user_id),  # Wymagana autoryzacja
    link_service: LinkService = Depends(get_link_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Fetches link statistics and renders the details partial template."""
    print(f"Fetching stats partial for link {link_id} by user {user_id}")
    try:
        # Używamy istniejącej metody serwisu do pobrania statystyk
        stats_data: LinkStatsResponse = await link_service.get_link_statistics(
            link_id=link_id, user_id=user_id
        )
        # Renderujemy nowy szablon częściowy, przekazując obiekt stats
        return templates.TemplateResponse(
            "partials/link_stats_details.html",
            {"request": request, "stats": stats_data},  # Przekazujemy dane statystyk
        )
    except LinkNotFoundException as e:
        print(
            f"[NOT FOUND] Link {link_id} not found for stats partial, user {user_id}: {e.detail}"
        )
        # Zwracamy błąd w formie HTML, który można wyświetlić w zakładce
        return templates.TemplateResponse(
            "partials/stats_error.html",  # Można stworzyć dedykowany szablon błędu statystyk
            {"request": request, "error_message": e.detail},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        print(f"Error fetching link stats for partial rendering (link {link_id}): {e}")
        return templates.TemplateResponse(
            "partials/stats_error.html",
            {"request": request, "error_message": "Nie udało się załadować statystyk."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# --- Endpoint GET /links ---
# Definicja PO endpointach UI partials
@router.get(
    "",
    response_model=PaginatedLinkResponse,
    summary="List User's Links",
    description="Retrieves a paginated list of routr links owned by the authenticated user.",
    tags=["Links"],
)
async def list_links_endpoint(
    # Usunięty request, bo nie jest już używany do sprawdzania HTMX
    pagination: PaginationParams = Depends(pagination_dependency),
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """Retrieves a paginated list of links for the current user (JSON)."""
    print(
        f"Received request to list links (JSON) for user {current_user_id} with pagination: page={pagination.page}, size={pagination.page_size}."
    )
    try:
        paginated_result = await link_service.get_links_paginated(
            user_id=current_user_id,
            page=pagination.page,
            page_size=pagination.page_size,
        )
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
    description="Creates a new unique routr link associated with the authenticated user using form data. Returns HX-Redirect header on success for HTMX clients.",
    tags=["Links"],
)
async def create_link_endpoint(
    response: Response,
    alias: str = Form(...),
    default_url: Optional[str] = Form(None),
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """Endpoint to create a new routr link from form data."""
    print(
        f"Received request to create link via form with alias '{alias}' and default_url '{default_url}' for user {current_user_id}"
    )
    link_data_dict = {"alias": alias}
    if default_url:
        link_data_dict["default_url"] = default_url
    try:
        link_data = LinkCreate.model_validate(link_data_dict)
    except Exception as validation_error:
        print(f"Validation error creating LinkCreate DTO: {validation_error}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid form data provided.",  # Keep error simple
        ) from validation_error
    try:
        created_link = await link_service.create_link(
            link_data=link_data, user_id=current_user_id
        )
        edit_url = f"/app/links/{created_link.id}/edit"
        response.headers["HX-Redirect"] = edit_url
        print(f"Link created successfully. Setting HX-Redirect to: {edit_url}")
        return created_link
    except AliasConflictException as e:
        print(f"[CONFLICT] Alias conflict for alias '{link_data.alias}': {e.detail}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    except (DatabaseException, ServiceException, ValidationException) as e:
        print(f"[ERROR] DB/Service/Validation error during link creation: {e.detail}")
        error_status = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if isinstance(e, ValidationException)
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        raise HTTPException(
            status_code=error_status,
            detail=f"A server error occurred: {e.detail}",
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error in create_link_endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while creating the link.",
        )


# --- Endpoint GET /links/{link_id} ---
# <<< Defined AFTER specific partials like /{link_id}/edit-header-partial >>>
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
    """Retrieves details for a single link identified by its ID (JSON response)."""
    print(f"Received request to get link {link_id} for user {current_user_id} (JSON)")
    try:
        link = await link_service.get_link_by_id(
            link_id=link_id, user_id=current_user_id
        )
        return link
    except LinkNotFoundException as e:
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
    update_data: LinkUpdate,
    link_id: UUID = Path(..., description="The ID of the link to update"),
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """Updates the default URL for a specific link."""
    update_payload_info = update_data.model_dump(exclude_unset=True)
    print(
        f"Received request to update link {link_id} for user {current_user_id} with data: {update_payload_info}"
    )
    try:
        updated_link = await link_service.update_link(
            link_id=link_id, update_data=update_data, user_id=current_user_id
        )
        return updated_link
    except LinkNotFoundException as e:
        print(
            f"[NOT FOUND] {e.detail} during update for link {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except ValidationException as e:
        print(
            f"[BAD REQUEST] Validation error during update for link {link_id}: {e.detail}"
        )
        # Zwróć 422 dla błędów walidacji z Pydantic/serwisu
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.detail
        )
    except (DatabaseException, ServiceException) as e:
        print(f"[ERROR] DB/Service error updating link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A server error occurred during update: {e.detail}",
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
    """Deletes a link identified by its ID."""
    print(f"Received request to delete link {link_id} for user {current_user_id}")
    try:
        await link_service.delete_link(link_id=link_id, user_id=current_user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except LinkNotFoundException as e:
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
# <<< Defined AFTER specific partials like /{link_id}/edit-header-partial >>>
# <<< Defined BEFORE generic /{link_id} if it has overlapping path structure (it doesn't here, but good practice) >>>
@router.get(
    "/{link_id}/stats",
    response_model=LinkStatsResponse,
    summary="Get Link Statistics",
    description="Retrieves click statistics for a specific link owned by the authenticated user.",
    tags=["Statistics", "Links"],
)
async def get_link_statistics_endpoint(
    link_id: UUID = Path(..., description="The ID of the link to get stats for"),
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """Retrieves total clicks and target clicks for a link (JSON response)."""
    print(
        f"Received request to get stats for link {link_id} by user {current_user_id} (JSON)"
    )
    try:
        stats_data = await link_service.get_link_statistics(
            link_id=link_id, user_id=current_user_id
        )
        return stats_data
    except LinkNotFoundException as e:
        print(
            f"[NOT FOUND] {e.detail} for link stats {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except (DatabaseException, ServiceException) as e:
        print(f"[ERROR] DB/Service error getting stats for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A server error occurred while retrieving statistics: {e.detail}",
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error getting stats for link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.get(
    "/{link_id}/stats",
    response_model=LinkStatsResponse,
    summary="Get Link Statistics (JSON)",  # Zmieniono summary dla odróżnienia
    description="Retrieves click statistics for a specific link (JSON response).",
    tags=["Statistics", "Links"],
)
async def get_link_statistics_endpoint(  # Nazwa funkcji pozostaje ta sama
    link_id: UUID = Path(..., description="The ID of the link to get stats for"),
    current_user_id: UUID = Depends(get_current_user_id),
    link_service: LinkService = Depends(get_link_service),
):
    """Retrieves total clicks and target clicks for a link (JSON response)."""
    print(
        f"Received request to get stats (JSON) for link {link_id} by user {current_user_id}"
    )
    try:
        stats_data = await link_service.get_link_statistics(
            link_id=link_id, user_id=current_user_id
        )
        return stats_data
    except LinkNotFoundException as e:
        print(
            f"[NOT FOUND] {e.detail} for link stats {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except (DatabaseException, ServiceException) as e:
        print(f"[ERROR] DB/Service error getting stats for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {e.detail}",
        )
    except Exception as e:
        print(f"[ERROR] Unexpected error getting stats for link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Koniec pliku ---
