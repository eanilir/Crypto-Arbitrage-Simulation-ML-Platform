from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from shared.domain import MarketQuote, normalize_symbol, normalize_timestamp

from .errors import CollectorPayloadError, MissingMarketFieldError

_QUOTE_ASSETS = ("USDT", "USDC", "BUSD", "USD", "BTC", "ETH")


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CollectorPayloadError(f"{context} payload must be an object")
    return value


def _required(payload: dict[str, Any], field: str) -> Any:
    value = payload.get(field)
    if value is None or value == "":
        message = f"missing required market field: {field}"
        raise MissingMarketFieldError(message)
    return value


def _number(
    value: Any,
    field: str,
    *,
    required: bool = False,
) -> float | None:
    if value is None or value == "":
        if required:
            message = f"missing required market field: {field}"
            raise MissingMarketFieldError(message)
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        message = f"invalid numeric market field: {field}"
        raise CollectorPayloadError(message) from error
    if not isfinite(result):
        raise CollectorPayloadError(f"invalid numeric market field: {field}")
    return result


def _timestamp(value: Any, fallback: datetime) -> datetime:
    if value is None or value == "":
        return normalize_timestamp(fallback)
    numeric_value = value
    if isinstance(value, str):
        try:
            numeric_value = float(value)
        except ValueError:
            numeric_value = None
    is_numeric = isinstance(numeric_value, (int, float))
    if is_numeric and not isinstance(numeric_value, bool):
        try:
            return datetime.fromtimestamp(
                float(numeric_value) / 1000,
                tz=timezone.utc,
            )
        except (OverflowError, OSError, ValueError) as error:
            message = "invalid exchange timestamp"
            raise CollectorPayloadError(message) from error
    try:
        return normalize_timestamp(value)
    except (TypeError, ValueError) as error:
        raise CollectorPayloadError("invalid exchange timestamp") from error


def _symbol(value: Any, exchange: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissingMarketFieldError("missing required market field: symbol")
    candidate = value.strip().upper().replace("-", "/").replace("_", "/")
    if "/" not in candidate:
        for quote_asset in _QUOTE_ASSETS:
            has_quote = candidate.endswith(quote_asset)
            has_base = len(candidate) > len(quote_asset)
            if has_quote and has_base:
                candidate = f"{candidate[:-len(quote_asset)]}/{quote_asset}"
                break
    try:
        return normalize_symbol(candidate)
    except Exception as error:
        raise CollectorPayloadError(
            f"invalid {exchange} market symbol: {value!r}"
        ) from error


def _quote(
    exchange: str,
    symbol: Any,
    payload: dict[str, Any],
    received_at: datetime,
    *,
    bid: str,
    ask: str,
    last: str | None = None,
    volume: str | None = None,
    timestamp: Any = None,
) -> MarketQuote:
    volume_value = None
    if volume:
        volume_value = _number(payload.get(volume), volume)
    last_value = None
    if last:
        last_value = _number(payload.get(last), last)
    return MarketQuote(
        exchange=exchange,
        symbol=_symbol(symbol, exchange),
        timestamp=_timestamp(timestamp, received_at),
        bid=_number(_required(payload, bid), bid, required=True),
        ask=_number(_required(payload, ask), ask, required=True),
        last=last_value,
        volume=volume_value,
        metadata={"source": "market_data", "standardized": "true"},
    )


class MarketDataStandardizer:
    """Convert exchange payloads into validated MarketQuote values."""

    def standardize_rest(
        self,
        exchange: str,
        payload: Any,
        symbol: str,
        received_at: datetime,
    ) -> MarketQuote:
        if exchange == "binance":
            return _quote(
                exchange,
                symbol,
                _mapping(payload, exchange),
                received_at,
                bid="bidPrice",
                ask="askPrice",
                last="lastPrice",
                volume="volume",
            )
        if exchange == "bybit":
            root = _mapping(payload, exchange)
            result = _mapping(root.get("result"), "bybit result")
            rows = result.get("list")
            if not isinstance(rows, list) or not rows:
                raise MissingMarketFieldError(
                    "missing required market field: result.list"
                )
            return _quote(
                exchange,
                symbol,
                _mapping(rows[0], "bybit ticker"),
                received_at,
                bid="bid1Price",
                ask="ask1Price",
                last="lastPrice",
                volume="volume24h",
                timestamp=root.get("time"),
            )
        if exchange == "okx":
            root = _mapping(payload, exchange)
            rows = root.get("data")
            if not isinstance(rows, list) or not rows:
                message = "missing required market field: data"
                raise MissingMarketFieldError(message)
            data = _mapping(rows[0], "okx ticker")
            return _quote(
                exchange,
                data.get("instId", symbol),
                data,
                received_at,
                bid="bidPx",
                ask="askPx",
                last="last",
                volume="vol24h",
                timestamp=data.get("ts"),
            )
        raise CollectorPayloadError(f"unsupported exchange: {exchange}")

    def standardize_websocket(
        self,
        exchange: str,
        payload: Any,
        received_at: datetime,
    ) -> MarketQuote | None:
        if exchange == "binance":
            root = _mapping(payload, exchange)
            data = _mapping(root.get("data", root), "binance websocket")
            if not data.get("s"):
                return None
            return _quote(
                exchange,
                data["s"],
                data,
                received_at,
                bid="b",
                ask="a",
                timestamp=data.get("E"),
            )
        if exchange == "bybit":
            root = _mapping(payload, exchange)
            data = root.get("data")
            if not isinstance(data, dict) or not data.get("symbol"):
                return None
            return _quote(
                exchange,
                data["symbol"],
                data,
                received_at,
                bid="bid1Price",
                ask="ask1Price",
                last="lastPrice",
                volume="volume24h",
                timestamp=data.get("ts"),
            )
        if exchange == "okx":
            root = _mapping(payload, exchange)
            rows = root.get("data")
            if not isinstance(rows, list) or not rows:
                return None
            data = _mapping(rows[0], "okx websocket")
            return _quote(
                exchange,
                data.get("instId"),
                data,
                received_at,
                bid="bidPx",
                ask="askPx",
                last="last",
                volume="vol24h",
                timestamp=data.get("ts"),
            )
        raise CollectorPayloadError(f"unsupported exchange: {exchange}")
