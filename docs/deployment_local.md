# Local deployment

> **Verification status.** The Docker files (`Dockerfile`, `docker-compose.yml`, health checks) were
> written and statically checked (`tests/test_infrastructure.py` parses them and verifies health
> checks, private databases, loopback-only ports, no committed secrets and a non-root user).
> They were **never built or started**, because Docker is not installed on the development
> machine. Expect to fix small problems on the first `docker compose up`.

## Without Docker (verified)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest                       # full suite

# 1. record real data (leave running; Ctrl+C stops cleanly)
.\.venv\Scripts\python.exe -m services.data_collector.app.depth_recorder --output-dir data/raw/live

# 2. API and dashboard
$env:ARBITRAGE_DATA_SOURCE = "live"
.\.venv\Scripts\python.exe -m services.api.app.main                 # http://localhost:8000/docs
.\run_dashboard.ps1                                                  # http://localhost:8501

# 3. research
.\.venv\Scripts\python.exe experiments/run_experiments.py --input data/raw/live --output experiments/results/live
```

The project targets Python 3.11+; the test suite also passes on 3.10.

## With Docker Compose (unverified)

```powershell
copy .env.example .env             # set every CHANGE_ME value
python scripts/check_env.py        # refuses missing or placeholder secrets
docker compose up -d --build                     # data-collector, api, dashboard
docker compose --profile storage up -d           # + PostgreSQL, InfluxDB, Redis, Grafana
docker compose --profile research run --rm research
docker compose down                              # volumes (data, models, results) are kept
```

Properties implemented in the compose file:

- One image definition (`Dockerfile`) with per-service dependency sets (`requirements/*.txt`),
  Python 3.11, non-root user.
- Health checks and `restart: unless-stopped` for every long-running service; the collector's
  health check fails when its stats file stops updating.
- Named volumes for raw data, models, results and each database.
- Databases and the research job sit on an `internal` network with no route to the internet or the
  host; API, dashboard and Grafana are published on `127.0.0.1` only.
- Secrets come only from `.env`; compose refuses to start when a required one is missing.
- Log rotation (10 MB x 3) and a 20 s stop grace period for the collector, which finalizes its
  stats on SIGTERM.

Not done: the application does not read or write PostgreSQL, InfluxDB or Redis yet (data lives in
NDJSON files on the `rawdata` volume); Grafana has a PostgreSQL data source but no dashboards;
restart/recovery against a real database was not tested.
