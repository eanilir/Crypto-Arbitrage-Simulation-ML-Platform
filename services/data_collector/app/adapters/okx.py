from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.domain import MarketQuote

from .base import ExchangeAdapter
from ..standardization import MarketDataStandardizer

_STANDARDIZER = MarketDataStandardizer()


class OKXAdapter(ExchangeAdapter):
    name = "okx"
    rest_base_url = "https://www.okx.com"
    websocket_url = "wss://ws.okx.com:8443/ws/v5/public"

    def rest_request_url(self, symbol: str) -> str:
        exchange_symbol = self.exchange_symbol(symbol, "-")
        path = "/api/v5/market/ticker"
        return f"{self.rest_base_url}{path}?instId={exchange_symbol}"

    def websocket_request(self, symbol: str) -> tuple[str, str]:
        import json

        message = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "tickers",
                    "instId": self.exchange_symbol(symbol, "-"),
                }
            ],
        }
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
