import unittest
from datetime import datetime, timezone

from services.arbitrage_engine.app.engine import ArbitrageEngine, ArbitrageSettings
from shared.domain import MarketQuote


class ArbitrageEngineTests(unittest.TestCase):
    def test_engine_detects_profitable_opportunity(self) -> None:
        engine = ArbitrageEngine()
        buy_quote = MarketQuote(
            exchange="binance",
            symbol="BTC/USDT",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            bid=100.0,
            ask=100.5,
            last=100.2,
            volume=2.0,
        )
        sell_quote = MarketQuote(
            exchange="bybit",
            symbol="BTC/USDT",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            bid=101.1,
            ask=101.5,
            last=101.3,
            volume=2.5,
        )

        opportunity = engine.evaluate_opportunity(buy_quote, sell_quote)

        self.assertIsNotNone(opportunity)
        self.assertEqual(opportunity.symbol, "BTC/USDT")
        self.assertEqual(opportunity.buy_exchange, "binance")
        self.assertEqual(opportunity.sell_exchange, "bybit")
        self.assertGreater(opportunity.net_profit, 0.0)

    def test_engine_ignores_opportunities_below_threshold(self) -> None:
        settings = ArbitrageSettings(min_profit_threshold=1.0)
        engine = ArbitrageEngine(settings=settings)
        buy_quote = MarketQuote(
            exchange="binance",
            symbol="ETH/USDT",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            bid=200.0,
            ask=200.5,
            last=200.2,
            volume=2.0,
        )
        sell_quote = MarketQuote(
            exchange="okx",
            symbol="ETH/USDT",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            bid=200.6,
            ask=201.0,
            last=200.8,
            volume=2.5,
        )

        self.assertIsNone(engine.evaluate_opportunity(buy_quote, sell_quote))

    def test_spread_percentage_and_fee_estimates_are_reasonable(self) -> None:
        engine = ArbitrageEngine()
        spread = engine.calculate_spread(100.0, 101.0)
        spread_percent = engine.calculate_spread_percent(100.0, 101.0)
        fee = engine.calculate_fee_cost(100.0, 101.0)

        self.assertEqual(spread, 1.0)
        self.assertAlmostEqual(spread_percent, 0.01)
        self.assertGreaterEqual(fee, 0.0)


if __name__ == "__main__":
    unittest.main()
