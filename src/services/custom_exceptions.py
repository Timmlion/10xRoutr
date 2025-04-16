# src/services/custom_exceptions.py


class ServiceException(Exception):
    """Base class for service layer exceptions."""

    def __init__(self, detail: str = "Service layer error"):
        self.detail = detail
        super().__init__(self.detail)


class DatabaseException(ServiceException):
    """Raised for general database errors."""

    def __init__(self, detail: str = "Database error occurred"):
        super().__init__(detail)


class NotFoundException(ServiceException):
    """Raised when a resource is not found."""

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail)


# --- Wyjątki specyficzne dla AuthService ---


class AuthServiceException(ServiceException):
    """Base exception for authentication service errors."""

    def __init__(self, detail: str = "Authentication service error"):
        super().__init__(detail)


class AuthenticationFailedException(AuthServiceException):
    """Raised for invalid login credentials."""

    def __init__(self, detail: str = "Invalid login credentials"):
        super().__init__(detail)


class EmailExistsException(AuthServiceException):
    """Raised when trying to register with an existing email."""

    def __init__(self, detail: str = "Email address already registered"):
        super().__init__(detail)


class PasswordPolicyException(AuthServiceException):
    """Raised when a password does not meet complexity requirements."""

    def __init__(self, detail: str = "Password does not meet complexity requirements"):
        super().__init__(detail)


# --- Wyjątki specyficzne dla LinkService/RuleService ---
# (Mogą być dodane później lub już istnieć)
class AliasConflictException(
    DatabaseException
):  # Może dziedziczyć po DatabaseException
    """Raised when an alias conflict occurs during creation."""

    def __init__(self, detail: str = "Alias already exists"):
        super().__init__(detail)


class ParentLinkNotFoundException(NotFoundException):
    """Raised when the parent link for a rule operation is not found or not owned."""

    def __init__(self, detail: str = "Parent link not found or access denied"):
        super().__init__(detail)


class PriorityConflictException(
    DatabaseException
):  # Może dziedziczyć po DatabaseException
    """Raised when a rule priority conflict occurs."""

    def __init__(self, detail: str = "Priority conflict for this link"):
        super().__init__(detail)


class ValidationException(ServiceException):
    """Raised for business logic validation errors."""

    def __init__(self, detail: str = "Business logic validation failed"):
        super().__init__(detail)


class LinkNotFoundException(
    NotFoundException
):  # Dziedziczy po ogólnym NotFoundException
    """Raised specifically when a link alias is not found during redirection."""

    def __init__(self, detail: str = "Link alias not found."):
        super().__init__(detail)
