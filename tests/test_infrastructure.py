"""Static checks of the container setup.

Docker is not required (or exercised) here: these tests parse the files and verify the
properties the plan asks for (health checks, private databases, no committed secrets,
non-root user). They do NOT prove that `docker compose up` works.
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]
JOBS = {"research"}  # run-to-completion jobs do not need a health check


def test_every_long_running_service_has_a_healthcheck_and_restart_policy() -> None:
    for name, service in SERVICES.items():
        if name in JOBS:
            continue
        assert "healthcheck" in service, name
        assert service.get("restart") == "unless-stopped", name


def test_databases_are_private_and_published_ports_are_loopback_only() -> None:
    for name in ("postgres", "influxdb", "redis"):
        assert "ports" not in SERVICES[name], f"{name} must not be published to the host"
        assert SERVICES[name]["networks"] == ["backend"]
    assert COMPOSE["networks"]["backend"]["internal"] is True
    for name, service in SERVICES.items():
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{name}: {port}"


def test_no_hard_coded_credentials_in_compose() -> None:
    secret_keys = re.compile(r"(PASSWORD|TOKEN|SECRET)", re.IGNORECASE)
    for name, service in SERVICES.items():
        env = service.get("environment", {})
        for key, value in env.items() if isinstance(env, dict) else []:
            if secret_keys.search(key):
                assert str(value).startswith("${"), f"{name}.{key} must come from the environment"
        for part in service.get("command", []) if isinstance(service.get("command"), list) else []:
            assert not re.fullmatch(r"[A-Za-z0-9]{12,}", str(part)), f"{name}: suspicious literal"


def test_required_secrets_fail_fast_when_unset() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for variable in (
        "POSTGRES_PASSWORD",
        "INFLUXDB_PASSWORD",
        "INFLUXDB_TOKEN",
        "REDIS_PASSWORD",
        "GRAFANA_ADMIN_PASSWORD",
    ):
        assert f"${{{variable}:?" in text


def test_stateful_services_use_named_volumes() -> None:
    declared = set(COMPOSE["volumes"])
    for name in ("postgres", "influxdb", "redis", "grafana"):
        mounted = {v.split(":")[0] for v in SERVICES[name]["volumes"]}
        assert mounted & declared, name
    assert {"rawdata", "models", "results"} <= declared


def test_build_arguments_point_to_existing_requirement_files() -> None:
    for name, service in SERVICES.items():
        build = service.get("build")
        if build:
            requirement = build["args"]["REQUIREMENTS"]
            assert (ROOT / "requirements" / f"{requirement}.txt").exists(), name


def test_dockerfile_runs_as_non_root_and_copies_existing_directories() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    users = re.findall(r"^USER\s+(\S+)", dockerfile, re.MULTILINE)
    assert users and users[-1] not in {"root", "0"}
    assert dockerfile.startswith("# One image") or "FROM python:3.11" in dockerfile
    for source in re.findall(r"^COPY\s+(\S+)\s", dockerfile, re.MULTILINE):
        assert (ROOT / source.rstrip("/")).exists(), source


def test_dockerignore_keeps_secrets_and_data_out_of_the_image() -> None:
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    for entry in (".env", ".git", ".venv", "data/raw/*", "models/*"):
        assert entry in ignored


def test_env_example_has_placeholders_only_and_env_is_git_ignored() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for line in example.splitlines():
        if re.match(r"^[A-Z_]*(PASSWORD|TOKEN)=", line):
            assert "CHANGE_ME" in line, line
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_init_sql_matches_python_schema_and_parses_as_postgres() -> None:
    from shared.storage import FULL_POSTGRESQL_SCHEMA

    sql = (ROOT / "infrastructure" / "postgres" / "init.sql").read_text(encoding="utf-8")
    assert FULL_POSTGRESQL_SCHEMA.strip() in sql
    sqlglot = pytest.importorskip("sqlglot")
    statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    created = {
        s.this.this.name for s in statements if s.key == "create" and s.args.get("kind") == "TABLE"
    }
    assert {
        "model_versions",
        "backtest_runs",
        "candidate_opportunities",
        "candidate_features",
        "ml_predictions",
        "simulated_trades",
        "portfolio_snapshots",
        "experiment_runs",
    } <= created


def run_healthcheck(stats_path: Path) -> int:
    import os

    env = {**os.environ, "COLLECTOR_STATS": str(stats_path), "COLLECTOR_MAX_STATS_AGE": "120"}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "healthcheck_collector.py")],
        env=env,
        capture_output=True,
    ).returncode


def test_collector_healthcheck_detects_fresh_stale_and_missing_stats(tmp_path) -> None:
    stats = tmp_path / "collector_stats.json"
    assert run_healthcheck(stats) == 1  # missing
    stats.write_text(json.dumps({"updated_at": datetime.now(timezone.utc).isoformat()}))
    assert run_healthcheck(stats) == 0  # fresh
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    stats.write_text(json.dumps({"updated_at": old.isoformat()}))
    assert run_healthcheck(stats) == 1  # stale


def test_check_env_rejects_missing_and_placeholder_secrets(tmp_path) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_env

    example = check_env.parse(ROOT / ".env.example")
    assert check_env.problems(example)  # placeholders must be replaced before starting
    real = {key: "s3cret-value-123" for key in check_env.REQUIRED}
    assert check_env.problems(real) == []
    assert any("not set" in p for p in check_env.problems({}))
    assert any(
        "8 characters" in p for p in check_env.problems({**real, "INFLUXDB_PASSWORD": "short"})
    )
