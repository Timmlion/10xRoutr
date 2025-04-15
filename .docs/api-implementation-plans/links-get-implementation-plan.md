# API Endpoint Implementation Plan: List Links

## 1. Endpoint Overview

This endpoint retrieves a paginated list of `routr_link` resources owned by the currently authenticated user. It allows clients (including potentially HTMX-driven frontend components) to fetch links in manageable chunks.

## 2. Request Details

- **Method:** `GET`
- **URL Structure:** `/links`
- **Parameters:**
  - **Path Parameters:** None
  - **Query Parameters:**
    - `page` (integer, Optional, Default: 1): Specifies the page number to retrieve. Must be >= 1.
    - `page_size` (integer, Optional, Default: 20): Specifies the maximum number of links per page. Should have a reasonable upper limit (e.g., 100).
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
- **Request Body:** None

## 3. DTOs and Models

- **Response Item DTO (Pydantic Model):** `LinkResponse` (Reuse from Get/Create Link)

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

- **Paginated Response DTO (Pydantic Model):** `PaginatedLinkResponse`

  ```python
  # Example definition (place in appropriate models file, e.g., schemas/pagination.py or schemas/link.py)
  from pydantic import BaseModel
  from typing import List

  class PaginatedLinkResponse(BaseModel):
      items: List[LinkResponse]
      total: int # Total number of items available across all pages
      page: int
      page_size: int
  ```

- **Query Parameter Model (Pydantic Model for dependency injection/validation):** `PaginationParams` (Optional but good practice)

  ```python
  # Example definition (place in e.g., dependencies.py or utils.py)
  from pydantic import BaseModel, Field

  class PaginationParams(BaseModel):
      page: int = Field(1, ge=1) # Default 1, must be >= 1
      page_size: int = Field(20, ge=1, le=100) # Default 20, range 1-100
  ```

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `GET` request at `/links`.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Query Parameter Validation:**
    - FastAPI (potentially using the `PaginationParams` dependency) validates `page` and `page_size` query parameters. Checks if they are integers and within allowed ranges (e.g., `page >= 1`, `1 <= page_size <= 100`).
    - If validation fails, return `400 Bad Request` (or `422 Unprocessable Entity` depending on FastAPI's handling).
4.  **Calculate Offset:** Calculate the database query offset based on validated `page` and `page_size`: `offset = (page - 1) * page_size`.
5.  **Call Service Layer:** The endpoint handler calls a method in the `LinkService` (e.g., `get_links_paginated`), passing the `user_id`, calculated `offset`, and `page_size` (limit).
6.  **Database Queries (Service Layer):**
    - The `LinkService` uses the `supabase-py` client.
    - **Query 1 (Items):** Execute a `SELECT` query on `public.routr_links`.
      - Filter by `user_id = auth.uid()` (implicitly handled by RLS).
      - Apply `LIMIT page_size`.
      - Apply `OFFSET offset`.
      - Optionally add an `ORDER BY` clause (e.g., `created_at DESC`) for consistent ordering.
    - **Query 2 (Total Count):** Execute a `SELECT count(*)` query on `public.routr_links`.
      - Filter by `user_id = auth.uid()` (implicitly handled by RLS).
      - _Optimization Note:_ Supabase/PostgREST might provide a way to get the total count alongside the limited items in a single request to avoid a separate count query (e.g., using range headers or specific functions). Investigate Supabase client capabilities for this. If not easily available, two queries are acceptable for MVP.
7.  **Handle Database Response (Service Layer):**
    - Collect the list of link items from Query 1.
    - Get the total count from Query 2 (or the combined response).
    - Return the list of items and the total count. Handle potential database errors.
8.  **Process Service Response (Endpoint Handler):**
    - If the service returns the items and total count successfully:
      - Construct the `PaginatedLinkResponse` object using the retrieved `items`, `total`, and the input `page` and `page_size`.
    - Handle any unexpected exceptions from the service layer by raising `HTTPException(status_code=500, detail="Internal server error")`.
9.  **Send Response:** FastAPI serializes the `PaginatedLinkResponse` model into JSON and sends the `200 OK` response.
    - **HTMX Consideration:** If the request contains specific HTMX headers (e.g., `HX-Request: true`), the endpoint could alternatively be designed to detect this and return an HTML fragment rendered using Jinja2 (containing only the `<li>` items for the list) instead of the JSON response. This requires conditional logic in the endpoint handler. For this plan, we assume JSON response by default.

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Enforced by RLS policy `USING (auth.uid() = user_id)` on `routr_links` table for both the item query and the count query. Ensures users only see their own links.
- **Input Validation:** Query parameters (`page`, `page_size`) are validated for type and range to prevent excessively large requests or invalid inputs (`400 Bad Request` / `422 Unprocessable Entity`). Impose a maximum `page_size`.
- **Denial of Service (DoS):** Limiting `page_size` helps mitigate potential DoS attacks attempting to retrieve excessively large amounts of data.

## 6. Error Handling

- **`400 Bad Request` / `422 Unprocessable Entity`:** Returned if `page` or `page_size` query parameters are invalid (e.g., not integers, outside allowed range).
- **`401 Unauthorized`:** Returned by the authentication dependency if the JWT token is missing, invalid, or expired.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors, such as:
  - Database connection issues.
  - Errors during Supabase client interaction (fetching items or count).
  - Uncaught exceptions in the service or endpoint logic.
  - Log detailed error information server-side.

## 7. Performance Considerations

- **Database Queries:** Two queries (one for items, one for count) might be executed per request if the Supabase client doesn't support fetching both efficiently at once.
  - The item query uses `LIMIT` and `OFFSET`, which can become less efficient on very large tables with high `OFFSET` values (large page numbers). However, for typical user link counts in MVP, this is unlikely to be a significant issue.
  - The `COUNT(*)` query also needs to scan based on the `user_id` filter (RLS).
- **Indexing:** An index on `user_id` (usually automatic for FK) is important for filtering in both queries. The optional `ORDER BY` clause should ideally use an indexed column (like `created_at`).
- **Mitigation:**
  - Investigate Supabase client/PostgREST features for efficient count retrieval alongside limited results.
  - Keep the maximum `page_size` reasonable (e.g., 100).
  - Ensure appropriate database indexes exist.
  - For future scaling (post-MVP), consider keyset pagination (cursor-based) instead of offset-based pagination if performance with large offsets becomes an issue.

## 8. Implementation Steps

1.  **Define/Confirm Pydantic Models:** Ensure `LinkResponse` and `PaginatedLinkResponse` are defined. Optionally define `PaginationParams`.
2.  **Create Service Layer Method:**
    - Define a function/method (e.g., `get_links_paginated`) in `LinkService`.
    - Accept `user_id: UUID`, `offset: int`, `limit: int` (page_size) as arguments.
    - Inject the Supabase client.
    - Implement the database query to fetch items: `supabase.table('routr_links').select('*', count='exact').eq('user_id', user_id).order('created_at', desc=True).range(offset, offset + limit - 1).execute()`. _Note: Using `count='exact'` with Supabase client v2+ should return both items and total count in one go, avoiding the second query._ Check the exact syntax for your `supabase-py` version.
    - If using two queries: Implement the `SELECT ... LIMIT ... OFFSET ...` query and a separate `SELECT count(*)` query.
    - Handle potential database errors.
    - Return a tuple or dictionary containing the list of items (`response.data`) and the total count (`response.count` if using `count='exact'`, or result of the separate count query).
3.  **Implement Authentication Dependency:** Reuse the dependency.
4.  **Implement Optional Pagination Dependency:** Create a dependency function that parses `page` and `page_size` from query parameters, applies defaults, validates ranges, and returns a `PaginationParams` object (or simple dictionary/tuple).
5.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.get("/links", response_model=PaginatedLinkResponse)` in `routers/links.py`.
    - Inject the `LinkService`, authentication dependency (`current_user`), and optionally the pagination dependency (`pagination: PaginationParams = Depends()`).
    - Calculate `offset = (pagination.page - 1) * pagination.page_size`.
    - Call `link_service.get_links_paginated(user_id=current_user.id, offset=offset, limit=pagination.page_size)`.
    - Construct the `PaginatedLinkResponse` using the results from the service (`items`, `total`) and the input pagination parameters (`page`, `page_size`).
    - Wrap the service call in `try...except` for `500` errors.
    - _(HTMX Alternative):_ Add logic to check for `HX-Request` header. If present, instead of returning the JSON model, render a Jinja2 template fragment containing only the list items (`items` from the service) and return an `HTMLResponse`.
6.  **Register Router:** Ensure the router is included in the main FastAPI app.
7.  **Write Unit/Integration Tests:**
    - Test fetching the first page with default page size.
    - Test fetching a specific page (e.g., page 2).
    - Test with custom `page_size`.
    - Test with invalid `page` (e.g., 0, negative, non-integer) - expect 400/422.
    - Test with invalid `page_size` (e.g., 0, negative, > max limit, non-integer) - expect 400/422.
    - Test when the user has no links (expect empty `items` list, `total`=0).
    - Test without authentication token (expect 401).
    - (Optional) Mock database errors to test 500 responses.
    - (Optional) Test the HTMX fragment response if implemented.
