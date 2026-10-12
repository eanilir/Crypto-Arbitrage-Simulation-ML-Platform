import unittest
from datetime import datetime, timezone

from services.data_collector.app.errors import (
    CollectorPayloadError,
    MissingMarketFieldError,
)
from services.data_collector.app.standardization import MarketDataStandardizer


class StandardizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.standardizer = MarketDataStandardizer()
        self.received_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_exchange_payloads_share_one_quote_shape(self) -> None:
        quotes = [
            self.standardizer.standardize_rest(
                "binance",
                {
                    "bidPrice": "100",
                    "askPrice": "101",
                    "lastPrice": "100.5",
                    "volume": "2",
                },
                "btc-usdt",
                self.received_at,
            ),
            self.standardizer.standardize_rest(
                "bybit",
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
                self.received_at,
            ),
            self.standardizer.standardize_rest(
                "okx",
                {
                    "data": [
                        {
                            "instId": "BTC-USDT",
                            "bidPx": "100",
                            "askPx": "101",
                            "last": "100.5",
                            "vol24h": "2",
                            "ts": "1767225600000",
                        }
                    ]
                },
                "BTC/USDT",
                self.received_at,
            ),
        ]
        self.assertEqual({quote.symbol for quote in quotes}, {"BTC/USDT"})
        self.assertEqual({quote.bid for quote in quotes}, {100.0})
        self.assertEqual({quote.ask for quote in quotes}, {101.0})
        self.assertEqual({quote.last for quote in quotes}, {100.5})
        self.assertEqual({quote.volume for quote in quotes}, {2.0})
        timestamps_are_utc = all(
            quote.timestamp.tzinfo == timezone.utc for quote in quotes
        )
        self.assertTrue(timestamps_are_utc)

    def test_missing_required_bid_is_rejected(self) -> None:
        with self.assertRaises(MissingMarketFieldError):
            self.standardizer.standardize_rest(
                "binance",
                {"askPrice": "101"},
                "BTC/USDT",
                self.received_at,
            )

    def test_malformed_numeric_value_is_rejected(self) -> None:
        with self.assertRaises(CollectorPayloadError):
            self.standardizer.standardize_rest(
                "okx",
                {"data": [{"bidPx": "bad", "askPx": "101"}]},
                "BTC/USDT",
                self.received_at,
            )

    def test_websocket_timestamp_is_converted_from_milliseconds(self) -> None:
        quote = self.standardizer.standardize_websocket(
            "binance",
            {"s": "ETHUSDT", "b": "200", "a": "201", "E": 1767225600000},
            self.received_at,
        )
        assert quote is not None
        self.assertEqual(quote.symbol, "ETH/USDT")
        self.assertEqual(quote.timestamp, self.received_at)


if __name__ == "__main__":
    unittest.main()
