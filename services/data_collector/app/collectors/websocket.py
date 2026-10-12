from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable

from shared.domain import MarketQuote

from ..adapters.base import ExchangeAdapter
from ..logging import get_collector_logger, log_event
from .base import QuoteDeduplicator, RetryPolicy

ConnectFactory = Callable[[str], Any]


class WebSocketMarketDataCollector:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        retry_policy: RetryPolicy | None = None,
        connect: ConnectFactory | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or RetryPolicy()
        self.connect = connect or self._default_connect

    async def stream_quotes(
        self, adapter: ExchangeAdapter, symbol: str
    ) -> AsyncGenerator[MarketQuote, None]:
        logger = get_collector_logger(adapter.name)
        deduplicator = QuoteDeduplicator()
        url, subscription = adapter.websocket_request(symbol)
        for attempt in range(1, self.retry_policy.attempts + 1):
            try:
                async with self.connect(url) as socket:
                    if subscription:
                        await socket.send(subscription)
                    log_event(
                        logger,
                        "websocket_connected",
                        exchange=adapter.name,
                        attempt=attempt,
                    )
                    while True:
                        raw = await asyncio.wait_for(
                            socket.recv(), timeout=self.timeout_seconds
                        )
                        if isinstance(raw, str):
                            payload = json.loads(raw)
                        else:
                            payload = raw
                        quote = adapter.parse_websocket_quote(
                            payload, datetime.now(timezone.utc)
                        )
                        if quote is None:
                            continue
                        if deduplicator.is_duplicate(quote):
                            continue
                        log_event(
                            logger,
                            "quote_received",
                            exchange=adapter.name,
                            symbol=quote.symbol,
                        )
                        yield quote
            except (
                asyncio.TimeoutError,
                OSError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                log_event(
                    logger,
                    "websocket_reconnect",
                    exchange=adapter.name,
                    attempt=attempt,
                    reason=type(error).__name__,
                )
                if attempt == self.retry_policy.attempts:
                    raise
                exponent = 2 ** (attempt - 1)
                backoff = self.retry_policy.backoff_seconds * exponent
                max_backoff = self.retry_policy.max_backoff_seconds
                await asyncio.sleep(min(backoff, max_backoff))

    @staticmethod
    def _default_connect(url: str) -> Any:
        try:
            import websockets
        except ImportError as error:
            raise RuntimeError(
                "Install 'websockets' to use live WebSocket collection"
            ) from error
        return websockets.connect(url)
