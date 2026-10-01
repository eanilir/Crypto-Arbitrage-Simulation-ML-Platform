from datetime import datetime, timezone

import pytest

from shared.domain import (
    InvalidPriceError,
    InvalidSymbolError,
    InvalidTimestampError,
    MarketQuote,
    Price,
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
