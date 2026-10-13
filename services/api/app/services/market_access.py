"""Read recorded order books for the API without loading whole files."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from services.api.app.core.config import Settings
from shared.market_data import Tick, group_ticks

TAIL_BYTES = 600_000  # about 150 snapshots of depth 20


class DataUnavailable(RuntimeError):
    pass


def clean(value: Any) -> Any:
    """Make NaN/inf JSON-safe (None) recursively."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def resolve_source(settings: Settings, source: str) -> Path:
    """Resolve a data sub-directory, refusing anything outside the data root."""
    root = settings.data_root.resolve()
    path = (root / source).resolve()
    if root != path and root not in path.parents:
        raise DataUnavailable("source must be inside the data root")
    if not path.is_dir():
        raise DataUnavailable(f"unknown data source: {source}")
    return path


def latest_file(settings: Settings) -> Path:
    candidates: list[Path] = []
    if settings.default_source:
        candidates = list(
            resolve_source(settings, settings.default_source).glob("market_depth_*.ndjson")
        )
    elif settings.data_root.is_dir():
        candidates = list(settings.data_root.rglob("market_depth_*.ndjson"))
    if not candidates:
        raise DataUnavailable("no recorded market data found; start the depth recorder")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def tail_records(path: Path, tail_bytes: int = TAIL_BYTES) -> list[dict[str, Any]]:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - tail_bytes))
        chunk = handle.read().decode("utf-8", errors="ignore")
    lines = chunk.splitlines()
    if size > tail_bytes:
        lines = lines[1:]  # first line is probably cut
    records = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("validation_status") == "ok":
            records.append(record)
    return records


def latest_ticks(
    settings: Settings, symbol: str | None = None, count: int = 8
) -> tuple[list[Tick], Path, bool]:
    path = latest_file(settings)
    records = tail_records(path)
    if not records:
        raise DataUnavailable("recorded data contains no valid snapshots")
    synthetic = bool(records[-1].get("synthetic"))
    if symbol:
        records = [r for r in records if r["symbol"] == symbol]
        if not records:
            raise DataUnavailable(f"no data for symbol {symbol}")
    ticks = group_ticks(records)
    if symbol is None:
        ticks = [t for t in ticks if t.symbol == ticks[-1].symbol]
    return ticks[-count:], path, synthetic
