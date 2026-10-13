"""Model training, chronological validation and versioned persistence (plan §15-16).

Splitting is chronological by tick: train = earliest, validation = later, test = latest.
Because a row's label depends on a LATER snapshot (``outcome_time``), rows whose outcome
time reaches into the next period are purged, so no future information crosses a split
boundary. Hyper-parameters and the decision threshold are chosen on the validation
period only; the test period is evaluated once at the end.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from services.ml_service.app.dataset import CATEGORICAL_FEATURES, FEATURE_COLUMNS
from services.simulation_engine.app.backtest import dataset_fingerprint
from services.simulation_engine.app.evaluation import classification_metrics
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

MODEL_NAMES = ("logistic_regression", "random_forest", "gradient_boosting")


class InsufficientDataError(RuntimeError):
    """Raised when a split cannot support training or evaluation (e.g. one class only)."""


@dataclass(frozen=True)
class SplitConfig:
    train_fraction: float = 0.6
    validation_fraction: float = 0.2  # remaining fraction is the test period


@dataclass
class ChronologicalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    boundaries: dict[str, str]
    purged: dict[str, int]


def split_at(
    frame: pd.DataFrame, train_end_tick: int, val_end_tick: int, test_end_tick: int | None = None
) -> ChronologicalSplit:
    """Split by tick boundaries and purge rows whose outcome reaches into the next period."""
    data = frame.sort_values("tick_index", kind="stable").reset_index(drop=True)
    times = pd.to_datetime(data["decision_time"], utc=True)
    outcome_times = pd.to_datetime(data["outcome_time"], utc=True)
    tick = data["tick_index"]
    in_train = tick < train_end_tick
    in_val = (tick >= train_end_tick) & (tick < val_end_tick)
    in_test = tick >= val_end_tick
    if test_end_tick is not None:
        in_test &= tick < test_end_tick
    if not in_train.any() or not in_val.any() or not in_test.any():
        raise InsufficientDataError("a split period is empty")
    val_start = times[tick >= train_end_tick].min()
    test_start = times[tick >= val_end_tick].min()
    train = data[in_train & (outcome_times < val_start)]
    validation = data[in_val & (outcome_times < test_start)]
    test = data[in_test]
    return ChronologicalSplit(
        train=train,
        validation=validation,
        test=test,
        boundaries={
            "validation_start": val_start.isoformat(),
            "test_start": test_start.isoformat(),
        },
        purged={
            "train": int(in_train.sum() - len(train)),
            "validation": int(in_val.sum() - len(validation)),
        },
    )


def chronological_split(frame: pd.DataFrame, cfg: SplitConfig | None = None) -> ChronologicalSplit:
    cfg = cfg or SplitConfig()
    if not 0 < cfg.train_fraction < 1 or cfg.train_fraction + cfg.validation_fraction >= 1:
        raise ValueError("fractions must leave a non-empty test period")
    ticks = np.sort(frame["tick_index"].unique())
    if len(ticks) < 10:
        raise InsufficientDataError("need at least 10 ticks for a three-way split")
    train_end = int(ticks[int(len(ticks) * cfg.train_fraction)])
    val_end = int(ticks[int(len(ticks) * (cfg.train_fraction + cfg.validation_fraction))])
    return split_at(frame, train_end, val_end)


def walk_forward_splits(
    frame: pd.DataFrame, n_folds: int = 4, validation_fraction: float = 0.25
) -> list[ChronologicalSplit]:
    """Expanding-window evaluation: block k is tested on a model fit on blocks before it."""
    ticks = np.sort(frame["tick_index"].unique())
    if n_folds < 1 or len(ticks) < 10 * (n_folds + 1):
        raise InsufficientDataError("not enough ticks for the requested walk-forward folds")
    edges = [int(ticks[int(len(ticks) * k / (n_folds + 1))]) for k in range(n_folds + 1)]
    edges.append(int(ticks[-1]) + 1)
    splits = []
    for fold in range(1, n_folds + 1):
        history_start, history_end, test_end = edges[0], edges[fold], edges[fold + 1]
        history_ticks = ticks[(ticks >= history_start) & (ticks < history_end)]
        train_end = int(history_ticks[int(len(history_ticks) * (1 - validation_fraction))])
        splits.append(split_at(frame, train_end, history_end, test_end))
    return splits


def _preprocessor(feature_columns: Sequence[str], scale: bool) -> ColumnTransformer:
    categorical = [c for c in feature_columns if c in CATEGORICAL_FEATURES]
    numeric = [c for c in feature_columns if c not in CATEGORICAL_FEATURES]
    numeric_steps: list[tuple[str, Any]] = [
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True))
    ]
    if scale:
        numeric_steps.append(("scale", StandardScaler()))
    transformers: list[tuple[str, Any, list[str]]] = [("num", Pipeline(numeric_steps), numeric)]
    if categorical:
        transformers.append(("cat", OneHotEncoder(handle_unknown="ignore"), categorical))
    return ColumnTransformer(transformers)


def _estimator(name: str, params: dict[str, Any], seed: int) -> Any:
    if name == "logistic_regression":
        return LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=seed, **params
        )
    if name == "random_forest":
        return RandomForestClassifier(
            n_estimators=150,
            class_weight="balanced_subsample",
            random_state=seed,
            n_jobs=1,
            **params,
        )
    if name == "gradient_boosting":
        return HistGradientBoostingClassifier(random_state=seed, **params)
    raise ValueError(f"unknown model: {name}")


PARAM_GRIDS: dict[str, list[dict[str, Any]]] = {
    "logistic_regression": [{"C": 0.1}, {"C": 1.0}, {"C": 10.0}],
    "random_forest": [
        {"min_samples_leaf": 5, "max_depth": 8},
        {"min_samples_leaf": 20, "max_depth": None},
    ],
    "gradient_boosting": [
        {"learning_rate": 0.05, "max_depth": 3, "max_iter": 150},
        {"learning_rate": 0.1, "max_depth": 5, "max_iter": 100},
    ],
}


def build_pipeline(
    name: str, params: dict[str, Any], feature_columns: Sequence[str], seed: int
) -> Pipeline:
    scale = name == "logistic_regression"
    return Pipeline(
        [("prep", _preprocessor(feature_columns, scale)), ("model", _estimator(name, params, seed))]
    )


def choose_threshold(
    validation: pd.DataFrame, probabilities: np.ndarray, min_selected: int = 5
) -> tuple[float, dict[str, Any]]:
    """Threshold maximizing simulated net P&L on the validation period only."""
    best_threshold, best_pnl = 0.5, -np.inf
    grid = np.unique(
        np.round(
            np.concatenate(
                [np.linspace(0.05, 0.95, 19), np.quantile(probabilities, [0.9, 0.95, 0.99])]
            ),
            4,
        )
    )
    pnl = validation["outcome_net_profit"].to_numpy()
    for threshold in grid:
        mask = probabilities >= threshold
        if mask.sum() < min_selected:
            continue
        value = float(pnl[mask].sum())
        if value > best_pnl:
            best_threshold, best_pnl = float(threshold), value
    info = {
        "validation_net_pnl_at_threshold": None if best_pnl == -np.inf else best_pnl,
        "fallback": best_pnl == -np.inf,
    }
    return best_threshold, info


@dataclass
class TrainedModel:
    name: str
    version: str
    pipeline: Pipeline
    threshold: float
    feature_columns: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        return self.pipeline.predict_proba(frame[self.feature_columns])[:, 1]


def train_model(
    name: str,
    split: ChronologicalSplit,
    *,
    feature_columns: Sequence[str] | None = None,
    seed: int = 42,
    tune: bool = True,
) -> TrainedModel:
    columns = list(feature_columns or FEATURE_COLUMNS)
    train, validation = split.train, split.validation
    for label, part in (("train", train), ("validation", validation)):
        if part["label"].nunique() < 2:
            raise InsufficientDataError(f"{label} period has a single class; cannot fit/tune")

    grid = PARAM_GRIDS[name] if tune else PARAM_GRIDS[name][:1]
    best: tuple[float, dict[str, Any], Pipeline] | None = None
    tuning: list[dict[str, Any]] = []
    for params in grid:
        pipeline = build_pipeline(name, params, columns, seed)
        pipeline.fit(train[columns], train["label"])
        proba = pipeline.predict_proba(validation[columns])[:, 1]
        score = float(average_precision_score(validation["label"], proba))
        tuning.append({"params": params, "validation_pr_auc": score})
        if best is None or score > best[0]:
            best = (score, params, pipeline)
    assert best is not None
    _, best_params, pipeline = best

    val_proba = pipeline.predict_proba(validation[columns])[:, 1]
    threshold, threshold_info = choose_threshold(validation, val_proba)
    fingerprint = dataset_fingerprint(pd.concat([train, validation, split.test]))
    version = f"{name}-{fingerprint.split('-')[-1][:8]}-s{seed}"
    return TrainedModel(
        name=name,
        version=version,
        pipeline=pipeline,
        threshold=threshold,
        feature_columns=columns,
        metadata={
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "best_params": best_params,
            "tuning": tuning,
            "threshold": threshold,
            "threshold_info": threshold_info,
            "target": "label = outcome_net_profit > 0 after replayed execution",
            "feature_columns": columns,
            "split_boundaries": split.boundaries,
            "purged_rows": split.purged,
            "rows": {"train": len(train), "validation": len(validation), "test": len(split.test)},
            "data_fingerprint": fingerprint,
            "validation_metrics": classification_metrics(
                validation["label"],
                pd.Series(val_proba >= threshold, index=validation.index),
                pd.Series(val_proba, index=validation.index),
            ),
        },
    )


def evaluate_on_test(model: TrainedModel, split: ChronologicalSplit) -> dict[str, Any]:
    """Final, single evaluation on the held-out test period."""
    test = split.test
    proba = model.predict_proba(test)
    selected = pd.Series(proba >= model.threshold, index=test.index)
    return classification_metrics(test["label"], selected, pd.Series(proba, index=test.index))


def save_model(model: TrainedModel, root: Path | str = "models") -> Path:
    out = Path(root) / model.version
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": model.pipeline,
            "threshold": model.threshold,
            "feature_columns": model.feature_columns,
            "name": model.name,
            "version": model.version,
        },
        out / "model.joblib",
    )
    (out / "metadata.json").write_text(
        json.dumps(model.metadata, indent=2, default=str), encoding="utf-8"
    )
    return out


def load_model(path: Path | str) -> TrainedModel:
    path = Path(path)
    payload = joblib.load(path / "model.joblib")
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    return TrainedModel(
        name=payload["name"],
        version=payload["version"],
        pipeline=payload["pipeline"],
        threshold=payload["threshold"],
        feature_columns=payload["feature_columns"],
        metadata=metadata,
    )


def selector_for(model: TrainedModel) -> Any:
    from services.simulation_engine.app.selectors import MLFilteredSelector

    return MLFilteredSelector(
        predict_proba=model.predict_proba,
        threshold=model.threshold,
        model_name=model.name,
        model_version=model.version,
    )
