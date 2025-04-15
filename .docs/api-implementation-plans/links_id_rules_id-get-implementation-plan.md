# API Endpoint Implementation Plan: Get Rule

## 1. Endpoint Overview

This endpoint retrieves the detailed information for a single, specific `routing_rule`, identified by its ID and belonging to a specific `routr_link` owned by the authenticated user.

## 2. Request Details

- **Method:** `GET`
- **URL Structure:** `/links/{link_id}/rules/{rule_id}`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the parent `routr_link`.
    - `rule_id` (UUID, Required): The unique identifier of the specific `routing_rule` to retrieve.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
- **Request Body:** None

## 3. DTOs and Models

- **Response DTO (Pydantic Model):** `RuleResponse` (Reuse from Create/List Rule)

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

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `GET` request at `/links/{link_id}/rules/{rule_id}`.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Path Parameter Validation:** FastAPI validates that both `link_id` and `rule_id` are valid UUID formats. If not, returns `422 Unprocessable Entity`.
4.  **Call Service Layer:** The endpoint handler calls a method in the `RuleService` (or `LinkService`, e.g., `get_rule_details`), passing `link_id`, `rule_id`, and `user_id`.
5.  **Database Query (Service Layer):**
    - The `RuleService` uses the `supabase-py` client.
    - Execute a `SELECT` query on `public.routing_rules`.
    - Filter by `id = rule_id` AND `link_id = link_id`.
    - The RLS policy `USING (link_id IN (... WHERE auth.uid() = user_id))` implicitly ensures that the rule belongs to a link owned by the authenticated user. The query will return zero rows if the rule doesn't exist, if the `link_id` doesn't match the rule, or if the user doesn't own the parent link.
    - Select all columns needed for the `RuleResponse` DTO.
6.  **Handle Database Response (Service Layer):**
    - Use `.maybe_single()` in the Supabase query.
    - If `response.data` is present (rule found and ownership implicitly verified by RLS), return the rule data.
    - If `response.data` is `None` (rule not found, or link_id mismatch, or user doesn't own parent link), signal "Not Found".
    - Catch potential database errors and signal "Server Error".
7.  **Process Service Response (Endpoint Handler):**
    - If the service returns rule data, map it to the `RuleResponse` DTO.
    - If the service signals "Not Found", raise `HTTPException(status_code=404, detail="Rule not found or access denied")`.
    - Handle generic "Server Errors" by raising `HTTPException(status_code=500, detail="Internal server error")`.
8.  **Send Response:** FastAPI serializes the `RuleResponse` model (or error details) into JSON and sends the `200 OK` response (or appropriate error code).

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Enforced by the RLS policy `USING (link_id IN (... WHERE auth.uid() = user_id))` on the `routing_rules` table during the `SELECT`. This prevents fetching rules unless they belong to a link owned by the user. The explicit check on `link_id` in the query adds another layer.
- **Input Validation:** Path parameters `link_id` and `rule_id` are validated for UUID format (`422 Unprocessable Entity`).
- **Information Exposure:** Ensure only necessary fields defined in `RuleResponse` are returned.

## 6. Error Handling

- **`401 Unauthorized`:** Returned by the authentication dependency.
- **`403 Forbidden`:** Implicitly handled by the RLS query filter, resulting in a `404 Not Found`.
- **`404 Not Found`:** Returned if no `routing_rules` record matches the provided `rule_id` AND `link_id` _for the authenticated user_ (due to the query filter and RLS).
- **`422 Unprocessable Entity`:** Returned by FastAPI if `link_id` or `rule_id` are not valid UUIDs.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors (database connection, Supabase client issues, uncaught exceptions). Log details server-side.

## 7. Performance Considerations

- **Database Query:** The `SELECT` query filters on the primary key (`id`) and the foreign key (`link_id`).
  - Filtering by `id` (PK) is very fast.
  - Filtering by `link_id` also benefits from the foreign key index and potentially the composite index `idx_routing_rules_link_id_priority` (though the priority part isn't used for filtering here).
- **RLS:** The RLS policy involves a subquery, but checking against the parent table `routr_links` (filtered by `user_id`) should be efficient with appropriate indexing on `routr_links.user_id`.
- **Mitigation:** Performance is expected to be very good due to filtering on primary/indexed keys.

## 8. Implementation Steps

1.  **Define/Confirm Pydantic Models:** Ensure `RuleResponse` is defined.
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `get_rule_details`) in `RuleService` or `LinkService`.
    - Accept `link_id: UUID`, `rule_id: UUID`, `user_id: UUID` as arguments.
    - Inject the Supabase client.
    - Execute the query: `supabase.table('routing_rules').select('*').eq('id', rule_id).eq('link_id', link_id).maybe_single().execute()`. RLS handles the user ownership check.
    - Wrap the database call in `try...except`.
    - If `response.data` is present, return it.
    - If `response.data` is `None`, raise `NotFoundException`.
    - Handle other potential database/client errors by raising `DatabaseException`.
3.  **Implement Authentication Dependency:** Reuse the existing dependency.
4.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.get("/links/{link_id}/rules/{rule_id}", response_model=RuleResponse)` in `routers/rules.py` (or `routers/links.py`).
    - Use `Path(...)` for both `link_id` and `rule_id`.
    - Inject the `RuleService` (or `LinkService`) and the authentication dependency (`current_user`).
    - Call the service method `service.get_rule_details(link_id=link_id, rule_id=rule_id, user_id=current_user.id)`.
    - Wrap the service call in `try...except`:
      - Catch `NotFoundException` -> `HTTPException(404, "Rule not found or access denied")`.
      - Catch other exceptions -> `HTTPException(500, "Internal server error")`.
    - Return the rule data upon success.
5.  **Register Router:** Ensure the router is included in the main FastAPI app.
6.  **Write Unit/Integration Tests:**
    - Test fetching an existing rule belonging to the user's link.
    - Test fetching a rule that doesn't exist (expect 404).
    - Test fetching a rule where `rule_id` exists but `link_id` does not match (expect 404).
    - Test fetching a rule belonging to a link owned by another user (expect 404).
    - Test without authentication token (expect 401).
    - Test with invalid `link_id` or `rule_id` UUID format (expect 422).
    - (Optional) Mock database errors to test 500 responses.
