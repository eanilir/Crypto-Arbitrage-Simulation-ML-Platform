class CollectorError(Exception):
    """Base error for market data collection."""


class CollectorTransportError(CollectorError):
    """Raised when an exchange cannot be reached after retries."""


class CollectorPayloadError(CollectorError):
    """Raised when an exchange response cannot be normalized."""


class MissingMarketFieldError(CollectorPayloadError):
    """Raised when a required normalized market field is absent."""
