from datetime import datetime, timezone

import pytest

from shared.domain import (
    InvalidPriceError,
    InvalidSymbolError,
    InvalidTimestampError,
    MarketQuote,
    Price,
    SpreadOpportunity,
    Symbol,
    normalize_symbol,
    normalize_timestamp,
)


def test_symbol_normalization_uses_canonical_base_quote_form() -> None:
    assert normalize_symbol(" btc-usdt ") == "BTC/USDT"
    assert Symbol("eth_usdt").value == "ETH/USDT"


def test_symbol_without_separator_is_rejected() -> None:
    with pytest.raises(InvalidSymbolError):
        Symbol("BTCUSDT")


def test_timestamp_is_utc() -> None:
    normalized = normalize_timestamp("2026-01-01T12:00:00+02:00")
    assert normalized == datetime(2026, 1, 1, 10, tzinfo=timezone.utc)


def test_invalid_timestamp_has_domain_error() -> None:
    with pytest.raises(InvalidTimestampError):
        normalize_timestamp("not-a-timestamp")


def test_market_quote_normalizes_and_validates_values() -> None:
    quote = MarketQuote(" Binance ", "btc_usdt", "2026-01-01T00:00:00Z", 100, 101)
    assert quote.exchange == "binance"
    assert quote.symbol == "BTC/USDT"
    assert quote.timestamp.tzinfo == timezone.utc
    assert quote.bid == 100.0


def test_market_quote_rejects_crossed_book() -> None:
    with pytest.raises(InvalidPriceError):
        MarketQuote("binance", "BTC/USDT", datetime.now(timezone.utc), 101, 100)


def test_price_must_be_positive() -> None:
    with pytest.raises(InvalidPriceError):
        Price(0)


def _opportunity(**overrides) -> SpreadOpportunity:
    values = {
        "symbol": "BTC/USDT",
        "buy_exchange": "binance",
        "sell_exchange": "bybit",
        "spread": 10.0,
        "spread_percent": 0.1,
        "estimated_fees": 1.0,
        "estimated_slippage": 1.0,
        "estimated_latency_cost": 1.0,
        "net_profit": 7.0,
        "detected_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return SpreadOpportunity(**values)


def test_negative_spread_is_a_valid_unprofitable_outcome() -> None:
    opportunity = _opportunity(spread=-50.0, spread_percent=-0.05, net_profit=-53.0)
    assert opportunity.spread == -50.0
    assert opportunity.spread_percent == -0.05
    assert opportunity.net_profit < 0


def test_positive_gross_spread_can_have_negative_net_profit() -> None:
    opportunity = _opportunity(
        spread=5.0, estimated_fees=4.0, estimated_slippage=2.0, net_profit=-2.0
    )
    assert opportunity.spread > 0
    assert opportunity.net_profit < 0


def test_non_finite_spread_is_still_rejected() -> None:
    with pytest.raises(InvalidPriceError):
        _opportunity(spread=float("nan"))
