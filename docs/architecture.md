# Architecture

Simulation and research only. Nothing in this repository places orders, uses exchange credentials
or moves funds.

## Data flow (as implemented)

```text
Binance / Bybit / OKX public REST depth
        |
        v
services/data_collector  depth_recorder.py   (validates, flags, writes NDJSON)
        |   data/raw/<source>/market_depth_YYYYMMDD.ndjson
        v
shared/market_data.py     load records -> chronological ticks
        |
        +--> services/arbitrage_engine  candidates.py   (order-book walking, costs, status)
        |            |
        |            v
        |    services/ml_service  dataset.py   (rows, features, replayed-execution label)
        |            |                |
        |            |                v
        |            |        training.py / inference.py  (LR, RF, GB; versioned models)
        |            v
        +--> services/simulation_engine  selectors.py, evaluation.py, backtest.py
                     |
                     v
        experiments/run_experiments.py  ->  experiments/results/<name>/report.md
                     |
                     v
        services/api (FastAPI)   <->   services/dashboard (Streamlit)
```

## Services and where the code lives

| Plan component | Code | Notes |
|---|---|---|
| Data collector | `services/data_collector/app/depth_recorder.py` | REST depth snapshots (see limitations). The older adapters/WebSocket collectors in the same package are not wired into the recorder. |
| Arbitrage engine | `services/arbitrage_engine/app/candidates.py` | `engine.py` (top-of-book `ArbitrageEngine`) is kept for compatibility; `candidates.py` is the plan-conformant implementation. |
| ML service | `services/ml_service/app/{dataset,training,inference}.py` | scikit-learn; models saved under `models/<version>/`. |
| Simulation / backtesting | `services/simulation_engine/app/{selectors,evaluation,backtest}.py` | |
| API | `services/api/app/main.py` | `python -m services.api.app.main` |
| Dashboard | `services/dashboard/app.py`, `pages/1_Data_and_Backtests.py` | Streamlit (Grafana is provisioned in the `storage` profile, but no dashboards ship yet). |
| Shared | `shared/{domain,storage,market_data,data_quality,retention,synthetic}.py` | |

The arbitrage engine, ML service and simulation engine are libraries used by the API (backtests) and
by the `research` job rather than separate long-running processes. The plan allows combining
service boundaries when separate daemons would add complexity without benefit; they can be split
later because the modules only communicate through plain data (DataFrames, dataclasses, files).

## Key definitions (single source of truth)

See the module docstrings in `candidates.py` (spread, costs, status), `dataset.py` (label,
features, leakage rules) and `backtest.py` (execution assumptions). They are summarised in
[experiments.md](experiments.md).

## Known gaps versus the plan

- Market data is persisted to files, not InfluxDB/PostgreSQL/Redis. Schema and containers exist
  (`infrastructure/supabase/schema.sql`, `docker-compose.yml` `storage` profile) but no code writes
  to them yet.
- No WebSocket depth feed; the recorder polls REST snapshots (see [data.md](data.md)).
- Docker files were written and statically checked but never run on the development machine.
