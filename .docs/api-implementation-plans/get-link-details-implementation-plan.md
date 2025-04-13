# API Endpoint Implementation Plan: Get Link Details

## 1. Endpoint Overview

This endpoint retrieves the details of a specific `routr_link` identified by its ID. It is intended for authenticated users to view the details of links they own. The endpoint fetches data from the `routr_links` table, respecting Row Level Security policies.

## 2. Request Details

- **Method:** `GET`
- **URL Structure:** `/links/{link_id}`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the routr link to retrieve.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token obtained from Supabase Auth.
- **Request Body:** None

## 3. DTOs and Models

- **Response DTO (Pydantic Model):** `LinkResponse`

  ```python
  # Example definition (place in appropriate models file, e.g., schemas/link.py)
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

      # Add orm_mode if using SQLAlchemy or similar ORMs directly
      # class Config:
      #     orm_mode = True # or from_attributes = True for Pydantic v2+
  ```

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `GET` request at `/links/{link_id}`.
2.  **Authentication:** An authentication dependency (e.g., using `fastapi.Security` and Supabase client) verifies the JWT Bearer token in the `Authorization` header. If invalid or missing, returns `401 Unauthorized`. Extracts the authenticated user's ID (`user_id`).
3.  **Path Parameter Validation:** FastAPI automatically validates that `{link_id}` is a valid UUID format. If not, returns `422 Unprocessable Entity`.
4.  **Call Service Layer:** The endpoint handler calls a method in the `LinkService` (e.g., `get_link_by_id`), passing the validated `link_id` (from path) and the `user_id` (from authentication).
5.  **Database Query (Service Layer):**
    - The `LinkService` uses the `supabase-py` client (or chosen DB interaction layer) to execute a `SELECT` query on the `public.routr_links` table.
    - The query filters by `id = link_id`.
    - Crucially, this query is executed using the user's JWT context, so the RLS policy `USING (auth.uid() = user_id)` is automatically applied by PostgreSQL/Supabase. This ensures only the link owned by the user is returned.
    - The query selects all columns needed for the `LinkResponse` DTO.
6.  **Handle Database Response (Service Layer):**
    - If the query returns exactly one row (link found and owned by the user), the service returns the data (e.g., as a dictionary or directly mapped to the DTO).
    - If the query returns zero rows (link doesn't exist or user doesn't own it), the service signals this (e.g., returns `None` or raises a custom `NotFoundException`).
7.  **Process Service Response (Endpoint Handler):**
    - If the service returns link data, map it to the `LinkResponse` Pydantic model for serialization.
    - If the service signals "Not Found", raise an `HTTPException` with status code `404 Not Found`.
    - Handle any unexpected exceptions from the service layer by raising an `HTTPException` with status code `500 Internal Server Error`.
8.  **Send Response:** FastAPI serializes the `LinkResponse` model (or the error details) into JSON and sends the HTTP response with the appropriate status code (`200 OK`, `404 Not Found`, etc.).

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation. Unauthenticated requests are rejected with `401 Unauthorized`.
- **Authorization:** Enforced primarily by PostgreSQL Row Level Security (RLS) policies on the `routr_links` table (`USING (auth.uid() = user_id)`). The API relies on the database to enforce ownership.
- **Input Validation:** Path parameter `link_id` is validated by FastAPI for UUID format (`422 Unprocessable Entity`). No other user input to validate for this GET request.
- **Information Exposure:** Ensure only necessary fields defined in the `LinkResponse` DTO are returned. Sensitive internal data should not be exposed.

## 6. Error Handling

- **`401 Unauthorized`:** Returned by the authentication dependency if the JWT token is missing, invalid, or expired.
- **`403 Forbidden`:** While technically possible if RLS fails unexpectedly, the intended behavior for unauthorized access (user doesn't own the link) is mapped to `404 Not Found` to avoid revealing the existence of the resource.
- **`404 Not Found`:** Returned if no `routr_links` record matches the provided `link_id` _for the authenticated user_ (due to RLS).
- **`422 Unprocessable Entity`:** Returned by FastAPI if the `link_id` path parameter is not a valid UUID.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors, such as:
  - Database connection issues.
  - Errors during Supabase client interaction.
  - Uncaught exceptions in the service or endpoint logic.
  - Log detailed error information server-side for debugging.

## 7. Performance Considerations

- **Database Query:** The primary performance factor is the database query.
  - The query filters by `id` (primary key), which is inherently very fast.
  - RLS policy adds an implicit `WHERE user_id = auth.uid()`. An index on `user_id` (usually created automatically for Foreign Keys) is beneficial, though less critical than the PK lookup here.
- **Network Latency:** Latency between the API server and the Supabase database instance.
- **Serialization:** Pydantic serialization/deserialization overhead is generally minimal for simple models.
- **Mitigation:** Ensure proper indexing (PK index is sufficient here). For very high load (beyond MVP scope), consider caching strategies if reads become frequent for the same links, but this is not needed initially.

## 8. Implementation Steps

1.  **Define Pydantic Response Model:** Create the `LinkResponse` class in `schemas/link.py` (or your chosen location) matching the API specification.
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `get_link_by_id`) within a `LinkService` class (or module `services/link_service.py`).
    - This method should accept `link_id: UUID` and `user_id: UUID` as arguments.
    - Inject the Supabase client instance into the service.
    - Implement the `supabase.table('routr_links').select('*').eq('id', link_id).maybe_single().execute()` query. _Note: `maybe_single()` combined with RLS handles both finding the specific link and checking ownership implicitly._
    - If `response.data` is present, return it.
    - If `response.data` is `None`, return `None` or raise a custom `NotFoundException`.
    - Include basic error handling for Supabase client exceptions.
3.  **Implement Authentication Dependency:**
    - Create a FastAPI dependency (e.g., in `auth/dependencies.py`) that:
      - Expects an `Authorization: Bearer <token>` header.
      - Uses the Supabase client (`supabase.auth.get_user(token)`) to validate the token.
      - If valid, returns the `User` object (or just the `user.id` as `UUID`).
      - If invalid/missing, raises an `HTTPException(status_code=401, detail="Not authenticated")`.
4.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.get("/links/{link_id}", response_model=LinkResponse)` within an `APIRouter` (e.g., in `routers/links.py`).
    - Use `Path(...)` for the `link_id` parameter to specify it comes from the path.
    - Inject the `LinkService` and the authentication dependency (`current_user: User = Depends(get_current_user)`).
    - Call `link_service.get_link_by_id(link_id=link_id, user_id=current_user.id)`.
    - Check the service response:
      - If data is returned, return the data (FastAPI will validate against `LinkResponse`).
      - If `None` (or `NotFoundException` is raised), raise `HTTPException(status_code=404, detail="Link not found")`.
    - Wrap the service call in a `try...except` block to catch potential Supabase/database errors and raise `HTTPException(status_code=500, detail="Internal server error")`.
5.  **Register Router:** Ensure the `APIRouter` containing the endpoint is included in the main FastAPI application instance.
6.  **Write Unit/Integration Tests:**
    - Test the endpoint with a valid token and correct `link_id`.
    - Test with a valid token but `link_id` belonging to another user (should return 404).
    - Test with a valid token but non-existent `link_id` (should return 404).
    - Test with an invalid or missing token (should return 401).
    - Test with an invalid UUID format for `link_id` (should return 422).
    - (Optional) Mock database errors to test 500 responses.
