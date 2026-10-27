"""Static checks that the Supabase schema matches the report's ER diagram (Sekil 2. 9).

The SQL is parsed, not executed: the Supabase database was unreachable when this was written, so
the schema has NOT been applied to a real database.
"""

import re
from pathlib import Path

import pytest

sqlglot = pytest.importorskip("sqlglot")

SQL = (Path(__file__).resolve().parents[1] / "infrastructure" / "supabase" / "schema.sql").read_text(
    encoding="utf-8"
)

# table -> columns shown in the report's ER diagram
ER_DIAGRAM = {
    "price_tick": {"exchange", "symbol", "ts", "open", "high", "low", "close", "volume"},
    "arbitrage_opportunity": {
        "id", "detected_at", "buy_exchange", "sell_exchange", "symbol",
        "price_diff_pct", "estimated_profit", "commission_total", "status",
    },
    "model_registry": {"id", "model_name", "version", "accuracy", "f1_score", "trained_at", "artifact_path"},
    "ml_prediction": {
        "id", "opportunity_id", "model_name", "probability_score",
        "prediction_label", "predicted_at", "model_version",
    },
    "simulation_result": {
        "id", "opportunity_id", "prediction_id", "actual_profit",
        "slippage", "net_pnl", "execution_ms", "simulated_at",
    },
}


def tables() -> dict[str, set[str]]:
    found = {}
    for statement in sqlglot.parse(SQL, read="postgres"):
        if statement is not None and statement.key == "create" and statement.args.get("kind") == "TABLE":
            name = statement.this.this.name
            found[name] = {c.name for c in statement.find_all(sqlglot.exp.ColumnDef)}
    return found


def test_every_table_in_the_er_diagram_exists_with_its_columns() -> None:
    created = tables()
    assert set(ER_DIAGRAM) <= set(created)
    for name, columns in ER_DIAGRAM.items():
        assert columns <= created[name], f"{name} is missing {columns - created[name]}"


def test_price_tick_uses_the_composite_key_from_the_report() -> None:
    block = re.search(r"create table if not exists price_tick \((.*?)\);", SQL, re.S).group(1)
    assert "primary key (exchange, symbol, ts)" in block


def test_relationships_follow_the_diagram() -> None:
    assert "opportunity_id uuid not null references arbitrage_opportunity(id)" in SQL
    assert "prediction_id  uuid references ml_prediction(id)" in SQL
    assert "model_id          uuid references model_registry(id)" in SQL


def test_row_level_security_is_enabled_on_every_table() -> None:
    for name in ER_DIAGRAM:
        assert f"alter table {name}" in SQL and "enable row level security" in SQL
        assert re.search(rf"alter table {name}\s+enable row level security", SQL), name


def test_probability_is_constrained_and_script_is_idempotent() -> None:
    assert "probability_score between 0 and 1" in SQL
    assert "drop table" not in SQL.lower()
    for line in SQL.splitlines():
        if line.lower().startswith("create table") or line.lower().startswith("create index"):
            assert "if not exists" in line.lower(), line
