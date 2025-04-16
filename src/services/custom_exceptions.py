# src/services/custom_exceptions.py


class ServiceException(Exception):
    """Base class for service layer exceptions."""

    def __init__(self, detail: str = "Service layer error"):
        self.detail = detail
        super().__init__(self.detail)


class AliasConflictException(ServiceException):
    """Raised when an alias conflict occurs during creation."""

    def __init__(self, detail: str = "Alias already exists"):
        super().__init__(detail)


class DatabaseException(ServiceException):
    """Raised for general database errors."""

    def __init__(self, detail: str = "Database error occurred"):
        super().__init__(detail)


class NotFoundException(ServiceException):
    """Raised when a resource is not found."""

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(detail)
