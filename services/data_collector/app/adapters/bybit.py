from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.domain import MarketQuote

from .base import ExchangeAdapter
from ..standardization import MarketDataStandardizer

_STANDARDIZER = MarketDataStandardizer()


class BybitAdapter(ExchangeAdapter):
    name = "bybit"
    rest_base_url = "https://api.bybit.com"
    websocket_url = "wss://stream.bybit.com/v5/public/spot"

    def rest_request_url(self, symbol: str) -> str:
        return (
            f"{self.rest_base_url}/v5/market/tickers?category=spot"
            f"&symbol={self.exchange_symbol(symbol)}"
        )

    def websocket_request(self, symbol: str) -> tuple[str, str]:
        message = {
            "op": "subscribe",
            "args": [f"tickers.{self.exchange_symbol(symbol)}"],
        }
        import json

        return self.websocket_url, json.dumps(message)

    def parse_rest_quote(
        self, payload: Any, symbol: str, received_at: datetime
    ) -> MarketQuote:
        standardize = _STANDARDIZER.standardize_rest
        return standardize(self.name, payload, symbol, received_at)

    def parse_websocket_quote(
        self, payload: Any, received_at: datetime
    ) -> MarketQuote | None:
        standardize = _STANDARDIZER.standardize_websocket
        return standardize(self.name, payload, received_at)
