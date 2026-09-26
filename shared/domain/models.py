from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Exchange:
    name: str
    symbol_normalization: str = "upper"


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
