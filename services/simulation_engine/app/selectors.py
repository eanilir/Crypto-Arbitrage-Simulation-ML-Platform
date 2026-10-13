"""Candidate selectors: rule-based baselines A/B/C and the ML-filtered rule D.

All selectors consume the SAME dataset rows (same candidates, fees, execution
assumptions) and only decision-time feature columns, so no method gets an unfair
advantage (project_plan.md §14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd


class Selector(Protocol):
    name: str

    def select(self, frame: pd.DataFrame) -> pd.Series:
        """Boolean mask of candidates to trade."""

    def score(self, frame: pd.DataFrame) -> pd.Series:
        """Ranking score; higher is better (used when several candidates compete)."""

    def params(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class GrossSpreadBaseline:
    """Baseline A: trade whenever the top-of-book gross spread is positive."""

    min_gross_bps: float = 0.0
    name: str = "A_gross_spread"

    def select(self, frame: pd.DataFrame) -> pd.Series:
        return frame["gross_spread_bps"] > self.min_gross_bps

    def score(self, frame: pd.DataFrame) -> pd.Series:
        return frame["gross_spread_bps"]

    def params(self) -> dict[str, Any]:
        return {"min_gross_bps": self.min_gross_bps}


@dataclass(frozen=True)
class FeeAwareBaseline:
    """Baseline B: gross spread must exceed the transaction fees."""

    min_edge_bps: float = 0.0
    name: str = "B_fee_aware"

    def _edge(self, frame: pd.DataFrame) -> pd.Series:
        return frame["gross_spread_bps"] - frame["fees_bps"]

    def select(self, frame: pd.DataFrame) -> pd.Series:
        return self._edge(frame) > self.min_edge_bps

    def score(self, frame: pd.DataFrame) -> pd.Series:
        return self._edge(frame)

    def params(self) -> dict[str, Any]:
        return {"min_edge_bps": self.min_edge_bps}


@dataclass(frozen=True)
class CostAwareBaseline:
    """Baseline C: net edge after fees, order-book slippage and modeled latency cost,
    optionally requiring data fresher than ``max_data_age_ms``."""

    min_net_edge_bps: float = 0.0
    max_data_age_ms: float | None = None
    name: str = "C_cost_aware"

    def select(self, frame: pd.DataFrame) -> pd.Series:
        mask = frame["net_edge_bps"] > self.min_net_edge_bps
        if self.max_data_age_ms is not None:
            mask &= frame["data_age_ms"] <= self.max_data_age_ms
        return mask

    def score(self, frame: pd.DataFrame) -> pd.Series:
        return frame["net_edge_bps"]

    def params(self) -> dict[str, Any]:
        return {
            "min_net_edge_bps": self.min_net_edge_bps,
            "max_data_age_ms": self.max_data_age_ms,
        }


@dataclass
class MLFilteredSelector:
    """Baseline D: trade candidates whose predicted P(profitable) >= ``threshold``.

    ``predict_proba`` maps a feature frame to probabilities in [0, 1]. The threshold must
    be chosen on validation data only.
    """

    predict_proba: Any
    threshold: float
    model_name: str = "model"
    model_version: str = "unversioned"
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = f"D_ml_{self.model_name}"

    def score(self, frame: pd.DataFrame) -> pd.Series:
        return pd.Series(np.asarray(self.predict_proba(frame)), index=frame.index)

    def select(self, frame: pd.DataFrame) -> pd.Series:
        return self.score(frame) >= self.threshold

    def params(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "model_version": self.model_version,
            "threshold": self.threshold,
        }
