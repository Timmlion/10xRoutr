# API Endpoint Implementation Plan: Create Rule

## 1. Endpoint Overview

This endpoint allows an authenticated user to add a new routing rule (`routing_rules`) to one of their existing `routr_link` resources. It requires specifying the rule's priority, type (time or clicks), target details (type and value), and the corresponding parameters for the chosen rule type. It validates the input, ensures the user owns the parent link, checks for priority conflicts, inserts the new rule, and returns its details.

## 2. Request Details

- **Method:** `POST`
- **URL Structure:** `/links/{link_id}/rules`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the parent `routr_link`.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
    - `Content-Type: application/json` (Required)
- **Request Body:** Required (JSON payload)
  ```json
  {
    "priority": "integer (required, positive, unique per link)",
    "rule_type": "string (required, 'time' or 'clicks')",
    "target_type": "string (required, 'url' or 'html')",
    "target_value": "string (required, valid URL if target_type='url', HTML code if target_type='html')",
    "start_time": "iso_timestamp_with_tz | null (required if rule_type='time', else ignored/null)",
    "end_time": "iso_timestamp_with_tz | null (required if rule_type='time', else ignored/null)",
    "max_clicks": "integer | null (required and positive if rule_type='clicks', else ignored/null)"
  }
  ```

## 3. DTOs and Models

- **Request DTO (Pydantic Model):** `RuleCreate`

  ```python
  # Example definition (place in schemas/rule.py)
  from pydantic import BaseModel, field_validator, root_validator, Field, UUID4
  from datetime import datetime
  from typing import Optional, Literal

  # Re-use or define Enums if not globally available
  RuleTypeEnum = Literal['time', 'clicks']
  TargetTypeEnum = Literal['url', 'html']

  class RuleCreate(BaseModel):
      priority: int = Field(..., gt=0) # Must be positive
      rule_type: RuleTypeEnum
      target_type: TargetTypeEnum
      target_value: str
      start_time: Optional[datetime] = None
      end_time: Optional[datetime] = None
      max_clicks: Optional[int] = Field(None, gt=0) # Must be positive if provided

      @root_validator(pre=False, skip_on_failure=True) # Pydantic v1 style, adapt for v2 if needed
      def check_conditional_fields(cls, values):
          rule_type = values.get('rule_type')
          start_time = values.get('start_time')
          end_time = values.get('end_time')
          max_clicks = values.get('max_clicks')

          if rule_type == 'time' and (start_time is None or end_time is None):
              raise ValueError('start_time and end_time are required for rule_type "time"')
          if rule_type == 'time' and start_time and end_time and end_time <= start_time:
               raise ValueError('end_time must be after start_time')
          if rule_type == 'clicks' and max_clicks is None:
              raise ValueError('max_clicks is required for rule_type "clicks"')

          # Clear irrelevant fields based on type
          if rule_type == 'time':
              values['max_clicks'] = None
          elif rule_type == 'clicks':
              values['start_time'] = None
              values['end_time'] = None

          return values

      @field_validator('target_value')
      def validate_target_value_format(cls, v, values):
          # Use values.data in Pydantic v2
          target_type = values.data.get('target_type') if hasattr(values, 'data') else values.get('target_type')
          if target_type == 'url' and not (v.startswith('http://') or v.startswith('https://')):
              raise ValueError('Invalid URL format for target_value when target_type is "url"')
          # Add HTML length check here later if needed
          # if target_type == 'html' and len(v) > YOUR_HTML_LIMIT:
          #    raise ValueError(f'HTML content exceeds the maximum length of {YOUR_HTML_LIMIT} characters')
          return v
  ```

- **Response DTO (Pydantic Model):** `RuleResponse`

  ```python
  # Example definition (place in schemas/rule.py)
  from pydantic import BaseModel, UUID4
  from datetime import datetime
  from typing import Optional

  # Assume Enums are defined or imported
  # RuleTypeEnum = Literal['time', 'clicks']
  # TargetTypeEnum = Literal['url', 'html']

  class RuleResponse(BaseModel):
      id: UUID4
      link_id: UUID4
      priority: int
      rule_type: RuleTypeEnum
      target_type: TargetTypeEnum
      target_value: str
      start_time: Optional[datetime]
      end_time: Optional[datetime]
      max_clicks: Optional[int]
      current_clicks: int
      created_at: datetime
      updated_at: datetime

      # class Config:
      #     orm_mode = True # or from_attributes = True
  ```

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `POST` request at `/links/{link_id}/rules` with a JSON payload.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Path Parameter Validation:** FastAPI validates `link_id` is a valid UUID. If not, returns `422 Unprocessable Entity`.
4.  **Request Body Validation:** FastAPI validates the incoming JSON payload against the `RuleCreate` Pydantic model.
    - Checks required fields, types, positive `priority`, positive `max_clicks`.
    - Runs `root_validator` to check conditional requirements (`start_time`/`end_time` for 'time', `max_clicks` for 'clicks').
    - Runs `field_validator` for `target_value` format based on `target_type`.
    - If validation fails, returns `422 Unprocessable Entity`.
5.  **Call Service Layer:** The endpoint handler calls a method in the `RuleService` (or potentially `LinkService` if managing rules within it, e.g., `add_rule_to_link`), passing the `link_id`, the validated `RuleCreate` data, and the `user_id`.
6.  **Check Link Ownership (Service Layer):**
    - Before attempting insertion, the service _must_ verify that the `link_id` exists and belongs to the `user_id`. This can be done with a quick `SELECT id FROM routr_links WHERE id = link_id AND user_id = user_id` query using the user's JWT context (RLS applies).
    - If the link is not found or not owned, raise `NotFoundException` (which translates to `404 Not Found` in the handler, effectively acting like `403 Forbidden` as well).
7.  **Database Query (Service Layer):**
    - If link ownership is confirmed, the service uses the `supabase-py` client to execute an `INSERT` query on the `public.routing_rules` table.
    - The data dictionary includes all validated fields from `RuleCreate`, plus the `link_id` from the path parameter. `current_clicks` defaults to 0. `created_at`/`updated_at` use database defaults.
    - The RLS policy `WITH CHECK (link_id IN (... WHERE auth.uid() = user_id))` provides an additional layer ensuring the rule is inserted only for a link owned by the user.
    - The database `UNIQUE (link_id, priority)` constraint handles priority conflicts.
8.  **Handle Database Response (Service Layer):**
    - If the `INSERT` is successful, return the data of the newly created rule.
    - If the `INSERT` fails due to the `UNIQUE` constraint violation on `(link_id, priority)`, catch the specific database error (e.g., code `23505`) and signal "Priority Conflict".
    - If the `INSERT` fails due to other constraint violations (e.g., `CHECK` rules missed by Pydantic), signal "Bad Request".
    - Catch other potential database errors and signal "Server Error".
9.  **Process Service Response (Endpoint Handler):**
    - If the service returns the newly created rule data, map it to the `RuleResponse` DTO.
    - If the service raises `NotFoundException` (from link ownership check), raise `HTTPException(status_code=404, detail="Parent link not found or access denied")`.
    - If the service signals "Priority Conflict", raise `HTTPException(status_code=409, detail="Priority conflict for this link")`.
    - If the service signals "Bad Request", raise `HTTPException(status_code=400, detail="Invalid input data violating database constraints")`.
    - Handle generic "Server Errors" by raising `HTTPException(status_code=500, detail="Internal server error")`.
10. **Send Response:** FastAPI serializes the `RuleResponse` model (or error details) into JSON and sends the HTTP response with the appropriate status code (`201 Created`, `409 Conflict`, etc.).

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Multi-layered:
  - Service layer explicitly checks if the parent `link_id` exists and belongs to the authenticated `user_id` before attempting insertion.
  - RLS policy `WITH CHECK (link_id IN (...))` provides database-level enforcement that the rule is associated with a link owned by the user performing the insert.
- **Input Validation:** Comprehensive validation by the `RuleCreate` Pydantic model, including conditional logic based on `rule_type`. Database constraints (`UNIQUE`, `CHECK`, `NOT NULL`, FK, ENUMs) provide secondary validation.
- **Data Integrity:** Database constraints ensure priority uniqueness per link and presence of required fields based on rule type.

## 6. Error Handling

- **`400 Bad Request`:** Returned if database `CHECK` constraints fail (though Pydantic should catch most issues first).
- **`401 Unauthorized`:** Returned by the authentication dependency.
- **`403 Forbidden`:** Handled implicitly by the ownership check, resulting in a `404 Not Found` response to avoid confirming the link's existence to unauthorized users.
- **`404 Not Found`:** Returned if the parent `link_id` does not exist or does not belong to the authenticated user.
- **`409 Conflict`:** Returned specifically when the database `UNIQUE` constraint on `(link_id, priority)` is violated.
- **`422 Unprocessable Entity`:** Returned by FastAPI if the request body fails validation against `RuleCreate` (e.g., missing fields, invalid types, failed custom validators like conditional field checks or `target_value` format). Also returned if `link_id` is not a valid UUID.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors (database connection, Supabase client issues, uncaught exceptions). Log details server-side.

## 7. Performance Considerations

- **Database Queries:** Involves potentially one `SELECT` (for ownership check) and one `INSERT`.
  - The ownership check query filters on primary key (`id`) and indexed foreign key (`user_id`), making it fast.
  - The `INSERT` performance depends on checking the `UNIQUE (link_id, priority)` constraint (supported by `idx_routing_rules_link_id_priority`) and other `CHECK` constraints.
- **Indexing:** The index `idx_routing_rules_link_id_priority` is crucial for efficiently checking priority uniqueness during insertion.
- **Mitigation:** Performance is unlikely to be a significant issue for MVP. Ensure necessary indexes are in place.

## 8. Implementation Steps

1.  **Define Pydantic Models:** Create/Confirm `RuleCreate` (with validators) and `RuleResponse` models in `schemas/rule.py`. Define or import necessary `ENUM` types or use `Literal`.
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `add_rule_to_link`) possibly within `RuleService` or `LinkService`.
    - Accept `link_id: UUID`, `rule_data: RuleCreate`, `user_id: UUID` as arguments.
    - Inject the Supabase client.
    - **Step 1: Verify Link Ownership.** Execute a query like `supabase.table('routr_links').select('id').eq('id', link_id).eq('user_id', user_id).maybe_single().execute()`. If `response.data` is `None`, raise `NotFoundException`.
    - **Step 2: Prepare Insert Data.** Create the dictionary for insertion, combining `link_id` with data from `rule_data`. Ensure fields irrelevant to the `rule_type` are set to `None` (handled by Pydantic validator ideally).
    - **Step 3: Insert Rule.** Execute `supabase.table('routing_rules').insert(insert_dict).execute()`. Use `.single()` or equivalent to get the returned row.
    - Wrap the insert call in a `try...except` block:
      - Catch the specific database error for unique constraint violation (`23505`) and raise `PriorityConflictException`.
      - Catch other database/client errors and raise `DatabaseException`.
    - If successful, return the data of the newly created rule.
3.  **Implement Authentication Dependency:** Reuse the existing dependency.
4.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.post("/links/{link_id}/rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)` in `routers/rules.py` (or `routers/links.py`).
    - Accept `link_id: UUID` from the path and `rule_data: RuleCreate` from the body.
    - Inject the `RuleService` (or `LinkService`) and the authentication dependency (`current_user`).
    - Call the service method `service.add_rule_to_link(link_id=link_id, rule_data=rule_data, user_id=current_user.id)`.
    - Wrap the service call in `try...except`:
      - Catch `NotFoundException` -> `HTTPException(404, "Parent link not found or access denied")`.
      - Catch `PriorityConflictException` -> `HTTPException(409, "Priority conflict for this link")`.
      - Catch other specific service/database exceptions -> `HTTPException(400/500, ...)`
    - Return the created rule data upon success.
5.  **Register Router:** Ensure the router handling `/links/{link_id}/rules` is included in the main FastAPI app.
6.  **Write Unit/Integration Tests:**
    - Test successful creation of 'time' rules and 'clicks' rules.
    - Test validation: missing required fields for type, invalid priority (0, negative), invalid `target_value` format, `end_time` before `start_time`. Expect 422.
    - Test creating a rule with a priority that already exists for the same link (expect 409).
    - Test creating a rule for a link that doesn't exist (expect 404).
    - Test creating a rule for a link owned by another user (expect 404).
    - Test without authentication token (expect 401).
    - Test with invalid `link_id` UUID format (expect 422).
    - (Optional) Mock database errors to test 500 responses.
