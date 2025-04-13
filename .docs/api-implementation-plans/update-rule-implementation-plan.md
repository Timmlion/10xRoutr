# API Endpoint Implementation Plan: Update Rule

## 1. Endpoint Overview

This endpoint allows an authenticated user to partially update the details of a specific `routing_rule` they own, identified by its ID and its parent `link_id`. It uses the `PATCH` method, meaning only the fields provided in the request body should be updated. Validation ensures data consistency, especially when changing rule or target types.

## 2. Request Details

- **Method:** `PATCH`
- **URL Structure:** `/links/{link_id}/rules/{rule_id}`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the parent `routr_link`.
    - `rule_id` (UUID, Required): The unique identifier of the specific `routing_rule` to update.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
    - `Content-Type: application/json` (Required)
- **Request Body:** Required (JSON payload containing only fields to be updated)
  ```json
  {
    "priority": "integer (optional, positive, unique per link)",
    "rule_type": "string (optional, 'time' or 'clicks')",
    "target_type": "string (optional, 'url' or 'html')",
    "target_value": "string (optional, context-dependent validation)",
    "start_time": "iso_timestamp_with_tz | null (optional)",
    "end_time": "iso_timestamp_with_tz | null (optional)",
    "max_clicks": "integer | null (optional, positive)"
    // current_clicks cannot be updated via API
  }
  ```

## 3. DTOs and Models

- **Request DTO (Pydantic Model):** `RuleUpdate`

  ```python
  # Example definition (place in schemas/rule.py)
  from pydantic import BaseModel, field_validator, root_validator, Field, UUID4
  from datetime import datetime
  from typing import Optional, Literal, Dict, Any

  # Assume Enums are defined or imported
  RuleTypeEnum = Literal['time', 'clicks']
  TargetTypeEnum = Literal['url', 'html']

  class RuleUpdate(BaseModel):
      # All fields are optional for PATCH
      priority: Optional[int] = Field(None, gt=0)
      rule_type: Optional[RuleTypeEnum] = None
      target_type: Optional[TargetTypeEnum] = None
      target_value: Optional[str] = None
      start_time: Optional[datetime | None] = None # Allow explicit null
      end_time: Optional[datetime | None] = None   # Allow explicit null
      max_clicks: Optional[int | None] = Field(None, gt=0) # Allow explicit null, must be positive if not null

      # Need complex validation considering existing values if type changes
      # This might be better handled in the service layer after fetching the current rule
      @root_validator(pre=False, skip_on_failure=True) # Pydantic v1 style
      def check_consistency(cls, values: Dict[str, Any]):
          # This validation becomes complex for PATCH.
          # It needs the *current* state of the rule from the DB
          # to correctly validate conditional requirements if types change.
          # Suggestion: Perform basic format validation here,
          # and complex consistency checks in the service layer.

          priority = values.get('priority')
          max_clicks = values.get('max_clicks')
          start_time = values.get('start_time')
          end_time = values.get('end_time')

          if priority is not None and priority <= 0:
               raise ValueError('priority must be positive') # Basic check
          if max_clicks is not None and max_clicks <= 0:
               raise ValueError('max_clicks must be positive') # Basic check
          if start_time and end_time and end_time <= start_time:
               raise ValueError('end_time must be after start_time') # Basic check

          # Cross-field validation based on changing types is hard here.
          # E.g., if rule_type is PATCHed to 'time', are start/end provided?
          # Requires knowing the original rule_type too.

          return values

      @field_validator('target_value')
      def validate_target_value_format_if_needed(cls, v, values):
          # This validator also needs context of target_type (potentially changing)
          # Perform basic checks, rely on service for full context validation
          target_type = values.data.get('target_type') if hasattr(values, 'data') else values.get('target_type')
          if target_type == 'url' and v is not None and not (v.startswith('http://') or v.startswith('https://')):
               raise ValueError('Invalid URL format for target_value')
          # Add potential HTML length check if target_type is 'html' or being set to 'html'
          return v

  ```

- **Response DTO (Pydantic Model):** `RuleResponse` (Reuse from Get/Create Rule)
  ```python
  # Example definition (reuse)
  # ... (same as before) ...
  ```

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `PATCH` request at `/links/{link_id}/rules/{rule_id}` with a JSON payload.
2.  **Authentication:** The authentication dependency verifies JWT. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Path Parameter Validation:** FastAPI validates `link_id` and `rule_id` are valid UUIDs. If not, returns `422 Unprocessable Entity`.
4.  **Request Body Validation:** FastAPI validates the incoming JSON payload against the `RuleUpdate` Pydantic model.
    - Validates types and basic constraints (e.g., `priority > 0`).
    - _Note:_ Complex cross-field validation (e.g., ensuring `start_time` is present if `rule_type` is changed to `time`) is difficult solely within the Pydantic model for PATCH and should be handled primarily in the service layer.
    - If basic validation fails, returns `422 Unprocessable Entity`.
5.  **Call Service Layer:** Endpoint handler calls `RuleService.update_rule`, passing `link_id`, `rule_id`, the validated `RuleUpdate` data, and `user_id`.
6.  **Fetch Current Rule & Check Ownership (Service Layer):**
    - The service _must_ first fetch the _current_ state of the rule using `SELECT * FROM routing_rules WHERE id = rule_id AND link_id = link_id` with the user's JWT context (RLS applies).
    - If the rule is not found or not owned, raise `NotFoundException`.
7.  **Apply Updates & Validate Consistency (Service Layer):**
    - Create a dictionary representing the final intended state by applying the non-None values from the `RuleUpdate` data onto the current rule data fetched from the database.
    - **Perform Complex Consistency Validation:** Now, using the _final intended state_, validate the conditional requirements:
      - If final `rule_type` is 'time', ensure final `start_time` and `end_time` are not None and `end_time > start_time`.
      - If final `rule_type` is 'clicks', ensure final `max_clicks` is not None and is positive.
      - If final `target_type` is 'url', ensure final `target_value` has a valid URL format.
      - If any validation fails, raise `BadRequestException`.
    - **Clear Irrelevant Fields:** Based on the final `rule_type`, explicitly set the irrelevant fields to `NULL` in the `data_to_update` dictionary (e.g., set `max_clicks=None` if `rule_type` becomes 'time').
8.  **Database Query (Service Layer):**
    - Execute an `UPDATE` query on `public.routing_rules`.
    - Target the row `WHERE id = rule_id`. RLS `USING (link_id IN (...))` ensures the user owns the parent link.
    - Use the prepared `data_to_update` dictionary (containing only the changed fields and cleared irrelevant fields). The `updated_at` trigger handles that column.
9.  **Handle Database Response (Service Layer):**
    - If the `UPDATE` is successful, fetch the fully updated rule data (either from the `UPDATE ... RETURNING *` or a subsequent `SELECT`).
    - If `UPDATE` fails due to `UNIQUE (link_id, priority)` constraint (if `priority` was changed), catch the specific error (`23505`) and signal "Priority Conflict".
    - If `UPDATE` fails due to other constraints (e.g., `CHECK`), signal "Bad Request".
    - Catch other database errors and signal "Server Error".
10. **Process Service Response (Endpoint Handler):**
    - If the service returns updated rule data, map it to `RuleResponse`.
    - If `NotFoundException` was raised, raise `HTTPException(404, "Rule not found or access denied")`.
    - If `BadRequestException` was raised (consistency validation), raise `HTTPException(400, detail="Inconsistent rule data provided")`.
    - If "Priority Conflict", raise `HTTPException(409, "Priority conflict for this link")`.
    - If "Bad Request" (DB constraint), raise `HTTPException(400, detail="Invalid input data violating database constraints")`.
    - Handle generic "Server Errors" -> `HTTPException(500, "Internal server error")`.
11. **Send Response:** Send serialized `RuleResponse` or error details with the appropriate status code.

## 5. Security Considerations

- **Authentication:** Enforced via JWT (`401 Unauthorized`).
- **Authorization:** Multi-layered: Service fetches rule first, ensuring ownership via RLS before attempting update. RLS on `UPDATE` provides database-level guarantee.
- **Input Validation:** Basic validation by Pydantic, complex consistency checks in the service layer before DB update. Database constraints provide final checks.
- **Mass Assignment:** Using `RuleUpdate` DTO prevents updating immutable fields or internal counters like `current_clicks`.

## 6. Error Handling

- **`400 Bad Request`:** Returned for consistency errors detected in the service layer (e.g., changing `rule_type` without required fields) or if database `CHECK` constraints fail.
- **`401 Unauthorized`:** Returned by authentication dependency.
- **`403 Forbidden`:** Implicitly handled by ownership check, resulting in `404 Not Found`.
- **`404 Not Found`:** Returned if the specified `rule_id` (or `link_id`) does not exist or does not belong to the user.
- **`409 Conflict`:** Returned if updating the `priority` results in a conflict with another rule under the same `link_id`.
- **`422 Unprocessable Entity`:** Returned by FastAPI for basic validation failures against `RuleUpdate` (e.g., invalid types, basic constraint violations like non-positive priority) or invalid UUID formats in path parameters.
- **`500 Internal Server Error`:** Returned for unexpected database/server errors. Log details server-side.

## 7. Performance Considerations

- **Database Queries:** Typically involves one `SELECT` (fetch current state/verify ownership) and one `UPDATE` targeting the primary key (`id`). Both are generally fast.
- **Constraint Checking:** Checking the `UNIQUE (link_id, priority)` constraint during `UPDATE` (if priority changes) utilizes the index and is efficient.
- **Indexing:** Primary key index on `id` is crucial. Index `idx_routing_rules_link_id_priority` supports the unique constraint check.
- **Locking:** Standard `UPDATE` row-level lock.

## 8. Implementation Steps

1.  **Define Pydantic Models:** Create/Confirm `RuleUpdate` (with basic validators) and `RuleResponse`.
2.  **Create Service Layer Method:**
    - Define `update_rule` in `RuleService` or `LinkService`.
    - Accept `link_id: UUID`, `rule_id: UUID`, `update_data: RuleUpdate`, `user_id: UUID`.
    - Inject Supabase client.
    - **Step 1: Fetch Current Rule.** Query `routing_rules` for `id=rule_id` and `link_id=link_id`. Use user's JWT context (RLS applies). If not found, raise `NotFoundException`. Store the current rule data.
    - **Step 2: Merge Data.** Create the `final_state` dictionary by merging `update_data` onto the `current_rule` data. Use `update_data.model_dump(exclude_unset=True)` to get only provided fields.
    - **Step 3: Validate Consistency.** Perform checks on `final_state` (e.g., required fields based on `rule_type`). If invalid, raise `BadRequestException`.
    - **Step 4: Prepare Update Payload.** Create `db_update_payload` containing only the fields that actually changed _and_ are relevant based on the final `rule_type` (clear irrelevant fields like setting `max_clicks=None` if `rule_type` is 'time').
    - **Step 5: Execute Update.** If `db_update_payload` is not empty, execute `supabase.table('routing_rules').update(db_update_payload).eq('id', rule_id).execute()`. Request returning updated row.
    - Wrap update in `try...except`, catching unique constraint violation (`23505` -> `PriorityConflictException`) and other DB errors (`DatabaseException`).
    - **Step 6: Fetch Updated State (if needed).** If update didn't return the full row, re-fetch it using the `rule_id`.
    - Return the final updated rule data.
3.  **Implement Authentication Dependency:** Reuse existing dependency.
4.  **Create FastAPI Endpoint Handler:**
    - Define `@router.patch("/links/{link_id}/rules/{rule_id}", response_model=RuleResponse)` in `routers/rules.py`.
    - Accept `link_id`, `rule_id` from path, `update_data: RuleUpdate` from body.
    - Inject service and authentication dependency.
    - Call the service `update_rule` method.
    - Wrap service call in `try...except` mapping service exceptions (`NotFoundException`, `BadRequestException`, `PriorityConflictException`, `DatabaseException`) to appropriate `HTTPException`s (404, 400, 409, 500).
    - Return the result on success.
5.  **Register Router:** Include router in the main app.
6.  **Write Unit/Integration Tests:**
    - Test updating each field (`priority`, `target_value`, `start_time`, etc.) individually.
    - Test changing `rule_type` and providing necessary related fields.
    - Test changing `rule_type` _without_ providing necessary fields (expect 400/422).
    - Test updating `priority` to an existing value for the same link (expect 409).
    - Test updating a rule that doesn't exist or belongs to another user (expect 404).
    - Test with invalid basic data types/formats (expect 422).
    - Test without authentication (expect 401).
    - (Optional) Mock database errors (expect 500).
