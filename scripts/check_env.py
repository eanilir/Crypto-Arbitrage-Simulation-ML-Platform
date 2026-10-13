"""Refuse to start the stack with a missing .env or leftover placeholder secrets.

python scripts/check_env.py && docker compose up -d --build
"""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "INFLUXDB_USER",
    "INFLUXDB_PASSWORD",
    "INFLUXDB_TOKEN",
    "REDIS_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
)


def parse(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def problems(values: dict[str, str]) -> list[str]:
    found = []
    for key in REQUIRED:
        value = values.get(key, "")
        if not value:
            found.append(f"{key} is not set")
        elif "CHANGE_ME" in value:
            found.append(f"{key} still has the CHANGE_ME placeholder")
    if len(values.get("INFLUXDB_PASSWORD", "")) < 8 and values.get("INFLUXDB_PASSWORD"):
        found.append("INFLUXDB_PASSWORD must be at least 8 characters")
    return found


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
    if not path.exists():
        print(f"{path} not found; run: cp .env.example .env")
        return 1
    found = problems(parse(path))
    for item in found:
        print(f"error: {item}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
