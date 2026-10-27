"""Build the labeled dataset with bounded memory from market-depth NDJSON."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.arbitrage_engine.app.candidates import CostModel, evaluate_pair  # noqa: E402
from services.ml_service.app.dataset import (  # noqa: E402
    FEATURE_COLUMNS,
    META_COLUMNS,
    DatasetConfig,
    build_features,
    simulate_execution,
)
from shared.domain.orderbook import OrderBook  # noqa: E402
from shared.market_data import Tick, iter_pairs  # noqa: E402

EXCHANGES = frozenset({"binance", "bybit", "okx"})
OUTPUT_COLUMNS = META_COLUMNS + FEATURE_COLUMNS


@dataclass(frozen=True)
class StreamTick:
    tick: Tick
    run_id: str | None
    gap_before_seconds: float


@dataclass
class StreamLoadReport:
    files: int = 0
    records: int = 0
    malformed_lines: int = 0
    invalid_records: int = 0
    incomplete_cycles: int = 0
    incomplete_missing_exchanges: Counter[str] = None  # type: ignore[assignment]
    segments: int = 0

    def __post_init__(self) -> None:
        if self.incomplete_missing_exchanges is None:
            self.incomplete_missing_exchanges = Counter()

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["incomplete_missing_exchanges"] = dict(self.incomplete_missing_exchanges)
        return data


def _tick_from_records(records: dict[str, dict[str, Any]]) -> Tick:
    books = {exchange: OrderBook.from_record(record) for exchange, record in records.items()}
    first = next(iter(books.values()))
    decision_time = max(book.received_at for book in books.values())
    return Tick(symbol=first.symbol, decision_time=decision_time, books=books)


def iter_complete_ticks(
    source: Path,
    report: StreamLoadReport,
    *,
    gap_seconds: float = 5.0,
) -> Iterator[StreamTick]:
    """Yield complete cycles while retaining only the current cycle in memory."""
    paths = [source] if source.is_file() else sorted(source.glob("market_depth_*.ndjson"))
    report.files = len(paths)
    current_key: tuple[str | None, int] | None = None
    current_records: dict[str, dict[str, Any]] = {}
    previous_time: datetime | None = None

    def flush() -> StreamTick | None:
        nonlocal current_key, current_records
        if current_key is None:
            return None
        missing = EXCHANGES - current_records.keys()
        if missing:
            report.incomplete_cycles += 1
            report.incomplete_missing_exchanges.update(missing)
            current_key = None
            current_records = {}
            return None
        tick = _tick_from_records(current_records)
        run_id = current_key[0]
        gap = 0.0 if previous_time is None else (tick.decision_time - previous_time).total_seconds()
        current_key = None
        current_records = {}
        return StreamTick(tick, run_id, gap)

    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    record = json.loads(text)
                except json.JSONDecodeError:
                    report.malformed_lines += 1
                    continue
                report.records += 1
                if record.get("validation_status") != "ok":
                    report.invalid_records += 1
                    continue
                try:
                    key = (record["run_id"], int(record["cycle"]))
                    exchange = str(record["exchange"])
                except (KeyError, TypeError, ValueError):
                    report.malformed_lines += 1
                    continue
                if current_key != key:
                    completed = flush()
                    if completed is not None:
                        yield completed
                        previous_time = completed.tick.decision_time
                current_key = key
                current_records[exchange] = record
        if current_key is not None:
            completed = flush()
            if completed is not None:
                yield completed
                previous_time = completed.tick.decision_time


@dataclass
class PendingDecision:
    tick: Tick
    tick_index: int
    candidates: list[tuple[Any, dict[str, Any]]]
    target_time: datetime


def _write_row(writer: csv.DictWriter, row: dict[str, Any]) -> None:
    writer.writerow({column: row.get(column) for column in OUTPUT_COLUMNS})


def build_streaming_dataset(
    source: Path,
    output: Path,
    cfg: DatasetConfig,
    *,
    gap_seconds: float = 5.0,
) -> dict[str, Any]:
    """Write rows incrementally; only history and pending execution windows stay in RAM."""
    output.parent.mkdir(parents=True, exist_ok=True)
    report = StreamLoadReport()
    dataset_report: Counter[str] = Counter()
    label_counts: Counter[int] = Counter()
    history: deque[Tick] = deque(maxlen=cfg.history_ticks)
    pending: deque[PendingDecision] = deque()
    tick_index = 0
    segments = 0
    last_run: str | None = None

    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        def finish_pending() -> None:
            dataset_report["unlabeled_dropped"] += sum(
                len(item.candidates) for item in pending
            )
            pending.clear()

        for streamed in iter_complete_ticks(source, report, gap_seconds=gap_seconds):
            tick = streamed.tick
            boundary = (
                not history
                or streamed.run_id != last_run
                or streamed.gap_before_seconds > gap_seconds
            )
            if boundary:
                finish_pending()
                history.clear()
                segments += 1

            def resolve_ready() -> None:
                nonlocal pending
                while pending:
                    item = pending[0]
                    if tick.decision_time < item.target_time:
                        break
                    pending.popleft()
                    wait_ms = (
                        tick.decision_time - item.target_time
                    ).total_seconds() * 1000
                    if wait_ms > cfg.max_execution_wait_ms:
                        dataset_report["unlabeled_dropped"] += len(item.candidates)
                        continue
                    for candidate, row in item.candidates:
                        execution = simulate_execution(tick, candidate, cfg.cost_model)
                        if execution.status in {"exec_missing_exchange", "exec_invalid_book"}:
                            dataset_report["unlabeled_dropped"] += 1
                            continue
                        outcome = execution.net_profit
                        row = dict(row)
                        row.update(
                            outcome_net_profit=outcome if outcome is not None else 0.0,
                            outcome_status=execution.status,
                            outcome_buy_cost=execution.buy_cost,
                            outcome_sell_proceeds=execution.sell_proceeds,
                            outcome_fees=execution.fees,
                            outcome_time=tick.decision_time.isoformat(),
                            label=1 if outcome is not None and outcome > 0 else 0,
                        )
                        _write_row(writer, row)
                        dataset_report["rows"] += 1
                        label_counts[row["label"]] += 1

            window = list(history) + [tick]
            index = len(window) - 1
            candidates: list[tuple[Any, dict[str, Any]]] = []
            for buy, sell in iter_pairs(tick):
                dataset_report["candidates_seen"] += 1
                candidate = evaluate_pair(
                    buy,
                    sell,
                    cfg.notional,
                    cfg.cost_model,
                    decision_time=tick.decision_time,
                    max_data_age_ms=cfg.max_data_age_ms,
                )
                if candidate.is_rejected:
                    dataset_report[f"rejected_{candidate.status.value}"] += 1
                    continue
                row: dict[str, Any] = {
                    "decision_time": tick.decision_time.isoformat(),
                    "tick_index": tick_index,
                    "symbol": tick.symbol,
                    "status": candidate.status.value,
                    "label": None,
                    "quantity": candidate.quantity,
                    "outcome_net_profit": None,
                    "outcome_status": None,
                    "outcome_buy_cost": None,
                    "outcome_sell_proceeds": None,
                    "outcome_fees": None,
                    "outcome_time": None,
                    "candidate_net_profit": candidate.net_profit,
                }
                row.update(build_features(window, index, buy, sell, candidate, cfg))
                candidates.append((candidate, row))
            pending.append(
                PendingDecision(
                    tick=tick,
                    tick_index=tick_index,
                    candidates=candidates,
                    target_time=tick.decision_time
                    + timedelta(milliseconds=cfg.latency_ms),
                )
            )
            resolve_ready()
            history.append(tick)
            tick_index += 1
            last_run = streamed.run_id

        finish_pending()

    report.segments = segments
    summary = {
        "input": str(source),
        "output": str(output),
        "load": report.to_dict(),
        "dataset": {
            "ticks": tick_index,
            "segments": segments,
            "candidates_seen": dataset_report["candidates_seen"],
            "rows": dataset_report["rows"],
            "unlabeled_dropped": dataset_report["unlabeled_dropped"],
            "label_counts": {str(k): v for k, v in label_counts.items()},
            "rejected": {
                key.removeprefix("rejected_"): value
                for key, value in dataset_report.items()
                if key.startswith("rejected_")
            },
        },
    }
    output.with_suffix(".report.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notional", type=float, default=10_000.0)
    parser.add_argument("--latency-ms", type=float, default=0.0)
    parser.add_argument("--fee-rate", type=float, default=0.001)
    parser.add_argument("--latency-bps", type=float, default=0.0)
    parser.add_argument("--max-data-age-ms", type=float, default=None)
    parser.add_argument("--gap-seconds", type=float, default=5.0)
    args = parser.parse_args()
    cfg = DatasetConfig(
        notional=args.notional,
        latency_ms=args.latency_ms,
        cost_model=CostModel(default_fee_rate=args.fee_rate, latency_bps=args.latency_bps),
        max_data_age_ms=args.max_data_age_ms,
    )
    print(json.dumps(build_streaming_dataset(args.input, args.output, cfg, gap_seconds=args.gap_seconds), indent=2))


if __name__ == "__main__":
    main()
