import unittest
from datetime import datetime, timezone

from shared.feature_pipeline import FeatureEngineer, FeatureVector
from shared.domain import MarketQuote


class FeatureEngineeringTests(unittest.TestCase):
    def test_build_features_from_cross_exchange_quotes(self) -> None:
        engineer = FeatureEngineer()
        quotes = [
            MarketQuote(
                exchange="binance",
                symbol="BTC/USDT",
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                bid=100.0,
                ask=100.5,
                last=100.2,
                volume=2.0,
            ),
            MarketQuote(
                exchange="bybit",
                symbol="BTC/USDT",
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                bid=101.1,
                ask=101.5,
                last=101.3,
                volume=2.5,
            ),
        ]

        feature_vector = engineer.build_features(quotes)

        self.assertIsInstance(feature_vector, FeatureVector)
        self.assertEqual(feature_vector.exchange_pair, "binance-bybit")
        self.assertGreater(feature_vector.price_difference, 0.0)
        self.assertGreater(feature_vector.spread_percentage, 0.0)
        self.assertGreaterEqual(feature_vector.total_volume, 4.5)
        self.assertGreaterEqual(feature_vector.volatility, 0.0)
        self.assertGreaterEqual(feature_vector.fee_slippage_latency, 0.0)

    def test_pipeline_requires_two_quotes_for_arbitrage_features(self) -> None:
        engineer = FeatureEngineer()
        quote = MarketQuote(
            exchange="binance",
            symbol="ETH/USDT",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            bid=200.0,
            ask=200.5,
            last=200.2,
            volume=1.0,
        )

        with self.assertRaises(ValueError):
            engineer.build_features([quote])


if __name__ == "__main__":
    unittest.main()
