# API Endpoint Implementation Plan: Delete Rule

## 1. Endpoint Overview

This endpoint allows an authenticated user to permanently delete a specific `routing_rule` associated with one of their `routr_link` resources. Both the parent link ID and the rule ID are required for identification and authorization. The endpoint returns no content upon successful deletion.

## 2. Request Details

- **Method:** `DELETE`
- **URL Structure:** `/links/{link_id}/rules/{rule_id}`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the parent `routr_link`.
    - `rule_id` (UUID, Required): The unique identifier of the `routing_rule` to delete.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
- **Request Body:** None

## 3. DTOs and Models

- **Request DTO:** None
- **Response DTO:** None (Response body is empty on success)

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `DELETE` request at `/links/{link_id}/rules/{rule_id}`.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Path Parameter Validation:** FastAPI validates that both `link_id` and `rule_id` are valid UUID formats. If not, returns `422 Unprocessable Entity`.
4.  **Call Service Layer:** The endpoint handler calls a method in the `RuleService` (or `LinkService`, e.g., `delete_rule`), passing `link_id`, `rule_id`, and `user_id`.
5.  **Database Query (Service Layer):**
    - The `RuleService` uses the `supabase-py` client.
    - Execute a `DELETE` query on the `public.routing_rules` table.
    - The `DELETE` query targets the row `WHERE id = rule_id AND link_id = link_id`.
    - The RLS policy `USING (link_id IN (... WHERE auth.uid() = user_id))` ensures the user can only attempt to delete rules belonging to their own links. The explicit `link_id = link_id` condition in the `WHERE` clause adds a specific check that the rule belongs to the _specified_ parent link.
6.  **Handle Database Response (Service Layer):**
    - Check the result of the `DELETE` operation (e.g., number of rows affected).
    - If the `DELETE` affected exactly one row, signal success.
    - If the `DELETE` affected zero rows, it means the rule didn't exist, the `link_id` didn't match, or the user didn't own the parent link (due to RLS). Signal "Not Found".
    - Catch potential database errors and signal "Server Error".
7.  **Process Service Response (Endpoint Handler):**
    - If the service signals success, return an empty response with status code `204 No Content`.
    - If the service signals "Not Found", raise `HTTPException(status_code=404, detail="Rule not found or access denied")`.
    - Handle generic "Server Errors" by raising `HTTPException(status_code=500, detail="Internal server error")`.
8.  **Send Response:** FastAPI sends the HTTP response with the appropriate status code (`204 No Content`, `404 Not Found`, etc.).

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Enforced primarily by the RLS `USING (link_id IN (... WHERE auth.uid() = user_id))` policy on the `DELETE` operation. The explicit `link_id = link_id` check in the `WHERE` clause prevents deleting a rule using the correct `rule_id` but the wrong `link_id` path parameter (even if both belong to the user).
- **Input Validation:** Path parameters `link_id` and `rule_id` are validated for UUID format (`422 Unprocessable Entity`).

## 6. Error Handling

- **`401 Unauthorized`:** Returned by the authentication dependency.
- **`403 Forbidden`:** Implicitly handled by RLS/query filter, resulting in `404 Not Found`.
- **`404 Not Found`:** Returned if no `routing_rules` record matches the provided `rule_id` AND `link_id` _for the authenticated user_ (i.e., the delete operation affected 0 rows).
- **`422 Unprocessable Entity`:** Returned by FastAPI if `link_id` or `rule_id` are not valid UUIDs.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors (database connection, Supabase client issues, uncaught exceptions). Log details server-side.

## 7. Performance Considerations

- **Database Query:** The `DELETE` operation targets the primary key (`id`) and includes a filter on the foreign key (`link_id`). This is generally very fast due to indexes.
- **Indexing:** Primary key index on `id` and the FK index on `link_id` are used.
- **Locking:** `DELETE` acquires a row-level lock briefly. Not expected to be an issue.

## 8. Implementation Steps

1.  **Define Pydantic Models:** None needed for request/response.
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `delete_rule`) in `RuleService` or `LinkService`.
    - Accept `link_id: UUID`, `rule_id: UUID`, `user_id: UUID` as arguments.
    - Inject the Supabase client.
    - Execute the delete query: `supabase.table('routing_rules').delete().eq('id', rule_id).eq('link_id', link_id).execute()`. RLS handles the user ownership implicitly via the `link_id` check.
    - Check the response count. If 1, return `True`. If 0, raise `NotFoundException`.
    - Wrap in `try...except` for database errors (`DatabaseException`).
3.  **Implement Authentication Dependency:** Reuse existing dependency.
4.  **Create FastAPI Endpoint Handler:**
    - Define `@router.delete("/links/{link_id}/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)` in `routers/rules.py`.
    - Use `Path(...)` for `link_id` and `rule_id`.
    - Inject the service and authentication dependency (`current_user`).
    - Call `service.delete_rule(link_id=link_id, rule_id=rule_id, user_id=current_user.id)`.
    - Wrap service call in `try...except`:
      - Catch `NotFoundException` -> `HTTPException(404, "Rule not found or access denied")`.
      - Catch other exceptions -> `HTTPException(500, "Internal server error")`.
    - If successful, the handler implicitly returns `204 No Content`.
5.  **Register Router:** Include the router in the main app.
6.  **Write Unit/Integration Tests:**
    - Test deleting an existing rule successfully (verify 204 status, check DB).
    - Test deleting a rule that doesn't exist (expect 404).
    - Test deleting a rule with correct `rule_id` but wrong `link_id` (expect 404).
    - Test deleting a rule belonging to another user's link (expect 404).
    - Test without authentication token (expect 401).
    - Test with invalid `link_id` or `rule_id` UUID format (expect 422).
    - (Optional) Mock database errors to test 500 responses.
