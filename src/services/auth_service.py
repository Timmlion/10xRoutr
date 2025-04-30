# src/services/auth_service.py

import traceback  # Used for printing detailed exception information for debugging
from supabase import AsyncClient
from gotrue.errors import (
    AuthApiError,
)  # Specific exception class from Supabase's auth library

# Import custom exceptions for more specific error handling
from src.services.custom_exceptions import (
    AuthenticationFailedException,
    EmailExistsException,
    PasswordPolicyException,
    AuthServiceException,  # Generic exception for this service
    ServiceException,  # Base class for service errors (optional, depends on definition)
)

# Import Pydantic models (Data Transfer Objects) for request/response structures
from src.schemas.auth import (
    UserLogin,
    UserRegister,
    TokenResponse,
    UserRegistrationResponse,
    UserInfo,
    UserInfoMinimal,
)


class AuthService:
    """
    Provides authentication-related services (login, registration)
    by interacting with the Supabase authentication backend.
    """

    def __init__(self, supabase_client: AsyncClient):
        """
        Initializes the AuthService with an asynchronous Supabase client instance.

        Args:
            supabase_client: An initialized Supabase AsyncClient, typically configured
                             with the public anonymous key for auth operations.
        """
        self.supabase: AsyncClient = supabase_client
        # Convenience accessor for the auth interface
        self.auth = supabase_client.auth

    async def login_user(self, login_data: UserLogin) -> TokenResponse:
        """
        Authenticates a user using email and password via Supabase Auth.

        Args:
            login_data: A UserLogin object containing the user's email and password.

        Returns:
            A TokenResponse object containing the access token, refresh token (if available),
            token type, expiration info (if available), and user details upon successful login.

        Raises:
            AuthenticationFailedException: If the provided credentials are invalid or the user
                                           account has issues (e.g., email not confirmed).
            AuthServiceException: For unexpected errors during the login process,
                                  including issues communicating with Supabase or parsing responses.
        """
        try:
            print(f"Attempting login for user: {login_data.email}")  # MVP Logging
            # Call the Supabase client's sign-in method
            response = await self.auth.sign_in_with_password(
                {"email": login_data.email, "password": login_data.password}
            )

            # Check if the response contains the expected session and user data
            if response and response.session and response.user:
                print(f"Login successful for user: {login_data.email}")  # MVP Logging

                # Validate and structure the user data from Supabase using the UserInfo schema
                try:
                    # Use model_validate (Pydantic v2) to parse the Supabase user object's data
                    user_info = UserInfo.model_validate(response.user.model_dump())
                except Exception as pydantic_error:
                    print(
                        f"[ERROR] Pydantic validation error for UserInfo: {pydantic_error}. Supabase user data: {response.user.model_dump()}"
                    )  # MVP Error Logging
                    # Raise if the user data structure is unexpected or invalid
                    raise AuthServiceException(
                        detail="Failed to parse user information from authentication service."
                    )

                # Construct the final TokenResponse object
                try:
                    token_response = TokenResponse(
                        access_token=response.session.access_token,
                        # Use getattr for potentially missing attributes in the session object
                        token_type=getattr(response.session, "token_type", "bearer"),
                        expires_in=getattr(response.session, "expires_in", None),
                        refresh_token=getattr(response.session, "refresh_token", None),
                        user=user_info,  # Embed the validated user information
                    )
                    return token_response
                except Exception as pydantic_error:
                    print(
                        f"[ERROR] Pydantic validation error for TokenResponse: {pydantic_error}. Supabase session data: {response.session}"
                    )  # MVP Error Logging
                    # Raise if the session data structure is unexpected or invalid
                    raise AuthServiceException(
                        detail="Failed to parse session information from authentication service."
                    )
            else:
                # If Supabase call succeeded but response structure is wrong, treat as auth failure
                print(
                    f"[ERROR] Unexpected response structure during login for {login_data.email}: {response}"
                )  # MVP Error Logging
                # Raise a specific exception indicating failed login attempt
                raise AuthenticationFailedException(detail="Invalid credentials.")

        except AuthApiError as e:
            # Handle specific errors raised by the Supabase auth library
            self._handle_auth_api_error(
                e, context="login"
            )  # Delegates to helper method
        except Exception as e:
            # Catch any other unexpected exceptions during the process
            print(
                f"[ERROR] Unexpected error during login for {login_data.email}:"
            )  # MVP Error Logging
            traceback.print_exc()  # Print detailed traceback for debugging
            raise AuthServiceException(
                detail="An unexpected error occurred during login."
            )

    async def register_user(
        self, register_data: UserRegister
    ) -> UserRegistrationResponse:
        """
        Registers a new user using Supabase Auth with the provided email and password.

        Args:
            register_data: A UserRegister object containing the desired email and password.

        Returns:
            A UserRegistrationResponse object containing minimal information about the
            newly created user account (confirmation might still be required depending
            on Supabase settings).

        Raises:
            EmailExistsException: If a user with the given email already exists.
            PasswordPolicyException: If the provided password does not meet Supabase's
                                     configured requirements (e.g., length, complexity).
            AuthServiceException: For unexpected errors during the registration process.
        """
        try:
            print(
                f"Attempting registration for user: {register_data.email}"
            )  # MVP Logging
            # Call the Supabase client's sign-up method
            response = await self.auth.sign_up(
                {
                    "email": register_data.email,
                    "password": register_data.password,
                    # Options like 'data' for user_metadata can be added here if needed
                }
            )

            # Check if the response contains the newly created user object
            if response and response.user:
                # Note: Supabase might require email confirmation depending on settings.
                print(
                    f"Registration successful for user: {register_data.email} (Confirmation might be required)"
                )  # MVP Logging

                # Validate and structure the minimal user data using UserInfoMinimal schema
                try:
                    # Use model_validate (Pydantic v2)
                    user_info = UserInfoMinimal.model_validate(
                        response.user.model_dump()
                    )
                except Exception as pydantic_error:
                    print(
                        f"[ERROR] Pydantic validation error for UserInfoMinimal: {pydantic_error}. Supabase user data: {response.user.model_dump()}"
                    )  # MVP Error Logging
                    raise AuthServiceException(
                        detail="Failed to parse user information from registration service."
                    )

                # Construct the registration response
                registration_response = UserRegistrationResponse(user=user_info)
                # Note: Supabase V1 might have included session here, V2 often returns user only.
                # Adjust based on observed Supabase behavior if session data is needed immediately.
                return registration_response
            else:
                # Handle unexpected response structure from Supabase sign_up
                print(
                    f"[ERROR] Unexpected response structure during registration for {register_data.email}: {response}"
                )  # MVP Error Logging
                raise AuthServiceException(
                    detail="Invalid response received from registration service."
                )

        except AuthApiError as e:
            # Handle specific errors raised by the Supabase auth library
            self._handle_auth_api_error(
                e, context="register"
            )  # Delegates to helper method
        except Exception as e:
            # Catch any other unexpected exceptions
            print(
                f"[ERROR] Unexpected error during registration for {register_data.email}:"
            )  # MVP Error Logging
            traceback.print_exc()  # Print detailed traceback for debugging
            raise AuthServiceException(
                detail="An unexpected error occurred during registration."
            )

    def _handle_auth_api_error(self, error: AuthApiError, context: str):
        """
        Analyzes a GoTrue AuthApiError and raises a more specific custom application exception.
        This centralizes the mapping logic from Supabase errors to application-defined errors.

        Args:
            error: The original AuthApiError exception from the gotrue-py library.
            context: A string indicating the operation being performed ('login' or 'register')
                     to provide context for error interpretation.

        Raises:
            AuthenticationFailedException: For login failures due to bad credentials or unconfirmed email.
            EmailExistsException: For registration failures because the email is already in use.
            PasswordPolicyException: For registration failures due to weak passwords.
            AuthServiceException: For other unhandled or generic Supabase auth errors.
        """
        # Attempt to extract status code and message from the error object
        status_code = getattr(error, "status", None)
        details = getattr(
            error, "message", str(error)
        ).lower()  # Normalize message for checks

        print(
            f"[WARNING] AuthApiError during {context}: Status={status_code}, Message='{details}'"
        )  # MVP Warning Log

        if context == "login":
            # Check for common login failure reasons based on status code and message content
            if status_code == 400 and (
                "invalid login credentials" in details
                or "email not confirmed" in details
            ):
                print(
                    "Authentication failed for login: Invalid credentials or email not confirmed."
                )  # MVP Log
                raise AuthenticationFailedException(
                    detail="Invalid credentials or email not confirmed."
                )
            else:
                # Handle other potential login errors
                print(f"Unhandled AuthApiError during login: {details}")  # MVP Log
                # Raise a generic service exception for unmapped login errors
                raise AuthServiceException(
                    detail=f"Authentication service error: {getattr(error, 'message', 'Login failed')}"
                )

        elif context == "register":
            # Check for common registration failure reasons
            if status_code == 400 and (
                "user already registered" in details or "already exists" in details
            ):
                print("Registration failed: Email already exists.")  # MVP Log
                raise EmailExistsException()  # Custom exception has a default detail message
            elif status_code == 422 and (
                "password should be" in details or "password is too weak" in details
            ):
                # Extract the specific password policy message from Supabase if possible
                specific_detail = getattr(
                    error, "message", "Password does not meet requirements."
                )
                print(
                    f"Registration failed: Password policy violation - {specific_detail}"
                )  # MVP Log
                raise PasswordPolicyException(detail=specific_detail)
            elif status_code == 400 and (
                "password" in details
            ):  # Broader check for password issues
                specific_detail = getattr(error, "message", "check policy")
                print(
                    f"Registration failed: Password validation failed - {specific_detail}"
                )  # MVP Log
                raise PasswordPolicyException(
                    detail=f"Password validation failed: {specific_detail}"
                )
            elif status_code == 400 and (
                "email" in details
            ):  # Handle potential email format issues server-side
                specific_detail = getattr(error, "message", "check input")
                print(
                    f"Registration failed: Email validation failed - {specific_detail}"
                )  # MVP Log
                raise AuthServiceException(
                    detail=f"Email validation failed: {specific_detail}"
                )
            else:
                # Handle other potential registration errors
                print(
                    f"Unhandled AuthApiError during registration: {details}"
                )  # MVP Log
                raise AuthServiceException(
                    detail=f"Authentication service error: {getattr(error, 'message', 'Registration failed')}"
                )
        else:
            # Fallback for unknown contexts
            print(
                f"Unhandled AuthApiError in unknown context '{context}': {details}"
            )  # MVP Log
            raise AuthServiceException(detail="Unhandled authentication service error.")
