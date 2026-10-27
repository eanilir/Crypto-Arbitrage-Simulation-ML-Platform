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
