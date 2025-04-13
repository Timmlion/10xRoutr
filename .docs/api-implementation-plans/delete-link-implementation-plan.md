# API Endpoint Implementation Plan: Delete Link

## 1. Endpoint Overview

This endpoint allows an authenticated user to permanently delete a `routr_link` they own. Deleting a link will also automatically delete all associated `routing_rules` due to the `ON DELETE CASCADE` constraint defined on the foreign key in the `routing_rules` table. The endpoint returns no content upon successful deletion.

## 2. Request Details

- **Method:** `DELETE`
- **URL Structure:** `/links/{link_id}`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the routr link to delete.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
- **Request Body:** None

## 3. DTOs and Models

- **Request DTO:** None
- **Response DTO:** None (Response body is empty on success)

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `DELETE` request at `/links/{link_id}`.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Path Parameter Validation:** FastAPI validates that `link_id` is a valid UUID format. If not, returns `422 Unprocessable Entity`.
4.  **Call Service Layer:** The endpoint handler calls a method in the `LinkService` (e.g., `delete_link`), passing the validated `link_id` and the `user_id`.
5.  **Database Query (Service Layer):**
    - The `LinkService` uses the `supabase-py` client.
    - Execute a `DELETE` query on the `public.routr_links` table.
    - The `DELETE` query targets the row `WHERE id = link_id`.
    - The RLS policy `USING (auth.uid() = user_id)` ensures that the user can only attempt to delete their own link. The database will prevent deletion if the `user_id` does not match `auth.uid()`.
6.  **Handle Database Response (Service Layer):**
    - Check the result of the `DELETE` operation. The Supabase client might indicate how many rows were affected.
    - If the `DELETE` affected exactly one row, the operation was successful (the link existed and was owned by the user). Signal success.
    - If the `DELETE` affected zero rows, it means the link either didn't exist or was not owned by the user (due to the RLS policy). Signal "Not Found".
    - Catch potential database errors (e.g., connection issues) and signal a generic "Server Error".
7.  **Process Service Response (Endpoint Handler):**
    - If the service signals success, return an empty response with status code `204 No Content`.
    - If the service signals "Not Found", raise `HTTPException(status_code=404, detail="Link not found")`.
    - Handle generic "Server Errors" by raising `HTTPException(status_code=500, detail="Internal server error")`.
8.  **Send Response:** FastAPI sends the HTTP response with the appropriate status code (`204 No Content`, `404 Not Found`, etc.).

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Enforced primarily by the RLS `USING (auth.uid() = user_id)` policy on the `DELETE` operation. This is the critical security mechanism preventing users from deleting others' links.
- **Input Validation:** Path parameter `link_id` is validated by FastAPI for UUID format (`422 Unprocessable Entity`).
- **Cascade Effects:** Be aware that the `ON DELETE CASCADE` constraint on `routing_rules.link_id` means deleting a link permanently removes all its associated rules. This is intended behavior but should be clearly understood.

## 6. Error Handling

- **`401 Unauthorized`:** Returned by the authentication dependency.
- **`403 Forbidden`:** Similar to `Update Link`, RLS prevents the action, but the practical result (0 rows affected) is usually mapped to `404 Not Found` to avoid confirming the resource's existence to an unauthorized user.
- **`404 Not Found`:** Returned if no `routr_links` record matches the provided `link_id` _for the authenticated user_ (i.e., the delete operation affected 0 rows because the link didn't exist or wasn't owned by the user).
- **`422 Unprocessable Entity`:** Returned by FastAPI if `link_id` is not a valid UUID.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors (database connection, Supabase client issues, unexpected errors during delete, uncaught exceptions). Log details server-side.

## 7. Performance Considerations

- **Database Query:** The `DELETE` operation targets a primary key (`id`) and is generally very fast.
- **Cascading Deletes:** The performance impact of the `ON DELETE CASCADE` depends on the number of associated `routing_rules`. Deleting a link with many rules will take longer than deleting one with few or none. For MVP, this is unlikely to be a bottleneck.
- **Indexing:** The primary key index on `id` is used. The index on `user_id` helps the RLS check.
- **Locking:** `DELETE` acquires row-level locks. The cascade operation might lock related rows in `routing_rules` briefly. Not expected to be an issue in MVP.

## 8. Implementation Steps

1.  **Define Pydantic Models:** No specific request or response DTOs are needed for this endpoint.
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `delete_link`) within `LinkService`.
    - Accept `link_id: UUID` and `user_id: UUID` as arguments.
    - Inject the Supabase client.
    - Execute the delete query: `supabase.table('routr_links').delete().eq('id', link_id).execute()`. _Note: RLS handles the user_id check implicitly._
    - Check the response from the Supabase client. Verify if the `count` (or equivalent indicator) of deleted rows is 1.
    - If `count` is 1, return `True` (or signal success).
    - If `count` is 0, raise `NotFoundException`.
    - Wrap the database call in `try...except` to catch potential database/client errors and raise a generic `DatabaseException`.
3.  **Implement Authentication Dependency:** Reuse the existing dependency.
4.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)` in `routers/links.py`.
    - Use `Path(...)` for the `link_id` parameter.
    - Inject the `LinkService` and the authentication dependency (`current_user`).
    - Call `link_service.delete_link(link_id=link_id, user_id=current_user.id)`.
    - Wrap the service call in a `try...except` block:
      - Catch `NotFoundException` and raise `HTTPException(status_code=404, detail="Link not found")`.
      - Catch other exceptions and raise `HTTPException(status_code=500, detail="Internal server error")`.
    - If the service call completes without exceptions, FastAPI will automatically return the `204 No Content` response because no value is explicitly returned from the handler.
5.  **Register Router:** Ensure the router is included in the main FastAPI app.
6.  **Write Unit/Integration Tests:**
    - Test deleting a link successfully (verify 204 status and check if the link and its rules are gone from the DB).
    - Test deleting a link that doesn't exist (expect 404).
    - Test deleting a link owned by another user (expect 404).
    - Test without authentication token (expect 401).
    - Test with an invalid `link_id` UUID format (expect 422).
    - (Optional) Mock database errors to test 500 responses.
