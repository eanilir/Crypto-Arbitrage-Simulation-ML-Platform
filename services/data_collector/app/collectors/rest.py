from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from shared.domain import MarketQuote

from ..adapters.base import ExchangeAdapter
from ..errors import CollectorTransportError
from ..logging import get_collector_logger, log_event
from .base import RetryPolicy, retry_call


class RestMarketDataCollector:
    def __init__(
        self,
        *,
        timeout_seconds: float = 5.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retry_policy = retry_policy or RetryPolicy()

    def fetch_quote(
        self,
        adapter: ExchangeAdapter,
        symbol: str,
    ) -> MarketQuote:
        url = adapter.rest_request_url(symbol)
        logger = get_collector_logger(adapter.name)

        def request() -> MarketQuote:
            try:
                request = Request(url, headers={"Accept": "application/json"})
                timeout = self.timeout_seconds
                with urlopen(request, timeout=timeout) as response:
                    payload = json.load(response)
                received_at = datetime.now(timezone.utc)
                result = adapter.parse_rest_quote(payload, symbol, received_at)
                log_event(
                    logger,
                    "quote_received",
                    exchange=adapter.name,
                    symbol=result.symbol,
                )
                return result
            except (OSError, ValueError, KeyError) as error:
                raise CollectorTransportError(
                    f"REST request failed for {adapter.name}: {url}"
                ) from error

        return retry_call(
            request,
            self.retry_policy,
            exchange=adapter.name,
            event="rest_request",
        )
