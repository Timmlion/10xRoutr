# src/api/v1/endpoints/rules.py

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,  # Used to extract parameters from the URL path
    status,
    Request,  # Needed for template context
    Response,  # Used for returning custom responses (e.g., 204 No Content)
    Form,  # Used to receive data from HTML forms
)
from fastapi.templating import Jinja2Templates
from uuid import UUID
from typing import List, Optional, Dict, Any  # For type hinting
import traceback  # For printing detailed exception information
from datetime import datetime

# Import Pydantic models (Data Transfer Objects) for request/response validation and serialization
from src.schemas.rule import RuleCreate, RuleUpdate, RuleResponse

# Import the rule service and custom exceptions
from src.services.rule_service import RuleService
from src.services.custom_exceptions import (
    DatabaseException,
    NotFoundException,  # Specific exception for when a resource isn't found
    PriorityConflictException,  # Specific exception for rule priority conflicts
    ValidationException,  # Generic validation errors
    ServiceException,  # Generic service layer errors
)

# Import dependency injector functions
from src.api.deps import get_current_user_id, get_rule_service, get_templates

# Create an API router instance for rule endpoints
# Note: This router is mounted under /api/v1/links/{link_id}/rules in api.py,
# so 'link_id' is implicitly available to all endpoints here.
router = APIRouter()


# --- HTML Partial Endpoints (for HTMX Integration) ---


@router.get(
    "/create-form-partial",
    summary="Get Rule Creation Form HTML Partial",
    description="Returns an HTML fragment containing an empty form for creating a new rule, intended for modal dialogs.",
    tags=["Rules UI Partials"],  # Tag for UI-specific partials
    include_in_schema=False,  # Hide from public API docs
)
async def get_rule_create_form_partial(
    request: Request,  # Needed for template context
    link_id: UUID,  # Automatically extracted from the path prefix by FastAPI
    templates: Jinja2Templates = Depends(get_templates),
):
    """
    Renders and returns the HTML form partial for creating a new rule.
    The form is empty, ready for user input. `link_id` is passed to the template
    so the form submission knows which link the rule belongs to.
    """
    print(f"Fetching create form partial for link {link_id}")
    return templates.TemplateResponse(
        "partials/rule_form.html",  # Path to the partial template file
        {
            "request": request,
            "link_id": link_id,  # Pass link_id for form action/context
            "rule": None,  # Pass None as 'rule' to indicate creation mode
            "now": datetime.utcnow(),  # Optional: Pass current time if needed in template
        },
    )


@router.get(
    "/{rule_id}/edit-form-partial",
    summary="Get Rule Edit Form HTML Partial",
    description="Returns an HTML fragment containing a pre-filled form for editing an existing rule, intended for modal dialogs.",
    tags=["Rules UI Partials"],
    include_in_schema=False,
)
async def get_rule_edit_form_partial(
    request: Request,
    link_id: UUID,  # Automatically extracted from the path prefix
    rule_id: UUID = Path(
        ..., description="The ID of the rule to edit"
    ),  # Extracted from this specific path
    user_id: UUID = Depends(
        get_current_user_id
    ),  # Ensure user is authenticated and authorized
    rule_service: RuleService = Depends(get_rule_service),  # Inject rule service
    templates: Jinja2Templates = Depends(get_templates),  # Inject template engine
):
    """
    Fetches the data for an existing rule and renders the HTML form partial
    pre-filled with that data, ready for editing.
    """
    print(
        f"Fetching edit form partial for rule {rule_id} on link {link_id} by user {user_id}"
    )
    try:
        # Fetch the rule details; service performs ownership check
        rule = await rule_service.get_rule_details(
            link_id=link_id, rule_id=rule_id, user_id=user_id
        )
        # Render the same form partial as create, but pass the fetched 'rule' object
        return templates.TemplateResponse(
            "partials/rule_form.html",
            {
                "request": request,
                "link_id": link_id,
                "rule": rule,  # Pass the rule data to pre-fill the form
                "now": datetime.utcnow(),
            },
        )
    except NotFoundException as e:
        # Handle cases where the link or rule doesn't exist or user lacks access
        print(
            f"[NOT FOUND] Rule {rule_id} or Link {link_id} not found for edit form, user {user_id}: {e.detail}"
        )
        # Return an error partial suitable for display within the modal
        return templates.TemplateResponse(
            "partials/modal_error.html",  # Specific error template for modals
            {
                "request": request,
                "error_title": "Error Loading Form",
                "error_message": e.detail,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        # Catch unexpected errors during fetch/render
        print(f"Error fetching rule for edit form partial (rule {rule_id}): {e}")
        # Return a generic server error partial
        return templates.TemplateResponse(
            "partials/modal_error.html",
            {
                "request": request,
                "error_title": "Server Error",
                "error_message": "Could not load the edit form.",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@router.get(
    "/list-partial",
    summary="Get Rules List HTML Partial",
    description="Returns an HTML fragment containing table rows for the rules of a specific link, for dynamic table updates.",
    tags=["Rules UI Partials"],
    include_in_schema=False,
)
async def get_rules_list_partial(
    request: Request,
    link_id: UUID,  # Automatically extracted from the path prefix
    user_id: UUID = Depends(get_current_user_id),  # Ensure user auth
    rule_service: RuleService = Depends(get_rule_service),  # Inject rule service
    templates: Jinja2Templates = Depends(get_templates),  # Inject template engine
):
    """
    Fetches all rules associated with the given link_id for the authenticated user
    and renders them as a list of HTML table rows (`<tr>`).
    Used by HTMX to dynamically load or refresh the rules table on the link edit page.
    """
    print(f"Fetching rules list partial for link {link_id} by user {user_id}")
    try:
        # Fetch rules; service performs ownership check based on link_id and user_id
        rules = await rule_service.get_rules_for_link(link_id=link_id, user_id=user_id)
        # Render the partial template containing the table rows
        return templates.TemplateResponse(
            "partials/rule_rows.html",
            {"request": request, "rules": rules, "link_id": link_id},
        )
    except NotFoundException as e:
        # Handle case where the parent link doesn't exist or user lacks access
        print(
            f"[NOT FOUND] Link {link_id} not found for rules partial, user {user_id}: {e.detail}"
        )
        # Return an error row template
        return templates.TemplateResponse(
            "partials/rule_row_error.html",
            {
                "request": request,
                "error_message": "Link not found or access denied.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        # Catch unexpected errors during fetch/render
        print(f"Error fetching rules for partial rendering (link {link_id}): {e}")
        # Return a generic error row template
        return templates.TemplateResponse(
            "partials/rule_row_error.html",
            {"request": request, "error_message": "Could not load rules."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# --- Standard JSON API Endpoints ---


# Note the path change: Using "/create" to avoid conflicting with "/{rule_id}" GET path
# This endpoint handles the FORM SUBMISSION from the create rule modal.
@router.post(
    "/create",
    response_model=RuleResponse,  # Specifies the expected JSON response on success
    status_code=status.HTTP_201_CREATED,  # Standard code for successful creation
    summary="Create Rule from Form Data",
    description="Adds a new routing rule to the specified link using data submitted via an HTML form.",
    tags=["Rules"],  # Standard API tag
)
async def create_rule_endpoint(
    link_id: UUID,  # Automatically extracted from the path prefix
    # --- Form Data Parsing ---
    # Use Form(...) to extract data fields from the submitted form.
    # Perform necessary type conversions and handle optional fields carefully.
    priority: int = Form(...),  # Required integer field
    rule_type: str = Form(...),  # Required string (validated later as enum)
    target_type: str = Form(...),  # Required string (validated later as enum)
    target_value: str = Form(...),  # Required string (URL or HTML content)
    start_time: Optional[str] = Form(
        None
    ),  # Optional datetime string (YYYY-MM-DD HH:MM)
    end_time: Optional[str] = Form(None),  # Optional datetime string (YYYY-MM-DD HH:MM)
    max_clicks: Optional[str] = Form(
        None
    ),  # Optional integer, received as string (might be empty)
    # --------------------------------------
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Inject user ID for ownership check
    rule_service: RuleService = Depends(get_rule_service),  # Inject rule service
):
    """
    API endpoint to create a new routing rule based on data submitted from an HTML form.
    It parses form fields, performs initial validation/conversion, validates using
    the Pydantic model (RuleCreate), and then calls the service to persist the rule.
    """
    print(
        f"Received request to create rule via form for link {link_id} by user {current_user_id}"
    )
    print(
        f"Raw form data: priority={priority}, rule_type={rule_type}, target_type={target_type}, target_value={target_value}, start={start_time}, end={end_time}, max_clicks={max_clicks}"
    )

    # Manually construct a dictionary from form data for Pydantic validation.
    # This allows handling specific conversions (string -> datetime/int) and empty strings.
    rule_data_dict: Dict[str, Any] = {
        "priority": priority,
        "rule_type": rule_type,
        "target_type": target_type,
        "target_value": target_value,
        # Optional fields are handled below
    }

    # --- Convert and Validate Optional Fields ---
    # Convert date strings to datetime objects, handling empty strings and format errors.
    parsed_start_time = None
    if start_time and start_time.strip():  # Check if not None and not just whitespace
        try:
            parsed_start_time = datetime.strptime(start_time.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid format for start_time: '{start_time}'. Use YYYY-MM-DD HH:MM.",
            )
    rule_data_dict["start_time"] = (
        parsed_start_time  # Assign converted datetime or None
    )

    parsed_end_time = None
    if end_time and end_time.strip():
        try:
            parsed_end_time = datetime.strptime(end_time.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid format for end_time: '{end_time}'. Use YYYY-MM-DD HH:MM.",
            )
    rule_data_dict["end_time"] = parsed_end_time

    # Convert max_clicks string to int, handling empty strings and non-integer values.
    parsed_max_clicks = None
    if max_clicks and max_clicks.strip():
        try:
            parsed_max_clicks = int(max_clicks.strip())
            if parsed_max_clicks < 1:  # Add domain-specific validation
                raise ValueError("max_clicks must be a positive integer")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid value for max_clicks: '{max_clicks}'. {e}",
            )
    rule_data_dict["max_clicks"] = parsed_max_clicks  # Assign converted int or None
    # ---------------------------------------------------------------

    try:
        # Validate the constructed dictionary using the RuleCreate Pydantic model.
        # This checks types, enums, required fields, and any custom validation rules.
        print(f"Data prepared for Pydantic validation: {rule_data_dict}")
        rule_data = RuleCreate.model_validate(rule_data_dict)
        print("RuleCreate DTO validated:", rule_data.model_dump())
    except Exception as validation_error:
        # Handle Pydantic validation errors
        print(f"Validation error creating RuleCreate DTO: {validation_error}")
        # Extract more detailed error messages if available
        error_details = getattr(
            validation_error, "errors", lambda: [{"msg": str(validation_error)}]
        )()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_details,  # Provide detailed validation errors to the client
        )

    # If validation passes, proceed to call the service layer
    try:
        created_rule = await rule_service.add_rule_to_link(
            link_id=link_id, rule_data=rule_data, user_id=current_user_id
        )
        # On success, return the created rule object (JSON) and 201 status.
        # HTMX typically uses this response or just the status code to trigger UI updates (e.g., closing modal, refreshing list).
        return created_rule
    except NotFoundException as e:
        # Handle case where the parent link doesn't exist (should be rare if UI prevents this)
        print(
            f"[NOT FOUND] Parent link {link_id} not found during rule creation: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent link not found or access denied.",
        )
    except (PriorityConflictException, ValidationException) as e:
        # Handle specific service-layer validation errors (priority conflict, etc.)
        print(
            f"[CONFLICT/VALIDATION] Error creating rule for link {link_id}: {e.detail}"
        )
        status_code = (
            status.HTTP_409_CONFLICT
            if isinstance(e, PriorityConflictException)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=e.detail)
    except (DatabaseException, ServiceException) as e:
        # Handle generic database or service errors
        print(f"[ERROR] DB/Service error creating rule for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {e.detail}",
        )
    except Exception as e:
        # Catch any other unexpected errors
        print(f"[ERROR] Unexpected error creating rule for link {link_id}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.get(
    "/",  # Corresponds to GET /api/v1/links/{link_id}/rules
    response_model=List[RuleResponse],  # Expect a list of rule objects
    summary="List Rules for Link (JSON)",
    description="Retrieves a list of all routing rules associated with a specific link owned by the authenticated user.",
    tags=["Rules"],
)
async def list_rules_endpoint(
    link_id: UUID,  # Automatically extracted from the path prefix
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Inject user ID for auth check
    rule_service: RuleService = Depends(get_rule_service),  # Inject rule service
):
    """API endpoint to retrieve all rules for a specific link as JSON."""
    print(
        f"Received request to list rules (JSON) for link {link_id} by user {current_user_id}"
    )
    try:
        # Fetch rules; service handles ownership check
        rules = await rule_service.get_rules_for_link(
            link_id=link_id, user_id=current_user_id
        )
        print(f"Returning JSON response for {len(rules)} rules.")
        return rules  # Return the list of rules
    except NotFoundException as e:
        # Handle parent link not found or no access
        print(
            f"[NOT FOUND] Parent link {link_id} not found or access denied: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent link not found or access denied.",
        )
    except DatabaseException as e:
        # Handle database errors during fetch
        print(f"[ERROR] Database error listing rules for link {link_id}: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e.detail}",
        )
    except Exception as e:
        # Catch unexpected errors
        print(
            f"[ERROR] Unexpected error in list_rules_endpoint for link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


@router.get(
    "/{rule_id}",  # Corresponds to GET /api/v1/links/{link_id}/rules/{rule_id}
    response_model=RuleResponse,  # Expect a single rule object
    summary="Get Rule Details (JSON)",
    description="Retrieves details of a specific routing rule.",
    tags=["Rules"],
)
async def get_rule_endpoint(
    link_id: UUID,  # Automatically extracted from the path prefix
    rule_id: UUID = Path(
        ..., description="The ID of the rule to retrieve"
    ),  # Extracted from this path segment
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Inject user ID for auth check
    rule_service: RuleService = Depends(get_rule_service),  # Inject rule service
):
    """API endpoint to retrieve details for a single rule as JSON."""
    print(
        f"Received request to get rule {rule_id} for link {link_id} by user {current_user_id} (JSON)"
    )
    try:
        # Fetch rule details; service handles ownership check
        rule = await rule_service.get_rule_details(
            link_id=link_id, rule_id=rule_id, user_id=current_user_id
        )
        return rule  # Return the rule object
    except NotFoundException as e:
        # Handle rule or link not found / no access
        print(
            f"[NOT FOUND] {e.detail} for rule {rule_id} on link {link_id}, user {current_user_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        # Handle database errors
        print(
            f"[ERROR] Database error getting rule {rule_id} for link {link_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e.detail}",
        )
    except Exception as e:
        # Catch unexpected errors
        print(
            f"[ERROR] Unexpected error getting rule {rule_id} for link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# This endpoint handles the FORM SUBMISSION from the edit rule modal.
@router.patch(
    "/{rule_id}",  # Corresponds to PATCH /api/v1/links/{link_id}/rules/{rule_id}
    response_model=RuleResponse,  # Return the updated rule object
    summary="Update Rule from Form Data",
    description="Updates details of a specific routing rule using data submitted via an HTML form. Only provided fields are updated.",
    tags=["Rules"],
)
async def update_rule_endpoint(
    link_id: UUID,  # Automatically extracted from the path prefix
    rule_id: UUID = Path(
        ..., description="The ID of the rule to update"
    ),  # Extracted from this path segment
    # --- Form Data Parsing for PATCH ---
    # Receive all potential fields as Optional, as a PATCH might only send changed fields.
    # Use Form(None) to distinguish between a field not being sent vs. being sent with an empty value.
    priority: Optional[int] = Form(None),
    rule_type: Optional[str] = Form(None),
    target_type: Optional[str] = Form(None),
    target_value: Optional[str] = Form(
        None
    ),  # Empty string might be valid (e.g., clear HTML content)
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
    max_clicks: Optional[str] = Form(
        None
    ),  # Receive as string to handle potential "" for clearing
    # --------------------------------------
    current_user_id: UUID = Depends(get_current_user_id),  # Inject user ID for auth
    rule_service: RuleService = Depends(get_rule_service),  # Inject rule service
):
    """
    API endpoint to update an existing routing rule based on data submitted from an HTML form.
    It constructs a dictionary containing only the fields present in the form data,
    performs necessary conversions/validations, validates using the Pydantic model (RuleUpdate),
    and then calls the service to apply the partial update.
    """
    print(
        f"Received request to update rule {rule_id} via form for link {link_id} by user {current_user_id}"
    )

    # Build a dictionary containing only the fields that were actually submitted in the form.
    update_data_dict: Dict[str, Any] = {}
    if priority is not None:
        update_data_dict["priority"] = priority
    if rule_type is not None:
        update_data_dict["rule_type"] = rule_type
    if target_type is not None:
        update_data_dict["target_type"] = target_type
    # For fields where None/empty string might mean "clear the value", pass them if present.
    if target_value is not None:
        update_data_dict["target_value"] = target_value

    # Handle optional datetime and integer fields, converting if present and non-empty.
    parsed_start_time = None
    if start_time is not None:  # Field was present in form
        if start_time.strip():  # If not empty after stripping whitespace
            try:
                parsed_start_time = datetime.strptime(
                    start_time.strip(), "%Y-%m-%d %H:%M"
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid format for start_time: '{start_time}'. Use YYYY-MM-DD HH:MM.",
                )
        # If start_time was present but empty (""), parsed_start_time remains None (meaning clear the date)
        update_data_dict["start_time"] = parsed_start_time

    parsed_end_time = None
    if end_time is not None:
        if end_time.strip():
            try:
                parsed_end_time = datetime.strptime(end_time.strip(), "%Y-%m-%d %H:%M")
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid format for end_time: '{end_time}'. Use YYYY-MM-DD HH:MM.",
                )
        update_data_dict["end_time"] = parsed_end_time

    parsed_max_clicks = None
    if max_clicks is not None:
        if max_clicks.strip():
            try:
                parsed_max_clicks = int(max_clicks.strip())
                if parsed_max_clicks < 1:
                    raise ValueError("max_clicks must be a positive integer")
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid value for max_clicks: '{max_clicks}'. {e}",
                )
        update_data_dict["max_clicks"] = parsed_max_clicks

    # Check if any update data was actually provided
    if not update_data_dict:
        # Depending on desired behavior, could return 200 OK with current rule, or 400.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update data provided in the form.",
        )

    try:
        # Validate the potentially partial data using the RuleUpdate Pydantic model.
        print(f"Data prepared for Pydantic validation (Update): {update_data_dict}")
        # `model_validate` handles the partial nature correctly if fields are Optional in the schema.
        update_data = RuleUpdate.model_validate(update_data_dict)
        print(
            "RuleUpdate DTO validated:", update_data.model_dump(exclude_unset=True)
        )  # Log only updated fields
    except Exception as validation_error:
        # Handle Pydantic validation errors
        print(f"Validation error creating RuleUpdate DTO: {validation_error}")
        error_details = getattr(
            validation_error, "errors", lambda: [{"msg": str(validation_error)}]
        )()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_details,
        )

    # If validation passes, call the service layer to perform the update
    try:
        updated_rule = await rule_service.update_rule(
            link_id=link_id,
            rule_id=rule_id,
            update_data=update_data,  # Pass the validated Pydantic model
            user_id=current_user_id,  # Service checks ownership
        )
        # Return the updated rule object. HTMX will likely use the success status
        # to close the modal and trigger a refresh of the rule list.
        return updated_rule
    except NotFoundException as e:
        # Handle rule/link not found or no access
        print(
            f"[NOT FOUND] Error updating rule {rule_id} on link {link_id}: {e.detail}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except (ValidationException, PriorityConflictException) as e:
        # Handle specific service-layer validation errors
        print(
            f"[CONFLICT/VALIDATION] Error updating rule {rule_id} on link {link_id}: {e.detail}"
        )
        status_code = (
            status.HTTP_409_CONFLICT
            if isinstance(e, PriorityConflictException)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=e.detail)
    except (DatabaseException, ServiceException) as e:
        # Handle generic database or service errors
        print(
            f"[ERROR] DB/Service error updating rule {rule_id} on link {link_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {e.detail}",
        )
    except Exception as e:
        # Catch any other unexpected errors
        print(
            f"[ERROR] Unexpected error updating rule {rule_id} on link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )


# This endpoint handles DELETE requests, likely triggered by a button in the UI.
@router.delete(
    "/{rule_id}",  # Corresponds to DELETE /api/v1/links/{link_id}/rules/{rule_id}
    status_code=status.HTTP_204_NO_CONTENT,  # Standard code for successful deletion with no response body
    summary="Delete Rule",
    description="Deletes a specific routing rule.",
    tags=["Rules"],
)
async def delete_rule_endpoint(
    link_id: UUID,  # Automatically extracted from the path prefix
    rule_id: UUID = Path(
        ..., description="The ID of the rule to delete"
    ),  # Extracted from this path segment
    current_user_id: UUID = Depends(
        get_current_user_id
    ),  # Inject user ID for auth check
    rule_service: RuleService = Depends(get_rule_service),  # Inject rule service
):
    """API endpoint to delete a specific rule."""
    print(
        f"Received request to delete rule {rule_id} for link {link_id} by user {current_user_id}"
    )
    try:
        # Call the service to delete the rule; service handles ownership check
        await rule_service.delete_rule(
            link_id=link_id, rule_id=rule_id, user_id=current_user_id
        )
        # Return a Response with 204 status and no body on success
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NotFoundException as e:
        # Handle rule/link not found or no access
        print(
            f"[NOT FOUND] {e.detail} during delete for rule {rule_id} on link {link_id}"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.detail)
    except DatabaseException as e:
        # Handle database errors during deletion
        print(
            f"[ERROR] Database error deleting rule {rule_id} for link {link_id}: {e.detail}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e.detail}",
        )
    except Exception as e:
        # Catch unexpected errors
        print(
            f"[ERROR] Unexpected error deleting rule {rule_id} for link {link_id}: {e}"
        )
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred.",
        )
