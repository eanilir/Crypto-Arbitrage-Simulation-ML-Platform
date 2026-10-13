"""Records public order-book depth snapshots from Binance, Bybit and OKX to NDJSON.

Public, unauthenticated REST endpoints only. Nothing here can place orders.

Each record keeps the exchange event time (when the exchange provides one) and the
local receive time separately. ``round_trip_ms`` is the local request round trip; it
is NOT a network latency measurement. Missing or invalid data is flagged through
``validation_status`` and never replaced with invented prices.

Run from the repository root:

    python -m services.data_collector.app.depth_recorder --duration 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import signal
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.utils.logging import configure_logging

logger = logging.getLogger("collector.depth_recorder")

Levels = list[list[float]]
DEFAULT_EXCHANGES = ("binance", "bybit", "okx")
DEFAULT_SYMBOLS = ("BTC/USDT",)


@dataclass(frozen=True)
class DepthSnapshot:
    bids: Levels
    asks: Levels
    event_timestamp_ms: int | None
    sequence_id: int | None


def _levels(raw: Any) -> Levels:
    # Exchanges send [price, quantity, ...]; extra fields (OKX) are ignored.
    return [[float(level[0]), float(level[1])] for level in raw]


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_binance(payload: Any) -> DepthSnapshot:
    return DepthSnapshot(
        bids=_levels(payload["bids"]),
        asks=_levels(payload["asks"]),
        event_timestamp_ms=None,  # /api/v3/depth carries no event time
        sequence_id=_optional_int(payload.get("lastUpdateId")),
    )


def parse_bybit(payload: Any) -> DepthSnapshot:
    if payload.get("retCode") != 0:
        raise ValueError(f"bybit error {payload.get('retCode')}: {payload.get('retMsg')}")
    result = payload["result"]
    return DepthSnapshot(
        bids=_levels(result["b"]),
        asks=_levels(result["a"]),
        event_timestamp_ms=_optional_int(result.get("ts")),
        sequence_id=_optional_int(result.get("u")),
    )


def parse_okx(payload: Any) -> DepthSnapshot:
    if payload.get("code") != "0":
        raise ValueError(f"okx error {payload.get('code')}: {payload.get('msg')}")
    book = payload["data"][0]
    return DepthSnapshot(
        bids=_levels(book["bids"]),
        asks=_levels(book["asks"]),
        event_timestamp_ms=_optional_int(book.get("ts")),
        sequence_id=None,  # this REST endpoint exposes no sequence id
    )


@dataclass(frozen=True)
class ExchangeSource:
    name: str
    url: Callable[[str, int], str]
    parse: Callable[[Any], DepthSnapshot]


SOURCES: dict[str, ExchangeSource] = {
    "binance": ExchangeSource(
        "binance",
        lambda symbol, depth: (
            f"https://api.binance.com/api/v3/depth?symbol={symbol.replace('/', '')}&limit={depth}"
        ),
        parse_binance,
    ),
    "bybit": ExchangeSource(
        "bybit",
        lambda symbol, depth: (
            "https://api.bybit.com/v5/market/orderbook"
            f"?category=spot&symbol={symbol.replace('/', '')}&limit={depth}"
        ),
        parse_bybit,
    ),
    "okx": ExchangeSource(
        "okx",
        lambda symbol, depth: (
            f"https://www.okx.com/api/v5/market/books?instId={symbol.replace('/', '-')}&sz={depth}"
        ),
        parse_okx,
    ),
}


def validate_snapshot(snapshot: DepthSnapshot) -> list[str]:
    """Return a list of validation issues; an empty list means the snapshot is valid."""
    issues: list[str] = []
    if not snapshot.bids:
        issues.append("empty_bids")
    if not snapshot.asks:
        issues.append("empty_asks")
    for side, levels in (("bid", snapshot.bids), ("ask", snapshot.asks)):
        for price, quantity in levels:
            if not (math.isfinite(price) and math.isfinite(quantity)):
                issues.append(f"{side}_non_finite")
                break
            if price <= 0:
                issues.append(f"{side}_non_positive_price")
                break
            if quantity < 0:
                issues.append(f"{side}_negative_quantity")
                break
    bid_prices = [level[0] for level in snapshot.bids]
    ask_prices = [level[0] for level in snapshot.asks]
    if bid_prices != sorted(bid_prices, reverse=True):
        issues.append("bids_not_sorted_descending")
    if ask_prices != sorted(ask_prices):
        issues.append("asks_not_sorted_ascending")
    if bid_prices and ask_prices and bid_prices[0] > ask_prices[0]:
        issues.append("crossed_book")  # flagged, not silently accepted
    return issues


def build_record(
    *,
    exchange: str,
    symbol: str,
    snapshot: DepthSnapshot,
    requested_at: datetime,
    received_at: datetime,
    round_trip_ms: float,
    cycle: int | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    issues = validate_snapshot(snapshot)
    event_time = (
        datetime.fromtimestamp(snapshot.event_timestamp_ms / 1000, timezone.utc).isoformat()
        if snapshot.event_timestamp_ms is not None
        else None
    )
    return {
        "exchange": exchange,
        "symbol": symbol,
        "run_id": run_id,
        "cycle": cycle,
        "event_timestamp": event_time,
        "received_timestamp": received_at.isoformat(),
        "request_timestamp": requested_at.isoformat(),
        "round_trip_ms": round(round_trip_ms, 3),
        "timestamp_quality": "present" if event_time else "missing",
        "sequence_id": snapshot.sequence_id,
        "data_source": "rest_depth",
        "order_book_depth": min(len(snapshot.bids), len(snapshot.asks)),
        "validation_status": "ok" if not issues else "invalid",
        "validation_issues": issues,
        "bids": snapshot.bids,
        "asks": snapshot.asks,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _http_get_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "arbitrage-research/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


@dataclass
class RecorderStats:
    started_at: str = field(default_factory=lambda: _utc_now().isoformat())
    cycles: int = 0
    records: int = 0
    invalid_records: int = 0
    errors: dict[str, int] = field(default_factory=dict)
    records_by_exchange: dict[str, int] = field(default_factory=dict)
    missing_event_timestamp: int = 0
    stale_gap_cycles: int = 0  # cycles where at least one exchange returned nothing
    bytes_written: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["updated_at"] = _utc_now().isoformat()
        return data


class DepthRecorder:
    def __init__(
        self,
        output_dir: Path,
        exchanges: tuple[str, ...] = DEFAULT_EXCHANGES,
        symbols: tuple[str, ...] = DEFAULT_SYMBOLS,
        depth: int = 20,
        interval: float = 1.0,
        timeout: float = 3.0,
    ) -> None:
        unknown = [name for name in exchanges if name not in SOURCES]
        if unknown:
            raise ValueError(f"unsupported exchanges: {unknown}")
        if depth < 1 or interval <= 0 or timeout <= 0:
            raise ValueError("depth, interval and timeout must be positive")
        self.output_dir = output_dir
        self.exchanges = exchanges
        self.symbols = symbols
        self.depth = depth
        self.interval = interval
        self.timeout = timeout
        self.stats = RecorderStats()
        self.run_id = uuid.uuid4().hex[:12]  # cycles restart at 0 after a restart
        output_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, prefix: str, when: datetime) -> Path:
        return self.output_dir / f"{prefix}_{when:%Y%m%d}.ndjson"

    def _append(self, prefix: str, when: datetime, row: dict[str, Any]) -> None:
        line = json.dumps(row, separators=(",", ":")) + "\n"
        with self._path(prefix, when).open("a", encoding="utf-8") as handle:
            handle.write(line)
        self.stats.bytes_written += len(line.encode("utf-8"))

    async def _fetch(self, exchange: str, symbol: str, cycle: int) -> dict[str, Any] | None:
        source = SOURCES[exchange]
        requested_at = _utc_now()
        started = time.monotonic()
        try:
            payload = await asyncio.to_thread(
                _http_get_json, source.url(symbol, self.depth), self.timeout
            )
            received_at = _utc_now()
            round_trip_ms = (time.monotonic() - started) * 1000
            snapshot = source.parse(payload)
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            key = f"{exchange}:{type(error).__name__}"
            self.stats.errors[key] = self.stats.errors.get(key, 0) + 1
            logger.warning("fetch_failed exchange=%s symbol=%s error=%s", exchange, symbol, error)
            self._append(
                "collector_events",
                requested_at,
                {
                    "type": "fetch_error",
                    "exchange": exchange,
                    "symbol": symbol,
                    "timestamp": requested_at.isoformat(),
                    "error": f"{type(error).__name__}: {error}",
                },
            )
            return None
        return build_record(
            exchange=exchange,
            symbol=symbol,
            snapshot=snapshot,
            requested_at=requested_at,
            received_at=received_at,
            round_trip_ms=round_trip_ms,
            cycle=cycle,
            run_id=self.run_id,
        )

    async def run_cycle(self) -> None:
        results = await asyncio.gather(
            *(
                self._fetch(ex, sym, self.stats.cycles)
                for sym in self.symbols
                for ex in self.exchanges
            )
        )
        got_all = True
        for record in results:
            if record is None:
                got_all = False
                continue
            self._append("market_depth", _utc_now(), record)
            self.stats.records += 1
            self.stats.records_by_exchange[record["exchange"]] = (
                self.stats.records_by_exchange.get(record["exchange"], 0) + 1
            )
            if record["validation_status"] != "ok":
                self.stats.invalid_records += 1
                logger.warning(
                    "invalid_record exchange=%s issues=%s",
                    record["exchange"],
                    record["validation_issues"],
                )
            if record["timestamp_quality"] == "missing":
                self.stats.missing_event_timestamp += 1
        if not got_all:
            self.stats.stale_gap_cycles += 1
        self.stats.cycles += 1

    def write_stats(self) -> None:
        path = self.output_dir / "collector_stats.json"
        path.write_text(json.dumps(self.stats.to_dict(), indent=2), encoding="utf-8")

    async def run(self, duration: float | None) -> RecorderStats:
        deadline = time.monotonic() + duration if duration else None
        last_stats = time.monotonic()
        logger.info(
            "recorder_started exchanges=%s symbols=%s depth=%s interval=%ss",
            self.exchanges,
            self.symbols,
            self.depth,
            self.interval,
        )
        try:
            while deadline is None or time.monotonic() < deadline:
                cycle_started = time.monotonic()
                await self.run_cycle()
                if time.monotonic() - last_stats >= 30:
                    self.write_stats()
                    last_stats = time.monotonic()
                await asyncio.sleep(max(0.0, self.interval - (time.monotonic() - cycle_started)))
        finally:
            self.write_stats()
            logger.info("recorder_stopped %s", json.dumps(self.stats.to_dict()))
        return self.stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Record public order-book depth (no trading)")
    parser.add_argument(
        "--duration", type=float, default=None, help="seconds to run; omit to run until Ctrl+C"
    )
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between snapshots")
    parser.add_argument("--depth", type=int, default=20, help="order-book levels per side")
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="per-request timeout; a slow exchange delays the whole cycle by this much",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
        help="e.g. BTC/USDT ETH/USDT (commas also accepted)",
    )
    parser.add_argument("--exchanges", nargs="+", default=list(DEFAULT_EXCHANGES))
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    configure_logging()
    symbols = tuple(s for arg in args.symbols for s in arg.replace(",", " ").split())
    recorder = DepthRecorder(
        output_dir=args.output_dir,
        exchanges=tuple(args.exchanges),
        symbols=symbols,
        depth=args.depth,
        interval=args.interval,
        timeout=args.timeout,
    )

    def _terminate(signum: int, frame: object) -> None:
        raise KeyboardInterrupt  # `docker stop` sends SIGTERM; finish with a final stats write

    signal.signal(signal.SIGTERM, _terminate)
    try:
        stats = asyncio.run(recorder.run(args.duration))
    except KeyboardInterrupt:
        stats = recorder.stats
    print(json.dumps(stats.to_dict(), indent=2))


if __name__ == "__main__":
    main()
