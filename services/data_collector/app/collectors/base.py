from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import sleep
from typing import Callable, TypeVar

from shared.domain import MarketQuote

from ..logging import get_collector_logger, log_event

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.backoff_seconds < 0:
            raise ValueError("retry policy values must be valid")


class QuoteDeduplicator:
    def __init__(self, max_size: int = 10_000) -> None:
        self._keys: set[tuple[object, ...]] = set()
        self._order: deque[tuple[object, ...]] = deque()
        self.max_size = max_size

    def is_duplicate(self, quote: MarketQuote) -> bool:
        key = (
            quote.exchange,
            quote.symbol,
            quote.bid,
            quote.ask,
            quote.last,
            quote.volume,
        )
        if key in self._keys:
            return True
        self._keys.add(key)
        self._order.append(key)
        if len(self._order) > self.max_size:
            self._keys.remove(self._order.popleft())
        return False


def retry_call(
    operation: Callable[[], T],
    policy: RetryPolicy,
    *,
    exchange: str,
    event: str,
) -> T:
    logger = get_collector_logger(exchange)
    delay = policy.backoff_seconds
    for attempt in range(1, policy.attempts + 1):
        try:
            result = operation()
            log_event(logger, event, exchange=exchange, attempt=attempt)
            return result
        except Exception:
            log_event(logger, "retry", exchange=exchange, attempt=attempt)
            if attempt == policy.attempts:
                raise
            sleep(delay)
            delay = min(delay * 2, policy.max_backoff_seconds)
    raise RuntimeError("unreachable retry state")
