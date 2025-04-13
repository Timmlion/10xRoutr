# API Endpoint Implementation Plan: Register User (Optional)

## 1. Endpoint Overview

This public endpoint handles new user registration. It accepts an email and password, passes them to the Supabase Auth service for account creation, and returns information about the newly created user (or a confirmation). Note that registration might also be handled directly by the frontend client using the Supabase JS library; this endpoint provides a backend-mediated option.

## 2. Request Details

- **Method:** `POST`
- **URL Structure:** `/auth/register`
- **Parameters:**
  - **Path Parameters:** None
  - **Query Parameters:** None
  - **Headers:**
    - `Content-Type: application/json` (Required)
- **Request Body:** Required (JSON payload)
  ```json
  {
    "email": "string (required, valid email format)",
    "password": "string (required, meets complexity requirements)"
  }
  ```

## 3. DTOs and Models

- **Request DTO (Pydantic Model):** `UserRegister`

  ```python
  # Example definition (place in schemas/auth.py)
  from pydantic import BaseModel, EmailStr, Field

  class UserRegister(BaseModel):
      email: EmailStr
      password: str = Field(..., min_length=8) # Example: Enforce minimum password length
      # Add more password complexity validation here if needed using custom validators
  ```

- **Response DTO (Pydantic Model):** `UserRegistrationResponse` (Structure based on Supabase Auth sign-up response)

  ```python
  # Example definition (place in schemas/auth.py)
  from pydantic import BaseModel, UUID4, EmailStr
  from typing import Optional
  from datetime import datetime # Import if using datetime fields

  class UserInfoMinimal(BaseModel): # Reusing UserInfo from Login might expose too much
      id: UUID4
      aud: str
      role: Optional[str] = None # May not be present immediately after sign-up
      email: Optional[EmailStr] = None
      # Include other fields if Supabase consistently returns them on sign-up
      # created_at: Optional[datetime] = None

  class UserRegistrationResponse(BaseModel):
      # Supabase sign_up often returns the User object directly within the response data
      user: UserInfoMinimal
      # Session object might be null or present depending on email confirmation settings
      # session: Optional[dict] = None # Or define a Session model

      # class Config:
      #     orm_mode = True # or from_attributes = True
  ```

  _Note: Supabase's `sign_up` response might differ based on whether email confirmation is enabled. If confirmation is required, the `session` might be `null`. Adapt the `UserRegistrationResponse` model based on the actual observed response from `supabase-py` in your specific configuration._

## 4. Data Flow

1.  **Receive Request:** FastAPI receives a `POST` request at `/auth/register` with a JSON payload.
2.  **Request Body Validation:** FastAPI validates the incoming JSON payload against the `UserRegister` Pydantic model.
    - Checks for required fields (`email`, `password`).
    - Validates `email` format and password minimum length/complexity rules defined in the model.
    - If validation fails, returns `422 Unprocessable Entity`.
3.  **Call Authentication Service (or directly Supabase client):**
    - The endpoint handler obtains an instance of the Supabase client.
    - It calls the Supabase authentication method for signing up: `supabase.auth.sign_up({"email": register_data.email, "password": register_data.password})`.
4.  **Handle Supabase Response:**
    - The `supabase-py` client interacts with Supabase Auth.
    - **Success:** If the email is not already registered and the password meets requirements, Supabase creates the user account. The response typically includes details of the new user object (and potentially a session object if auto-confirmation is enabled).
    - **Failure (Email Exists):** If the email address is already in use, Supabase Auth will return an error. The `supabase-py` client will likely raise an `AuthApiError` (potentially with a specific indicator or status code like 400/422/409 depending on Supabase implementation - need to verify).
    - **Failure (Password Policy):** If the password doesn't meet Supabase's configured complexity rules, an error/exception will be raised.
    - **Other Errors:** Network issues or internal Supabase errors might cause exceptions.
5.  **Process Supabase Response/Exception (Endpoint Handler):**
    - **If successful:**
      - Extract the user data from the Supabase response (`SignUpResponse` or similar).
      - Map this data to the `UserRegistrationResponse` Pydantic model.
      - Return the `UserRegistrationResponse` object with status code `201 Created`.
    - **If `AuthApiError` indicates email already exists:** Raise `HTTPException(status_code=409, detail="Email address already registered")`.
    - **If `AuthApiError` indicates password policy violation:** Raise `HTTPException(status_code=400, detail="Password does not meet complexity requirements")`.
    - **If other `AuthApiError` or network errors are caught:** Raise `HTTPException(status_code=500, detail="Authentication service error")`. Log details server-side.
    - **Handle unexpected exceptions:** Catch any other exceptions and raise `HTTPException(status_code=500, detail="Internal server error")`.
6.  **Send Response:** FastAPI serializes the `UserRegistrationResponse` model (or error details) into JSON and sends the HTTP response with the appropriate status code (`201 Created`, `409 Conflict`, etc.).

## 5. Security Considerations

- **Password Complexity:** Enforce password complexity rules within the `UserRegister` Pydantic model _and_ configure corresponding rules in your Supabase Auth settings for consistency and robustness.
- **Email Confirmation:** Strongly recommend enabling email confirmation in Supabase Auth settings. This prevents users from signing up with emails they don't own and activates the account only after verification. The API response might differ slightly (e.g., `session` might be null until confirmation).
- **Rate Limiting:** Implement rate limiting on this endpoint to prevent abuse (e.g., automated scripts creating spam accounts).
- **Input Validation:** Pydantic model provides validation for email format and basic password rules.
- **Error Messages:** Return clear but non-revealing error messages. A `409 Conflict` clearly indicates the email is taken. Password policy errors should be specific enough for the user to correct (`400 Bad Request`).

## 6. Error Handling

- **`400 Bad Request`:** Returned if the password doesn't meet complexity rules defined either in Pydantic or by Supabase Auth.
- **`409 Conflict`:** Returned specifically when Supabase Auth indicates the provided email address is already registered.
- **`422 Unprocessable Entity`:** Returned by FastAPI automatically if the request body fails basic validation against the `UserRegister` model (e.g., missing fields, invalid email format, password too short according to Pydantic `min_length`).
- **`500 Internal Server Error`:** Returned for:
  - Errors communicating with Supabase Auth.
  - Unexpected errors within the Supabase client library.
  - Uncaught exceptions in the endpoint logic.
  - Log detailed original errors server-side.

## 7. Performance Considerations

- **Supabase Auth Latency:** Performance depends on the Supabase Auth service's response time for creating a new user record.
- **Database Interaction:** Supabase Auth handles the necessary database interactions (checking email uniqueness, inserting user record).
- **Mitigation:** Minimal optimization possible on the API side. Ensure reliable network connectivity.

## 8. Implementation Steps

1.  **Define Pydantic Models:** Create/Confirm `UserRegister` (with password validation) and `UserRegistrationResponse` (including `UserInfoMinimal`) in `schemas/auth.py`. Adjust `UserRegistrationResponse` based on expected Supabase output with your email confirmation settings.
2.  **Inject Supabase Client:** Ensure the Supabase client is available in the handler.
3.  **Create FastAPI Endpoint Handler:**
    - Define the route function using `@router.post("/auth/register", response_model=UserRegistrationResponse, status_code=status.HTTP_201_CREATED)` in `routers/auth.py`.
    - Accept the request body validated into a `register_data: UserRegister` object.
    - Wrap the Supabase call in a `try...except` block:
      - Call `supabase.auth.sign_up(...)`.
      - If successful, extract data, construct `UserRegistrationResponse`, and return it.
      - Catch specific Supabase `AuthApiError` indicating email exists (check error code/message from Supabase) -> `HTTPException(409, "Email address already registered")`.
      - Catch specific Supabase `AuthApiError` indicating password error -> `HTTPException(400, "Password does not meet requirements")`.
      - Catch other Supabase/network errors -> `HTTPException(500, "Authentication service error")`.
      - Catch any other exceptions -> `HTTPException(500, "Internal server error")`.
4.  **Register Router:** Include the auth router in the main FastAPI app.
5.  **Write Unit/Integration Tests:**
    - Test successful registration (verify 201 status and response structure).
    - Test registration with an email that already exists (expect 409).
    - Test registration with a password that violates complexity rules (expect 400 or 422 depending on where validation occurs).
    - Test with invalid email format (expect 422).
    - Test with missing email or password (expect 422).
    - (Optional) Mock Supabase client to simulate service errors (expect 500).
