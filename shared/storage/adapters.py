from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Any

from shared.domain import MarketQuote


class InMemoryMarketDataAdapter:
    """A simple in-memory storage adapter for market quotes."""

    def __init__(self) -> None:
        self._quotes: dict[str, list[MarketQuote]] = defaultdict(list)
        self._lock = Lock()

    def save_quote(self, quote: MarketQuote) -> MarketQuote:
        with self._lock:
            self._quotes[quote.symbol].append(quote)
        return quote

    def get_latest_quote(self, symbol: str) -> MarketQuote | None:
        history = self.get_history(symbol)
        if not history:
            return None
        return max(history, key=lambda item: item.timestamp)

    def get_history(
        self, symbol: str, *, limit: int | None = None
    ) -> list[MarketQuote]:
        with self._lock:
            items = list(self._quotes.get(symbol, []))
        items = sorted(items, key=lambda item: item.timestamp)
        if limit is not None:
            return items[-limit:]
        return items

    def __len__(self) -> int:
        with self._lock:
            return sum(len(items) for items in self._quotes.values())

    def clear(self) -> None:
        with self._lock:
            self._quotes.clear()
