# API Endpoint Implementation Plan: Get Link Statistics

## 1. Endpoint Overview

This endpoint retrieves aggregated click statistics for a specific `routr_link` owned by the authenticated user. It provides the total clicks on the link itself and a breakdown of clicks directed through each specific routing rule associated with that link.

## 2. Request Details

- **Method:** `GET`
- **URL Structure:** `/links/{link_id}/stats`
- **Parameters:**
  - **Path Parameters:**
    - `link_id` (UUID, Required): The unique identifier of the `routr_link` for which statistics are requested.
  - **Query Parameters:** None
  - **Headers:**
    - `Authorization: Bearer <JWT_TOKEN>` (Required): Standard JWT authentication token.
- **Request Body:** None

## 3. DTOs and Models

- **Target Click Stat DTO (Pydantic Model):** `TargetClickStat`

  ```python
  # Example definition (place in schemas/stats.py or schemas/link.py)
  from pydantic import BaseModel, UUID4
  from typing import Literal

  TargetTypeEnum = Literal['url', 'html']

  class TargetClickStat(BaseModel):
      rule_id: UUID4
      target_type: TargetTypeEnum
      target_value_preview: str # URL or a placeholder/truncated preview for HTML
      current_clicks: int
  ```

- **Response DTO (Pydantic Model):** `LinkStatsResponse`

  ```python
  # Example definition (place in schemas/stats.py or schemas/link.py)
  from pydantic import BaseModel, UUID4
  from typing import List

  class LinkStatsResponse(BaseModel):
      link_id: UUID4
      alias: str
      total_clicks: int
      target_clicks: List[TargetClickStat]
  ```

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `GET` request at `/links/{link_id}/stats`.
2.  **Authentication:** The authentication dependency verifies the JWT Bearer token. If invalid/missing, returns `401 Unauthorized`. Extracts `user_id`.
3.  **Path Parameter Validation:** FastAPI validates `link_id` is a valid UUID. If not, returns `422 Unprocessable Entity`.
4.  **Call Service Layer:** The endpoint handler calls a method in a relevant service (e.g., `LinkService` or a dedicated `StatsService` like `get_link_statistics`), passing `link_id` and `user_id`.
5.  **Database Queries (Service Layer):**
    - **Step 1: Fetch Link & Verify Ownership.** Execute a `SELECT id, alias, total_clicks FROM routr_links WHERE id = link_id` using the user's JWT context (RLS applies: `USING (auth.uid() = user_id)`). If no link is found (returns 0 rows), raise `NotFoundException`. Store the `alias` and `total_clicks`.
    - **Step 2: Fetch Rule Stats.** Execute a `SELECT id as rule_id, target_type, target_value, current_clicks FROM routing_rules WHERE link_id = link_id ORDER BY priority ASC` using the user's JWT context (RLS applies implicitly via the parent link check).
6.  **Process Data (Service Layer):**
    - Iterate through the results from the rule stats query.
    - For each rule:
      - Determine `target_value_preview`:
        - If `target_type` is 'url', use `target_value` directly.
        - If `target_type` is 'html', generate a placeholder (e.g., "[Custom HTML Content]") or truncate `target_value` safely (e.g., first 100 characters + '...') to avoid returning potentially huge HTML blocks.
      - Create a `TargetClickStat` dictionary/object with `rule_id`, `target_type`, the generated `target_value_preview`, and `current_clicks`.
    - Collect these `TargetClickStat` objects into a list.
    - Combine the fetched `link_id`, `alias`, `total_clicks` (from Step 1) and the generated list of `target_clicks` into a structure matching `LinkStatsResponse`.
    - Return the combined statistics structure.
    - Handle potential database errors during queries.
7.  **Process Service Response (Endpoint Handler):**
    - If the service returns the statistics structure, map it to the `LinkStatsResponse` DTO.
    - If the service raises `NotFoundException` (from link ownership check), raise `HTTPException(status_code=404, detail="Link not found or access denied")`.
    - Handle generic "Server Errors" from the service by raising `HTTPException(status_code=500, detail="Internal server error")`.
8.  **Send Response:** FastAPI serializes the `LinkStatsResponse` model into JSON and sends the `200 OK` response (or appropriate error code).

## 5. Security Considerations

- **Authentication:** Enforced via JWT Bearer token validation (`401 Unauthorized`).
- **Authorization:** Enforced by the service layer checking link ownership via RLS before querying rule statistics. RLS on `routing_rules` provides an additional layer. Ensures users only see stats for their own links.
- **Input Validation:** Path parameter `link_id` is validated for UUID format (`422 Unprocessable Entity`).
- **Information Exposure:** The `target_value_preview` logic prevents exposing potentially large or complex user-provided HTML in the statistics response. Only the URL or a placeholder/preview is returned for `target_value`.

## 6. Error Handling

- **`401 Unauthorized`:** Returned by the authentication dependency.
- **`403 Forbidden`:** Implicitly handled by the ownership check, resulting in `404 Not Found`.
- **`404 Not Found`:** Returned if the `link_id` does not correspond to a link owned by the authenticated user.
- **`422 Unprocessable Entity`:** Returned by FastAPI if `link_id` is not a valid UUID.
- **`500 Internal Server Error`:** Returned for unexpected server-side errors (database connection, Supabase client issues, errors during data processing/preview generation, uncaught exceptions). Log details server-side.

## 7. Performance Considerations

- **Database Queries:** Involves two `SELECT` queries:
  - One on `routr_links` filtering by `id` (PK) and `user_id` (RLS) - very fast.
  - One on `routing_rules` filtering by `link_id` (FK) and ordering by `priority` - efficient with the composite index `idx_routing_rules_link_id_priority`.
- **Data Processing:** Iterating through rules and generating previews is done in memory on the API server. For links with an extremely large number of rules (beyond MVP scope), this could consume more memory/CPU, but it's unlikely to be an issue initially.
- **Mitigation:** Ensure necessary indexes (`PK`, `FK`, `idx_routing_rules_link_id_priority`) exist. The preview generation logic for HTML should be simple (e.g., fixed placeholder or basic truncation) to avoid performance overhead.

## 8. Implementation Steps

1.  **Define Pydantic Models:** Create/Confirm `TargetClickStat` and `LinkStatsResponse` models in `schemas/stats.py` (or similar).
2.  **Create Service Layer Method:**
    - Define `get_link_statistics` in `LinkService` or `StatsService`.
    - Accept `link_id: UUID`, `user_id: UUID`.
    - Inject Supabase client.
    - **Step 1: Fetch Link.** Execute `supabase.table('routr_links').select('id, alias, total_clicks').eq('id', link_id).maybe_single().execute()`. RLS handles user ownership. If `response.data` is `None`, raise `NotFoundException`. Store `link_data = response.data`.
    - **Step 2: Fetch Rules.** Execute `supabase.table('routing_rules').select('id, target_type, target_value, current_clicks').eq('link_id', link_id).order('priority', desc=False).execute()`. Store `rules_data = response.data`.
    - **Step 3: Process Rules.** Initialize `target_clicks_list = []`. Iterate through `rules_data`:
      - Determine `preview`: if `rule['target_type'] == 'url'`, `preview = rule['target_value']`; else `preview = "[Custom HTML Content]" # Or truncate rule['target_value']`.
      - Append a dictionary/object like `{'rule_id': rule['id'], 'target_type': rule['target_type'], 'target_value_preview': preview, 'current_clicks': rule['current_clicks']}` to `target_clicks_list`.
    - **Step 4: Combine Results.** Create the final result dictionary: `{'link_id': link_data['id'], 'alias': link_data['alias'], 'total_clicks': link_data['total_clicks'], 'target_clicks': target_clicks_list}`.
    - Wrap DB calls in `try...except` for `DatabaseException`.
    - Return the final result dictionary.
3.  **Implement Authentication Dependency:** Reuse existing dependency.
4.  **Create FastAPI Endpoint Handler:**
    - Define `@router.get("/links/{link_id}/stats", response_model=LinkStatsResponse)` in `routers/stats.py` (or `routers/links.py`).
    - Use `Path(...)` for `link_id`.
    - Inject the service and authentication dependency (`current_user`).
    - Call `service.get_link_statistics(link_id=link_id, user_id=current_user.id)`.
    - Wrap service call in `try...except`:
      - Catch `NotFoundException` -> `HTTPException(404, "Link not found or access denied")`.
      - Catch other exceptions -> `HTTPException(500, "Internal server error")`.
    - Return the statistics data upon success.
5.  **Register Router:** Include the router in the main app.
6.  **Write Unit/Integration Tests:**
    - Test fetching stats for a link with 0, 1, and multiple rules (including both URL and HTML targets). Verify `total_clicks` and aggregated `target_clicks` list structure and content (including previews).
    - Test fetching stats for a link that doesn't exist (expect 404).
    - Test fetching stats for a link owned by another user (expect 404).
    - Test without authentication token (expect 401).
    - Test with invalid `link_id` UUID format (expect 422).
    - (Optional) Mock database errors to test 500 responses.
