"""Data-quality metrics for recorded order-book data (project_plan.md §19.3, §9).

Everything here is derived from the files on disk, so quality can be re-audited at any
time. "Stale" means cross-exchange receive skew inside a tick (see ``candidates.py``),
not exchange or network latency.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.market_data import group_ticks, iter_record_files

EVENT_AHEAD_TOLERANCE_MS = 1_000  # event time later than receive time by more than this = anomaly


@dataclass
class QualityReport:
    source: str
    files: int = 0
    total_records: int = 0
    invalid_records: int = 0
    malformed_lines: int = 0
    records_by_exchange: dict[str, int] = field(default_factory=dict)
    fetch_errors_by_exchange: dict[str, int] = field(default_factory=dict)
    event_timestamp_missing: int = 0
    timestamp_anomalies: dict[str, int] = field(default_factory=dict)
    timestamps_consistent: bool = True
    data_gaps: dict[str, Any] = field(default_factory=dict)
    ticks: int = 0
    incomplete_ticks: int = 0
    stale_ticks: int = 0
    stale_threshold_ms: float = 0.0
    collector_availability: float | None = None
    tick_spacing_ms: dict[str, float] = field(default_factory=dict)
    period_start: str | None = None
    period_end: str | None = None
    storage_bytes: int = 0
    estimated_bytes_per_day: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def analyze(
    source: Path | str, *, stale_ms: float = 1_000.0, gap_seconds: float = 5.0
) -> QualityReport:
    source = Path(source)
    report = QualityReport(source=str(source), stale_threshold_ms=stale_ms)
    files = iter_record_files(source)
    report.files = len(files)
    report.storage_bytes = sum(f.stat().st_size for f in files)

    valid: list[dict[str, Any]] = []
    by_exchange: Counter = Counter()
    anomalies: Counter = Counter()
    last_received: dict[str, datetime] = {}
    request_times: dict[str, list[datetime]] = defaultdict(list)

    for path in files:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    report.malformed_lines += 1
                    continue
                report.total_records += 1
                if record.get("validation_status") != "ok":
                    report.invalid_records += 1
                    continue
                exchange = record["exchange"]
                by_exchange[exchange] += 1
                valid.append(record)

                received = datetime.fromisoformat(record["received_timestamp"])
                requested = datetime.fromisoformat(record["request_timestamp"])
                request_times[exchange].append(requested)
                if received < requested:
                    anomalies["received_before_request"] += 1
                previous = last_received.get(exchange)
                if previous is not None and received < previous:
                    anomalies["out_of_order_received"] += 1
                last_received[exchange] = received
                if record.get("event_timestamp"):
                    event = datetime.fromisoformat(record["event_timestamp"])
                    if (event - received).total_seconds() * 1000 > EVENT_AHEAD_TOLERANCE_MS:
                        anomalies["event_after_receive"] += 1
                else:
                    report.event_timestamp_missing += 1
                if record.get("round_trip_ms") is not None and record["round_trip_ms"] < 0:
                    anomalies["negative_round_trip"] += 1

    event_files = sorted(source.glob("collector_events_*.ndjson")) if source.is_dir() else []
    for event_file in event_files:
        for line in event_file.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("type") == "fetch_error":
                report.fetch_errors_by_exchange[row["exchange"]] = (
                    report.fetch_errors_by_exchange.get(row["exchange"], 0) + 1
                )

    report.records_by_exchange = dict(by_exchange)
    report.timestamp_anomalies = dict(anomalies)
    report.timestamps_consistent = not anomalies

    gaps: dict[str, Any] = {}
    for exchange, times in request_times.items():
        times.sort()
        deltas = [(b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)]
        big = [d for d in deltas if d > gap_seconds]
        gaps[exchange] = {
            "gaps_over_threshold": len(big),
            "max_gap_seconds": max(deltas) if deltas else 0.0,
        }
    report.data_gaps = {"threshold_seconds": gap_seconds, "by_exchange": gaps}

    ticks = group_ticks(valid)
    report.ticks = len(ticks)
    expected = len(by_exchange)
    for tick in ticks:
        if len(tick.books) < expected:
            report.incomplete_ticks += 1
        received = [b.received_at for b in tick.books.values()]
        skew = (max(received) - min(received)).total_seconds() * 1000
        if skew > stale_ms:
            report.stale_ticks += 1
    if ticks:
        report.collector_availability = (report.ticks - report.incomplete_ticks) / report.ticks
        report.period_start = ticks[0].decision_time.isoformat()
        report.period_end = ticks[-1].decision_time.isoformat()
        spacing = [
            (b.decision_time - a.decision_time).total_seconds() * 1000
            for a, b in zip(ticks, ticks[1:], strict=False)
        ]
        if spacing:
            report.tick_spacing_ms = {
                "median": statistics.median(spacing),
                "p95": _percentile(spacing, 0.95),
                "p99": _percentile(spacing, 0.99),
            }
        duration = (ticks[-1].decision_time - ticks[0].decision_time).total_seconds()
        if duration > 0:
            report.estimated_bytes_per_day = report.storage_bytes / duration * 86_400
    return report
