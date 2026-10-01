from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
import re

from .errors import (
    InvalidOpportunityError,
    InvalidPriceError,
    InvalidSpreadError,
    InvalidSymbolError,
)
from .time import normalize_timestamp

_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+/[A-Z0-9]+$")


def _require_number(value: float, field_name: str, *, positive: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise InvalidPriceError(f"{field_name} must be a finite number")
    if positive and value <= 0:
        raise InvalidPriceError(f"{field_name} must be greater than zero")
    return float(value)


def normalize_symbol(value: str) -> str:
    """Return the canonical BASE/QUOTE symbol form."""
    if not isinstance(value, str):
        raise InvalidSymbolError("symbol must be a string")
    normalized = value.strip().upper().replace("-", "/").replace("_", "/")
    if not _SYMBOL_PATTERN.fullmatch(normalized):
        raise InvalidSymbolError("symbol must use the canonical BASE/QUOTE format")
    return normalized


@dataclass(frozen=True)
class Exchange:
    name: str
    symbol_normalization: str = "upper"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidSymbolError("exchange name must be a non-empty string")
        if self.symbol_normalization != "upper":
            raise InvalidSymbolError("symbol_normalization must be 'upper'")


@dataclass(frozen=True)
class Symbol:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", normalize_symbol(self.value))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Price:
    value: float
    currency: str = "USD"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "value", _require_number(self.value, "price", positive=True)
        )
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise InvalidPriceError("price currency must be a non-empty string")
        object.__setattr__(self, "currency", self.currency.strip().upper())


@dataclass(frozen=True)
class MarketQuote:
    exchange: str
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    last: float | None = None
    volume: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.exchange, str) or not self.exchange.strip():
            raise InvalidSymbolError("exchange must be a non-empty string")
        object.__setattr__(self, "exchange", self.exchange.strip().lower())
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(self, "timestamp", normalize_timestamp(self.timestamp))
        object.__setattr__(self, "bid", _require_number(self.bid, "bid", positive=True))
        object.__setattr__(self, "ask", _require_number(self.ask, "ask", positive=True))
        if self.ask < self.bid:
            raise InvalidPriceError("ask must be greater than or equal to bid")
        if self.last is not None:
            object.__setattr__(
                self, "last", _require_number(self.last, "last", positive=True)
            )
        if self.volume is not None:
            object.__setattr__(
                self,
                "volume",
                _require_number(self.volume, "volume", positive=True),
            )


@dataclass(frozen=True)
class SpreadOpportunity:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    spread: float
    spread_percent: float
    estimated_fees: float
    estimated_slippage: float
    estimated_latency_cost: float
    net_profit: float
    detected_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        for field_name in ("buy_exchange", "sell_exchange"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidOpportunityError(
                    f"{field_name} must be a non-empty string"
                )
            object.__setattr__(self, field_name, value.strip().lower())
        if self.buy_exchange == self.sell_exchange:
            raise InvalidOpportunityError("buy and sell exchanges must differ")
        object.__setattr__(self, "spread", _require_number(self.spread, "spread"))
        object.__setattr__(
            self,
            "spread_percent",
            _require_number(self.spread_percent, "spread_percent"),
        )
        for field_name in (
            "estimated_fees",
            "estimated_slippage",
            "estimated_latency_cost",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_number(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self, "net_profit", _require_number(self.net_profit, "net_profit")
        )
        if self.spread < 0 or self.spread_percent < 0:
            raise InvalidSpreadError("spread values cannot be negative")
        object.__setattr__(self, "detected_at", normalize_timestamp(self.detected_at))


Opportunity = SpreadOpportunity
