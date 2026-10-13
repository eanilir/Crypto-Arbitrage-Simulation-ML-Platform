"""Run research experiments 1-6 (project_plan.md §18) and write tables, plots and a report.

    python experiments/run_experiments.py --input data/raw/synthetic --output experiments/results/synthetic

Everything is reproducible from the saved ``config.json`` plus the input data. Results
computed from synthetic data are labeled as such in the report; they describe the
generator's assumptions, not real markets.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.arbitrage_engine.app.candidates import CostModel  # noqa: E402
from services.ml_service.app.dataset import (  # noqa: E402
    FEATURE_COLUMNS,
    FEATURE_GROUPS,
    DatasetConfig,
    build_dataset,
)
from services.ml_service.app.training import (  # noqa: E402
    MODEL_NAMES,
    InsufficientDataError,
    chronological_split,
    selector_for,
    train_model,
    walk_forward_splits,
)
from services.simulation_engine.app.backtest import BacktestConfig, run_backtest  # noqa: E402
from services.simulation_engine.app.evaluation import candidate_level_report  # noqa: E402
from services.simulation_engine.app.selectors import (  # noqa: E402
    CostAwareBaseline,
    FeeAwareBaseline,
    GrossSpreadBaseline,
)
from shared.market_data import LoadReport, load_ticks, ticks_by_symbol  # noqa: E402

warnings.filterwarnings("ignore")


@dataclass
class ExperimentConfig:
    notional: float = 10_000.0
    fee_rate: float = 0.001
    latency_bps: float = 0.0  # modeled latency cost used by the cost-aware baseline
    latencies_ms: list[float] = field(default_factory=lambda: [0, 50, 100, 250, 500])
    staleness_quantiles: list[float] = field(default_factory=lambda: [0.5, 0.75, 0.9])
    ml_latency_ms: float = 250.0
    cooldown_ticks: int = 2
    n_folds: int = 3
    seed: int = 42
    min_train_positives: int = 30
    initial_quote_per_exchange: float = 1_000_000.0


def cost_model(cfg: ExperimentConfig) -> CostModel:
    return CostModel(default_fee_rate=cfg.fee_rate, latency_bps=cfg.latency_bps)


def backtest_cfg(cfg: ExperimentConfig, reference_price: float) -> BacktestConfig:
    return BacktestConfig(
        initial_quote_per_exchange=cfg.initial_quote_per_exchange,
        initial_base_per_exchange=cfg.initial_quote_per_exchange / reference_price,
        cooldown_ticks=cfg.cooldown_ticks,
        cost_model=cost_model(cfg),
    )


def make_frame(ticks, cfg: ExperimentConfig, latency_ms: float, max_age: float | None = None):
    return build_dataset(
        ticks,
        DatasetConfig(
            notional=cfg.notional,
            latency_ms=latency_ms,
            cost_model=cost_model(cfg),
            max_data_age_ms=max_age,
        ),
    )


def baselines() -> list:
    return [GrossSpreadBaseline(), FeeAwareBaseline(), CostAwareBaseline()]


def row_for(selector, frame, bt_cfg) -> dict[str, Any]:
    report = candidate_level_report(frame, selector)
    metrics = run_backtest(frame, selector, bt_cfg).metrics
    return {
        "selector": selector.name,
        "candidates": report["candidates"],
        "selected": report["selected"],
        "precision": report["precision"],
        "recall": report["recall"],
        "f1": report["f1"],
        "pr_auc": report["pr_auc"],
        "candidate_level_net_pnl": report["total_net_pnl"],
        "trades": metrics["trades"],
        "backtest_net_pnl": metrics["total_net_pnl"],
        "backtest_gross_pnl": metrics["gross_pnl"],
        "backtest_fees": metrics["total_fees"],
        "pct_profitable_trades": metrics["pct_profitable_trades"],
        "max_drawdown": metrics["max_drawdown"],
        "skipped_inventory": metrics["decision_outcomes"].get("skipped_inventory", 0),
    }


def experiment_1_and_3(
    ticks, cfg: ExperimentConfig, bt_cfg
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Gross vs net (exp. 1) and latency scenarios (exp. 3) share the per-latency datasets."""
    gross_rows, latency_rows, frames = [], [], {}
    for latency in cfg.latencies_ms:
        frame, report = make_frame(ticks, cfg, latency)
        frames[latency] = frame
        gp = frame[frame["gross_spread_bps"] > 0]
        gross_rows.append(
            {
                "latency_ms": latency,
                "priced_candidates": len(frame),
                "gross_positive": len(gp),
                "gross_positive_net_profitable": int((gp["label"] == 1).sum()),
                "pct_gross_positive_unprofitable_after_costs": (
                    float((gp["label"] == 0).mean()) if len(gp) else None
                ),
                "mean_gross_spread_bps_of_gross_positive": float(gp["gross_spread_bps"].mean())
                if len(gp)
                else None,
                "mean_net_outcome_per_gross_positive": float(gp["outcome_net_profit"].mean())
                if len(gp)
                else None,
            }
        )
        for selector in baselines():
            row = row_for(selector, frame, bt_cfg)
            row["latency_ms"] = latency
            latency_rows.append(row)
    return pd.DataFrame(gross_rows), pd.DataFrame(latency_rows), frames


def experiment_2(ticks, cfg: ExperimentConfig, bt_cfg, base_frame: pd.DataFrame) -> pd.DataFrame:
    ages = base_frame["data_age_ms"].dropna()
    limits: list[float | None] = [None] + [float(ages.quantile(q)) for q in cfg.staleness_quantiles]
    rows = []
    for limit in limits:
        frame, report = make_frame(ticks, cfg, 0.0, limit)
        for selector in (GrossSpreadBaseline(), CostAwareBaseline()):
            row = row_for(selector, frame, bt_cfg) if len(frame) else {"selector": selector.name}
            row["max_data_age_ms"] = limit
            row["rejected_stale"] = int(report.rejected.get("rejected_stale", 0))
            rows.append(row)
    return pd.DataFrame(rows)


def has_enough_positives(split, cfg: ExperimentConfig) -> tuple[bool, str]:
    positives = int(split.train["label"].sum())
    if positives < cfg.min_train_positives:
        return False, f"only {positives} positive training labels (< {cfg.min_train_positives})"
    if split.validation["label"].nunique() < 2:
        return False, "validation period has a single class"
    return True, ""


def experiment_4(
    frame: pd.DataFrame, cfg: ExperimentConfig, bt_cfg
) -> tuple[pd.DataFrame, dict, Any]:
    split = chronological_split(frame)
    ok, reason = has_enough_positives(split, cfg)
    info: dict[str, Any] = {
        "split": split.boundaries,
        "purged": split.purged,
        "rows": {
            "train": len(split.train),
            "validation": len(split.validation),
            "test": len(split.test),
        },
    }
    rows = [row_for(s, split.test, bt_cfg) for s in baselines()]
    models = {}
    if ok:
        for name in MODEL_NAMES:
            model = train_model(name, split, seed=cfg.seed)
            models[name] = model
            rows.append(row_for(selector_for(model), split.test, bt_cfg))
        info["model_versions"] = {n: m.version for n, m in models.items()}
        info["thresholds"] = {n: m.threshold for n, m in models.items()}
    else:
        info["ml_skipped"] = reason
    return pd.DataFrame(rows), info, (split, models)


def experiment_5(split, cfg: ExperimentConfig, bt_cfg) -> pd.DataFrame | str:
    ok, reason = has_enough_positives(split, cfg)
    if not ok:
        return f"skipped: {reason}"
    variants = {"all_features": FEATURE_COLUMNS}
    for group in ("data_age", "depth", "movement"):
        variants[f"without_{group}"] = [
            c for c in FEATURE_COLUMNS if c not in FEATURE_GROUPS[group]
        ]
    rows = []
    for name in ("logistic_regression", "gradient_boosting"):
        for label, columns in variants.items():
            model = train_model(name, split, feature_columns=columns, seed=cfg.seed, tune=False)
            row = row_for(selector_for(model), split.test, bt_cfg)
            row.update({"model": name, "variant": label})
            rows.append(row)
    return pd.DataFrame(rows)


def experiment_6(frame: pd.DataFrame, cfg: ExperimentConfig, bt_cfg) -> pd.DataFrame | str:
    try:
        folds = walk_forward_splits(frame, n_folds=cfg.n_folds)
    except InsufficientDataError as error:
        return f"skipped: {error}"
    rows = []
    for number, split in enumerate(folds, start=1):
        base = row_for(CostAwareBaseline(), split.test, bt_cfg)
        row = {
            "fold": number,
            "test_rows": len(split.test),
            "test_positives": int(split.test["label"].sum()),
            "C_cost_aware_pnl": base["backtest_net_pnl"],
        }
        ok, reason = has_enough_positives(split, cfg)
        for name in ("logistic_regression", "gradient_boosting"):
            if ok:
                model = train_model(name, split, seed=cfg.seed, tune=False)
                row[f"ml_{name}_pnl"] = row_for(selector_for(model), split.test, bt_cfg)[
                    "backtest_net_pnl"
                ]
            else:
                row[f"ml_{name}_pnl"] = None
        row["note"] = "" if ok else reason
        rows.append(row)
    return pd.DataFrame(rows)


def plot_latency(latency_df: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, group in latency_df.groupby("selector"):
        ax.plot(group["latency_ms"], group["backtest_net_pnl"], marker="o", label=name)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xlabel("simulated execution latency (ms)")
    ax.set_ylabel("backtest net P&L (simulated)")
    ax.set_title("Net simulated P&L by latency scenario")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_selectors(table: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(table["selector"], table["backtest_net_pnl"])
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_ylabel("backtest net P&L (simulated, test period)")
    ax.set_title("Rule-based vs ML-filtered selection")
    plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_equity(split, models, bt_cfg, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    selectors = baselines() + [selector_for(m) for m in models.values()]
    for selector in selectors:
        result = run_backtest(split.test, selector, bt_cfg)
        if len(result.trades):
            ax.plot(range(len(result.trades)), result.trades["cumulative_pnl"], label=selector.name)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xlabel("trade number")
    ax.set_ylabel("cumulative net P&L (simulated)")
    ax.set_title("Equity curves on the test period")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def md_table(frame: pd.DataFrame, columns: list[str] | None = None, digits: int = 4) -> str:
    if frame.empty:
        return "_no rows_"
    frame = frame[columns] if columns else frame
    formatted = frame.copy()
    for column in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[column]):
            formatted[column] = formatted[column].map(
                lambda v: "" if pd.isna(v) else f"{v:.{digits}g}"
            )
    header = "| " + " | ".join(map(str, formatted.columns)) + " |"
    rule = "|" + "|".join("---" for _ in formatted.columns) + "|"
    body = [
        "| " + " | ".join(str(v) for v in row) + " |" for row in formatted.itertuples(index=False)
    ]
    return "\n".join([header, rule, *body])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=None, help="JSON overriding ExperimentConfig"
    )
    parser.add_argument("--max-ticks", type=int, default=None, help="use only the first N ticks")
    args = parser.parse_args()

    cfg = ExperimentConfig()
    if args.config:
        for key, value in json.loads(args.config.read_text()).items():
            setattr(cfg, key, value)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)

    load_report = LoadReport()
    all_ticks = load_ticks(args.input, report=load_report)
    synthetic = any("synthetic" in str(p) for p in [args.input]) or _is_synthetic(args.input)
    symbol, ticks = max(ticks_by_symbol(all_ticks).items(), key=lambda kv: len(kv[1]))
    if args.max_ticks:
        ticks = ticks[: args.max_ticks]
    spacings = [
        (b.decision_time - a.decision_time).total_seconds() * 1000 for a, b in zip(ticks, ticks[1:], strict=False)
    ]
    resolution_ms = statistics.median(spacings) if spacings else None
    reference_price = float(
        np.mean([(t.books[next(iter(t.books))].bids[0][0]) for t in ticks[:50]])
    )
    bt_cfg = backtest_cfg(cfg, reference_price)

    (out / "config.json").write_text(
        json.dumps(
            {
                "experiment": asdict(cfg),
                "input": str(args.input),
                "symbol": symbol,
                "ticks": len(ticks),
                "synthetic_data": synthetic,
            },
            indent=2,
        )
    )

    gross_df, latency_df, frames = experiment_1_and_3(ticks, cfg, bt_cfg)
    base_frame = frames[cfg.latencies_ms[0]]
    stale_df = experiment_2(ticks, cfg, bt_cfg, base_frame)
    ml_frame = (
        frames[cfg.ml_latency_ms]
        if cfg.ml_latency_ms in frames
        else make_frame(ticks, cfg, cfg.ml_latency_ms)[0]
    )
    try:
        ml_df, ml_info, (split, models) = experiment_4(ml_frame, cfg, bt_cfg)
        ablation = experiment_5(split, cfg, bt_cfg)
        walk = experiment_6(ml_frame, cfg, bt_cfg)
    except InsufficientDataError as error:
        ml_df, ml_info, split, models = pd.DataFrame(), {"skipped": str(error)}, None, {}
        ablation = walk = f"skipped: {error}"

    for name, table in {
        "exp1_gross_vs_net": gross_df,
        "exp2_staleness": stale_df,
        "exp3_latency": latency_df,
        "exp4_rule_vs_ml": ml_df,
        "exp5_ablation": ablation,
        "exp6_walk_forward": walk,
    }.items():
        if isinstance(table, pd.DataFrame):
            table.to_csv(out / f"{name}.csv", index=False)
    if not latency_df.empty:
        plot_latency(latency_df, out / "latency_pnl.png")
    if not ml_df.empty:
        plot_selectors(ml_df, out / "selectors_test_pnl.png")
        if split is not None:
            plot_equity(split, models, bt_cfg, out / "equity_curves.png")

    write_report(
        out,
        cfg,
        args.input,
        symbol,
        ticks,
        resolution_ms,
        synthetic,
        load_report,
        gross_df,
        stale_df,
        latency_df,
        ml_df,
        ml_info,
        ablation,
        walk,
        bt_cfg,
    )
    print(f"report written to {out / 'report.md'}")


def _is_synthetic(path: Path) -> bool:
    files = [path] if path.is_file() else sorted(path.glob("market_depth_*.ndjson"))
    for file in files[:1]:
        with file.open(encoding="utf-8") as handle:
            first = handle.readline()
            return bool(first) and json.loads(first).get("synthetic") is True
    return False


def write_report(
    out,
    cfg,
    source,
    symbol,
    ticks,
    resolution_ms,
    synthetic,
    load_report,
    gross_df,
    stale_df,
    latency_df,
    ml_df,
    ml_info,
    ablation,
    walk,
    bt_cfg,
) -> None:
    banner = (
        "> **SYNTHETIC DATA.** These numbers come from a generator with assumed jumps and "
        "exchange lags. They show that the pipeline works and what the assumptions imply; "
        "they are NOT findings about real markets.\n\n"
        if synthetic
        else "> Recorded public order-book snapshots; simulation only, no orders were placed.\n\n"
    )
    period = (
        f"{ticks[0].decision_time.isoformat()} -> {ticks[-1].decision_time.isoformat()}"
        if ticks
        else "n/a"
    )
    lines = [
        f"# Experiment report: {symbol}",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        banner,
        "## Setup (plan §19.4)",
        "",
        f"- **Dataset period:** {period}",
        f"- **Data source / resolution:** `{source}`; {len(ticks)} ticks; median tick spacing "
        f"{resolution_ms:.0f} ms; REST depth snapshots"
        if resolution_ms
        else f"- **Data source:** `{source}`",
        f"- **Records loaded:** {load_report.records} ({load_report.invalid_records} invalid, "
        f"{load_report.malformed_lines} malformed); by exchange {dict(load_report.by_exchange)}",
        "- **Baselines:** A gross spread, B fee-aware, C cost-aware (+ D ML-filtered)",
        f"- **Models:** {', '.join(MODEL_NAMES)}; chronological 60/20/20 split with purge; "
        "threshold and hyper-parameters chosen on validation only",
        f"- **Feature set:** {', '.join(FEATURE_COLUMNS)}",
        "- **Target:** label = 1 if replayed execution net profit > 0 after fees (see `dataset.py`)",
        f"- **Fees / costs:** taker fee {cfg.fee_rate:.4%} per exchange (assumption); modeled latency cost "
        f"{cfg.latency_bps} bps in baseline C; notional {cfg.notional:,.0f}",
        f"- **Latency scenarios (ms):** {cfg.latencies_ms}; **staleness limits:** quantiles {cfg.staleness_quantiles}",
        f"- **Backtest:** pre-positioned inventory ({bt_cfg.initial_quote_per_exchange:,.0f} quote and "
        f"{bt_cfg.initial_base_per_exchange:.3f} base per exchange), cooldown {cfg.cooldown_ticks} ticks, "
        "1 trade per tick, full fills at visible depth, no transfer fees",
        "",
        "## Experiment 1: gross spread versus net profit",
        "",
        md_table(gross_df),
        "",
        "## Experiment 2: market-data staleness",
        "",
        "Data age = decision time minus the oldest book receive time of the pair (cross-exchange receive skew). "
        "Limits are derived from observed quantiles, not universal thresholds.",
        "",
        md_table(
            stale_df,
            [
                "max_data_age_ms",
                "selector",
                "rejected_stale",
                "candidates",
                "selected",
                "trades",
                "backtest_net_pnl",
            ],
        ),
        "",
        "## Experiment 3: simulated execution latency",
        "",
        f"Resolution limit: with median tick spacing of {resolution_ms:.0f} ms, any latency between 1 ms and "
        "one tick maps to the next snapshot, so nearby scenarios can coincide. These are simulation settings, "
        "not measured exchange latencies."
        if resolution_ms
        else "",
        "",
        md_table(
            latency_df,
            [
                "latency_ms",
                "selector",
                "selected",
                "trades",
                "backtest_net_pnl",
                "pct_profitable_trades",
                "max_drawdown",
            ],
        ),
        "",
        "![latency](latency_pnl.png)",
        "",
        f"## Experiment 4: rule-based versus ML filtering (latency {cfg.ml_latency_ms:.0f} ms, test period)",
        "",
        f"```json\n{json.dumps(ml_info, indent=2, default=str)}\n```",
        "",
        md_table(
            ml_df,
            [
                "selector",
                "candidates",
                "selected",
                "precision",
                "recall",
                "pr_auc",
                "trades",
                "backtest_net_pnl",
                "pct_profitable_trades",
            ],
        )
        if not ml_df.empty
        else "_not run_",
        "",
        "![selectors](selectors_test_pnl.png)",
        "",
        "## Experiment 5: feature ablation",
        "",
        md_table(
            ablation,
            ["model", "variant", "selected", "precision", "recall", "pr_auc", "backtest_net_pnl"],
        )
        if isinstance(ablation, pd.DataFrame)
        else str(ablation),
        "",
        "## Experiment 6: cross-period (walk-forward) evaluation",
        "",
        md_table(walk) if isinstance(walk, pd.DataFrame) else str(walk),
        "",
        "## Known limitations",
        "",
        "- Labels and fills come from replaying recorded snapshots; they are approximations, not real executions.",
        "- Pre-positioned inventory is assumed; cross-exchange transfers, rebalancing and withdrawal fees are not modeled.",
        "- Fee rates are assumptions, not verified for any account.",
        "- At latency 0 the label equals the decision-time net edge (the trade executes on the same snapshot), so rule C and the models look perfect by construction; only latency > 0 tests prediction.",
        "- A single test period (or a few walk-forward folds) cannot establish generalization.",
        "- ML is not assumed to beat the cost-aware rule; where it does not, that is reported as is.",
        "- Novelty claims require the literature review in `docs/literature_review.md` (not yet done).",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
