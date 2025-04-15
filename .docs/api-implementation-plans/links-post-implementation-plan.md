# API Endpoint Implementation Plan: Create Link

## 1. Endpoint Overview

This endpoint allows an authenticated user to create a new `routr_link`. It accepts the desired unique alias and an optional default URL, validates the input, inserts a new record into the `routr_links` table associated with the authenticated user, and returns the details of the newly created link.

## 2. Request Details

- **Method:** `POST`
- **URL Structure:** `/links`
- **Parameters:**
  - **Path Parameters:** None
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token obtained from Supabase Auth.
    - `Content-Type: application/json` (Required)
- **Request Body:** Required (JSON payload)
  ```json
  {
    "alias": "string (required, unique, 3-64 chars, ^[a-z0-9-]+$)",
    "default_url": "string (optional, valid URL format or null)"
  }
  ```

## 3. DTOs and Models

- **Request DTO (Pydantic Model):** `LinkCreate`

  ```python
  # Example definition (place in appropriate models file, e.g., schemas/link.py)
  from pydantic import BaseModel, field_validator, Field
  from typing import Optional
  import re

  class LinkCreate(BaseModel):
      alias: str = Field(..., min_length=3, max_length=64)
      default_url: Optional[str] = None

      @field_validator('alias')
      def validate_alias_format(cls, v):
          if not re.match(r'^[a-z0-9-]+$', v):
              raise ValueError('Alias must contain only lowercase letters, numbers, and hyphens')
          return v

      @field_validator('default_url')
      def validate_default_url(cls, v):
          if v is not None and not (v.startswith('http://') or v.startswith('https://')):
               # Basic check, consider using a more robust URL validation library if needed
              raise ValueError('Invalid URL format for default_url')
          return v
  ```

- **Response DTO (Pydantic Model):** `LinkResponse` (Reuse from Get Link Details)

  ```python
  # Example definition (reuse from Get Link Details)
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
      #     orm_mode = True # or from_attributes = True for Pydantic v2+
  ```

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `POST` request at `/links` with a JSON payload.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid or missing, returns `401 Unauthorized`. Extracts the authenticated user's ID (`user_id`).
3.  **Request Body Validation:** FastAPI automatically validates the incoming JSON payload against the `LinkCreate` Pydantic model.
    - Checks for required fields (`alias`).
    - Validates types.
    - Runs custom validators (`validate_alias_format`, `validate_default_url`).
    - If validation fails, returns `422 Unprocessable Entity` with details.
4.  **Call Service Layer:** The endpoint handler calls a method in the `LinkService` (e.g., `create_link`), passing the validated data from the `LinkCreate` model and the `user_id`.
5.  **Database Query (Service Layer):**
    - The `LinkService` uses the `supabase-py` client to execute an `INSERT` query on the `public.routr_links` table.
    - The data to be inserted includes `alias`, `default_url`, and crucially, the `user_id` obtained from the authenticated user's token. Other fields like `id`, `total_clicks`, `created_at`, `updated_at` will use their default database values.
    - The RLS policy `WITH CHECK (auth.uid() = user_id)` ensures that the `user_id` being inserted matches the authenticated user.
    - The database's `UNIQUE` constraint on the `alias` column handles checking for duplicates.
6.  **Handle Database Response (Service Layer):**
    - If the `INSERT` is successful, the database returns the newly created row (including the generated `id`, `created_at`, etc.). The service layer returns this data.
    - If the `INSERT` fails due to the `UNIQUE` constraint violation on `alias`, the Supabase client will likely raise a specific database error (e.g., `IntegrityError` with code `23505`). The service layer should catch this specific error and signal an "Alias Conflict".
    - If the `INSERT` fails due to other constraint violations (e.g., `CHECK` on `alias` format, although Pydantic should catch this first), it should signal a "Bad Request".
    - Catch other potential database errors and signal a generic "Server Error".
7.  **Process Service Response (Endpoint Handler):**
    - If the service returns the newly created link data, map it to the `LinkResponse` DTO.
    - If the service signals "Alias Conflict", raise an `HTTPException` with status code `409 Conflict`.
    - If the service signals "Bad Request" (due to DB constraint failure missed by Pydantic), raise `HTTPException(status_code=400, detail="Invalid input data violating database constraints")`.
    - Handle generic "Server Errors" by raising `HTTPException(status_code=500, detail="Internal server error")`.
8.  **Send Response:** FastAPI serializes the `LinkResponse` model (or the error details) into JSON and sends the HTTP response with the appropriate status code (`201 Created`, `409 Conflict`, etc.).

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Enforced by the RLS `WITH CHECK (auth.uid() = user_id)` policy during `INSERT`. This prevents a user from creating a link attributed to another user.
- **Input Validation:** Thorough validation performed by the `LinkCreate` Pydantic model (required fields, types, format checks via validators). Database constraints provide a secondary check.
- **CSRF Protection:** While less critical for stateless APIs using JWT Bearer tokens, ensure no session-based authentication mechanisms are inadvertently used that could be vulnerable.
- **Unique Constraint Handling:** Explicitly handle the unique constraint violation for the `alias` field to provide a clear `409 Conflict` error instead of a generic `500`.

## 6. Error Handling

- **`400 Bad Request`:** Returned if database `CHECK` constraints fail (though Pydantic should catch most format issues earlier). Can also be used if custom business logic validation fails within the service layer.
- **`401 Unauthorized`:** Returned by the authentication dependency if the JWT token is missing, invalid, or expired.
- **`409 Conflict`:** Returned specifically when the database `UNIQUE` constraint on the `alias` column is violated during the `INSERT` operation.
- **`422 Unprocessable Entity`:** Returned by FastAPI automatically if the request body fails validation against the `LinkCreate` Pydantic model (e.g., missing `alias`, invalid `alias` format/length, invalid `default_url` format).
- **`500 Internal Server Error`:** Returned for unexpected server-side errors, such as:
  - Database connection issues.
  - Unexpected errors during Supabase client interaction (other than unique constraint violation).
  - Uncaught exceptions in the service or endpoint logic.
  - Log detailed error information server-side.

## 7. Performance Considerations

- **Database Query:** The main operation is an `INSERT`. Performance depends on:
  - The efficiency of the `UNIQUE` constraint check on the `alias` column (supported by `idx_routr_links_alias`).
  - The overhead of applying RLS policies (generally minimal for simple checks).
  - Overall database load.
- **Mitigation:** The `UNIQUE` constraint is necessary for correctness. Ensure the index on `alias` is present. For extremely high insert rates (beyond MVP scope), more advanced database tuning or alternative unique ID generation strategies might be considered, but this is unlikely to be an issue initially.

## 8. Implementation Steps

1.  **Define Pydantic Models:** Create/Confirm the `LinkCreate` and `LinkResponse` models in `schemas/link.py` (or equivalent).
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `create_link`) within `LinkService`.
    - Accept `link_data: LinkCreate` and `user_id: UUID` as arguments.
    - Inject the Supabase client instance.
    - Prepare the data dictionary for insertion, including `alias`, `default_url`, and `user_id`.
    - Implement the `supabase.table('routr_links').insert(data_dict).execute()` query. Use `.single()` if Supabase client v2+ returns the inserted row by default upon request, or perform a select after insert if needed to get the full object for the response.
    - Wrap the database call in a `try...except` block.
      - Specifically catch the database error corresponding to a unique constraint violation (e.g., `psycopg2.errors.UniqueViolation` or equivalent error from the Supabase client, often wrapping a `PostgrestAPIError` with code `23505`). If caught, raise a custom `AliasConflictException`.
      - Catch other potential database/client errors and raise a generic `DatabaseException`.
    - If successful, return the data of the newly created link.
3.  **Implement Authentication Dependency:** Reuse the dependency created for `Get Link Details`.
4.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.post("/links", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)` in `routers/links.py`.
    - The function should accept the request body, automatically validated into a `link_data: LinkCreate` object by FastAPI.
    - Inject the `LinkService` and the authentication dependency (`current_user: User = Depends(get_current_user)`).
    - Call `link_service.create_link(link_data=link_data, user_id=current_user.id)`.
    - Wrap the service call in a `try...except` block:
      - Catch `AliasConflictException` and raise `HTTPException(status_code=409, detail="Alias already exists")`.
      - Catch other potential service-level/database exceptions and raise `HTTPException(status_code=500, detail="Internal server error")`.
    - If the service call is successful, return the created link data (FastAPI will serialize it).
5.  **Register Router:** Ensure the `APIRouter` is included in the main FastAPI app.
6.  **Write Unit/Integration Tests:**
    - Test successful link creation with and without `default_url`.
    - Test creation with an alias that already exists (expect 409).
    - Test creation with invalid alias format/length (expect 422 from Pydantic).
    - Test creation with invalid `default_url` format (expect 422 from Pydantic).
    - Test without authentication token (expect 401).
    - (Optional) Mock database errors to test 500 responses.
