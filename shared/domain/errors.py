class DomainError(Exception):
    """Base error for shared domain logic."""


class DataValidationError(DomainError):
    """Raised when incoming market data does not match the common schema."""


class InvalidTimestampError(DataValidationError):
    """Raised when a timestamp is malformed or not datetime-like."""


class InvalidSymbolError(DataValidationError):
    """Raised when a trading symbol cannot be normalized."""


class InvalidPriceError(DataValidationError):
    """Raised when a price or volume is not a finite positive number."""


class InvalidSpreadError(DataValidationError):
    """Raised when spread values are invalid."""


class InvalidOpportunityError(DataValidationError):
    """Raised when an arbitrage opportunity is invalid."""
