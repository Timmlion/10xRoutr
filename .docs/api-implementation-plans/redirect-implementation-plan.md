# API Endpoint Implementation Plan: Redirect based on Alias

## 1. Endpoint Overview

This is the core public-facing endpoint of the _routr_ application. It handles incoming `GET` requests for specific link aliases. Based on the requested alias, it looks up the corresponding link and its associated routing rules, evaluates these rules based on priority and conditions (time or click count), performs the appropriate action (HTTP redirect to a URL or serving custom HTML content), and atomically increments the relevant click counters. This endpoint does not require user authentication.

## 2. Request Details

- **Method:** `GET`
- **URL Structure:** `/{alias_path:path}`
- **Parameters:**
  - **Path Parameters:**
    - `alias_path` (string, Required): The unique alias identifying the `routr_link`.
  - **Query Parameters:** None (Query parameters from the original request are generally _not_ passed through to the target URL unless explicitly designed for).
  - **Headers:** Standard HTTP request headers (e.g., `User-Agent`, `Accept`, etc.). No specific custom headers required for input.
- **Request Body:** None

## 3. DTOs and Models

- **Request DTO:** None
- **Internal Data Structures/Models (Service Layer):**
  - `LinkData`: Represents data fetched from `routr_links` (id, alias, default_url).
  - `RuleData`: Represents data fetched from `routing_rules` (id, priority, rule_type, target_type, target_value, start_time, end_time, max_clicks, current_clicks).
- **Response:** Not a DTO, but rather specific FastAPI response types:
  - `RedirectResponse` (from `fastapi.responses`)
  - `HTMLResponse` (from `fastapi.responses`)

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `GET` request matching the `/{alias_path:path}` pattern.
2.  **Extract Alias:** The `alias_path` parameter is extracted from the URL.
3.  **Call Service Layer:** The endpoint handler calls a method in the `RedirectionService` (e.g., `process_redirection`), passing the extracted `alias_path`.
4.  **Database Access (Service Layer - using `service_role` key):**
    - **Step 4.1: Find Link.** Execute `SELECT id, alias, default_url FROM routr_links WHERE alias = alias_path LIMIT 1`. If no row is found, raise `NotFoundException`. Store the found `link_id` and `default_url`.
    - **Step 4.2: Increment Total Clicks.** Execute an **atomic** `UPDATE routr_links SET total_clicks = total_clicks + 1 WHERE id = link_id`. Log any errors but try to continue if possible (redirection is prioritised over perfect stats in case of transient DB errors).
    - **Step 4.3: Fetch Rules.** Execute `SELECT id, priority, rule_type, target_type, target_value, start_time, end_time, max_clicks, current_clicks FROM routing_rules WHERE link_id = link_id ORDER BY priority ASC`.
5.  **Evaluate Rules (Service Layer):**
    - Iterate through the fetched rules (ordered by priority).
    - For each rule:
      - Check `rule_type`:
        - If `'time'`: Check if `now() AT TIME ZONE 'utc'` is between `start_time` and `end_time`.
        - If `'clicks'`: Check if `current_clicks < max_clicks`.
      - If the condition for the current rule is **met**:
        - Store this `matched_rule` data.
        - Break the loop (first match wins).
6.  **Determine Action & Increment Rule Clicks (Service Layer):**
    - **If a `matched_rule` was found:**
      - **Step 6.1: Increment Rule Clicks.** Execute an **atomic** `UPDATE routing_rules SET current_clicks = current_clicks + 1 WHERE id = matched_rule.id`. Log errors but continue.
      - **Step 6.2: Determine Action.**
        - If `matched_rule.target_type == 'url'`, the action is `REDIRECT_URL` with `url = matched_rule.target_value`.
        - If `matched_rule.target_type == 'html'`, the action is `SERVE_HTML` with `html_content = matched_rule.target_value`.
    - **If no rule matched:**
      - Check if the fetched `default_url` (from Step 4.1) is not null/empty.
      - If yes, the action is `REDIRECT_DEFAULT` with `url = default_url`.
      - If no, the action is `REDIRECT_GLOBAL_FALLBACK`.
7.  **Return Action to Handler (Service Layer):** The service returns an indicator of the action to perform (e.g., an Enum or tuple like `('REDIRECT_URL', 'http://example.com')`, `('SERVE_HTML', '<h1>Hello</h1>')`, `('REDIRECT_DEFAULT', 'http://fallback.com')`, `('REDIRECT_GLOBAL_FALLBACK', None)`). It also signals if the initial link lookup failed (`NotFoundException`).
8.  **Process Service Response (Endpoint Handler):**
    - If the service indicates `REDIRECT_URL` or `REDIRECT_DEFAULT`, create and return a `RedirectResponse(url=returned_url, status_code=302)`.
    - If the service indicates `SERVE_HTML`, create and return an `HTMLResponse(content=returned_html_content, status_code=200)`.
    - If the service indicates `REDIRECT_GLOBAL_FALLBACK`, fetch the global fallback URL from configuration/environment variables and return a `RedirectResponse(url=global_fallback_url, status_code=302)`.
    - If the service raised `NotFoundException`, raise `HTTPException(status_code=404, detail="Link alias not found")`.
    - Handle any other service exceptions by raising `HTTPException(status_code=500, detail="Internal server error")`.
9.  **Send Response:** FastAPI sends the appropriate `RedirectResponse` or `HTMLResponse`.

## 5. Security Considerations

- **Authentication/Authorization:** None required for the end-user accessing the link. However, the backend service performing database operations **must use the `service_role` key** to bypass RLS intended for link owners. Secure management of this key is critical.
- **Open Redirect Vulnerability:** Prevented by validating the `target_value` (for URL type rules) during the _creation/update_ of the rule via the management API (requiring `http://` or `https://`). This endpoint relies on that prior validation.
- **Cross-Site Scripting (XSS):** If `target_type` is 'html', the content stored in `target_value` is served directly. **This is a significant XSS risk.** The responsibility for safe HTML lies with the user creating the rule. For MVP, this risk is noted. Future enhancements should include server-side sanitization during rule creation/update. Consider adding a `Content-Security-Policy` header to responses serving custom HTML, although its effectiveness depends on the injected content.
- **Denial of Service (DoS):** High traffic on a single alias could lead to many database updates (counter increments). Rate limiting at the infrastructure level (load balancer, gateway) or application level (e.g., using `slowapi` middleware) is recommended to mitigate potential database load or abuse.
- **Alias Enumeration:** While `404` is returned for non-existent aliases, attackers could still attempt to guess valid aliases. Rate limiting helps mitigate this.

## 6. Error Handling

- **`404 Not Found`:** Returned if the `alias_path` provided in the URL does not correspond to any existing `alias` in the `routr_links` table.
- **`500 Internal Server Error`:** Returned for any unexpected server-side issues, including:
  - Failure to connect to the database.
  - Errors during `SELECT` queries for links or rules.
  - Errors during atomic `UPDATE` operations for click counters.
  - Errors during the rule evaluation logic.
  - Failure to retrieve the global fallback URL (if applicable).
  - Uncaught exceptions.
  - Detailed errors should be logged server-side for diagnosis.

## 7. Performance Considerations

- **Database Queries:** This endpoint performs multiple database operations per request:
  - `SELECT` on `routr_links` by `alias` (indexed, fast).
  - `UPDATE` on `routr_links` by `id` (PK, fast, but requires write lock).
  - `SELECT` on `routing_rules` by `link_id` with `ORDER BY priority` (indexed, efficient).
  - Potentially one `UPDATE` on `routing_rules` by `id` (PK, fast, but requires write lock).
- **Rule Evaluation:** The evaluation logic itself (comparing time, checking click count) is computationally inexpensive for MVP rule types.
- **Bottlenecks:**
  - **Database Write Load:** Frequent updates to click counters under very high traffic could become a bottleneck due to write locks or general database load.
  - **Network Latency:** Communication with the database.
- **Mitigation:**
  - Ensure indexes (`idx_routr_links_alias`, `idx_routing_rules_link_id_priority`, PKs, FKs) are correctly in place.
  - Use atomic database updates.
  - Monitor database performance under load.
  - _Post-MVP:_ Consider caching rule data for frequently accessed aliases (with appropriate invalidation), or offloading counter updates to a background queue/different data store if write contention becomes severe. Rate limiting helps manage load.

## 8. Implementation Steps

1.  **Define Service Layer:** Create `RedirectionService` (or similar). Inject the Supabase client configured with the `service_role` key.
2.  **Implement `process_redirection` Method:**
    - Implement the database query logic (Steps 4.1, 4.2, 4.3) using the `service_role` client. Ensure atomic updates for counters. Handle the case where the link is not found (`NotFoundException`).
    - Implement the rule evaluation loop (Step 5). Pay attention to timezone handling (use UTC).
    - Implement the action determination and rule counter increment logic (Step 6).
    - Return a clear representation of the final action and necessary data (URL or HTML) or raise appropriate exceptions.
3.  **Configure Global Fallback:** Store the global fallback URL in application settings or environment variables.
4.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.get("/{alias_path:path}", response_class=Response)` (using the base `Response` allows returning different types like `RedirectResponse` or `HTMLResponse`).
    - Use `Path(...)` to capture `alias_path`.
    - Inject the `RedirectionService`.
    - Call `service.process_redirection(alias_path=alias_path)`.
    - Wrap the service call in `try...except`:
      - Catch `NotFoundException` -> `HTTPException(404)`.
      - Catch other service/database exceptions -> `HTTPException(500)`.
    - Based on the action returned by the service:
      - If redirect (URL, Default, Global): Create and return `RedirectResponse(url=..., status_code=302)`.
      - If serve HTML: Create and return `HTMLResponse(content=..., status_code=200)`.
5.  **Register Router:** Ensure the router handling the root path (`/`) is included _last_ in the main FastAPI app registration to act as a catch-all for aliases, or configure it appropriately based on your base URL setup.
6.  **Write Unit/Integration Tests:**
    - Test redirection for a 'time' rule within the valid period.
    - Test redirection for a 'time' rule outside the valid period (should fall through or hit default/global).
    - Test redirection for a 'clicks' rule below the limit.
    - Test redirection for a 'clicks' rule at/above the limit (should fall through).
    - Test correct priority handling (rule with lower priority wins if conditions met).
    - Test redirection to `default_url` when no rules match.
    - Test redirection to global fallback URL when no rules match and no `default_url`.
    - Test serving HTML content for an 'html' target rule.
    - Test accessing a non-existent alias (expect 404).
    - Verify click counters (`total_clicks`, `current_clicks`) are incremented correctly (requires checking DB state or specific service return values if designed for testing).
    - (Optional) Mock database errors to test 500 responses.
