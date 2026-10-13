"""Dataset generation and target definition (project_plan.md §13).

Unit of observation
    One row = one priced cross-exchange candidate (buy exchange, sell exchange, symbol)
    at one decision tick. All ordered exchange pairs are included, profitable or not,
    so periods without an opportunity stay in the data (no selection bias).
    Candidates rejected at decision time (insufficient depth, invalid or stale data)
    are counted in the report but not emitted as rows.

Decision time
    The latest receive time among the books of the tick.

Target (``label``)
    The trade is assumed to execute at the first later tick whose decision time is at
    least ``latency_ms`` after the decision time (same tick when latency is 0). The
    quantity is fixed at decision time. Both legs are assumed to fill and are priced
    by walking the *execution-tick* books:

        outcome_net_profit = sell_proceeds - buy_cost - fees
        label = 1 if outcome_net_profit > 0 else 0

    The modeled ``latency_bps`` cost is NOT applied here because replaying a later book
    already captures the price move. If the execution books cannot fill the quantity,
    the trade is treated as not executed (label 0, ``outcome_status`` records why).
    If no execution tick exists within ``max_execution_wait_ms`` (end of data or a data
    gap) the row has no label and is dropped from the labeled dataset.

    The label is an approximation limited by the recording resolution: with 1 s
    snapshots every latency between 1 ms and 1000 ms maps to the next snapshot.

Features
    Computed only from the decision tick and *earlier* ticks. ``outcome_*`` and
    ``label`` columns are never features (see ``FEATURE_COLUMNS``).
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd
from services.arbitrage_engine.app.candidates import (
    Candidate,
    CostModel,
    evaluate_pair,
    walk_levels,
)
from shared.domain.orderbook import OrderBook
from shared.market_data import Tick, iter_pairs

FEATURE_GROUPS: dict[str, list[str]] = {
    "core": [
        "gross_spread_bps",
        "net_edge_bps",
        "fees_bps",
        "latency_cost_bps",
        "top_qty_ratio",
        "configured_latency_ms",
        "buy_exchange",
        "sell_exchange",
    ],
    "data_age": ["data_age_ms", "event_skew_ms"],
    "depth": ["slippage_bps", "depth_ratio", "imbalance_buy", "imbalance_sell"],
    "movement": ["mid_change_buy_bps", "mid_change_sell_bps", "spread_change_bps"],
}
FEATURE_COLUMNS: list[str] = [c for cols in FEATURE_GROUPS.values() for c in cols]
CATEGORICAL_FEATURES = ["buy_exchange", "sell_exchange"]
META_COLUMNS = [
    "decision_time",
    "tick_index",
    "symbol",
    "status",
    "label",
    "quantity",
    "outcome_net_profit",
    "outcome_status",
    "outcome_buy_cost",
    "outcome_sell_proceeds",
    "outcome_fees",
    "outcome_time",
    "candidate_net_profit",
]


@dataclass(frozen=True)
class DatasetConfig:
    notional: float = 10_000.0
    latency_ms: float = 0.0
    cost_model: CostModel = field(default_factory=CostModel)
    max_data_age_ms: float | None = None
    history_ticks: int = 5
    max_execution_wait_ms: float = 2_000.0


@dataclass
class DatasetReport:
    ticks: int = 0
    candidates_seen: int = 0
    rows: int = 0
    unlabeled_dropped: int = 0
    rejected: Counter = field(default_factory=Counter)
    label_counts: Counter = field(default_factory=Counter)
    period_start: str | None = None
    period_end: str | None = None
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = dict(self.__dict__)
        data["rejected"] = dict(self.rejected)
        data["label_counts"] = {str(k): v for k, v in self.label_counts.items()}
        return data


def _mid(book: OrderBook | None) -> float | None:
    return None if book is None else (book.bids[0][0] + book.asks[0][0]) / 2


def _change_bps(now: float | None, before: float | None) -> float:
    if now is None or before is None or before <= 0:
        return math.nan
    return (now / before - 1) * 10_000


def _top_n_qty(levels: Sequence[tuple[float, float]], n: int = 5) -> float:
    return sum(q for _, q in levels[:n])


def _imbalance(book: OrderBook) -> float:
    bid_qty, ask_qty = _top_n_qty(book.bids), _top_n_qty(book.asks)
    total = bid_qty + ask_qty
    return (bid_qty - ask_qty) / total if total > 0 else math.nan


def _top_of_book_spread_bps(buy: OrderBook | None, sell: OrderBook | None) -> float:
    if buy is None or sell is None or not buy.asks or not sell.bids:
        return math.nan
    return (sell.bids[0][0] / buy.asks[0][0] - 1) * 10_000


def build_features(
    ticks: Sequence[Tick],
    index: int,
    buy: OrderBook,
    sell: OrderBook,
    candidate: Candidate,
    cfg: DatasetConfig,
) -> dict[str, float | str]:
    """Features for ``candidate`` using only ``ticks[: index + 1]``."""
    cost = candidate.buy_cost or math.nan
    quantity = candidate.quantity or math.nan
    h = cfg.history_ticks
    past = ticks[index - h] if index - h >= 0 else None

    past_spreads = [
        _top_of_book_spread_bps(ticks[j].book(buy.exchange), ticks[j].book(sell.exchange))
        for j in range(max(0, index - h), index)
    ]
    past_spreads = [s for s in past_spreads if not math.isnan(s)]
    current_spread = _top_of_book_spread_bps(buy, sell)
    spread_change = (
        current_spread - sum(past_spreads) / len(past_spreads) if past_spreads else math.nan
    )

    event_skew = (
        abs((buy.event_at - sell.event_at).total_seconds() * 1000)
        if buy.event_at and sell.event_at
        else math.nan
    )
    return {
        "gross_spread_bps": candidate.gross_spread / cost * 10_000,
        "net_edge_bps": candidate.net_profit / cost * 10_000,
        "fees_bps": candidate.fees / cost * 10_000,
        "latency_cost_bps": candidate.latency_cost / cost * 10_000,
        "top_qty_ratio": min(buy.asks[0][1], sell.bids[0][1]) / quantity,
        "configured_latency_ms": cfg.latency_ms,
        "buy_exchange": buy.exchange,
        "sell_exchange": sell.exchange,
        "data_age_ms": candidate.data_age_ms,
        "event_skew_ms": event_skew,
        "slippage_bps": candidate.slippage / cost * 10_000,
        "depth_ratio": min(_top_n_qty(buy.asks), _top_n_qty(sell.bids)) / quantity,
        "imbalance_buy": _imbalance(buy),
        "imbalance_sell": _imbalance(sell),
        "mid_change_buy_bps": _change_bps(
            _mid(buy), _mid(past.book(buy.exchange)) if past else None
        ),
        "mid_change_sell_bps": _change_bps(
            _mid(sell), _mid(past.book(sell.exchange)) if past else None
        ),
        "spread_change_bps": spread_change,
    }


@dataclass(frozen=True)
class Execution:
    status: str  # "executed" or an "exec_*" reason
    net_profit: float | None = None
    buy_cost: float = 0.0
    sell_proceeds: float = 0.0
    fees: float = 0.0


def simulate_execution(tick: Tick, candidate: Candidate, cost_model: CostModel) -> Execution:
    """Price the candidate's fixed quantity on the books of the execution tick."""
    buy = tick.book(candidate.buy_exchange)
    sell = tick.book(candidate.sell_exchange)
    if buy is None or sell is None:
        return Execution("exec_missing_exchange")
    if not buy.is_valid() or not sell.is_valid():
        return Execution("exec_invalid_book")
    cost = walk_levels(buy.asks, candidate.quantity)
    proceeds = walk_levels(sell.bids, candidate.quantity)
    if cost is None or proceeds is None:
        return Execution("exec_insufficient_depth")
    fees = cost * cost_model.fee_rate(buy.exchange) + proceeds * cost_model.fee_rate(sell.exchange)
    return Execution("executed", proceeds - cost - fees, cost, proceeds, fees)


def execution_index(
    ticks: Sequence[Tick], times: Sequence, index: int, cfg: DatasetConfig
) -> int | None:
    target = ticks[index].decision_time + timedelta(milliseconds=cfg.latency_ms)
    j = bisect_left(times, target, lo=index)
    if j >= len(ticks):
        return None
    wait_ms = (ticks[j].decision_time - target).total_seconds() * 1000
    return j if wait_ms <= cfg.max_execution_wait_ms else None


def build_dataset(
    ticks_for_symbol: Sequence[Tick], cfg: DatasetConfig | None = None
) -> tuple[pd.DataFrame, DatasetReport]:
    """Build the labeled dataset for one symbol's chronologically ordered ticks."""
    cfg = cfg or DatasetConfig()
    ticks = list(ticks_for_symbol)
    if any(a.decision_time > b.decision_time for a, b in zip(ticks, ticks[1:], strict=False)):
        raise ValueError("ticks must be in chronological order")
    times = [t.decision_time for t in ticks]
    report = DatasetReport(ticks=len(ticks))
    report.limitations = [
        "Labels come from replaying later snapshots; resolution limits latency effects.",
        "Both legs are assumed to fill at the execution tick's visible depth.",
        "Pre-positioned inventory on both exchanges is assumed; transfers are not modeled.",
    ]
    if ticks:
        report.period_start = ticks[0].decision_time.isoformat()
        report.period_end = ticks[-1].decision_time.isoformat()

    rows: list[dict] = []
    for i, tick in enumerate(ticks):
        for buy, sell in iter_pairs(tick):
            report.candidates_seen += 1
            candidate = evaluate_pair(
                buy,
                sell,
                cfg.notional,
                cfg.cost_model,
                decision_time=tick.decision_time,
                max_data_age_ms=cfg.max_data_age_ms,
            )
            if candidate.is_rejected:
                report.rejected[candidate.status.value] += 1
                continue
            j = execution_index(ticks, times, i, cfg)
            if j is None:
                report.unlabeled_dropped += 1
                continue
            execution = simulate_execution(ticks[j], candidate, cfg.cost_model)
            if execution.status in {"exec_missing_exchange", "exec_invalid_book"}:
                report.unlabeled_dropped += 1  # no trustworthy outcome; do not guess
                continue
            outcome = execution.net_profit
            label = 1 if (outcome is not None and outcome > 0) else 0
            row: dict = {
                "decision_time": tick.decision_time.isoformat(),
                "tick_index": i,
                "symbol": tick.symbol,
                "status": candidate.status.value,
                "label": label,
                "quantity": candidate.quantity,
                "outcome_net_profit": outcome if outcome is not None else 0.0,
                "outcome_status": execution.status,
                "outcome_buy_cost": execution.buy_cost,
                "outcome_sell_proceeds": execution.sell_proceeds,
                "outcome_fees": execution.fees,
                "outcome_time": ticks[j].decision_time.isoformat(),
                "candidate_net_profit": candidate.net_profit,
            }
            row.update(build_features(ticks, i, buy, sell, candidate, cfg))
            rows.append(row)
            report.label_counts[label] += 1

    report.rows = len(rows)
    frame = pd.DataFrame(rows, columns=META_COLUMNS + FEATURE_COLUMNS)
    return frame, report
