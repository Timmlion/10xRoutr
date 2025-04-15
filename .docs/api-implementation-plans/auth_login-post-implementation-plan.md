# API Endpoint Implementation Plan: Login

## 1. Endpoint Overview

This public endpoint handles user authentication. It accepts an email and password, verifies these credentials against the Supabase Auth service, and upon success, returns authentication tokens (JWT access token, refresh token) and basic user information provided by Supabase.

## 2. Request Details

- **Method:** `POST`
- **URL Structure:** `/auth/login`
- **Parameters:**
  - **Path Parameters:** None
  - **Query Parameters:** None
  - **Headers:**
    - `Content-Type: application/json` (Required)
- **Request Body:** Required (JSON payload)
  ```json
  {
    "email": "string (required, valid email format)",
    "password": "string (required)"
  }
  ```

## 3. DTOs and Models

- **Request DTO (Pydantic Model):** `UserLogin`

  ```python
  # Example definition (place in schemas/auth.py)
  from pydantic import BaseModel, EmailStr

  class UserLogin(BaseModel):
      email: EmailStr # Pydantic's EmailStr validates email format
      password: str
  ```

- **Response DTO (Pydantic Model):** `TokenResponse` (Structure mirrors Supabase Auth response)

  ```python
  # Example definition (place in schemas/auth.py)
  from pydantic import BaseModel, UUID4, EmailStr
  from typing import Optional

  class UserInfo(BaseModel):
      id: UUID4
      aud: str # Audience
      role: str # e.g., 'authenticated'
      email: Optional[EmailStr] = None
      # Add other fields returned by Supabase Auth's user object if needed
      # e.g., phone: Optional[str] = None, created_at: datetime, etc.
      # Be mindful of what you expose via the API

  class TokenResponse(BaseModel):
      access_token: str
      token_type: str = "bearer" # Usually fixed to 'bearer'
      expires_in: Optional[int] = None # Supabase might not always return this
      refresh_token: Optional[str] = None # Supabase might not always return this depending on flow
      user: UserInfo

      # Allow extra fields if Supabase response is variable
      # class Config:
      #     extra = 'allow'
  ```

  _Note: The exact structure of the `user` object and the presence/names of `expires_in`, `refresh_token` might vary slightly depending on the Supabase Auth configuration and the `supabase-py` client version. Adapt the model accordingly based on actual Supabase responses._

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `POST` request at `/auth/login` with a JSON payload.
2.  **Request Body Validation:** FastAPI validates the incoming JSON payload against the `UserLogin` Pydantic model.
    - Checks for required fields (`email`, `password`).
    - Validates `email` format using `EmailStr`.
    - If validation fails, returns `422 Unprocessable Entity`.
3.  **Call Authentication Service (or directly Supabase client):**
    - The endpoint handler obtains an instance of the Supabase client (likely injected).
    - It calls the Supabase authentication method for signing in with email and password: `supabase.auth.sign_in_with_password({"email": login_data.email, "password": login_data.password})`.
4.  **Handle Supabase Response:**
    - The `supabase-py` client interacts with the Supabase Auth backend.
    - **Success:** If credentials are valid, Supabase returns a session object containing the access token, user details, potentially refresh token, etc.
    - **Failure:** If credentials are invalid or the user doesn't exist, the `supabase-py` client will likely raise an exception (e.g., `AuthApiError` or a specific subtype like `AuthInvalidCredentialsError` - check the library's specific exceptions).
    - **Other Errors:** Network issues or internal Supabase errors might also cause exceptions.
5.  **Process Supabase Response/Exception (Endpoint Handler):**
    - **If successful:**
      - Extract the necessary data (access token, user info, refresh token, etc.) from the Supabase response object (`AuthResponse` or similar).
      - Map this data to the `TokenResponse` Pydantic model. Handle potential missing fields like `refresh_token` or `expires_in` if they are optional in the Supabase response.
      - Return the `TokenResponse` object.
    - **If `AuthInvalidCredentialsError` (or similar) is caught:** Raise `HTTPException(status_code=401, detail="Invalid login credentials")`.
    - **If other `AuthApiError` or network errors are caught:** Raise `HTTPException(status_code=500, detail="Authentication service error")`. Log the original error details server-side.
    - **Handle unexpected exceptions:** Catch any other exceptions and raise `HTTPException(status_code=500, detail="Internal server error")`.
6.  **Send Response:** FastAPI serializes the `TokenResponse` model (or error details) into JSON and sends the HTTP response with the appropriate status code (`200 OK`, `401 Unauthorized`, etc.).

## 5. Security Considerations

- **Password Handling:** Passwords are sent over HTTPS (ensure HTTPS is enforced in production). The API endpoint itself does not store the password; it passes it directly to Supabase Auth for verification. Supabase handles secure password hashing and storage.
- **Rate Limiting:** Implement rate limiting on this endpoint (e.g., using `slowapi` middleware with FastAPI) to prevent brute-force attacks against user accounts.
- **Input Validation:** Pydantic model (`UserLogin`) validates email format and ensures password is provided.
- **Token Security:** The returned JWT `access_token` should be treated as sensitive by the client and stored securely (e.g., in memory or secure storage, _not_ typically localStorage). It should be sent in the `Authorization` header for subsequent requests. `refresh_token` (if used) requires even more secure storage.
- **Error Messages:** Return generic error messages (`401 Invalid login credentials`) for failed login attempts to avoid confirming whether an email address is registered or not (prevents user enumeration).

## 6. Error Handling

- **`400 Bad Request`:** Although Pydantic handles most format validation (returning 422), this code _could_ potentially be used if there were additional server-side validation rules beyond basic format (unlikely for this simple login).
- **`401 Unauthorized`:** Returned specifically when Supabase Auth indicates invalid email/password credentials.
- **`422 Unprocessable Entity`:** Returned by FastAPI automatically if the request body fails validation against the `UserLogin` Pydantic model (e.g., missing fields, invalid email format).
- **`500 Internal Server Error`:** Returned for:
  - Errors communicating with Supabase Auth (network issues, Supabase downtime).
  - Unexpected errors within the Supabase client library.
  - Uncaught exceptions in the endpoint logic.
  - Log detailed original errors server-side.

## 7. Performance Considerations

- **Supabase Auth Latency:** Performance is primarily dependent on the response time of the Supabase Auth service. This involves database lookups and cryptographic operations on Supabase's side.
- **Network Latency:** Latency between the API server and the Supabase Auth endpoint.
- **Mitigation:** Generally minimal optimization possible on the API side itself, as the bottleneck is the external authentication service. Ensure the API server has reliable network connectivity to Supabase.

## 8. Implementation Steps

1.  **Define Pydantic Models:** Create/Confirm `UserLogin` and `TokenResponse` (including `UserInfo` sub-model) in `schemas/auth.py` or similar. Ensure `TokenResponse` accurately reflects the expected Supabase client response structure.
2.  **Inject Supabase Client:** Ensure the Supabase client instance is readily available in the endpoint handler (e.g., via FastAPI dependency injection).
3.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.post("/auth/login", response_model=TokenResponse)` in `routers/auth.py`.
    - The function should accept the request body validated into a `login_data: UserLogin` object.
    - Wrap the Supabase call in a `try...except` block:
      - Call `supabase.auth.sign_in_with_password(...)`.
      - If successful, extract data from the `AuthResponse` object and construct the `TokenResponse`. Return it.
      - Catch specific Supabase authentication error(s) indicating invalid credentials (e.g., `gotrue.errors.AuthApiError` with specific status/message - check `supabase-py` documentation) and raise `HTTPException(status_code=401, detail="Invalid login credentials")`.
      - Catch other potential Supabase/network errors and raise `HTTPException(status_code=500, detail="Authentication service error")`.
      - Catch any other exceptions and raise `HTTPException(status_code=500, detail="Internal server error")`.
4.  **Register Router:** Ensure the `APIRouter` containing the `/auth/login` endpoint is included in the main FastAPI application instance.
5.  **Write Unit/Integration Tests:**
    - Test successful login with valid credentials (verify 200 status and token structure).
    - Test login with invalid password (expect 401).
    - Test login with non-existent email (expect 401).
    - Test login with invalid email format in request (expect 422).
    - Test login with missing email or password in request (expect 422).
    - (Optional) Mock Supabase client to simulate auth service errors (expect 500).
