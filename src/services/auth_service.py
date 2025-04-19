# src/services/auth_service.py

# Usunięto: import logging
import traceback  # Potrzebne dla print_exc()

from supabase import AsyncClient  # <<< POPRAWIONY IMPORT

# Importuj typy wyjątków GoTrue/Auth
from gotrue.errors import AuthApiError

# Importuj niestandardowe wyjątki
from src.services.custom_exceptions import (
    AuthenticationFailedException,
    EmailExistsException,
    PasswordPolicyException,
    AuthServiceException,  # Zakładamy, że AuthServiceException jest zdefiniowane w custom_exceptions.py
    ServiceException,
)

# Importuj modele Pydantic (DTOs)
from src.schemas.auth import (
    UserLogin,
    UserRegister,
    TokenResponse,
    UserRegistrationResponse,
    UserInfo,
    UserInfoMinimal,
)

# Usunięto konfigurację loggera


class AuthService:
    """
    Service layer for handling authentication logic using Supabase Auth.
    """

    def __init__(self, supabase_client: AsyncClient):
        """
        Initializes the AuthService.

        Args:
            supabase_client: An instance of the Supabase async client
                             (typically initialized with the anon key).
        """
        self.supabase = supabase_client
        self.auth = supabase_client.auth

    async def login_user(self, login_data: UserLogin) -> TokenResponse:
        """
        Authenticates a user using email and password via Supabase Auth.

        Args:
            login_data: UserLogin schema containing email and password.

        Returns:
            TokenResponse schema containing access token, user info, etc.

        Raises:
            AuthenticationFailedException: If login credentials are invalid.
            AuthServiceException: For other Supabase or network errors during login.
        """
        try:
            print(
                f"Attempting login for user: {login_data.email}"
            )  # Zastąpiono logger.info
            response = await self.auth.sign_in_with_password(
                {"email": login_data.email, "password": login_data.password}
            )

            if response and response.session and response.user:
                print(
                    f"Login successful for user: {login_data.email}"
                )  # Zastąpiono logger.info

                try:
                    # Zakładamy, że response.user jest obiektem User z gotrue/supabase
                    # Używamy model_dump() w Pydantic v2 do serializacji
                    user_info = UserInfo.model_validate(response.user.model_dump())
                except Exception as pydantic_error:
                    # Zastąpiono logger.error
                    print(
                        f"[ERROR] Pydantic validation error for UserInfo: {pydantic_error}. Supabase user data: {response.user.model_dump()}"
                    )
                    raise AuthServiceException(
                        detail="Failed to parse user information from authentication service."
                    )

                try:
                    token_response = TokenResponse(
                        access_token=response.session.access_token,
                        token_type=getattr(response.session, "token_type", "bearer"),
                        expires_in=getattr(response.session, "expires_in", None),
                        refresh_token=getattr(response.session, "refresh_token", None),
                        user=user_info,
                    )
                    return token_response
                except Exception as pydantic_error:
                    # Zastąpiono logger.error
                    print(
                        f"[ERROR] Pydantic validation error for TokenResponse: {pydantic_error}. Supabase session data: {response.session}"
                    )
                    raise AuthServiceException(
                        detail="Failed to parse session information from authentication service."
                    )
            else:
                # Zastąpiono logger.error
                print(
                    f"[ERROR] Unexpected response structure during login for {login_data.email}: {response}"
                )
                # Jeśli brak wyjątku AuthApiError, a odpowiedź jest zła, podnosimy własny błąd
                raise AuthenticationFailedException(
                    detail="Invalid credentials."
                )  # Bardziej konkretny błąd niż AuthServiceException

        except AuthApiError as e:
            self._handle_auth_api_error(e, context="login")
        except Exception as e:
            # Zastąpiono logger.exception
            print(f"[ERROR] Unexpected error during login for {login_data.email}:")
            traceback.print_exc()
            raise AuthServiceException(
                detail="An unexpected error occurred during login."
            )

    async def register_user(
        self, register_data: UserRegister
    ) -> UserRegistrationResponse:
        """
        Registers a new user using Supabase Auth.

        Args:
            register_data: UserRegister schema containing email and password.

        Returns:
            UserRegistrationResponse schema containing information about the newly created user.

        Raises:
            EmailExistsException: If the email address is already registered.
            PasswordPolicyException: If the password does not meet complexity requirements.
            AuthServiceException: For other Supabase or network errors during registration.
        """
        try:
            print(
                f"Attempting registration for user: {register_data.email}"
            )  # Zastąpiono logger.info
            response = await self.auth.sign_up(
                {
                    "email": register_data.email,
                    "password": register_data.password,
                }
            )

            if response and response.user:
                print(  # Zastąpiono logger.info
                    f"Registration successful for user: {register_data.email} (Confirmation might be required)"
                )

                try:
                    # Używamy model_dump() w Pydantic v2
                    user_info = UserInfoMinimal.model_validate(
                        response.user.model_dump()
                    )
                except Exception as pydantic_error:
                    # Zastąpiono logger.error
                    print(
                        f"[ERROR] Pydantic validation error for UserInfoMinimal: {pydantic_error}. Supabase user data: {response.user.model_dump()}"
                    )
                    raise AuthServiceException(
                        detail="Failed to parse user information from registration service."
                    )

                registration_response = UserRegistrationResponse(user=user_info)
                return registration_response
            else:
                # Zastąpiono logger.error
                print(
                    f"[ERROR] Unexpected response structure during registration for {register_data.email}: {response}"
                )
                raise AuthServiceException(
                    detail="Invalid response received from registration service."
                )

        except AuthApiError as e:
            self._handle_auth_api_error(e, context="register")
        except Exception as e:
            # Zastąpiono logger.exception
            print(
                f"[ERROR] Unexpected error during registration for {register_data.email}:"
            )
            traceback.print_exc()
            raise AuthServiceException(
                detail="An unexpected error occurred during registration."
            )

    def _handle_auth_api_error(self, error: AuthApiError, context: str):
        """
        Analyzes AuthApiError and raises a more specific custom exception.
        """
        status_code = getattr(error, "status", None)
        details = getattr(error, "message", str(error)).lower()

        # Zastąpiono logger.warning
        print(
            f"[WARNING] AuthApiError during {context}: Status={status_code}, Message='{details}'"
        )

        if context == "login":
            if status_code == 400 and (
                "invalid login credentials" in details
                or "email not confirmed" in details
            ):
                print(
                    f"Authentication failed for login: Invalid credentials or email not confirmed."
                )  # Logowanie MVP
                raise AuthenticationFailedException(
                    detail="Invalid credentials or email not confirmed."
                )
            else:
                print(
                    f"Unhandled AuthApiError during login: {details}"
                )  # Logowanie MVP
                raise AuthServiceException(  # Lub AuthenticationFailedException jako ogólny błąd logowania?
                    detail=f"Authentication service error: {getattr(error, 'message', 'Login failed')}"
                )

        elif context == "register":
            if status_code == 400 and (
                "user already registered" in details or "already exists" in details
            ):
                print(f"Registration failed: Email already exists.")  # Logowanie MVP
                raise EmailExistsException()  # Wyjątek już niesie domyślny komunikat
            elif status_code == 422 and (
                "password should be" in details or "password is too weak" in details
            ):
                specific_detail = getattr(
                    error, "message", "Password does not meet requirements."
                )
                print(
                    f"Registration failed: Password policy violation - {specific_detail}"
                )  # Logowanie MVP
                raise PasswordPolicyException(detail=specific_detail)
            elif status_code == 400 and ("password" in details):
                specific_detail = getattr(error, "message", "check policy")
                print(
                    f"Registration failed: Password validation failed - {specific_detail}"
                )  # Logowanie MVP
                raise PasswordPolicyException(
                    detail=f"Password validation failed: {specific_detail}"
                )
            elif status_code == 400 and ("email" in details):
                specific_detail = getattr(error, "message", "check input")
                print(
                    f"Registration failed: Email validation failed - {specific_detail}"
                )  # Logowanie MVP
                raise AuthServiceException(
                    detail=f"Email validation failed: {specific_detail}"
                )
            else:
                print(
                    f"Unhandled AuthApiError during registration: {details}"
                )  # Logowanie MVP
                raise AuthServiceException(
                    detail=f"Authentication service error: {getattr(error, 'message', 'Registration failed')}"
                )
        else:
            print(
                f"Unhandled AuthApiError in unknown context '{context}': {details}"
            )  # Logowanie MVP
            raise AuthServiceException(detail="Unhandled authentication service error.")
