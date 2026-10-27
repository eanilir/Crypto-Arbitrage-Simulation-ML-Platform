"""Train and evaluate models that predict the NEXT minute's cross-exchange price gap (1-minute candles).

    python experiments/train_klines_model.py \
        --klines data/raw/historical/klines_1m --output experiments/results/historical_klines_model

Question answered: "will the best buy->sell gap in the next minute exceed the round-trip cost?"
Target at minute t uses only minute t+horizon; features at minute t use only minutes <= t.

LIMITED SIMULATION: candles contain no bid/ask or depth, so the target is a close-to-close gap
versus an ASSUMED round-trip cost, not an executable profit (project_plan.md §8.5). The "P&L"
columns are upper bounds that ignore fills, inventory, latency and persistence.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.historical import read_csv  # noqa: E402

warnings.filterwarnings("ignore")

HORIZON = 1  # minutes ahead
MIN_POSITIVES = 30  # fewer positive training labels than this: refuse to train


def load_closes_and_volumes(
    klines_dir: Path, exchanges: list[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    closes, volumes = [], []
    for exchange in exchanges:
        path = next(klines_dir.glob(f"{exchange}_*_1m.csv"))
        candles = read_csv(path)
        index = [c.open_time_ms for c in candles]
        closes.append(pd.Series([c.close for c in candles], index=index, name=exchange))
        volumes.append(pd.Series([c.volume_quote for c in candles], index=index, name=exchange))
    close = pd.concat(closes, axis=1, join="inner").sort_index()
    volume = pd.concat(volumes, axis=1, join="inner").sort_index().loc[close.index]
    return close, volume


def pair_gaps(close: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {f"{b}->{s}": (close[s] / close[b] - 1) * 1e4 for b, s in permutations(close.columns, 2)}
    )


def build_features(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """Features at minute t from minutes <= t only (rolling windows look backwards)."""
    gaps = pair_gaps(close)
    best = gaps.max(axis=1)
    feats = pd.DataFrame(index=close.index)
    feats["best_gap"] = best
    for pair in gaps.columns:
        feats[f"gap_{pair}"] = gaps[pair]
    for lag in (1, 2, 3, 5):
        feats[f"best_gap_lag{lag}"] = best.shift(lag)
    for window in (5, 15, 60):
        feats[f"best_gap_mean_{window}"] = best.rolling(window).mean()
        feats[f"best_gap_std_{window}"] = best.rolling(window).std()
    ret = np.log(close.iloc[:, 0]).diff() * 1e4
    feats["ret_1"] = ret
    for window in (5, 15, 60):
        feats[f"volatility_{window}"] = ret.rolling(window).std()
    total_volume = volume.sum(axis=1)
    feats["log_volume_1"] = np.log1p(total_volume)
    feats["volume_ratio_5_60"] = total_volume.rolling(5).mean() / total_volume.rolling(60).mean()
    minutes = pd.to_datetime(close.index, unit="ms", utc=True)
    feats["hour_sin"] = np.sin(2 * np.pi * minutes.hour.to_numpy() / 24)
    feats["hour_cos"] = np.cos(2 * np.pi * minutes.hour.to_numpy() / 24)
    feats["weekday"] = minutes.weekday.to_numpy()
    return feats.replace([np.inf, -np.inf], np.nan)


def build_target(close: pd.DataFrame, cost_bps: float, horizon: int = HORIZON) -> pd.DataFrame:
    """Label and the realised future gap (the latter is NOT a feature)."""
    future_best = pair_gaps(close).max(axis=1).shift(-horizon)
    return pd.DataFrame(
        {"future_best_gap": future_best, "label": (future_best > cost_bps).astype("float")}
    ).where(future_best.notna())


def chronological_split(n: int, horizon: int = HORIZON) -> dict[str, slice]:
    """60/20/20 split with a purge of `horizon` rows so no label reaches into the next period."""
    a, b = int(n * 0.6), int(n * 0.8)
    return {
        "train": slice(0, a - horizon),
        "validation": slice(a, b - horizon),
        "test": slice(b, n),
    }


def make_model(name: str, seed: int) -> Pipeline:
    if name == "logistic_regression":
        model = LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5, random_state=seed)
        steps = [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    elif name == "random_forest":
        model = RandomForestClassifier(
            n_estimators=120,
            min_samples_leaf=20,
            max_depth=8,
            class_weight="balanced_subsample",
            n_jobs=1,
            random_state=seed,
        )
        steps = [("impute", SimpleImputer(strategy="median"))]
    else:
        model = HistGradientBoostingClassifier(
            learning_rate=0.05, max_depth=4, max_iter=150, random_state=seed
        )
        steps = [("impute", SimpleImputer(strategy="median"))]
    return Pipeline([*steps, ("model", model)])


def selection_metrics(
    y: np.ndarray,
    selected: np.ndarray,
    score: np.ndarray,
    future_gap: np.ndarray,
    cost_bps: float,
    notional: float = 10_000.0,
) -> dict:
    tp = int((selected & (y == 1)).sum())
    fp = int((selected & (y == 0)).sum())
    fn = int((~selected & (y == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    pnl = float(((future_gap[selected] - cost_bps) * notional / 1e4).sum())
    return {
        "selected": int(selected.sum()),
        "precision": precision,
        "recall": recall,
        "pr_auc": float(average_precision_score(y, score)) if 0 < y.sum() < len(y) else None,
        "upper_bound_pnl_per_10k": pnl,
        "positives_in_period": int(y.sum()),
    }


def pick_threshold(
    proba: np.ndarray, future_gap: np.ndarray, cost_bps: float, min_selected: int = 5
) -> float:
    """Threshold with the best validation upper-bound P&L (validation data only)."""
    best, best_pnl = 0.5, -np.inf
    for threshold in np.unique(
        np.round(
            np.concatenate([np.linspace(0.05, 0.95, 19), np.quantile(proba, [0.95, 0.99, 0.999])]),
            4,
        )
    ):
        mask = proba >= threshold
        if mask.sum() < min_selected:
            continue
        pnl = float((future_gap[mask] - cost_bps).sum())
        if pnl > best_pnl:
            best, best_pnl = float(threshold), pnl
    return best


def run_scenario(
    features: pd.DataFrame, close: pd.DataFrame, cost_bps: float, seed: int = 42
) -> dict:
    target = build_target(close, cost_bps)
    data = features.join(target).dropna(subset=["label", "future_best_gap"])
    data = data.iloc[60:]  # rolling windows need history
    columns = [c for c in features.columns]
    parts = chronological_split(len(data))
    train, val, test = (data.iloc[parts[k]] for k in ("train", "validation", "test"))
    info: dict = {
        "cost_bps_round_trip": cost_bps,
        "rows": {"train": len(train), "validation": len(val), "test": len(test)},
        "positives": {
            "train": int(train["label"].sum()),
            "validation": int(val["label"].sum()),
            "test": int(test["label"].sum()),
        },
        "period": {
            "start": pd.to_datetime(data.index[0], unit="ms", utc=True).isoformat(),
            "end": pd.to_datetime(data.index[-1], unit="ms", utc=True).isoformat(),
        },
    }
    if train["label"].sum() < MIN_POSITIVES or val["label"].sum() < 5 or test["label"].sum() < 5:
        info["skipped"] = (
            f"not enough positive examples (train {int(train['label'].sum())}, "
            f"validation {int(val['label'].sum())}, test {int(test['label'].sum())}); "
            "a model cannot learn from this and any result would be noise"
        )
        return info

    y_test = test["label"].to_numpy().astype(int)
    gap_test = test["future_best_gap"].to_numpy()
    results = {}
    persistence = (test["best_gap"] > cost_bps).to_numpy()
    results["rule_persistence (gap now > cost)"] = selection_metrics(
        y_test, persistence, test["best_gap"].to_numpy(), gap_test, cost_bps
    )
    for name in ("logistic_regression", "random_forest", "gradient_boosting"):
        model = make_model(name, seed)
        model.fit(train[columns], train["label"].astype(int))
        val_proba = model.predict_proba(val[columns])[:, 1]
        threshold = pick_threshold(val_proba, val["future_best_gap"].to_numpy(), cost_bps)
        proba = model.predict_proba(test[columns])[:, 1]
        metrics = selection_metrics(y_test, proba >= threshold, proba, gap_test, cost_bps)
        metrics["threshold"] = threshold
        results[name] = metrics
    results["trade_never"] = {"selected": 0, "upper_bound_pnl_per_10k": 0.0}
    info["test_results"] = results
    return info


def md_scenario(info: dict) -> str:
    lines = [
        f"### Round-trip cost {info['cost_bps_round_trip']} bps",
        "",
        f"- Period: {info['period']['start']} -> {info['period']['end']}",
        f"- Rows (train/validation/test): {info['rows']['train']:,} / {info['rows']['validation']:,} / {info['rows']['test']:,}",
        f"- Positive examples (train/validation/test): {info['positives']['train']} / "
        f"{info['positives']['validation']} / {info['positives']['test']}",
        "",
    ]
    if "skipped" in info:
        return "\n".join(lines + [f"**Not trained:** {info['skipped']}.", ""])
    lines += [
        "| method | selected | precision | recall | PR-AUC | upper-bound P&L per 10k | threshold |",
        "|---|---|---|---|---|---|---|",
    ]

    def fmt(v):
        return "" if v is None else (f"{v:.3g}" if isinstance(v, float) else str(v))

    for name, m in info["test_results"].items():
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    fmt(m.get("selected")),
                    fmt(m.get("precision")),
                    fmt(m.get("recall")),
                    fmt(m.get("pr_auc")),
                    fmt(m.get("upper_bound_pnl_per_10k")),
                    fmt(m.get("threshold")),
                ]
            )
            + " |"
        )
    return "\n".join(lines + [""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--klines", type=Path, default=Path("data/raw/historical/klines_1m"))
    parser.add_argument(
        "--output", type=Path, default=Path("experiments/results/historical_klines_model")
    )
    parser.add_argument("--exchanges", nargs="+", default=["binance", "bybit", "okx"])
    parser.add_argument(
        "--costs",
        nargs="+",
        type=float,
        default=[1.0, 2.0, 3.0, 5.0, 20.0],
        help="round-trip cost in bps (2 x fee per side + assumed spread)",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    close, volume = load_closes_and_volumes(args.klines, args.exchanges)
    features = build_features(close, volume)
    scenarios = [run_scenario(features, close, cost, args.seed) for cost in args.costs]
    (args.output / "results.json").write_text(
        json.dumps(scenarios, indent=2, default=str), encoding="utf-8"
    )

    lines = [
        "# 1-minute candle model: will next minute's cross-exchange gap exceed the cost?",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        "> **Limited, assumption-based simulation.** Candles hold no bid/ask or depth. The target is a "
        "close-to-close gap versus an assumed round-trip cost; 'upper-bound P&L' ignores fills, inventory, "
        "latency and how long a gap lasts. It is not achievable profit (project_plan.md §8.5).",
        "",
        "## Setup",
        "",
        f"- Exchanges: {', '.join(args.exchanges)}; {len(close):,} aligned minutes (nothing filled in)",
        f"- Target at minute t: best buy->sell close gap at minute t+{HORIZON} > round-trip cost",
        "- Features at minute t: current and lagged gaps, rolling gap mean/std, volatility, volume, hour/weekday "
        "(only minutes <= t)",
        "- Split: chronological 60/20/20 with a purge of 1 minute; threshold chosen on validation only; "
        "test evaluated once",
        "- Methods: persistence rule, Logistic Regression, Random Forest, Gradient Boosting, never trade",
        "",
        "## Results (test period)",
        "",
    ]
    lines += [md_scenario(s) for s in scenarios]
    lines += [
        "## How to read this",
        "",
        "- If a scenario was not trained, that is the finding for that cost level: there were too few "
        "positive minutes to learn from.",
        "- A model is only useful if it beats the persistence rule AND trade-never on the test period.",
        "- Fees are assumptions; real tiers differ by account.",
        "",
    ]
    (args.output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"report written to {args.output / 'report.md'}")


if __name__ == "__main__":
    main()
