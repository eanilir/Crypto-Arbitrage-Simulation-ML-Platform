from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from services.arbitrage_engine.app.candidates import CostModel
from services.ml_service.app.dataset import (
    FEATURE_COLUMNS,
    DatasetConfig,
    build_dataset,
)
from shared.domain.orderbook import OrderBook
from shared.market_data import Tick, group_ticks
from shared.synthetic import SyntheticConfig, generate_records

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
NO_FEES = CostModel(default_fee_rate=0.0)


def make_book(exchange, bid, ask, qty=100.0, at=T0) -> OrderBook:
    return OrderBook(
        exchange,
        "BTC/USDT",
        bids=tuple((bid - i * 0.01, qty) for i in range(10)),
        asks=tuple((ask + i * 0.01, qty) for i in range(10)),
        received_at=at,
    )


def make_tick(seconds, a_bid, a_ask, b_bid, b_ask, qty=100.0) -> Tick:
    at = T0 + timedelta(seconds=seconds)
    books = {"a": make_book("a", a_bid, a_ask, qty, at), "b": make_book("b", b_bid, b_ask, qty, at)}
    return Tick("BTC/USDT", at, books)


def rows_for(frame: pd.DataFrame, tick_index: int, buy: str, sell: str) -> pd.Series:
    sel = frame[
        (frame.tick_index == tick_index)
        & (frame.buy_exchange == buy)
        & (frame.sell_exchange == sell)
    ]
    assert len(sel) == 1
    return sel.iloc[0]


def test_label_is_based_on_the_execution_tick_not_the_decision_tick() -> None:
    # tick 0: buy on a (ask 100) / sell on b (bid 101) looks profitable (gross +1).
    # tick 1 (1 s later): b's bid has fallen to 99.5 -> the same trade loses money.
    ticks = [
        make_tick(0, 99.9, 100.0, 101.0, 101.1),
        make_tick(1, 99.9, 100.0, 99.5, 99.6),
        make_tick(2, 99.9, 100.0, 99.5, 99.6),
    ]
    now = build_dataset(ticks, DatasetConfig(latency_ms=0, cost_model=NO_FEES))[0]
    delayed = build_dataset(ticks, DatasetConfig(latency_ms=500, cost_model=NO_FEES))[0]
    assert rows_for(now, 0, "a", "b").label == 1
    assert rows_for(delayed, 0, "a", "b").label == 0
    assert rows_for(delayed, 0, "a", "b").candidate_net_profit > 0  # decision-time view


def test_fees_are_applied_in_the_label() -> None:
    ticks = [make_tick(0, 99.9, 100.0, 100.05, 100.1), make_tick(1, 99.9, 100.0, 100.05, 100.1)]
    free = build_dataset(ticks, DatasetConfig(cost_model=NO_FEES))[0]
    paid = build_dataset(ticks, DatasetConfig(cost_model=CostModel(default_fee_rate=0.001)))[0]
    assert rows_for(free, 0, "a", "b").label == 1
    assert rows_for(paid, 0, "a", "b").label == 0


def test_both_profitable_and_unprofitable_candidates_are_kept() -> None:
    ticks = [make_tick(i, 99.9, 100.0, 101.0, 101.1) for i in range(3)]
    frame, report = build_dataset(ticks, DatasetConfig(cost_model=NO_FEES))
    assert set(frame.label) == {0, 1}  # a->b profitable, b->a unprofitable
    assert report.label_counts[0] > 0 and report.label_counts[1] > 0


def test_rows_without_a_later_execution_tick_are_dropped_not_guessed() -> None:
    ticks = [make_tick(0, 99.9, 100.0, 101.0, 101.1)]
    frame, report = build_dataset(ticks, DatasetConfig(latency_ms=500, cost_model=NO_FEES))
    assert frame.empty
    assert report.unlabeled_dropped == 2


def test_insufficient_depth_at_execution_is_label_zero() -> None:
    first = make_tick(0, 99.9, 100.0, 101.0, 101.1, qty=100.0)
    # execution tick: almost no liquidity
    second = make_tick(1, 99.9, 100.0, 101.0, 101.1, qty=0.001)
    frame, _ = build_dataset([first, second], DatasetConfig(latency_ms=500, cost_model=NO_FEES))
    row = rows_for(frame, 0, "a", "b")
    assert row.label == 0
    assert row.outcome_status == "exec_insufficient_depth"


def test_rejected_candidates_are_counted_not_emitted() -> None:
    shallow_first = make_tick(0, 99.9, 100.0, 101.0, 101.1, qty=0.001)
    second = make_tick(1, 99.9, 100.0, 101.0, 101.1)
    frame, report = build_dataset([shallow_first, second], DatasetConfig(cost_model=NO_FEES))
    assert report.rejected["rejected_insufficient_depth"] == 2
    assert (frame.tick_index == 0).sum() == 0


def test_ticks_must_be_chronological() -> None:
    ticks = [make_tick(1, 99.9, 100.0, 101.0, 101.1), make_tick(0, 99.9, 100.0, 101.0, 101.1)]
    with pytest.raises(ValueError):
        build_dataset(ticks)


def test_outcome_and_label_columns_are_never_features() -> None:
    assert not [c for c in FEATURE_COLUMNS if c.startswith("outcome") or c == "label"]
    assert "candidate_net_profit" not in FEATURE_COLUMNS


def _synthetic_ticks(n=400):
    return group_ticks(generate_records(SyntheticConfig(n_ticks=n, interval_s=0.5, seed=3)))


def test_features_do_not_depend_on_future_ticks() -> None:
    ticks = _synthetic_ticks()
    cfg = DatasetConfig(latency_ms=0, cost_model=CostModel(default_fee_rate=0.001))
    full, _ = build_dataset(ticks, cfg)
    cut = 250
    truncated, _ = build_dataset(ticks[: cut + 1], cfg)
    last = truncated[truncated.tick_index == cut].reset_index(drop=True)
    same = full[full.tick_index == cut].reset_index(drop=True)
    assert len(last) == len(same) > 0
    pd.testing.assert_frame_equal(last[FEATURE_COLUMNS], same[FEATURE_COLUMNS])


def test_dataset_generation_is_deterministic() -> None:
    cfg = DatasetConfig(cost_model=CostModel(default_fee_rate=0.001))
    first, _ = build_dataset(_synthetic_ticks(200), cfg)
    second, _ = build_dataset(_synthetic_ticks(200), cfg)
    pd.testing.assert_frame_equal(first, second)


def test_history_features_are_nan_without_history_not_invented() -> None:
    ticks = [make_tick(i, 99.9, 100.0, 101.0, 101.1) for i in range(3)]
    frame, _ = build_dataset(ticks, DatasetConfig(cost_model=NO_FEES, history_ticks=2))
    first = rows_for(frame, 0, "a", "b")
    assert pd.isna(first.mid_change_buy_bps)
    assert pd.isna(first.spread_change_bps)
