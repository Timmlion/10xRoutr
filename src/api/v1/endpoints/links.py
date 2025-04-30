# src/api/v1/endpoints/links.py

# Standard library imports
import traceback
from typing import List, Union, Optional
from uuid import UUID  # For type hinting UUIDs

# Third-party imports
from pydantic import HttpUrl
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

# Application-specific imports
# Pydantic models (Data Transfer Objects)
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

# Dependencies for injection
from src.api.deps import (
    get_link_service,
    get_current_user_id,  # Ensures user is authenticated and provides their ID
    pagination_dependency,  # Handles pagination query parameters
    get_templates,  # Provides the Jinja2 template rendering engine
)

# Router for link-related endpoints
router = APIRouter()

# --- HTML Partial Endpoints (for HTMX integration) ---
# NOTE: Routes returning HTML partials for specific link IDs (e.g., /links/{link_id}/...)
#       should be defined BEFORE the generic /{link_id} JSON endpoint to ensure correct routing.
#       Similarly, general partials like /list-partial should come before /{link_id}.


@router.get(
    "/{link_id}/edit-header-partial",
    # No response_model as this returns HTML content directly
    summary="Get Link Edit Header HTML Partial",
    description="Returns an HTML fragment for the header section of the link edit page, including alias display and default URL form.",
    tags=["Links UI Partials"],  # Separate tag for UI-related partials
    include_in_schema=False,  # Hide from public API docs, as it's UI-specific
)
async def get_link_edit_header_partial(
    request: Request,  # Needed for template context
    link_id: UUID = Path(..., description="The ID of the link"),
    link_service: LinkService = Depends(get_link_service),
    user_id: UUID = Depends(get_current_user_id),  # Ensures user owns the link
    templates: Jinja2Templates = Depends(get_templates),
):
    """
    Fetches data for a specific link belonging to the authenticated user
    and renders an HTML partial representing the header/form part of the edit page.
    Used by the frontend (likely HTMX) to dynamically load parts of the edit UI.
    """
    print(f"Fetching edit header partial for link {link_id} by user {user_id}")
    try:
        # Fetch the link data; get_link_by_id includes ownership check
        link = await link_service.get_link_by_id(link_id=link_id, user_id=user_id)
        # Render the specific partial template with the link data
        return templates.TemplateResponse(
            "partials/link_edit_header.html",
            {"request": request, "link": link},
        )
    except LinkNotFoundException:
        # If link not found or doesn't belong to user, return 404
        print(
            f"[NOT FOUND] Link {link_id} not found for header partial, user {user_id}"
        )
        # Raise HTTPException directly for HTML partials, as they might not handle standard JSON error responses
        # A dedicated error partial could also be returned here.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found or access denied.",
        )
    except Exception as e:
        # Catch-all for unexpected errors during fetch/render
        print(f"Error fetching link for header partial (link {link_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load link data.",
        )


@router.get(
    "/list-partial",
    summary="Get Links List HTML Partial",
    description="Returns an HTML fragment containing table rows for the user's links, intended for dynamic table updates (e.g., with HTMX).",
    tags=["Links UI Partials"],
    include_in_schema=False,
)
async def get_links_list_partial(
    request: Request,  # Needed for template context
    link_service: LinkService = Depends(get_link_service),
    user_id: UUID = Depends(
        get_current_user_id
    ),  # Get links for the authenticated user
    pagination: PaginationParams = Depends(
        pagination_dependency
    ),  # Use standard pagination
    templates: Jinja2Templates = Depends(get_templates),
):
    """
    Fetches a paginated list of the authenticated user's links and renders them
    as HTML table rows (`<tr>`) within a partial template.
    Used by the frontend (likely HTMX) to load or refresh the links table.
    """
    print(
        f"Fetching links partial for user {user_id}, page: {pagination.page}, size: {pagination.page_size}"
    )
    try:
        # Fetch paginated links from the service
        paginated_response = await link_service.get_links_paginated(
            user_id=user_id, page=pagination.page, page_size=pagination.page_size
        )
        links = paginated_response.items  # Extract the list of links
        # Render the partial template containing the table rows
        return templates.TemplateResponse(
            "partials/link_rows.html", {"request": request, "links": links}
        )
    except Exception as e:
        # If fetching links fails, return an error partial
        print(f"Error fetching links for partial rendering (user {user_id}): {e}")
        # Render a specific error row/message template
        return templates.TemplateResponse(
            "partials/link_row_error.html",
            {"request": request, "error_message": "Could not load links."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get(
    "/{link_id}/stats-partial",
    summary="Get Link Statistics HTML Partial",
    description="Returns an HTML fragment displaying statistics for a specific link, for dynamic loading in the UI (e.g., HTMX tab).",
    tags=["Statistics", "Links UI Partials"],  # Belongs to both categories
    include_in_schema=False,
)
async def get_link_stats_partial(
    request: Request,  # Needed for template context
    link_id: UUID = Path(..., description="The ID of the link to get stats for"),
    user_id: UUID = Depends(get_current_user_id),  # Ensure user owns the link
    link_service: LinkService = Depends(get_link_service),
    templates: Jinja2Templates = Depends(get_templates),
):
    """
    Fetches click statistics for a specific link belonging to the authenticated user
    and renders them as an HTML partial.
    Used by the frontend (likely HTMX) to load statistics content dynamically.
    """
    print(f"Fetching stats partial for link {link_id} by user {user_id}")
    try:
        # Fetch statistics data using the service method
        stats_data: LinkStatsResponse = await link_service.get_link_statistics(
            link_id=link_id, user_id=user_id
        )
        # Render the partial template for displaying stats
        return templates.TemplateResponse(
            "partials/link_stats_details.html",
            {
                "request": request,
                "stats": stats_data,
            },  # Pass the stats data to the template
        )
    except LinkNotFoundException as e:
        # Handle case where link is not found or not owned by user
        print(
            f"[NOT FOUND] Link {link_id} not found for stats partial, user {user_id}: {e.detail}"
        )
        # Return an error partial indicating the issue
        return templates.TemplateResponse(
            "partials/stats_error.html",  # Specific template for stats errors
            {"request": request, "error_message": e.detail},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        # Catch-all for other errors during stats fetching/rendering
        print(f"Error fetching link stats for partial rendering (link {link_id}): {e}")
        return templates.TemplateResponse(
            "partials/stats_error.html",
            {"request": request, "error_message": "Could not load statistics."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# --- Standard JSON API Endpoints ---


@router.get(
    "",  # Corresponds to GET /api/v1/links
    response_model=PaginatedLinkResponse,  # Specifies the expected JSON response structure
    summary="List User's Links (JSON)",
    description="Retrieves a paginated list of routr links owned by the authenticated user as JSON.",
    tags=["Links"],  # Standard API tag
)
async def list_links_endpoint(
    pagination: PaginationParams = Depends(
        pagination_dependency
    ),  # Inject validated pagination params
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Inject authenticated user's ID
    link_service: LinkService = Depends(
        get_link_service
    ),  # Inject link service instance
):
    """API endpoint to retrieve a paginated list of links for the current user."""
    print(
        f"Received request to list links (JSON) for user {current_user_id} with pagination: page={pagination.page}, size={pagination.page_size}."
    )
    try:
        # Call the service method to get paginated links
        paginated_result = await link_service.get_links_paginated(
            user_id=current_user_id,
            page=pagination.page,
            page_size=pagination.page_size,
        )
        print(f"Returning JSON response for {len(paginated_result.items)} links.")
        return paginated_result
    except DatabaseException as e:
        # Handle potential database errors during retrieval
        print(f"[ERROR] Database error in list_links_endpoint: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve links due to a database error.",
        )
    except Exception as e:
        # Catch any unexpected errors
        print(f"[ERROR] Unexpected error in list_links_endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.post(
    "",  # Corresponds to POST /api/v1/links
    response_model=LinkResponse,  # Response is the created link object
    status_code=status.HTTP_201_CREATED,  # Standard status for successful creation
    summary="Create a new Routr Link (Form Data)",
    description="Creates a new unique routr link from form data (alias, optional default_url). Returns the created link data. Sets HX-Redirect header for HTMX clients.",
    tags=["Links"],
)
async def create_link_endpoint(
    response: Response,  # FastAPI Response object to set headers
    alias: str = Form(...),  # Expect 'alias' field from form data (required)
    default_url: Optional[str] = Form(
        None
    ),  # Expect optional 'default_url' from form data
    current_user_id: UUID = Depends(get_current_user_id),  # Inject user ID
    link_service: LinkService = Depends(get_link_service),  # Inject link service
):
    """
    API endpoint to create a new routr link using data submitted via a form.
    Primarily intended for use with HTMX forms. Sets an HX-Redirect header
    on success to redirect the user to the edit page of the newly created link.
    """
    print(
        f"Received request to create link via form with alias '{alias}' and default_url '{default_url}' for user {current_user_id}"
    )
    # Prepare data for Pydantic validation
    link_data_dict = {"alias": alias}
    if default_url:  # Only include default_url if provided
        link_data_dict["default_url"] = default_url

    try:
        # Validate the input data against the LinkCreate schema
        link_data = LinkCreate.model_validate(link_data_dict)
    except Exception as validation_error:
        # Handle Pydantic validation errors (e.g., invalid URL format)
        print(f"Validation error creating LinkCreate DTO: {validation_error}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid form data provided.",  # Keep error generic for the client
        ) from validation_error

    try:
        # Call the service method to create the link in the database
        created_link = await link_service.create_link(
            link_data=link_data, user_id=current_user_id
        )

        # --- HTMX Specific Enhancement ---
        # Set the HX-Redirect header to tell HTMX to navigate to the edit page after creation.
        edit_url = f"/app/links/{created_link.id}/edit"  # Construct the UI URL
        response.headers["HX-Redirect"] = edit_url
        print(f"Link created successfully. Setting HX-Redirect to: {edit_url}")
        # --- End HTMX Specific Enhancement ---

        return created_link  # Return the newly created link object as JSON
    except AliasConflictException as e:
        # Handle error if the chosen alias already exists for the user
        print(f"[CONFLICT] Alias conflict for alias '{link_data.alias}': {e.detail}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.detail)
    except (DatabaseException, ServiceException, ValidationException) as e:
        # Handle other specific errors from the service layer
        print(f"[ERROR] DB/Service/Validation error during link creation: {e.detail}")
        # Map ValidationException to 422, others to 500
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
        # Catch any other unexpected errors
        print(f"[ERROR] Unexpected error in create_link_endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while creating the link.",
        )


@router.get(
    "/{link_id}",  # Corresponds to GET /api/v1/links/{link_id}
    response_model=LinkResponse,  # Specifies the expected JSON response
    summary="Get Link Details (JSON)",
    description="Retrieves the details of a specific routr link owned by the authenticated user as JSON.",
    tags=["Links"],
)
async def get_link_endpoint(
    link_id: UUID = Path(
        ..., description="The ID of the link to retrieve"
    ),  # Extract ID from path
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Inject user ID for auth check
    link_service: LinkService = Depends(get_link_service),  # Inject link service
):
    """API endpoint to retrieve details for a single link identified by its ID."""
    print(f"Received request to get link {link_id} for user {current_user_id} (JSON)")
    try:
        # Fetch the link; service method includes ownership check
        link = await link_service.get_link_by_id(
            link_id=link_id, user_id=current_user_id
        )
        return link  # Return the link data as JSON
    except LinkNotFoundException as e:
        # Handle case where link doesn't exist or isn't owned by the user
        print(f"[NOT FOUND] {e.detail} for link {link_id}, user {current_user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        # Handle potential database errors
        print(f"[ERROR] Database error getting link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A database error occurred: {e.detail}",
        )
    except Exception as e:
        # Catch any other unexpected errors
        print(f"[ERROR] Unexpected error getting link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.patch(
    "/{link_id}",  # Corresponds to PATCH /api/v1/links/{link_id}
    response_model=LinkResponse,  # Return the updated link object
    summary="Update Link Details (Form Data)",
    description="Updates the default URL of a specific routr link using form data. Alias cannot be changed via this endpoint.",
    tags=["Links"],
)
async def update_link_endpoint(
    link_id: UUID = Path(
        ..., description="The ID of the link to update"
    ),  # Extract ID from path
    # Accept 'default_url' from form data. It's optional.
    default_url: Optional[str] = Form(None),
    current_user_id: UUID = Depends(get_current_user_id),  # Inject user ID for auth
    link_service: LinkService = Depends(get_link_service),  # Inject link service
):
    """
    API endpoint to update the default URL of a link using data submitted via a form.
    Intended for use with HTMX forms on the link edit page.
    Only the default_url field is accepted for update here.
    """
    print(
        f"Received request to update link {link_id} via form for user {current_user_id} with default_url: '{default_url}'"
    )

    # Manually construct the dictionary for the LinkUpdate Pydantic model.
    # This endpoint only supports updating the default_url.
    update_data_dict = {}
    # Map the form input to the dictionary.
    # An empty string from the form means "remove the default URL" (set to None).
    # If the field wasn't sent, Form(None) makes it None.
    if default_url is not None:  # Check if the field was present in the form
        update_data_dict["default_url"] = default_url if default_url else None

    try:
        # Validate the constructed data using the LinkUpdate schema.
        # This will check if the provided default_url (if not None) is a valid URL.
        # If update_data_dict is empty (default_url was None/not provided), validation still passes.
        update_data = LinkUpdate.model_validate(update_data_dict)
    except Exception as validation_error:
        # Handle Pydantic validation errors (e.g., invalid URL format)
        print(f"Validation error creating LinkUpdate DTO: {validation_error}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid form data: {validation_error}",
        )

    # Proceed with the update using the validated data
    try:
        # Call the service method to update the link in the database
        # The service method also checks if the user owns the link.
        updated_link = await link_service.update_link(
            link_id=link_id, update_data=update_data, user_id=current_user_id
        )
        print(f"Link {link_id} updated successfully.")
        # Return the updated link data as JSON. HTMX can use this or ignore it.
        return updated_link
    except LinkNotFoundException as e:
        # Handle link not found or not owned by user
        print(f"[NOT FOUND] {e.detail} during update for link {link_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except ValidationException as e:
        # Handle potential validation errors raised by the service itself (less likely here)
        print(
            f"[BAD REQUEST] Validation error during service update for link {link_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.detail
        )
    except (DatabaseException, ServiceException) as e:
        # Handle database or other service errors
        print(f"[ERROR] DB/Service error updating link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {e.detail}",
        )
    except Exception as e:
        # Catch any other unexpected errors
        print(f"[ERROR] Unexpected error updating link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.delete(
    "/{link_id}",  # Corresponds to DELETE /api/v1/links/{link_id}
    status_code=status.HTTP_204_NO_CONTENT,  # Standard status for successful deletion with no body
    summary="Delete Link",
    description="Deletes a specific routr link and its associated rules owned by the authenticated user.",
    tags=["Links"],
)
async def delete_link_endpoint(
    link_id: UUID = Path(
        ..., description="The ID of the link to delete"
    ),  # Extract ID from path
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Inject user ID for auth check
    link_service: LinkService = Depends(get_link_service),  # Inject link service
):
    """API endpoint to delete a link identified by its ID."""
    print(f"Received request to delete link {link_id} for user {current_user_id}")
    try:
        # Call the service method to delete the link; includes ownership check
        await link_service.delete_link(link_id=link_id, user_id=current_user_id)
        # Return an empty response with 204 status code on success
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except LinkNotFoundException as e:
        # Handle link not found or not owned by user
        print(
            f"[NOT FOUND] {e.detail} during delete for link {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        # Handle potential database errors during deletion
        print(f"[ERROR] Database error deleting link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A database error occurred during deletion: {e.detail}",
        )
    except Exception as e:
        # Catch any other unexpected errors
        print(f"[ERROR] Unexpected error deleting link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# --- Statistics Endpoint ---
# Note: This JSON endpoint `/stats` is separate from the HTML partial `/stats-partial` defined earlier.
@router.get(
    "/{link_id}/stats",  # Corresponds to GET /api/v1/links/{link_id}/stats
    response_model=LinkStatsResponse,  # Specifies the expected JSON response structure
    summary="Get Link Statistics (JSON)",
    description="Retrieves click statistics (total clicks, clicks per target) for a specific link owned by the authenticated user as JSON.",
    tags=["Statistics", "Links"],  # Belongs to both categories
)
async def get_link_statistics_endpoint(
    link_id: UUID = Path(
        ..., description="The ID of the link to get stats for"
    ),  # Extract ID from path
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Inject user ID for auth check
    link_service: LinkService = Depends(get_link_service),  # Inject link service
):
    """API endpoint to retrieve click statistics for a specific link as JSON."""
    print(
        f"Received request to get stats (JSON) for link {link_id} by user {current_user_id}"
    )
    try:
        # Call the service method to fetch statistics; includes ownership check
        stats_data = await link_service.get_link_statistics(
            link_id=link_id, user_id=current_user_id
        )
        return stats_data  # Return the statistics data as JSON
    except LinkNotFoundException as e:
        # Handle link not found or not owned by user
        print(
            f"[NOT FOUND] {e.detail} for link stats {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except (DatabaseException, ServiceException) as e:
        # Handle database or other service errors during stats retrieval
        print(f"[ERROR] DB/Service error getting stats for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"A server error occurred while retrieving statistics: {e.detail}",
        )
    except Exception as e:
        # Catch any other unexpected errors
        print(f"[ERROR] Unexpected error getting stats for link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# Note: The duplicate definition of get_link_statistics_endpoint has been removed.
