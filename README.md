# Crypto Arbitrage Simulation & ML Platform

Service-based Python monorepo for crypto market data collection, arbitrage detection, machine learning, simulation, and later AWS deployment.

## Structure

```text
project/
├── services/
│   ├── api/
│   ├── data_collector/
│   ├── arbitrage_engine/
│   ├── ml_service/
│   ├── simulation_engine/
│   └── dashboard/
├── shared/
├── infrastructure/
├── data/
├── models/
├── tests/
└── docs/
```

## Current Focus

The repository is set up as a service-oriented skeleton so each component can be developed and deployed independently.

## Project Standards

- Python 3.11+
- Ruff-based formatting and linting
- UTC timestamps for market data
- Shared domain models under `shared/domain`
- Environment-based configuration via `.env` and environment variables
- Structured logging with a consistent format
