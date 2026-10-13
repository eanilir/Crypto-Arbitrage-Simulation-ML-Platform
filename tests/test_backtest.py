import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from services.arbitrage_engine.app.candidates import CostModel
from services.ml_service.app.dataset import DatasetConfig, build_dataset
from services.simulation_engine.app.backtest import BacktestConfig, run_backtest, save_backtest
from services.simulation_engine.app.evaluation import candidate_level_report
from services.simulation_engine.app.selectors import (
    CostAwareBaseline,
    FeeAwareBaseline,
    GrossSpreadBaseline,
)
from shared.domain.orderbook import OrderBook
from shared.market_data import Tick, group_ticks
from shared.synthetic import SyntheticConfig, generate_records

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
FEES = CostModel(default_fee_rate=0.001)
INVENTORY = {"initial_quote_per_exchange": 1_000_000.0, "initial_base_per_exchange": 1_000.0}


def make_tick(seconds, a_bid, a_ask, b_bid, b_ask, qty=100.0) -> Tick:
    at = T0 + timedelta(seconds=seconds)

    def book(ex, bid, ask):
        return OrderBook(
            ex,
            "BTC/USDT",
            tuple((bid - i * 0.01, qty) for i in range(10)),
            tuple((ask + i * 0.01, qty) for i in range(10)),
            at,
        )

    return Tick("BTC/USDT", at, {"a": book("a", a_bid, a_ask), "b": book("b", b_bid, b_ask)})


def frame_for(ticks, cost=FEES, **kwargs) -> pd.DataFrame:
    return build_dataset(ticks, DatasetConfig(cost_model=cost, **kwargs))[0]


def test_gross_spread_baseline_trades_what_the_cost_aware_baseline_rejects() -> None:
    # gross +0.05 per 100 (5 bps) but fees are 20 bps round trip -> unprofitable
    frame = frame_for(
        [make_tick(0, 99.9, 100.0, 100.05, 100.1), make_tick(1, 99.9, 100.0, 100.05, 100.1)]
    )
    a = GrossSpreadBaseline().select(frame)
    b = FeeAwareBaseline().select(frame)
    c = CostAwareBaseline().select(frame)
    assert a.sum() > 0 and b.sum() == 0 and c.sum() == 0
    assert (frame[a].label == 0).all()  # gross-positive does not mean profitable


def test_baselines_are_evaluated_on_identical_candidates() -> None:
    frame = frame_for([make_tick(i, 99.9, 100.0, 100.5, 100.6) for i in range(4)])
    reports = [
        candidate_level_report(frame, s)
        for s in (GrossSpreadBaseline(), FeeAwareBaseline(), CostAwareBaseline())
    ]
    assert len({r["candidates"] for r in reports}) == 1


def test_candidate_report_metrics_are_consistent() -> None:
    frame = frame_for(
        [make_tick(i, 99.9, 100.0, 100.5, 100.6) for i in range(4)],
        cost=CostModel(default_fee_rate=0.0),
    )
    report = candidate_level_report(frame, CostAwareBaseline())
    confusion = report["confusion"]
    assert confusion["tp"] + confusion["fp"] == report["selected"]
    assert report["precision"] == pytest.approx(
        confusion["tp"] / (confusion["tp"] + confusion["fp"])
    )
    assert report["total_net_pnl"] == pytest.approx(
        frame[CostAwareBaseline().select(frame)].outcome_net_profit.sum()
    )


def test_backtest_pnl_matches_independent_calculation() -> None:
    # buy a @100.00 (walks 0.15 units), sell b @100.50; zero fees for a clean expectation
    ticks = [make_tick(i, 99.9, 100.0, 100.5, 100.6) for i in range(3)]
    cost = CostModel(default_fee_rate=0.0)
    frame = frame_for(ticks, cost=cost)
    result = run_backtest(
        frame,
        CostAwareBaseline(),
        BacktestConfig(cost_model=cost, max_trades_per_tick=1, **INVENTORY),
    )
    assert result.metrics["trades"] == 3  # latency 0: executes on the decision tick
    quantity = 10_000 / 100.0
    expected_each = quantity * (100.5 - 100.0)
    assert result.trades.net_pnl.tolist() == pytest.approx([expected_each] * 3)
    assert result.metrics["total_net_pnl"] == pytest.approx(3 * expected_each)
    # inventory moved from exchange b to exchange a: base on b down, on a up
    assert result.metrics["final_base_balances"]["a"] == pytest.approx(1_000.0 + 3 * quantity)
    assert result.metrics["final_base_balances"]["b"] == pytest.approx(1_000.0 - 3 * quantity)


def test_fees_in_backtest_match_dataset_outcome_fees() -> None:
    ticks = [make_tick(i, 99.9, 100.0, 101.0, 101.1) for i in range(4)]
    frame = frame_for(ticks)
    result = run_backtest(
        frame,
        CostAwareBaseline(),
        BacktestConfig(cost_model=FEES, max_trades_per_tick=1, **INVENTORY),
    )
    chosen = frame[CostAwareBaseline().select(frame)]
    assert result.metrics["total_fees"] == pytest.approx(chosen.outcome_fees.sum())


def test_inventory_constraint_skips_trades_instead_of_inventing_inventory() -> None:
    ticks = [make_tick(i, 99.9, 100.0, 101.0, 101.1) for i in range(8)]
    frame = frame_for(ticks)
    cfg = BacktestConfig(initial_base_per_exchange=150.0, cost_model=FEES)  # sells need 100 units
    result = run_backtest(frame, CostAwareBaseline(), cfg)
    outcomes = result.metrics["decision_outcomes"]
    assert outcomes.get("skipped_inventory", 0) > 0
    assert min(result.metrics["final_base_balances"].values()) >= 0


def test_cooldown_limits_repeated_trades_on_the_same_pair() -> None:
    ticks = [make_tick(i, 99.9, 100.0, 101.0, 101.1) for i in range(10)]
    frame = frame_for(ticks)
    free = run_backtest(
        frame, CostAwareBaseline(), BacktestConfig(cost_model=FEES, cooldown_ticks=0, **INVENTORY)
    )
    cooled = run_backtest(
        frame, CostAwareBaseline(), BacktestConfig(cost_model=FEES, cooldown_ticks=3, **INVENTORY)
    )
    assert cooled.metrics["trades"] < free.metrics["trades"]
    assert cooled.metrics["decision_outcomes"].get("skipped_cooldown", 0) > 0


def _synthetic_frame() -> pd.DataFrame:
    ticks = group_ticks(generate_records(SyntheticConfig(n_ticks=1500, interval_s=0.25, seed=11)))
    return frame_for(ticks)


def test_backtest_is_reproducible_and_order_independent() -> None:
    frame = _synthetic_frame()
    selector = CostAwareBaseline()
    first = run_backtest(frame, selector, BacktestConfig(cost_model=FEES))
    again = run_backtest(frame, selector, BacktestConfig(cost_model=FEES))
    shuffled = run_backtest(
        frame.sample(frac=1.0, random_state=1), selector, BacktestConfig(cost_model=FEES)
    )
    assert first.run_id == again.run_id == shuffled.run_id
    assert (
        first.metrics["total_net_pnl"]
        == again.metrics["total_net_pnl"]
        == shuffled.metrics["total_net_pnl"]
    )


def test_trades_are_chronological() -> None:
    result = run_backtest(_synthetic_frame(), CostAwareBaseline(), BacktestConfig(cost_model=FEES))
    assert result.trades.tick_index.is_monotonic_increasing


def test_drawdown_is_non_negative_and_save_writes_audit_files(tmp_path) -> None:
    result = run_backtest(
        _synthetic_frame(), GrossSpreadBaseline(), BacktestConfig(cost_model=FEES)
    )
    assert result.metrics["max_drawdown"] >= 0
    out = save_backtest(result, tmp_path)
    saved = json.loads((out / "config.json").read_text())
    assert saved["run_id"] == result.run_id
    for name in ("metrics.json", "trades.csv", "equity.csv", "decisions.csv"):
        assert (out / name).exists()


def test_gross_baseline_has_more_trades_but_lower_pnl_than_cost_aware() -> None:
    frame = _synthetic_frame()
    cfg = BacktestConfig(cost_model=FEES, cooldown_ticks=2)
    gross = run_backtest(frame, GrossSpreadBaseline(), cfg).metrics
    cost = run_backtest(frame, CostAwareBaseline(), cfg).metrics
    assert gross["trades"] >= cost["trades"]
    assert gross["total_net_pnl"] <= cost["total_net_pnl"]
