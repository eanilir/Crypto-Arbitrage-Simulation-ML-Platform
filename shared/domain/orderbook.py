"""Order-book value objects shared by the engine, dataset builder and simulator."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

Level = tuple[float, float]  # (price, quantity)


@dataclass(frozen=True)
class OrderBook:
    exchange: str
    symbol: str
    bids: tuple[Level, ...]  # best (highest) first
    asks: tuple[Level, ...]  # best (lowest) first
    received_at: datetime
    event_at: datetime | None = None

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> OrderBook:
        """Build a book from one ``market_depth`` NDJSON record."""
        event = record.get("event_timestamp")
        return cls(
            exchange=str(record["exchange"]),
            symbol=str(record["symbol"]),
            bids=tuple((float(p), float(q)) for p, q in record["bids"]),
            asks=tuple((float(p), float(q)) for p, q in record["asks"]),
            received_at=datetime.fromisoformat(record["received_timestamp"]),
            event_at=datetime.fromisoformat(event) if event else None,
        )

    def is_valid(self) -> bool:
        if not self.bids or not self.asks:
            return False
        for price, qty in (*self.bids, *self.asks):
            if not (math.isfinite(price) and math.isfinite(qty)) or price <= 0 or qty < 0:
                return False
        return self.bids[0][0] <= self.asks[0][0]  # crossed books are not tradable


def walk_levels(levels: Sequence[Level], quantity: float) -> float | None:
    """Quote-currency value of filling ``quantity`` through ``levels``.

    Returns ``None`` when the visible book is too shallow; liquidity is never invented.
    """
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    remaining, value = quantity, 0.0
    for price, available in levels:
        take = min(remaining, available)
        value += take * price
        remaining -= take
        if remaining <= 1e-12:
            return value
    return None
