from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from shared.domain import MarketQuote

from ..errors import CollectorPayloadError


def number(
    payload: dict[str, Any],
    key: str,
    *,
    required: bool = True,
) -> float | None:
    value = payload.get(key)
    if value is None and not required:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise CollectorPayloadError(f"invalid numeric field: {key}") from error


def timestamp(
    value: Any,
    fallback: datetime,
    *,
    milliseconds: bool = True,
) -> datetime:
    if value is None:
        return fallback
    try:
        numeric = float(value)
        if milliseconds:
            numeric /= 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (TypeError, ValueError, OSError) as error:
        raise CollectorPayloadError("invalid exchange timestamp") from error


def quote(
    exchange: str,
    symbol: str,
    payload: dict[str, Any],
    received_at: datetime,
    *,
    bid_key: str,
    ask_key: str,
    last_key: str | None = None,
    volume_key: str | None = None,
    timestamp_key: str | None = None,
) -> MarketQuote:
    volume_value = None
    if volume_key:
        volume_value = number(payload, volume_key, required=False)
    return MarketQuote(
        exchange=exchange,
        symbol=symbol,
        timestamp=(
            timestamp(payload.get(timestamp_key), received_at)
            if timestamp_key
            else received_at
        ),
        bid=number(payload, bid_key),
        ask=number(payload, ask_key),
        last=number(payload, last_key, required=False) if last_key else None,
        volume=volume_value,
        metadata={"source": "market_data"},
    )
