# API Endpoint Implementation Plan: List Rules

## 1. Endpoint Overview

This endpoint retrieves a list of all `routing_rules` associated with a specific `routr_link` owned by the authenticated user. The rules are returned sorted by their `priority` in ascending order (lowest number first). This is crucial for the user interface to display rules in their execution order.

## 2. Request Details

- **Method:** `GET`
- **URL Structure:** `/links/{link_id}/rules`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the parent `routr_link` whose rules are to be retrieved.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
- **Request Body:** None

## 3. DTOs and Models

- **Response Item DTO (Pydantic Model):** `RuleResponse` (Reuse from Create Rule)

  ```python
  # Example definition (reuse)
  from pydantic import BaseModel, UUID4
  from datetime import datetime
  from typing import Optional, Literal

  # Assume Enums are defined or imported
  RuleTypeEnum = Literal['time', 'clicks']
  TargetTypeEnum = Literal['url', 'html']

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

- **Response DTO (List):** `List[RuleResponse]` (FastAPI handles list serialization)

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `GET` request at `/links/{link_id}/rules`.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Path Parameter Validation:** FastAPI validates `link_id` is a valid UUID. If not, returns `422 Unprocessable Entity`.
4.  **Call Service Layer:** The endpoint handler calls a method in the `RuleService` (or `LinkService`, e.g., `get_rules_for_link`), passing the `link_id` and `user_id`.
5.  **Check Link Ownership (Service Layer):**
    - Similar to `Create Rule`, the service _must_ first verify that the `link_id` exists and belongs to the `user_id`. Execute `SELECT id FROM routr_links WHERE id = link_id AND user_id = user_id` using the user's JWT context (RLS applies).
    - If the link is not found or not owned, raise `NotFoundException`.
6.  **Database Query (Service Layer):**
    - If link ownership is confirmed, the service uses the `supabase-py` client to execute a `SELECT` query on the `public.routing_rules` table.
    - Filter by `link_id = link_id`. The RLS policy `USING (link_id IN (... WHERE auth.uid() = user_id))` ensures that only rules belonging to the user's link are considered, providing an extra layer of security although the initial check should suffice.
    - **Crucially, apply `ORDER BY priority ASC`** to retrieve rules in the correct execution order.
    - Select all columns needed for the `RuleResponse` DTO.
7.  **Handle Database Response (Service Layer):**
    - If the query is successful, return the list of rule data (which might be empty if the link has no rules).
    - Catch potential database errors and signal "Server Error".
8.  **Process Service Response (Endpoint Handler):**
    - If the service raises `NotFoundException` (from link ownership check), raise `HTTPException(status_code=404, detail="Parent link not found or access denied")`.
    - If the service returns the list of rules successfully, map each item in the list to the `RuleResponse` DTO. FastAPI will handle the serialization of the list.
    - Handle generic "Server Errors" by raising `HTTPException(status_code=500, detail="Internal server error")`.
9.  **Send Response:** FastAPI serializes the list of `RuleResponse` models into a JSON array and sends the `200 OK` response.
    - **HTMX Consideration:** Similar to `List Links`, if `HX-Request` header is present, the endpoint could render a Jinja2 template fragment containing the HTML list of rules instead of JSON.

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Multi-layered:
  - Service layer explicitly checks ownership of the parent `link_id`.
  - RLS policy `USING (link_id IN (... WHERE auth.uid() = user_id))` ensures only rules linked to the user's links are retrieved.
- **Input Validation:** Path parameter `link_id` is validated for UUID format (`422 Unprocessable Entity`). No request body to validate.
- **Information Exposure:** Ensure only necessary fields defined in `RuleResponse` are returned.

## 6. Error Handling

- **`401 Unauthorized`:** Returned by the authentication dependency.
- **`403 Forbidden`:** Handled implicitly by the ownership check, resulting in `404 Not Found`.
- **`404 Not Found`:** Returned if the parent `link_id` does not exist or does not belong to the authenticated user.
- **`422 Unprocessable Entity`:** Returned by FastAPI if `link_id` is not a valid UUID.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors (database connection, Supabase client issues, uncaught exceptions). Log details server-side.

## 7. Performance Considerations

- **Database Query:** The main factor is the `SELECT` query on `routing_rules`.
  - Filtering by `link_id` is efficient if indexed (FK index usually exists).
  - Sorting by `priority` benefits significantly from the composite index `idx_routing_rules_link_id_priority`.
- **Number of Rules:** If a single link can have a very large number of rules (unlikely in MVP scope, but possible later), fetching all rules at once might become slow or memory-intensive. Consider pagination for this endpoint in future iterations if necessary, although for managing rules, users often prefer seeing all of them together.
- **Mitigation:** Ensure the `idx_routing_rules_link_id_priority` index exists. Monitor performance if links start having hundreds or thousands of rules.

## 8. Implementation Steps

1.  **Define/Confirm Pydantic Models:** Ensure `RuleResponse` is defined.
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `get_rules_for_link`) in `RuleService` or `LinkService`.
    - Accept `link_id: UUID`, `user_id: UUID` as arguments.
    - Inject the Supabase client.
    - **Step 1: Verify Link Ownership.** Execute `supabase.table('routr_links').select('id').eq('id', link_id).eq('user_id', user_id).maybe_single().execute()`. If `response.data` is `None`, raise `NotFoundException`.
    - **Step 2: Fetch Rules.** Execute `supabase.table('routing_rules').select('*').eq('link_id', link_id).order('priority', desc=False).execute()`.
    - Wrap database calls in `try...except` for error handling.
    - Return the list of rule data (`response.data`).
3.  **Implement Authentication Dependency:** Reuse the existing dependency.
4.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.get("/links/{link_id}/rules", response_model=List[RuleResponse])` in `routers/rules.py` (or `routers/links.py`).
    - Use `Path(...)` for `link_id`.
    - Inject the `RuleService` (or `LinkService`) and the authentication dependency (`current_user`).
    - Call the service method `service.get_rules_for_link(link_id=link_id, user_id=current_user.id)`.
    - Wrap the service call in `try...except`:
      - Catch `NotFoundException` -> `HTTPException(404, "Parent link not found or access denied")`.
      - Catch other exceptions -> `HTTPException(500, "Internal server error")`.
    - Return the list of rules upon success.
    - _(HTMX Alternative):_ Check for `HX-Request` header and potentially return `HTMLResponse` with rendered template fragment.
5.  **Register Router:** Ensure the router is included in the main FastAPI app.
6.  **Write Unit/Integration Tests:**
    - Test fetching rules for a link owned by the user (with 0, 1, and multiple rules). Verify sorting by priority.
    - Test fetching rules for a link that doesn't exist (expect 404).
    - Test fetching rules for a link owned by another user (expect 404).
    - Test without authentication token (expect 401).
    - Test with invalid `link_id` UUID format (expect 422).
    - (Optional) Mock database errors to test 500 responses.
    - (Optional) Test the HTMX fragment response if implemented.
