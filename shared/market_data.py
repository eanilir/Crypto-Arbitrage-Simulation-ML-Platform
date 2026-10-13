"""Load recorded order-book snapshots and group them into chronological ticks.

A *tick* is the set of snapshots (one per exchange) taken in the same recorder cycle.
Records carry a ``run_id`` and ``cycle`` that are used directly when present. For older
records without them, grouping falls back to request-time clustering: within a cycle the
requests are issued concurrently, so their request timestamps are within milliseconds of
each other, while consecutive cycles are about one recorder interval apart. Clustering by
gaps (not wall-clock buckets) means a cycle is never split across a second boundary.

Invalid records (``validation_status != "ok"``) are excluded from ticks and counted.
Nothing is imputed: a missing exchange simply means it is absent from the tick.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.domain.orderbook import OrderBook

DEFAULT_TICK_GAP_SECONDS = 0.3


@dataclass(frozen=True)
class Tick:
    symbol: str
    decision_time: datetime  # latest receive time among the books in the tick
    books: Mapping[str, OrderBook]  # exchange -> book

    def book(self, exchange: str) -> OrderBook | None:
        return self.books.get(exchange)


@dataclass
class LoadReport:
    files: int = 0
    records: int = 0
    invalid_records: int = 0
    malformed_lines: int = 0
    by_exchange: dict[str, int] = field(default_factory=lambda: defaultdict(int))


def iter_record_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return sorted(source.glob("market_depth_*.ndjson"))


def load_records(source: Path | str, report: LoadReport | None = None) -> list[dict[str, Any]]:
    """Read ``market_depth_*.ndjson`` records, dropping invalid and malformed lines."""
    report = report if report is not None else LoadReport()
    records: list[dict[str, Any]] = []
    for path in iter_record_files(Path(source)):
        report.files += 1
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    report.malformed_lines += 1
                    continue
                report.records += 1
                if record.get("validation_status") != "ok":
                    report.invalid_records += 1
                    continue
                report.by_exchange[record["exchange"]] += 1
                records.append(record)
    return records


def group_ticks(
    records: Iterable[Mapping[str, Any]],
    gap_seconds: float = DEFAULT_TICK_GAP_SECONDS,
) -> list[Tick]:
    """Cluster records into chronological ticks (per symbol)."""
    by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_symbol[record["symbol"]].append(record)

    ticks: list[Tick] = []
    for symbol, items in by_symbol.items():
        if all(item.get("cycle") is not None for item in items):
            # cycle ids restart after a recorder restart, so key on (run_id, cycle)
            by_cycle: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
            for item in items:
                by_cycle[(str(item.get("run_id") or ""), item["cycle"])].append(item)
            ticks.extend(_make_tick(symbol, group) for group in by_cycle.values())
            continue
        items.sort(key=lambda r: r["request_timestamp"])
        cluster: list[Mapping[str, Any]] = []
        last_request: datetime | None = None
        for record in items:
            requested = datetime.fromisoformat(record["request_timestamp"])
            if (
                last_request is not None
                and (requested - last_request).total_seconds() > gap_seconds
            ):
                ticks.append(_make_tick(symbol, cluster))
                cluster = []
            cluster.append(record)
            last_request = requested
        if cluster:
            ticks.append(_make_tick(symbol, cluster))
    ticks.sort(key=lambda t: (t.decision_time, t.symbol))
    return ticks


def _make_tick(symbol: str, cluster: list[Mapping[str, Any]]) -> Tick:
    books: dict[str, OrderBook] = {}
    for record in cluster:
        book = OrderBook.from_record(record)
        books[book.exchange] = book  # one book per exchange per tick
    decision_time = max(book.received_at for book in books.values())
    return Tick(symbol=symbol, decision_time=decision_time, books=books)


def load_ticks(
    source: Path | str,
    gap_seconds: float = DEFAULT_TICK_GAP_SECONDS,
    report: LoadReport | None = None,
) -> list[Tick]:
    return group_ticks(load_records(source, report), gap_seconds)


def ticks_by_symbol(ticks: Iterable[Tick]) -> dict[str, list[Tick]]:
    grouped: dict[str, list[Tick]] = defaultdict(list)
    for tick in ticks:
        grouped[tick.symbol].append(tick)
    return grouped


def iter_pairs(tick: Tick) -> Iterator[tuple[OrderBook, OrderBook]]:
    """Ordered (buy_book, sell_book) pairs in a tick."""
    for buy in tick.books.values():
        for sell in tick.books.values():
            if buy.exchange != sell.exchange:
                yield buy, sell
