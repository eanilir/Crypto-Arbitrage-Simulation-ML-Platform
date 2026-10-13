POSTGRESQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_quotes (
    id SERIAL PRIMARY KEY,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quote_time TIMESTAMPTZ NOT NULL,
    bid DOUBLE PRECISION NOT NULL,
    ask DOUBLE PRECISION NOT NULL,
    last DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_market_quotes_symbol_time
    ON market_quotes(symbol, quote_time DESC);

CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    spread DOUBLE PRECISION NOT NULL,
    spread_percent DOUBLE PRECISION NOT NULL,
    estimated_fees DOUBLE PRECISION NOT NULL,
    estimated_slippage DOUBLE PRECISION NOT NULL,
    estimated_latency_cost DOUBLE PRECISION NOT NULL,
    net_profit DOUBLE PRECISION NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_opportunities_symbol_time
    ON arbitrage_opportunities(symbol, detected_at DESC);
"""


# Research and simulation records (project_plan.md §12.2). Every simulated row carries the
# run / model / experiment id it came from so results stay traceable and reproducible.
POSTGRESQL_RESEARCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_versions (
    version TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    trained_at TIMESTAMPTZ NOT NULL,
    data_fingerprint TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    selector TEXT NOT NULL,
    selector_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    config JSONB NOT NULL,
    data_fingerprint TEXT NOT NULL,
    model_version TEXT REFERENCES model_versions(version),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS candidate_opportunities (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT REFERENCES backtest_runs(run_id),
    symbol TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    decision_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    notional DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION,
    gross_spread DOUBLE PRECISION,
    gross_spread_percent DOUBLE PRECISION,
    buy_cost DOUBLE PRECISION,
    sell_proceeds DOUBLE PRECISION,
    fees DOUBLE PRECISION,
    slippage DOUBLE PRECISION,
    latency_cost DOUBLE PRECISION,
    net_profit DOUBLE PRECISION,
    data_age_ms DOUBLE PRECISION,
    reject_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_candidates_symbol_time
    ON candidate_opportunities(symbol, decision_time DESC);

CREATE TABLE IF NOT EXISTS candidate_features (
    candidate_id BIGINT PRIMARY KEY REFERENCES candidate_opportunities(id),
    features JSONB NOT NULL,
    label SMALLINT,
    outcome_net_profit DOUBLE PRECISION,
    outcome_status TEXT
);

CREATE TABLE IF NOT EXISTS ml_predictions (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT NOT NULL REFERENCES candidate_opportunities(id),
    model_version TEXT NOT NULL REFERENCES model_versions(version),
    probability_profitable DOUBLE PRECISION NOT NULL,
    selected BOOLEAN NOT NULL,
    predicted_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS simulated_trades (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    decision_time TIMESTAMPTZ NOT NULL,
    outcome_time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    buy_cost DOUBLE PRECISION NOT NULL,
    sell_proceeds DOUBLE PRECISION NOT NULL,
    fees DOUBLE PRECISION NOT NULL,
    net_pnl DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_simulated_trades_run
    ON simulated_trades(run_id, decision_time);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
    snapshot_time TIMESTAMPTZ NOT NULL,
    exchange TEXT NOT NULL,
    quote_balance DOUBLE PRECISION NOT NULL,
    base_balance DOUBLE PRECISION NOT NULL,
    cumulative_pnl DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_runs (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    config JSONB NOT NULL,
    data_source TEXT NOT NULL,
    synthetic_data BOOLEAN NOT NULL,
    results JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""

FULL_POSTGRESQL_SCHEMA = POSTGRESQL_SCHEMA + POSTGRESQL_RESEARCH_SCHEMA
