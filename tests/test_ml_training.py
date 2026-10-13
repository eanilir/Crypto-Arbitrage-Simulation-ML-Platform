import math

import numpy as np
import pandas as pd
import pytest
from services.arbitrage_engine.app.candidates import CostModel
from services.ml_service.app.dataset import (
    FEATURE_COLUMNS,
    FEATURE_GROUPS,
    DatasetConfig,
    build_dataset,
)
from services.ml_service.app.inference import FeatureValidationError, predict
from services.ml_service.app.training import (
    MODEL_NAMES,
    InsufficientDataError,
    SplitConfig,
    chronological_split,
    evaluate_on_test,
    load_model,
    save_model,
    selector_for,
    train_model,
)
from shared.market_data import group_ticks
from shared.synthetic import SyntheticConfig, generate_records


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    ticks = group_ticks(generate_records(SyntheticConfig(n_ticks=4000, interval_s=0.25, seed=5)))
    cfg = DatasetConfig(latency_ms=250, cost_model=CostModel(default_fee_rate=0.001))
    return build_dataset(ticks, cfg)[0]


@pytest.fixture(scope="module")
def split(frame):
    return chronological_split(frame)


def test_split_is_strictly_chronological(split) -> None:
    train_end = pd.to_datetime(split.train.decision_time, utc=True).max()
    val = pd.to_datetime(split.validation.decision_time, utc=True)
    test = pd.to_datetime(split.test.decision_time, utc=True)
    assert train_end < val.min()
    assert val.max() < test.min()


def test_split_purges_rows_whose_label_reaches_into_the_next_period(split) -> None:
    val_start = pd.Timestamp(split.boundaries["validation_start"])
    test_start = pd.Timestamp(split.boundaries["test_start"])
    assert (pd.to_datetime(split.train.outcome_time, utc=True) < val_start).all()
    assert (pd.to_datetime(split.validation.outcome_time, utc=True) < test_start).all()
    assert split.purged["train"] > 0  # 250 ms latency => rows at the boundary are purged


def test_split_rejects_bad_fractions(frame) -> None:
    with pytest.raises(ValueError):
        chronological_split(frame, SplitConfig(train_fraction=0.9, validation_fraction=0.2))


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_models_train_and_produce_valid_probabilities(name, split) -> None:
    model = train_model(name, split, tune=False)
    proba = model.predict_proba(split.test)
    assert len(proba) == len(split.test)
    assert ((proba >= 0) & (proba <= 1)).all()
    assert 0 < model.threshold < 1
    assert model.version.startswith(name)
    assert model.metadata["rows"]["test"] == len(split.test)
    metrics = evaluate_on_test(model, split)
    assert set(metrics["confusion"]) == {"tp", "fp", "fn", "tn"}


def test_training_is_reproducible_for_a_fixed_seed(split) -> None:
    a = train_model("random_forest", split, tune=False, seed=3)
    b = train_model("random_forest", split, tune=False, seed=3)
    assert a.version == b.version
    np.testing.assert_allclose(a.predict_proba(split.test), b.predict_proba(split.test))


def test_test_period_never_influences_model_or_threshold(split) -> None:
    baseline = train_model("logistic_regression", split)
    tampered_test = split.test.copy()
    tampered_test["label"] = 1 - tampered_test["label"]
    tampered_test["outcome_net_profit"] = -tampered_test["outcome_net_profit"]
    tampered = type(split)(
        split.train, split.validation, tampered_test, split.boundaries, split.purged
    )
    other = train_model("logistic_regression", tampered)
    assert baseline.threshold == other.threshold
    np.testing.assert_allclose(baseline.predict_proba(split.test), other.predict_proba(split.test))


def test_single_class_training_data_is_reported_not_hidden(split) -> None:
    bad_train = split.train.assign(label=0)
    bad = type(split)(bad_train, split.validation, split.test, split.boundaries, split.purged)
    with pytest.raises(InsufficientDataError):
        train_model("logistic_regression", bad, tune=False)


def test_feature_groups_support_ablation(split) -> None:
    without_age = [c for c in FEATURE_COLUMNS if c not in FEATURE_GROUPS["data_age"]]
    model = train_model("logistic_regression", split, feature_columns=without_age, tune=False)
    assert "data_age_ms" not in model.feature_columns
    assert model.predict_proba(split.test).shape[0] == len(split.test)


def test_save_and_load_roundtrip_keeps_predictions_and_metadata(split, tmp_path) -> None:
    model = train_model("logistic_regression", split, tune=False)
    path = save_model(model, tmp_path)
    loaded = load_model(path)
    assert loaded.version == model.version
    assert loaded.threshold == model.threshold
    np.testing.assert_allclose(loaded.predict_proba(split.test), model.predict_proba(split.test))
    assert loaded.metadata["data_fingerprint"] == model.metadata["data_fingerprint"]


def test_ml_selector_plugs_into_the_same_evaluation(split) -> None:
    from services.simulation_engine.app.evaluation import candidate_level_report

    model = train_model("logistic_regression", split, tune=False)
    report = candidate_level_report(split.test, selector_for(model))
    assert report["candidates"] == len(split.test)
    assert report["params"]["model_version"] == model.version


def test_inference_validates_features_and_returns_metadata(split) -> None:
    model = train_model("logistic_regression", split, tune=False)
    row = split.test.iloc[0][FEATURE_COLUMNS].to_dict()
    result = predict(model, row)
    assert 0 <= result["probability_profitable"] <= 1
    assert result["model_version"] == model.version

    with pytest.raises(FeatureValidationError):
        predict(model, {k: v for k, v in row.items() if k != "net_edge_bps"})
    with pytest.raises(FeatureValidationError):
        predict(model, {**row, "net_edge_bps": math.inf})
    with pytest.raises(FeatureValidationError):
        predict(model, {**row, "buy_exchange": 7})
    predict(model, {**row, "event_skew_ms": math.nan})  # NaN = missing is allowed


def test_walk_forward_folds_are_expanding_and_never_overlap(frame) -> None:
    from services.ml_service.app.training import walk_forward_splits

    folds = walk_forward_splits(frame, n_folds=3)
    assert len(folds) == 3
    previous_test_end = None
    for fold in folds:
        assert (
            pd.to_datetime(fold.train.decision_time, utc=True).max()
            < pd.to_datetime(fold.validation.decision_time, utc=True).min()
        )
        assert (
            pd.to_datetime(fold.validation.decision_time, utc=True).max()
            < pd.to_datetime(fold.test.decision_time, utc=True).min()
        )
        if previous_test_end is not None:  # later folds train on strictly more history
            assert len(fold.train) + len(fold.validation) > previous_test_end
        previous_test_end = len(fold.train) + len(fold.validation)
    assert folds[0].test.tick_index.max() < folds[1].test.tick_index.min()
