# API Endpoint Implementation Plan: Update Link

## 1. Endpoint Overview

This endpoint allows an authenticated user to update specific mutable details of a `routr_link` they own. For the MVP, the only updatable field is the `default_url`. The link's `alias` cannot be changed via this endpoint. The endpoint uses the `PATCH` method for partial updates.

## 2. Request Details

- **Method:** `PATCH`
- **URL Structure:** `/links/{link_id}`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the routr link to update.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
    - `Content-Type: application/json` (Required)
- **Request Body:** Required (JSON payload)
  ```json
  {
    "default_url": "string | null (optional, valid URL format or null to clear)"
    // Only include fields intended for update. Alias is never included.
  }
  ```

## 3. DTOs and Models

- **Request DTO (Pydantic Model):** `LinkUpdate`

  ```python
  # Example definition (place in schemas/link.py)
  from pydantic import BaseModel, field_validator
  from typing import Optional

  class LinkUpdate(BaseModel):
      # Make all fields optional for PATCH semantics
      default_url: Optional[str | None] = None # Allows explicitly setting to null

      # Reuse validator from LinkCreate if applicable
      @field_validator('default_url')
      def validate_default_url(cls, v):
          # Allow None to clear the value
          if v is not None and not (v.startswith('http://') or v.startswith('https://')):
              raise ValueError('Invalid URL format for default_url')
          return v
  ```

- **Response DTO (Pydantic Model):** `LinkResponse` (Reuse from Get/Create Link)

  ```python
  # Example definition (reuse)
  from pydantic import BaseModel, UUID4
  from datetime import datetime
  from typing import Optional

  class LinkResponse(BaseModel):
      id: UUID4
      user_id: UUID4
      alias: str
      default_url: Optional[str]
      total_clicks: int
      created_at: datetime
      updated_at: datetime
      # class Config:
      #     orm_mode = True # or from_attributes = True
  ```

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `PATCH` request at `/links/{link_id}` with a JSON payload.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Path Parameter Validation:** FastAPI validates `link_id` is a valid UUID. If not, returns `422 Unprocessable Entity`.
4.  **Request Body Validation:** FastAPI validates the incoming JSON payload against the `LinkUpdate` Pydantic model.
    - Validates types and format of provided fields (e.g., `default_url`).
    - If validation fails, returns `422 Unprocessable Entity`.
5.  **Call Service Layer:** The endpoint handler calls a method in the `LinkService` (e.g., `update_link`), passing the `link_id`, the validated update data (`LinkUpdate` model), and the `user_id`.
6.  **Database Query (Service Layer):**
    - The `LinkService` uses the `supabase-py` client.
    - **Crucially, it first needs to verify ownership and existence.** A common pattern is to fetch the link first using `SELECT` with the RLS filter (`id = link_id AND user_id = auth.uid()`). If not found, raise `NotFoundException`.
    - If the link exists and belongs to the user, execute an `UPDATE` query on the `public.routr_links` table.
    - The `UPDATE` query targets the row `WHERE id = link_id`. The RLS policy `USING (auth.uid() = user_id)` further ensures the user can only update their own link.
    - Set the `default_url` column to the value provided in the `LinkUpdate` data. The `updated_at` column will be updated automatically by the database trigger.
    - The `UPDATE` query should ideally return the updated row data.
7.  **Handle Database Response (Service Layer):**
    - If the initial fetch fails (link not found or not owned), raise `NotFoundException`.
    - If the `UPDATE` is successful, return the updated link data.
    - If the `UPDATE` fails due to database constraints (e.g., unexpected `CHECK` failure on `default_url`, though Pydantic should catch format errors), signal a "Bad Request".
    - Catch other potential database errors and signal a generic "Server Error".
8.  **Process Service Response (Endpoint Handler):**
    - If the service returns the updated link data, map it to the `LinkResponse` DTO.
    - If the service raises `NotFoundException`, raise `HTTPException(status_code=404, detail="Link not found")`.
    - If the service signals "Bad Request", raise `HTTPException(status_code=400, detail="Invalid data causing database constraint violation")`.
    - Handle generic "Server Errors" by raising `HTTPException(status_code=500, detail="Internal server error")`.
9.  **Send Response:** FastAPI serializes the `LinkResponse` model (or error details) into JSON and sends the `200 OK` response (or appropriate error code).

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Enforced primarily by the RLS `USING (auth.uid() = user_id)` policy on the `UPDATE` operation. The initial check/fetch in the service layer provides an additional safeguard.
- **Input Validation:** Performed by the `LinkUpdate` Pydantic model. Validates the format of `default_url` if provided. Database `CHECK` constraint provides a secondary check.
- **Mass Assignment:** By using a specific `LinkUpdate` DTO with only mutable fields (and only `default_url` in MVP), we prevent users from accidentally or maliciously updating immutable fields like `id`, `user_id`, `alias`, `created_at`, or internal counters like `total_clicks`.
- **CSRF Protection:** As with other endpoints, ensure statelessness.

## 6. Error Handling

- **`400 Bad Request`:** Returned if `default_url` violates database constraints (unlikely if Pydantic validation is correct).
- **`401 Unauthorized`:** Returned by the authentication dependency.
- **`403 Forbidden`:** While RLS handles ownership, if the initial check pattern isn't used in the service, RLS might prevent the update without explicitly returning a specific error code that translates easily to 403. Mapping "not found for user" to 404 is generally preferred.
- **`404 Not Found`:** Returned if no `routr_links` record matches the provided `link_id` _for the authenticated user_.
- **`422 Unprocessable Entity`:** Returned by FastAPI if the request body fails validation against `LinkUpdate` (e.g., invalid `default_url` format) or if `link_id` is not a valid UUID.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors (database connection, Supabase client issues, uncaught exceptions). Log details server-side.

## 7. Performance Considerations

- **Database Queries:** Typically involves one `SELECT` (to verify existence/ownership) and one `UPDATE` query targeting a primary key (`id`). Both are generally fast.
- **Indexing:** The primary key index on `id` is crucial. The index on `user_id` helps the RLS check during the initial `SELECT`.
- **Locking:** A standard `UPDATE` acquires a row-level lock, which is acceptable. Avoid long-running transactions holding locks.
- **Mitigation:** Performance is unlikely to be an issue for this endpoint in MVP. Ensure PK index exists.

## 8. Implementation Steps

1.  **Define Pydantic Models:** Create/Confirm the `LinkUpdate` and `LinkResponse` models in `schemas/link.py`.
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `update_link`) in `LinkService`.
    - Accept `link_id: UUID`, `update_data: LinkUpdate`, and `user_id: UUID` as arguments.
    - Inject the Supabase client.
    - _(Optional but Recommended)_ Perform an initial query to check if the link exists and belongs to the user: `supabase.table('routr_links').select('id').eq('id', link_id).eq('user_id', user_id).maybe_single().execute()`. If not found (`response.data` is None), raise `NotFoundException`.
    - Prepare the `data_to_update` dictionary from `update_data`, excluding fields that were not provided (Pydantic's `model_dump(exclude_unset=True)` is useful here).
    - If `data_to_update` is empty (user sent an empty PATCH body), consider returning the current link state without performing an update or returning a specific response/error.
    - Execute the update: `supabase.table('routr_links').update(data_to_update).eq('id', link_id).execute()`. Request the updated row be returned if the client supports it (check `supabase-py` docs).
    - If the update response doesn't include the full updated row, perform a subsequent `SELECT` query (similar to the initial check) to fetch the updated state.
    - Wrap database calls in `try...except` blocks, handling potential errors (database constraint errors -> `BadRequestException`, other errors -> `DatabaseException`).
    - Return the updated link data.
3.  **Implement Authentication Dependency:** Reuse the existing dependency.
4.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.patch("/links/{link_id}", response_model=LinkResponse)` in `routers/links.py`.
    - Accept `link_id: UUID` from the path and `update_data: LinkUpdate` from the request body.
    - Inject the `LinkService` and the authentication dependency (`current_user`).
    - Call `link_service.update_link(link_id=link_id, update_data=update_data, user_id=current_user.id)`.
    - Wrap the service call in a `try...except` block:
      - Catch `NotFoundException` and raise `HTTPException(status_code=404, detail="Link not found")`.
      - Catch `BadRequestException` and raise `HTTPException(status_code=400, detail="Invalid update data")`.
      - Catch other exceptions and raise `HTTPException(status_code=500, detail="Internal server error")`.
    - If successful, return the updated link data.
5.  **Register Router:** Include the router in the main FastAPI app.
6.  **Write Unit/Integration Tests:**
    - Test updating `default_url` successfully.
    - Test setting `default_url` to `null`.
    - Test sending an empty PATCH body (decide expected behavior - no update or error?).
    - Test updating a link that doesn't exist (expect 404).
    - Test updating a link owned by another user (expect 404).
    - Test with an invalid `default_url` format (expect 422 from Pydantic).
    - Test without authentication token (expect 401).
    - Test with invalid `link_id` UUID format (expect 422).
    - (Optional) Mock database errors to test 500 responses.
