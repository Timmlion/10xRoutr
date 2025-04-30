# src/services/custom_exceptions.py

# This module defines custom exception classes used throughout the application,
# primarily within the service layer, to indicate specific error conditions.
# This allows for more granular error handling in the API endpoints.


class ServiceException(Exception):
    """
    Base class for all custom exceptions originating from the service layer.
    Allows catching general service errors.
    """

    def __init__(self, detail: str = "Service layer error"):
        self.detail = detail  # Store the error message for potential use in responses
        super().__init__(self.detail)


class DatabaseException(ServiceException):
    """
    Raised for errors related to database operations (e.g., connection issues, query failures)
    that are not covered by more specific exceptions like NotFoundException or conflict errors.
    Inherits from ServiceException.
    """

    def __init__(self, detail: str = "Database error occurred"):
        super().__init__(detail)


class NotFoundException(ServiceException):
    """
    Raised when a requested resource (e.g., a link, a rule, a user) cannot be found.
    Inherits from ServiceException. Specific types like LinkNotFoundException inherit from this.
    """

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail)


# --- Authentication Service Specific Exceptions ---


class AuthServiceException(ServiceException):
    """
    Base class for exceptions specifically related to the authentication service (AuthService).
    Inherits from the general ServiceException.
    """

    def __init__(self, detail: str = "Authentication service error"):
        super().__init__(detail)


class AuthenticationFailedException(AuthServiceException):
    """
    Raised when user login fails due to invalid credentials, unconfirmed email, etc.
    Inherits from AuthServiceException.
    """

    def __init__(self, detail: str = "Invalid login credentials"):
        super().__init__(detail)


class EmailExistsException(AuthServiceException):
    """
    Raised during user registration when the provided email address is already in use.
    Inherits from AuthServiceException.
    """

    def __init__(self, detail: str = "Email address already registered"):
        super().__init__(detail)


class PasswordPolicyException(AuthServiceException):
    """
    Raised during user registration or password change when the provided password
    does not meet the defined complexity or length requirements.
    Inherits from AuthServiceException.
    """

    def __init__(self, detail: str = "Password does not meet complexity requirements"):
        super().__init__(detail)


# --- Link and Rule Service Specific Exceptions ---


class AliasConflictException(DatabaseException):
    """
    Raised when attempting to create a link with an alias that already exists for the user.
    Inherits from DatabaseException as it often relates to uniqueness constraints.
    """

    def __init__(self, detail: str = "Alias already exists"):
        super().__init__(detail)


class ParentLinkNotFoundException(NotFoundException):
    """
    Raised when an operation on a rule fails because the parent link
    associated with it cannot be found or accessed by the user.
    Inherits from the general NotFoundException.
    """

    def __init__(self, detail: str = "Parent link not found or access denied."):
        super().__init__(detail)


class PriorityConflictException(DatabaseException):
    """
    Raised when attempting to create or update a rule with a priority
    that already exists for another rule under the same parent link.
    Inherits from DatabaseException as it relates to uniqueness constraints.
    """

    def __init__(self, detail: str = "Priority conflict for this link"):
        super().__init__(detail)


class ValidationException(ServiceException):
    """
    Raised for general validation errors identified within the service layer's
    business logic (distinct from Pydantic schema validation errors).
    Inherits from ServiceException.
    """

    def __init__(self, detail: str = "Business logic validation failed"):
        super().__init__(detail)


class LinkNotFoundException(NotFoundException):
    """
    Raised specifically during the public redirection process when the requested
    link alias does not correspond to any existing link in the database.
    Inherits from the general NotFoundException.
    """

    def __init__(self, detail: str = "Link alias not found."):
        super().__init__(detail)
