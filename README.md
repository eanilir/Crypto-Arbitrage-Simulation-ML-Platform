# Crypto Arbitrage Simulation & ML Platform

Service-based Python monorepo for crypto market data collection, cross-exchange arbitrage
candidate detection, machine learning, backtesting and a monitoring dashboard.

**Simulation and research only.** No real trading, no exchange credentials, no real funds.
Every profit figure is a simulated estimate under documented assumptions.

## What works today

| Area | Status |
|---|---|
| Public order-book recorder (Binance, Bybit, OKX; REST depth snapshots, UTC timestamps, validation) | Working, tested, run against real exchanges |
| Arbitrage candidates: order-book walking, fees, slippage, modeled latency, negative spreads | Working, tested (plan cases A-G) |
| Dataset: replayed-execution label, decision-time features, leakage tests | Working, tested |
| Baselines A/B/C, ML-filtered D (Logistic Regression, Random Forest, Gradient Boosting), chronological split with purge | Working, tested |
| Backtest engine (virtual inventory, drawdown, reproducible runs) | Working, tested |
| Experiments 1-6 with reports and plots | Working; results so far are synthetic or from a 15-minute real sample |
| FastAPI service and Streamlit dashboard (2 pages) | Working, tested |
| Data-quality audit, retention policy | Working, tested |
| Docker Compose, Dockerfile, health checks | Written and statically checked, **never run** (no Docker on the dev machine) |
| PostgreSQL / InfluxDB / Redis persistence | Schema and containers only; **no application code writes to them yet** |
| WebSocket depth feed | Not implemented (REST polling instead) |
| 3-7 day data collection, literature review, AWS deployment | **Not done** (see `docs/`) |

No conclusion about the research question can be drawn yet: it needs the multi-day recording and the
literature review. See [docs/experiments.md](docs/experiments.md) for the honest status.

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest

# record real public data (Ctrl+C to stop)
.\.venv\Scripts\python.exe -m services.data_collector.app.depth_recorder --output-dir data/raw/live

# dashboard (http://localhost:8501) and API (http://localhost:8000/docs)
.\run_dashboard.ps1
$env:ARBITRAGE_DATA_SOURCE = "live"; .\.venv\Scripts\python.exe -m services.api.app.main

# research report from recorded data
.\.venv\Scripts\python.exe experiments/run_experiments.py --input data/raw/live --output experiments/results/live
```

Docker instructions: [docs/deployment_local.md](docs/deployment_local.md).

## Structure

```text
services/
  data_collector/      depth_recorder.py (+ earlier adapters)
  arbitrage_engine/    candidates.py (+ engine.py, top-of-book)
  ml_service/          dataset.py, training.py, inference.py
  simulation_engine/   selectors.py, evaluation.py, backtest.py
  api/                 FastAPI app
  dashboard/           Streamlit app and pages/
shared/                domain models, order books, market data loading, synthetic data,
                       data quality, retention, storage schema
experiments/           run_experiments.py and results/
scripts/               dataset, synthetic data, quality report, retention, health check
infrastructure/        supabase/schema.sql (report's ER schema), grafana provisioning
tests/                 unit, integration-style and static infrastructure tests
docs/                  architecture, data, experiments, deployment, AWS plan, literature review
```

## Documentation

- [Architecture](docs/architecture.md) | [Data](docs/data.md) | [Experiments](docs/experiments.md)
- [Local deployment](docs/deployment_local.md) | [AWS preparation](docs/aws_deployment_plan.md)
- [Literature review (pending)](docs/literature_review.md)
- [Project plan](project_plan.md) | [Storage guide](docs/storage_guide.md)

## Project standards

- Python 3.11+ (the test suite also passes on 3.10)
- Ruff for linting and formatting
- UTC timestamps for market data; event time and receive time stored separately
- Shared domain models under `shared/domain`
- Environment-based configuration via `.env` (never committed) and environment variables
- Negative spreads are valid unprofitable outcomes, not invalid data
- Data staleness and simulated latency are separate variables
- No future information in features; chronological splits only
