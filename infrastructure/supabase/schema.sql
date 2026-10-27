-- Supabase / PostgreSQL schema matching the report's ER diagram (Sekil 2. 9).
-- Apply once; every statement is idempotent. Row Level Security is enabled on every table with
-- no policies, so the public anon key can neither read nor write; only server-side roles
-- (postgres / service_role) can.

-- Time-series layer (the report places PRICE_TICK in InfluxDB; stored here until InfluxDB exists).
create table if not exists price_tick (
    exchange text not null,
    symbol   text not null,
    ts       timestamptz not null,
    open     double precision,
    high     double precision,
    low      double precision,
    close    double precision,
    volume   double precision,
    primary key (exchange, symbol, ts)
);

create table if not exists arbitrage_opportunity (
    id               uuid primary key default gen_random_uuid(),
    detected_at      timestamptz not null,
    buy_exchange     text not null,
    sell_exchange    text not null,
    symbol           text not null,
    price_diff_pct   double precision,
    estimated_profit double precision,
    commission_total double precision,
    status           text not null
);

create table if not exists model_registry (
    id            uuid primary key default gen_random_uuid(),
    model_name    text not null,
    version       text not null,
    accuracy      double precision,
    f1_score      double precision,
    trained_at    timestamptz not null,
    artifact_path text,
    unique (model_name, version)
);

create table if not exists ml_prediction (
    id                uuid primary key default gen_random_uuid(),
    opportunity_id    uuid not null references arbitrage_opportunity(id) on delete cascade,
    model_id          uuid references model_registry(id) on delete set null,
    model_name        text not null,
    probability_score double precision not null check (probability_score between 0 and 1),
    prediction_label  text,
    predicted_at      timestamptz not null,
    model_version     text not null
);

create table if not exists simulation_result (
    id             uuid primary key default gen_random_uuid(),
    opportunity_id uuid not null references arbitrage_opportunity(id) on delete cascade,
    prediction_id  uuid references ml_prediction(id) on delete set null,
    actual_profit  double precision,
    slippage       double precision,
    net_pnl        double precision,
    execution_ms   integer,
    simulated_at   timestamptz not null
);

create index if not exists idx_price_tick_symbol_ts on price_tick (symbol, ts desc);
create index if not exists idx_opportunity_symbol_time on arbitrage_opportunity (symbol, detected_at desc);
create index if not exists idx_prediction_opportunity on ml_prediction (opportunity_id);
create index if not exists idx_simulation_opportunity on simulation_result (opportunity_id);

alter table price_tick            enable row level security;
alter table arbitrage_opportunity enable row level security;
alter table model_registry        enable row level security;
alter table ml_prediction         enable row level security;
alter table simulation_result     enable row level security;

-- ---------------------------------------------------------------------------------------------
-- Users and login (the report's use cases require "valid credentials"; the ER diagram has no
-- user table, so APP_USER is an addition). Passwords are stored only as bcrypt hashes.
-- The dashboard never reads this table: it calls verify_login(), which returns the user's
-- name on success and null on failure (a failed attempt waits 1 s to slow down guessing).
-- ---------------------------------------------------------------------------------------------
create extension if not exists pgcrypto with schema extensions;

create table if not exists app_user (
    id            uuid primary key default gen_random_uuid(),
    username      text not null unique check (username = lower(username) and length(username) between 3 and 40),
    display_name  text,
    password_hash text not null,
    created_at    timestamptz not null default now(),
    last_login_at timestamptz
);

alter table app_user enable row level security;

create or replace function verify_login(p_username text, p_password text)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
    u app_user%rowtype;
begin
    select * into u from app_user where username = lower(trim(p_username));
    if found and u.password_hash = crypt(p_password, u.password_hash) then
        update app_user set last_login_at = now() where id = u.id;
        return jsonb_build_object('username', u.username, 'display_name', coalesce(u.display_name, u.username));
    end if;
    perform pg_sleep(1);
    return null;
end;
$$;

-- Public (anon) clients may only call verify_login; they get no direct table access at all.
revoke all on table price_tick, arbitrage_opportunity, model_registry, ml_prediction,
    simulation_result, app_user from anon, authenticated;
revoke all on function verify_login(text, text) from public;
grant execute on function verify_login(text, text) to anon, authenticated;
