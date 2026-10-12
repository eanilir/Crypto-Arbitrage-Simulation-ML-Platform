from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from shared.domain import MarketQuote


class ExchangeAdapter(ABC):
    name: str
    rest_base_url: str
    websocket_url: str

    @abstractmethod
    def rest_request_url(self, symbol: str) -> str:
        """Build the public ticker endpoint URL."""

    @abstractmethod
    def websocket_request(self, symbol: str) -> tuple[str, str]:
        """Return the WebSocket URL and subscription message."""

    @abstractmethod
    def parse_rest_quote(
        self, payload: Any, symbol: str, received_at: datetime
    ) -> MarketQuote:
        """Convert an exchange REST payload into a common quote."""

    @abstractmethod
    def parse_websocket_quote(
        self, payload: Any, received_at: datetime
    ) -> MarketQuote | None:
        """Convert an exchange WebSocket payload into a common quote."""

    @staticmethod
    def exchange_symbol(symbol: str, separator: str = "") -> str:
        return symbol.replace("/", separator).upper()
