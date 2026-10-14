import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

from shared.historical import MINUTE_MS, Candle, write_csv  # noqa: E402

import historical_klines_analysis as hka  # noqa: E402

T0 = 1_700_000_000_000 // MINUTE_MS * MINUTE_MS


def series(values) -> pd.Series:
    return pd.Series(values, index=range(len(values)))


def test_pair_gap_is_sell_over_buy_in_bps() -> None:
    aligned = pd.DataFrame({"a": [100.0, 100.0], "b": [100.1, 99.9]})
    gross = hka.pair_gross_bps(aligned)
    assert gross["a->b"].tolist() == pytest.approx([10.0, -10.0])
    assert gross["b->a"].tolist() == pytest.approx(
        [(100 / 100.1 - 1) * 1e4, (100 / 99.9 - 1) * 1e4]
    )


def test_episodes_merge_consecutive_minutes() -> None:
    mask = series([False, True, True, False, True, False, True, True, True])
    assert hka.episodes(mask) == (3, pytest.approx(2.0))
    assert hka.episodes(series([False, False])) == (0, 0.0)


def test_scenario_table_applies_fees_per_side_and_costs() -> None:
    gross = pd.DataFrame({"a->b": [3.0, 1.0, -2.0], "b->a": [-3.0, -1.0, 2.0]})
    costs = {
        "a": {"buy_cost_bps": 0.5, "sell_cost_bps": 0.5},
        "b": {"buy_cost_bps": 0.5, "sell_cost_bps": 0.5},
    }
    table = hka.scenario_table(gross, costs)
    row = table[(table.fee_bps_per_side == 1.0) & (table.cost_assumption == "fees only")].iloc[0]
    # net = gross - 2*1 bps: only the 3 bps and the +2 bps minutes... 3-2=1>0, 1-2<0, 2-2=0 (not > 0)
    assert row.profitable_minutes == 1
    with_costs = table[
        (table.fee_bps_per_side == 1.0) & (table.cost_assumption != "fees only")
    ].iloc[0]
    # extra cost is 0.5 + 0.5 = 1.0 bps, so the best minute is 3 - 2 - 1 = 0, which is not > 0
    assert with_costs.profitable_minutes == 0
    assert pd.isna(with_costs.mean_net_bps_when_profitable)
    no_costs_table = hka.scenario_table(gross, None)
    assert set(no_costs_table.cost_assumption) == {"fees only"}


def test_load_aligned_keeps_only_minutes_present_on_every_exchange(tmp_path) -> None:
    def candles(minutes, price):
        return [
            Candle(T0 + m * MINUTE_MS, price, price + 1, price - 1, price, 1.0, price)
            for m in minutes
        ]

    write_csv(tmp_path / "binance_BTCUSDT_1m.csv", candles([0, 1, 2, 3], 100.0))
    write_csv(tmp_path / "bybit_BTCUSDT_1m.csv", candles([0, 2, 3], 101.0))  # minute 1 missing
    aligned = hka.load_aligned(tmp_path, ["binance", "bybit"])
    assert len(aligned) == 3
    assert (T0 + MINUTE_MS) not in aligned.index  # nothing was filled in
