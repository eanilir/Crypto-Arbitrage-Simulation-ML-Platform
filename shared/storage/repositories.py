from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Iterable

from shared.domain import SpreadOpportunity


class InMemoryOpportunityRepository:
    """In-memory repository for arbitrage opportunities."""

    def __init__(self) -> None:
        self._opportunities: dict[str, list[SpreadOpportunity]] = defaultdict(list)
        self._lock = Lock()

    def save_opportunity(self, opportunity: SpreadOpportunity) -> SpreadOpportunity:
        with self._lock:
            self._opportunities[opportunity.symbol].append(opportunity)
        return opportunity

    def list_recent(
        self,
        symbol: str | None = None,
        *,
        limit: int | None = None,
    ) -> list[SpreadOpportunity]:
        with self._lock:
            items: Iterable[SpreadOpportunity]
            if symbol is None:
                items = [
                    entry for bucket in self._opportunities.values() for entry in bucket
                ]
            else:
                items = self._opportunities.get(symbol, [])
        ordered = sorted(items, key=lambda item: item.detected_at, reverse=True)
        if limit is not None:
            return ordered[:limit]
        return ordered

    def clear(self) -> None:
        with self._lock:
            self._opportunities.clear()
