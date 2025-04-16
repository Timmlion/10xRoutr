# src/services/auth_service.py

import logging
from supabase_py_async import AsyncClient  # Lub from supabase import Client

# Importuj typy wyjątków GoTrue/Auth, które faktycznie zwraca Twoja wersja biblioteki
# `AuthApiError` jest często używany jako bazowy lub jedyny typ błędu API.
from gotrue.errors import AuthApiError

# Importuj niestandardowe wyjątki
from src.services.custom_exceptions import (
    AuthenticationFailedException,
    EmailExistsException,
    PasswordPolicyException,
    AuthServiceException,
    ServiceException,  # Importuj też bazowy, jeśli potrzebny
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

# Konfiguracja logowania dla tego modułu
logger = logging.getLogger(__name__)


class AuthService:
    """
    Service layer for handling authentication logic using Supabase Auth.
    """

    def __init__(self, supabase_client: AsyncClient):  # Oczekuje klienta Supabase
        """
        Initializes the AuthService.

        Args:
            supabase_client: An instance of the Supabase async client.
                             This client is typically initialized with the anon key
                             as these operations don't require prior user authentication.
        """
        self.supabase = supabase_client
        self.auth = supabase_client.auth  # Skrót do modułu auth klienta

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
            logger.info(f"Attempting login for user: {login_data.email}")
            # Wywołanie metody Supabase do logowania
            response = await self.auth.sign_in_with_password(
                {"email": login_data.email, "password": login_data.password}
            )

            # Sprawdzenie odpowiedzi - struktura może zależeć od wersji supabase-py
            # Zakładamy, że sukces zwraca obiekt z atrybutami session i user
            if response and response.session and response.user:
                logger.info(f"Login successful for user: {login_data.email}")

                # Mapowanie danych użytkownika Supabase na nasz model UserInfo
                # Używamy .dict() do konwersji obiektu User z supabase-py na słownik
                # (upewnij się, że atrybuty pasują do UserInfo lub dostosuj UserInfo)
                try:
                    user_info = UserInfo.model_validate(
                        response.user.dict()
                    )  # Pydantic v2
                except Exception as pydantic_error:
                    logger.error(
                        f"Pydantic validation error for UserInfo: {pydantic_error}. Supabase user data: {response.user.dict()}"
                    )
                    raise AuthServiceException(
                        detail="Failed to parse user information from authentication service."
                    )

                # Mapowanie danych sesji Supabase na nasz model TokenResponse
                # Dostosuj nazwy pól, jeśli odpowiedź Supabase ma inne
                try:
                    token_response = TokenResponse(
                        access_token=response.session.access_token,
                        token_type=getattr(
                            response.session, "token_type", "bearer"
                        ),  # Bezpieczniej z getattr i domyślną wartością
                        expires_in=getattr(response.session, "expires_in", None),
                        refresh_token=getattr(response.session, "refresh_token", None),
                        user=user_info,
                    )
                    return token_response
                except Exception as pydantic_error:
                    logger.error(
                        f"Pydantic validation error for TokenResponse: {pydantic_error}. Supabase session data: {response.session}"
                    )
                    raise AuthServiceException(
                        detail="Failed to parse session information from authentication service."
                    )

            else:
                # Jeśli odpowiedź nie ma oczekiwanej struktury, mimo braku wyjątku
                logger.error(
                    f"Unexpected response structure during login for {login_data.email}: {response}"
                )
                raise AuthServiceException(
                    detail="Invalid response received from authentication service."
                )

        except AuthApiError as e:
            # Użyj metody pomocniczej do zmapowania błędu
            self._handle_auth_api_error(e, context="login")
            # Linia poniżej nie zostanie osiągnięta, bo _handle_auth_api_error rzuca wyjątek
        except Exception as e:
            # Nieoczekiwany błąd (np. sieciowy, błąd w bibliotece, błąd walidacji Pydantic powyżej)
            logger.exception(
                f"Unexpected error during login for {login_data.email}: {e}"
            )
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
            logger.info(f"Attempting registration for user: {register_data.email}")
            # Wywołanie metody Supabase do rejestracji
            response = await self.auth.sign_up(
                {
                    "email": register_data.email,
                    "password": register_data.password,
                    # Można dodać 'options' jeśli potrzebne, np. 'email_redirect_to'
                }
            )

            # Sprawdzenie odpowiedzi - zakładamy, że sukces zwraca obiekt UserResponse z atrybutem user
            if response and response.user:
                logger.info(
                    f"Registration successful for user: {register_data.email} (Confirmation might be required)"
                )

                # Mapowanie danych użytkownika Supabase na nasz model UserInfoMinimal
                # Używamy UserInfoMinimal, bo odpowiedź z sign_up może być mniej szczegółowa
                try:
                    user_info = UserInfoMinimal.model_validate(
                        response.user.dict()
                    )  # Pydantic v2
                except Exception as pydantic_error:
                    logger.error(
                        f"Pydantic validation error for UserInfoMinimal: {pydantic_error}. Supabase user data: {response.user.dict()}"
                    )
                    raise AuthServiceException(
                        detail="Failed to parse user information from registration service."
                    )

                # Stworzenie odpowiedzi - session może być None jeśli wymagana jest weryfikacja email
                registration_response = UserRegistrationResponse(
                    user=user_info
                    # session=response.session # Można dodać, jeśli session jest potrzebne i zwracane
                )
                return registration_response
            else:
                # Jeśli odpowiedź nie ma oczekiwanej struktury
                logger.error(
                    f"Unexpected response structure during registration for {register_data.email}: {response}"
                )
                raise AuthServiceException(
                    detail="Invalid response received from registration service."
                )

        except AuthApiError as e:
            # Użyj metody pomocniczej do zmapowania błędu
            self._handle_auth_api_error(e, context="register")
            # Linia poniżej nie zostanie osiągnięta
        except Exception as e:
            # Nieoczekiwany błąd
            logger.exception(
                f"Unexpected error during registration for {register_data.email}: {e}"
            )
            raise AuthServiceException(
                detail="An unexpected error occurred during registration."
            )

    def _handle_auth_api_error(self, error: AuthApiError, context: str):
        """
        Analyzes AuthApiError and raises a more specific custom exception.
        NOTE: The conditions for raising specific exceptions might need adjustment
              based on the exact error messages/codes returned by your Supabase version/config.
        """
        # Próbuj uzyskać status code i wiadomość z błędu
        status_code = getattr(error, "status", None)
        # Wiadomość może być w 'message' lub jako __str__
        details = getattr(error, "message", str(error)).lower()

        logger.warning(
            f"AuthApiError during {context}: Status={status_code}, Message='{details}'",
            exc_info=False,
        )  # Log without stack trace for expected errors

        if context == "login":
            # Sprawdź typowy komunikat lub status dla błędnego logowania
            if status_code == 400 and (
                "invalid login credentials" in details
                or "email not confirmed" in details
            ):
                # Możemy potraktować niepotwierdzony email jako błąd logowania
                raise AuthenticationFailedException(
                    detail="Invalid credentials or email not confirmed."
                )
            else:
                # Inne błędy podczas logowania traktujemy jako błędy serwisu auth
                raise AuthServiceException(
                    detail="Authentication service error during login."
                )

        elif context == "register":
            # Sprawdź typowe komunikaty/statusy dla błędów rejestracji
            if status_code == 400 and (
                "user already registered" in details or "already exists" in details
            ):
                raise EmailExistsException()
            # Supabase może zwracać 422 dla błędów walidacji hasła
            elif status_code == 422 and (
                "password should be" in details or "password is too weak" in details
            ):
                # Próbuj przekazać oryginalny komunikat, jeśli to możliwe
                specific_detail = getattr(
                    error, "message", "Password does not meet requirements."
                )
                raise PasswordPolicyException(detail=specific_detail)
            # Ogólniejszy fallback dla błędów hasła
            elif status_code == 400 and ("password" in details):
                raise PasswordPolicyException(
                    detail=f"Password validation failed: {getattr(error, 'message', 'check policy')}"
                )
            # Ogólniejszy fallback dla błędów email (jeśli nie złapany jako 'already registered')
            elif status_code == 400 and ("email" in details):
                raise AuthServiceException(
                    detail=f"Email validation failed: {getattr(error, 'message', 'check input')}"
                )
            else:
                # Inne błędy podczas rejestracji
                raise AuthServiceException(
                    detail="Authentication service error during registration."
                )
        else:
            # Nieznany kontekst - nie powinno się zdarzyć
            raise AuthServiceException(detail="Unhandled authentication service error.")
