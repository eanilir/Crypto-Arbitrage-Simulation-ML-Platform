import unittest
from datetime import datetime, timezone

from shared.domain import MarketQuote, SpreadOpportunity
from shared.storage import (
    InMemoryCacheStore,
    InMemoryMarketDataAdapter,
    InMemoryOpportunityRepository,
)


class StorageLayerTests(unittest.TestCase):
    def test_market_data_adapter_persists_and_reads_latest_quote(self) -> None:
        adapter = InMemoryMarketDataAdapter()
        quote = MarketQuote(
            exchange="binance",
            symbol="BTC/USDT",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            bid=100.0,
            ask=101.0,
            last=100.5,
            volume=2.0,
        )

        adapter.save_quote(quote)
        latest = adapter.get_latest_quote("BTC/USDT")

        self.assertIsNotNone(latest)
        self.assertEqual(latest.symbol, "BTC/USDT")
        self.assertEqual(latest.bid, 100.0)
        self.assertEqual(
            adapter.get_history("BTC/USDT", limit=10)[0].symbol, "BTC/USDT"
        )

    def test_opportunity_repository_tracks_recent_opportunities(self) -> None:
        repo = InMemoryOpportunityRepository()
        opportunity = SpreadOpportunity(
            symbol="BTC/USDT",
            buy_exchange="binance",
            sell_exchange="bybit",
            spread=0.5,
            spread_percent=0.005,
            estimated_fees=0.1,
            estimated_slippage=0.05,
            estimated_latency_cost=0.02,
            net_profit=0.33,
            detected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        repo.save_opportunity(opportunity)
        rows = repo.list_recent("BTC/USDT", limit=10)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].symbol, "BTC/USDT")
        self.assertEqual(rows[0].buy_exchange, "binance")

    def test_cache_store_sets_and_gets_values_with_ttl(self) -> None:
        cache = InMemoryCacheStore()

        cache.set("market:BTC/USDT", {"exchange": "binance"}, ttl_seconds=60)
        self.assertEqual(cache.get("market:BTC/USDT"), {"exchange": "binance"})
        self.assertIsNone(cache.get("missing:key"))


if __name__ == "__main__":
    unittest.main()
