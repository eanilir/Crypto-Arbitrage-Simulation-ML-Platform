"""FastAPI service exposing recorded market data, candidates, predictions and backtests.

Analysis only: nothing here can place orders. Errors share one body shape,
``{"error": {"code", "message"}}``; "no data / no model" is a 404/503 and is distinct from a
200 with an empty list (data exists but nothing matched).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from services.api.app.core.config import Settings
from services.api.app.schemas import BacktestRequest
from services.api.app.services.backtest_jobs import BacktestManager, find_model, list_models
from services.api.app.services.market_access import DataUnavailable, clean, latest_ticks
from services.arbitrage_engine.app.candidates import CostModel, find_candidates, rank_by_net_profit
from services.ml_service.app.dataset import DatasetConfig, build_features
from services.ml_service.app.inference import predict
from services.ml_service.app.training import load_model
from shared.market_data import iter_pairs
from shared.utils.logging import configure_logging

logger = logging.getLogger("api")
VERSION = "0.1.0"


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Crypto Arbitrage Simulation API", version=VERSION)
    app.state.settings = settings
    manager = BacktestManager(settings)
    app.state.backtests = manager

    @app.exception_handler(DataUnavailable)
    async def _unavailable(_: Request, error: DataUnavailable) -> JSONResponse:
        return error_response(404, "data_unavailable", str(error))

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0] if error.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []))
        return error_response(
            422, "invalid_request", f"{where}: {first.get('msg', 'invalid input')}"
        )

    @app.exception_handler(HTTPException)
    async def _http(_: Request, error: HTTPException) -> JSONResponse:
        return error_response(error.status_code, "http_error", str(error.detail))

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, error: Exception) -> JSONResponse:
        logger.exception("unhandled_error")
        return error_response(500, "internal_error", "unexpected server error")

    @app.get("/health")
    def health() -> dict[str, Any]:
        data_ok = settings.data_root.is_dir() and any(
            settings.data_root.rglob("market_depth_*.ndjson")
        )
        return {
            "status": "ok",
            "version": VERSION,
            "time": datetime.now(timezone.utc).isoformat(),
            "market_data_available": bool(data_ok),
            "models_available": len(list_models(settings)),
            "simulation_only": True,
        }

    @app.get("/markets")
    def markets() -> dict[str, Any]:
        ticks, path, synthetic = latest_ticks(settings, count=1)
        tick = ticks[-1]
        return {
            "symbols": sorted({tick.symbol}),
            "exchanges": sorted(tick.books),
            "source_file": path.name,
            "synthetic": synthetic,
        }

    @app.get("/prices")
    def prices(symbol: str | None = None) -> dict[str, Any]:
        ticks, path, synthetic = latest_ticks(settings, symbol, count=1)
        tick = ticks[-1]
        now = datetime.now(timezone.utc)
        return clean(
            {
                "symbol": tick.symbol,
                "decision_time": tick.decision_time.isoformat(),
                "age_seconds": (now - tick.decision_time).total_seconds(),
                "synthetic": synthetic,
                "quotes": [
                    {
                        "exchange": b.exchange,
                        "bid": b.bids[0][0],
                        "ask": b.asks[0][0],
                        "bid_qty": b.bids[0][1],
                        "ask_qty": b.asks[0][1],
                        "event_time": b.event_at.isoformat() if b.event_at else None,
                        "received_time": b.received_at.isoformat(),
                    }
                    for b in tick.books.values()
                ],
            }
        )

    @app.get("/opportunities")
    def opportunities(
        symbol: str | None = None,
        notional: float = Query(10_000.0, gt=0, le=10_000_000),
        fee_rate: float = Query(0.001, ge=0, le=0.05),
        latency_bps: float = Query(0.0, ge=0, le=1_000),
        max_data_age_ms: float | None = Query(None, gt=0),
        only_net_profitable: bool = False,
        include_rejected: bool = True,
    ) -> dict[str, Any]:
        ticks, _, synthetic = latest_ticks(settings, symbol, count=1)
        tick = ticks[-1]
        model = CostModel(default_fee_rate=fee_rate, latency_bps=latency_bps)
        found = rank_by_net_profit(
            find_candidates(
                tick.books.values(),
                notional,
                model,
                decision_time=tick.decision_time,
                max_data_age_ms=max_data_age_ms,
            )
        )
        if only_net_profitable:
            found = [c for c in found if c.is_net_profitable]
        elif not include_rejected:
            found = [c for c in found if not c.is_rejected]
        return clean(
            {
                "symbol": tick.symbol,
                "decision_time": tick.decision_time.isoformat(),
                "synthetic": synthetic,
                "assumptions": {
                    "notional": notional,
                    "fee_rate": fee_rate,
                    "latency_bps": latency_bps,
                },
                "count": len(found),
                "candidates": [c.to_dict() for c in found],
            }
        )

    @app.get("/predictions")
    def predictions(
        symbol: str | None = None,
        notional: float = Query(10_000.0, gt=0, le=10_000_000),
        fee_rate: float = Query(0.001, ge=0, le=0.05),
        model_version: str | None = None,
    ) -> dict[str, Any]:
        model = load_model(find_model(settings, model_version))
        cfg = DatasetConfig(notional=notional, cost_model=CostModel(default_fee_rate=fee_rate))
        ticks, _, synthetic = latest_ticks(settings, symbol, count=cfg.history_ticks + 1)
        tick, index = ticks[-1], len(ticks) - 1
        rows = []
        for buy, sell in iter_pairs(tick):
            from services.arbitrage_engine.app.candidates import evaluate_pair

            candidate = evaluate_pair(
                buy, sell, notional, cfg.cost_model, decision_time=tick.decision_time
            )
            if candidate.is_rejected:
                rows.append(
                    {
                        "buy_exchange": buy.exchange,
                        "sell_exchange": sell.exchange,
                        "status": candidate.status.value,
                        "prediction": None,
                    }
                )
                continue
            features = build_features(ticks, index, buy, sell, candidate, cfg)
            rows.append(
                {
                    "buy_exchange": buy.exchange,
                    "sell_exchange": sell.exchange,
                    "status": candidate.status.value,
                    "prediction": predict(model, features),
                }
            )
        return clean(
            {
                "symbol": tick.symbol,
                "synthetic": synthetic,
                "model_version": model.version,
                "decision_time": tick.decision_time.isoformat(),
                "predictions": rows,
            }
        )

    def _run(run_id: str | None) -> Any:
        run_dir = manager.latest_run_dir(run_id)
        if run_dir is None:
            raise DataUnavailable(
                "no completed backtest found" if run_id is None else f"unknown run: {run_id}"
            )
        return run_dir

    @app.get("/trades")
    def trades(
        run_id: str | None = None, limit: int = Query(200, ge=1, le=5_000)
    ) -> dict[str, Any]:
        run_dir = _run(run_id)
        frame = (
            pd.read_csv(run_dir / "trades.csv")
            if (run_dir / "trades.csv").stat().st_size > 5
            else pd.DataFrame()
        )
        return clean(
            {
                "run_id": run_dir.name,
                "simulated": True,
                "count": len(frame),
                "trades": frame.tail(limit).to_dict(orient="records"),
            }
        )

    @app.get("/portfolio")
    def portfolio(run_id: str | None = None) -> dict[str, Any]:
        run_dir = _run(run_id)
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        return clean(
            {
                "run_id": run_dir.name,
                "simulated": True,
                "quote_balances": metrics.get("final_quote_balances"),
                "base_balances": metrics.get("final_base_balances"),
                "assumptions": metrics.get("assumptions"),
            }
        )

    @app.get("/performance")
    def performance(run_id: str | None = None) -> dict[str, Any]:
        run_dir = _run(run_id)
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        return clean(
            {
                "run_id": run_dir.name,
                "simulated": True,
                "selector": config["selector"],
                "selector_params": config["selector_params"],
                "metrics": metrics,
            }
        )

    @app.post("/backtest", status_code=202)
    def submit_backtest(request: BacktestRequest) -> dict[str, Any]:
        job_id = manager.submit(request)
        return {"job_id": job_id, "status": "queued", "status_url": f"/backtest/{job_id}"}

    @app.get("/backtest/{run_id}")
    def backtest_status(run_id: str) -> dict[str, Any]:
        job = manager.get(run_id)
        if job is None:
            raise DataUnavailable(f"unknown backtest job: {run_id}")
        return clean(job)

    return app


def main() -> None:
    configure_logging()
    uvicorn.run(
        "services.api.app.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,  # noqa: S104
    )


if __name__ == "__main__":
    main()
