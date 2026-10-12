from __future__ import annotations

from datetime import datetime
from typing import Any

from shared.domain import MarketQuote

from .base import ExchangeAdapter
from ..standardization import MarketDataStandardizer

_STANDARDIZER = MarketDataStandardizer()


class BinanceAdapter(ExchangeAdapter):
    name = "binance"
    rest_base_url = "https://api.binance.com"
    websocket_url = "wss://stream.binance.com:9443/ws"

    def rest_request_url(self, symbol: str) -> str:
        return (
            f"{self.rest_base_url}/api/v3/ticker/24hr?"
            f"symbol={self.exchange_symbol(symbol)}"
        )

    def websocket_request(self, symbol: str) -> tuple[str, str]:
        stream = f"{self.exchange_symbol(symbol).lower()}@bookTicker"
        return f"{self.websocket_url}/{stream}", ""

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
