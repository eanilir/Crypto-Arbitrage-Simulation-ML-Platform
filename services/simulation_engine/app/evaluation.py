"""Metrics shared by the baseline report, ML evaluation and experiments (plan §19)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from services.simulation_engine.app.selectors import Selector
from sklearn.metrics import average_precision_score, roc_auc_score


def classification_metrics(
    y_true: pd.Series, selected: pd.Series, score: pd.Series
) -> dict[str, Any]:
    y = y_true.to_numpy().astype(int)
    pred = selected.to_numpy().astype(bool)
    tp = int(((y == 1) & pred).sum())
    fp = int(((y == 0) & pred).sum())
    fn = int(((y == 1) & ~pred).sum())
    tn = int(((y == 0) & ~pred).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    both_classes = len(np.unique(y)) == 2
    s = score.to_numpy().astype(float)
    finite = np.isfinite(s)
    ok = both_classes and finite.all()
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "pr_auc": float(average_precision_score(y, s)) if ok else None,
        "roc_auc": float(roc_auc_score(y, s)) if ok else None,
        "positive_rate": float(y.mean()) if len(y) else None,
    }


def candidate_level_report(frame: pd.DataFrame, selector: Selector) -> dict[str, Any]:
    """Evaluate a selector on every candidate row (no portfolio or inventory limits)."""
    selected = selector.select(frame).fillna(False).astype(bool)
    score = selector.score(frame)
    chosen = frame[selected]
    n_selected = int(selected.sum())
    gross = float((chosen["outcome_sell_proceeds"] - chosen["outcome_buy_cost"]).sum())
    executed = chosen[chosen["outcome_status"] == "executed"]
    net = float(chosen["outcome_net_profit"].sum())
    report: dict[str, Any] = {
        "selector": selector.name,
        "params": selector.params(),
        "candidates": int(len(frame)),
        "selected": n_selected,
        "executed": int(len(executed)),
        "total_net_pnl": net,
        "avg_net_per_selected": net / n_selected if n_selected else None,
        "pct_selected_profitable": float((chosen["label"] == 1).mean()) if n_selected else None,
        "gross_pnl": gross,
        "total_fees": float(chosen["outcome_fees"].sum()),
        "missed_profitable": int(((frame["label"] == 1) & ~selected).sum()),
    }
    report.update(classification_metrics(frame["label"], selected, score))
    return report
