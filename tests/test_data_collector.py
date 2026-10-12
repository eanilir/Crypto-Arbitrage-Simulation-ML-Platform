import asyncio
import json
import unittest
from datetime import datetime, timezone

from services.data_collector.app.adapters import (
    BinanceAdapter,
    BybitAdapter,
    OKXAdapter,
)
from services.data_collector.app.collectors import (
    QuoteDeduplicator,
    RetryPolicy,
)
from services.data_collector.app.collectors.websocket import (
    WebSocketMarketDataCollector,
)


class FakeSocket:
    def __init__(self, messages: list[str]) -> None:
        self.messages = iter(messages)
        self.sent: list[str] = []

    async def __aenter__(self) -> "FakeSocket":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        return next(self.messages)


class FakeConnect:
    def __init__(self, socket: FakeSocket) -> None:
        self.socket = socket

    def __call__(self, _: str) -> FakeSocket:
        return self.socket


class DataCollectorTests(unittest.TestCase):
    def test_exchange_adapters_normalize_rest_payloads(self) -> None:
        received_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        binance = BinanceAdapter().parse_rest_quote(
            {
                "bidPrice": "100",
                "askPrice": "101",
                "lastPrice": "100.5",
                "volume": "2",
            },
            "BTC/USDT",
            received_at,
        )
        bybit = BybitAdapter().parse_rest_quote(
            {
                "result": {
                    "list": [
                        {
                            "bid1Price": "100",
                            "ask1Price": "101",
                            "lastPrice": "100.5",
                            "volume24h": "2",
                        }
                    ]
                }
            },
            "BTC/USDT",
            received_at,
        )
        okx = OKXAdapter().parse_rest_quote(
            {
                "data": [
                    {
                        "bidPx": "100",
                        "askPx": "101",
                        "last": "100.5",
                        "vol24h": "2",
                        "ts": "1767225600000",
                    }
                ]
            },
            "BTC/USDT",
            received_at,
        )
        self.assertEqual(
            {binance.exchange, bybit.exchange, okx.exchange},
            {"binance", "bybit", "okx"},
        )
        self.assertEqual(binance.symbol, "BTC/USDT")
        self.assertEqual(okx.last, 100.5)

    def test_deduplicator_rejects_same_quote(self) -> None:
        quote = BinanceAdapter().parse_rest_quote(
            {"bidPrice": "100", "askPrice": "101"},
            "BTC/USDT",
            datetime.now(timezone.utc),
        )
        deduplicator = QuoteDeduplicator()
        self.assertFalse(deduplicator.is_duplicate(quote))
        self.assertTrue(deduplicator.is_duplicate(quote))

    def test_websocket_collector_reconnects_and_deduplicates(self) -> None:
        payload = json.dumps(
            {"s": "BTCUSDT", "b": "100", "a": "101", "E": 1767225600000}
        )
        socket = FakeSocket([payload, payload])
        collector = WebSocketMarketDataCollector(
            connect=FakeConnect(socket),
            retry_policy=RetryPolicy(attempts=1),
        )

        async def collect_one() -> list[object]:
            quotes = []
            adapter = BinanceAdapter()
            async for quote in collector.stream_quotes(adapter, "BTC/USDT"):
                quotes.append(quote)
                if len(quotes) == 1:
                    break
            return quotes

        quotes = asyncio.run(collect_one())
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].symbol, "BTC/USDT")


if __name__ == "__main__":
    unittest.main()
