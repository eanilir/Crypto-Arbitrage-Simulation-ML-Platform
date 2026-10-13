"""Run backtests in a background thread and keep their status on disk."""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from services.api.app.core.config import Settings
from services.api.app.schemas import BacktestRequest
from services.api.app.services.market_access import DataUnavailable, resolve_source
from services.arbitrage_engine.app.candidates import CostModel
from services.ml_service.app.dataset import DatasetConfig, build_dataset
from services.ml_service.app.training import load_model, selector_for
from services.simulation_engine.app.backtest import BacktestConfig, run_backtest, save_backtest
from services.simulation_engine.app.selectors import (
    CostAwareBaseline,
    FeeAwareBaseline,
    GrossSpreadBaseline,
)
from shared.market_data import load_ticks, ticks_by_symbol


def list_models(settings: Settings) -> list[Path]:
    if not settings.models_dir.is_dir():
        return []
    return sorted(
        (p for p in settings.models_dir.iterdir() if (p / "model.joblib").exists()),
        key=lambda p: p.stat().st_mtime,
    )


def find_model(settings: Settings, version: str | None) -> Path:
    models = list_models(settings)
    if not models:
        raise DataUnavailable("no trained model available")
    if version is None:
        return models[-1]
    for path in models:
        if path.name == version:
            return path
    raise DataUnavailable(f"unknown model version: {version}")


class BacktestManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self.settings.backtest_dir.mkdir(parents=True, exist_ok=True)

    def _status_path(self, job_id: str) -> Path:
        return self.settings.backtest_dir / f"job_{job_id}.json"

    def _write(self, job_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._status_path(job_id).write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )

    def submit(self, request: BacktestRequest) -> str:
        resolve_source(self.settings, request.source)  # fail fast on unknown/unsafe source
        if request.selector == "ml":
            find_model(self.settings, request.model_version)
        job_id = uuid.uuid4().hex[:12]
        self._write(
            job_id,
            {
                "job_id": job_id,
                "status": "queued",
                "request": request.model_dump(),
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._executor.submit(self._run, job_id, request)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        if not job_id.isalnum():
            return None
        path = self._status_path(job_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def latest_run_dir(self, run_id: str | None = None) -> Path | None:
        if run_id is not None:
            if not run_id.isalnum():
                return None
            path = self.settings.backtest_dir / run_id
            return path if (path / "metrics.json").exists() else None
        runs = [p for p in self.settings.backtest_dir.iterdir() if (p / "metrics.json").exists()]
        return max(runs, key=lambda p: p.stat().st_mtime) if runs else None

    def _run(self, job_id: str, request: BacktestRequest) -> None:
        base = {"job_id": job_id, "request": request.model_dump()}
        self._write(job_id, {**base, "status": "running"})
        try:
            result_info = self._execute(request)
            self._write(job_id, {**base, "status": "completed", **result_info})
        except Exception as error:  # surfaced to the client; details stay in the status file
            self._write(
                job_id,
                {
                    **base,
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                    "trace": traceback.format_exc(limit=3),
                },
            )

    def _execute(self, request: BacktestRequest) -> dict[str, Any]:
        ticks = load_ticks(resolve_source(self.settings, request.source))
        by_symbol = ticks_by_symbol(ticks)
        if not by_symbol:
            raise DataUnavailable("source contains no valid snapshots")
        symbol = request.symbol or max(by_symbol, key=lambda s: len(by_symbol[s]))
        if symbol not in by_symbol:
            raise DataUnavailable(f"no data for symbol {symbol}")
        costs = CostModel(default_fee_rate=request.fee_rate, latency_bps=request.latency_bps)
        frame, report = build_dataset(
            by_symbol[symbol],
            DatasetConfig(
                notional=request.notional,
                latency_ms=request.latency_ms,
                cost_model=costs,
                max_data_age_ms=request.max_data_age_ms,
            ),
        )
        if frame.empty:
            raise DataUnavailable("no labeled candidates could be built from this data")

        note = None
        if request.selector == "ml":
            model = load_model(find_model(self.settings, request.model_version))
            test_start = pd.Timestamp(model.metadata["split_boundaries"]["test_start"])
            frame = frame[pd.to_datetime(frame["decision_time"], utc=True) >= test_start]
            note = (
                "ML backtests only use rows at/after the model's test_start (no in-sample trading)"
            )
            if frame.empty:
                raise DataUnavailable("no rows after the model's test period in this source")
            selector = selector_for(model)
        else:
            selector = {
                "gross_spread": GrossSpreadBaseline(),
                "fee_aware": FeeAwareBaseline(),
                "cost_aware": CostAwareBaseline(max_data_age_ms=request.max_data_age_ms),
            }[request.selector]

        first_price = by_symbol[symbol][0].books
        reference_price = next(iter(first_price.values())).bids[0][0]
        bt_cfg = BacktestConfig(
            initial_quote_per_exchange=1_000_000.0,
            initial_base_per_exchange=1_000_000.0 / reference_price,
            cooldown_ticks=request.cooldown_ticks,
            cost_model=costs,
        )
        result = run_backtest(frame, selector, bt_cfg)
        run_dir = save_backtest(result, self.settings.backtest_dir)
        return {
            "run_id": result.run_id,
            "run_dir": run_dir.name,
            "symbol": symbol,
            "note": note,
            "metrics": result.metrics,
            "dataset": report.to_dict(),
        }
