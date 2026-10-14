"""Historical 1-minute candles (OHLCV) from the public REST APIs of Binance, Bybit and OKX.

Endpoints and limits (exchange documentation, verified with live requests):

* Binance  ``GET /api/v3/klines``                 interval=1m, limit<=1000, startTime/endTime (ms)
* Bybit    ``GET /v5/market/kline`` category=spot interval=1,  limit<=1000, start/end (ms),
           newest first
* OKX      ``GET /api/v5/market/history-candles`` bar=1m,      limit<=100,  ``after`` = return
           candles older than this ts, newest first

Candles hold open/high/low/close and volume per minute. They contain NO bid/ask and NO order
book depth, so they cannot reproduce executable spreads, slippage or sub-minute latency
(project_plan.md §8.5). Anything computed from them is a limited, assumption-based simulation.
"""

from __future__ import annotations

import csv
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MINUTE_MS = 60_000
COLUMNS = ["open_time_ms", "open", "high", "low", "close", "volume_base", "volume_quote"]

Fetcher = Callable[[str, float], Any]


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume_base: float
    volume_quote: float

    def row(self) -> list[Any]:
        return [
            self.open_time_ms,
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume_base,
            self.volume_quote,
        ]


def _candle(raw: list[Any], quote_index: int) -> Candle:
    return Candle(
        open_time_ms=int(raw[0]),
        open=float(raw[1]),
        high=float(raw[2]),
        low=float(raw[3]),
        close=float(raw[4]),
        volume_base=float(raw[5]),
        volume_quote=float(raw[quote_index]),
    )


def parse_binance(payload: Any) -> list[Candle]:
    return [_candle(row, 7) for row in payload]


def parse_bybit(payload: Any) -> list[Candle]:
    if payload.get("retCode") != 0:
        raise ValueError(f"bybit error {payload.get('retCode')}: {payload.get('retMsg')}")
    return [_candle(row, 6) for row in payload["result"]["list"]]


def parse_okx(payload: Any) -> list[Candle]:
    if payload.get("code") != "0":
        raise ValueError(f"okx error {payload.get('code')}: {payload.get('msg')}")
    # OKX rows: ts, o, h, l, c, vol (base), volCcy, volCcyQuote, confirm
    return [_candle(row, 7) for row in payload["data"] if row[8] == "1"]  # drop unfinished candle


def http_get_json(url: str, timeout: float = 10.0, retries: int = 20) -> Any:
    """GET JSON; retries with backoff up to ~60 s so short outages do not abort long downloads."""
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "arbitrage-research/0.1"})
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code not in {418, 429, 500, 502, 503, 504} or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == retries:
                raise
        time.sleep(delay)
        delay = min(delay * 2, 60.0)
    raise RuntimeError("unreachable")


def _binance_pages(symbol: str, start: int, end: int, fetch: Fetcher) -> Iterator[list[Candle]]:
    cursor = start
    while cursor < end:
        query = urllib.parse.urlencode(
            {
                "symbol": symbol.replace("/", ""),
                "interval": "1m",
                "limit": 1000,
                "startTime": cursor,
                "endTime": end - 1,
            }
        )
        page = parse_binance(fetch(f"https://api.binance.com/api/v3/klines?{query}", 10.0))
        if not page:
            return
        yield page
        cursor = page[-1].open_time_ms + MINUTE_MS


def _bybit_pages(symbol: str, start: int, end: int, fetch: Fetcher) -> Iterator[list[Candle]]:
    cursor_end = end - 1
    while cursor_end >= start:
        query = urllib.parse.urlencode(
            {
                "category": "spot",
                "symbol": symbol.replace("/", ""),
                "interval": 1,
                "limit": 1000,
                "start": start,
                "end": cursor_end,
            }
        )
        page = parse_bybit(fetch(f"https://api.bybit.com/v5/market/kline?{query}", 10.0))
        if not page:
            return
        page.sort(key=lambda c: c.open_time_ms)
        yield page
        cursor_end = page[0].open_time_ms - 1


def _okx_pages(symbol: str, start: int, end: int, fetch: Fetcher) -> Iterator[list[Candle]]:
    after = end  # OKX returns candles strictly older than `after`
    while after > start:
        query = urllib.parse.urlencode(
            {"instId": symbol.replace("/", "-"), "bar": "1m", "limit": 100, "after": after}
        )
        raw = fetch(f"https://www.okx.com/api/v5/market/history-candles?{query}", 10.0)
        page = parse_okx(raw)
        if not raw.get("data"):
            return
        page = [c for c in page if c.open_time_ms >= start]
        page.sort(key=lambda c: c.open_time_ms)
        if page:
            yield page
        oldest_seen = min(int(row[0]) for row in raw["data"])
        if oldest_seen >= after:
            return  # no progress
        after = oldest_seen
        time.sleep(0.11)  # stay well below the documented rate limit


PAGINATORS = {"binance": _binance_pages, "bybit": _bybit_pages, "okx": _okx_pages}


def fetch_candles(
    exchange: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    fetch: Fetcher = http_get_json,
    progress: Callable[[int, int], None] | None = None,
) -> list[Candle]:
    """Candles with start_ms <= open_time < end_ms, de-duplicated and sorted."""
    if exchange not in PAGINATORS:
        raise ValueError(f"unsupported exchange: {exchange}")
    if end_ms <= start_ms:
        raise ValueError("end must be after start")
    by_time: dict[int, Candle] = {}
    for page in PAGINATORS[exchange](symbol, start_ms, end_ms, fetch):
        for candle in page:
            if start_ms <= candle.open_time_ms < end_ms:
                by_time[candle.open_time_ms] = candle
        if progress:
            progress(len(by_time), (end_ms - start_ms) // MINUTE_MS)
    return [by_time[t] for t in sorted(by_time)]


@dataclass
class CandleValidation:
    rows: int
    expected_rows: int
    missing_minutes: int
    gaps: list[tuple[int, int]]  # (first missing minute, count)
    invalid_rows: int
    duplicate_or_unordered: int

    @property
    def coverage(self) -> float:
        return self.rows / self.expected_rows if self.expected_rows else 0.0


def validate_candles(candles: list[Candle], start_ms: int, end_ms: int) -> CandleValidation:
    expected = (end_ms - start_ms) // MINUTE_MS
    invalid = 0
    unordered = 0
    gaps: list[tuple[int, int]] = []
    previous: int | None = None
    for candle in candles:
        values = [candle.open, candle.high, candle.low, candle.close]
        ok = (
            all(math.isfinite(v) and v > 0 for v in values)
            and math.isfinite(candle.volume_base)
            and candle.volume_base >= 0
            and candle.low <= min(candle.open, candle.close)
            and candle.high >= max(candle.open, candle.close)
        )
        invalid += 0 if ok else 1
        if previous is not None:
            if candle.open_time_ms <= previous:
                unordered += 1
            elif candle.open_time_ms - previous > MINUTE_MS:
                gaps.append(
                    (previous + MINUTE_MS, (candle.open_time_ms - previous) // MINUTE_MS - 1)
                )
        previous = candle.open_time_ms
    return CandleValidation(
        rows=len(candles),
        expected_rows=expected,
        missing_minutes=max(0, expected - len(candles)),
        gaps=gaps,
        invalid_rows=invalid,
        duplicate_or_unordered=unordered,
    )


def write_csv(path: Path, candles: list[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for candle in candles:
            writer.writerow(candle.row())


def read_csv(path: Path) -> list[Candle]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            Candle(
                int(r["open_time_ms"]),
                float(r["open"]),
                float(r["high"]),
                float(r["low"]),
                float(r["close"]),
                float(r["volume_base"]),
                float(r["volume_quote"]),
            )
            for r in reader
        ]


def _append_csv(path: Path, candles: list[Candle]) -> None:
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(COLUMNS)
        for candle in candles:
            writer.writerow(candle.row())


def _csv_bounds(path: Path) -> tuple[int, int] | None:
    """(first, last) open_time_ms of an existing file, or None if it has no data rows."""
    if not path.exists():
        return None
    first = last = None
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) == len(COLUMNS):
                first = int(row[0]) if first is None else first
                last = int(row[0])
    return None if first is None else (first, last)


def download_to_csv(
    exchange: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    path: Path,
    fetch: Fetcher = http_get_json,
    window_minutes: int = 3 * 24 * 60,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """Download in windows, appending each to ``path``; an interrupted run resumes after the
    last saved candle instead of starting over. A partly written last line is discarded."""
    bounds = _csv_bounds(path)
    cursor = start_ms
    if bounds is not None:
        cursor = max(start_ms, bounds[1] + MINUTE_MS)
    total = (end_ms - start_ms) // MINUTE_MS
    while cursor < end_ms:
        window_end = min(cursor + window_minutes * MINUTE_MS, end_ms)
        candles = fetch_candles(exchange, symbol, cursor, window_end, fetch)
        _append_csv(path, candles)
        cursor = window_end
        if progress:
            progress((cursor - start_ms) // MINUTE_MS, total)
