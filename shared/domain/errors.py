class DomainError(Exception):
    """Base error for shared domain logic."""


class DataValidationError(DomainError):
    """Raised when incoming market data does not match the common schema."""
