import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))

import train_klines_model as tkm  # noqa: E402


def synthetic_closes(n: int = 2000, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    base = 100.0 * np.exp(np.cumsum(rng.normal(0, 1e-4, n)))
    index = list(range(0, n * 60_000, 60_000))
    close = pd.DataFrame(
        {
            "a": base * (1 + rng.normal(0, 1e-4, n)),
            "b": base * (1 + rng.normal(0, 1e-4, n)),
        },
        index=index,
    )
    volume = pd.DataFrame(rng.uniform(1, 10, (n, 2)), index=index, columns=["a", "b"])
    return close, volume


def test_features_at_minute_t_do_not_depend_on_later_minutes() -> None:
    close, volume = synthetic_closes()
    full = tkm.build_features(close, volume)
    cut = 1500
    truncated = tkm.build_features(close.iloc[: cut + 1], volume.iloc[: cut + 1])
    pd.testing.assert_series_equal(
        full.iloc[cut], truncated.iloc[cut], check_names=False, rtol=1e-9
    )


def test_label_uses_only_the_next_minute_and_is_not_a_feature() -> None:
    close, volume = synthetic_closes()
    target = tkm.build_target(close, cost_bps=1.0)
    gaps = tkm.pair_gaps(close).max(axis=1)
    assert target["future_best_gap"].iloc[10] == pytest.approx(gaps.iloc[11])
    assert target["label"].iloc[10] == float(gaps.iloc[11] > 1.0)
    assert pd.isna(target["label"].iloc[-1])  # no next minute at the end: no label
    features = tkm.build_features(close, volume)
    assert not {"label", "future_best_gap"} & set(features.columns)


def test_split_is_chronological_and_purged() -> None:
    parts = tkm.chronological_split(1000)
    train, val, test = parts["train"], parts["validation"], parts["test"]
    assert train.stop < val.start <= val.stop < test.start + 1
    assert val.start - train.stop >= tkm.HORIZON  # last training label cannot reach validation
    assert test.stop == 1000


def test_scenario_is_refused_when_there_are_too_few_positives() -> None:
    close, volume = synthetic_closes()
    features = tkm.build_features(close, volume)
    info = tkm.run_scenario(features, close, cost_bps=1_000.0)  # nothing is ever profitable
    assert "skipped" in info and "test_results" not in info


def test_scenario_trains_and_reports_all_methods_when_positives_exist() -> None:
    close, volume = synthetic_closes(6000)
    features = tkm.build_features(close, volume)
    info = tkm.run_scenario(features, close, cost_bps=1.0)
    assert "skipped" not in info
    assert set(info["test_results"]) == {
        "rule_persistence (gap now > cost)",
        "logistic_regression",
        "random_forest",
        "gradient_boosting",
        "trade_never",
    }
    assert info["test_results"]["trade_never"]["upper_bound_pnl_per_10k"] == 0.0
