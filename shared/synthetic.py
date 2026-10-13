"""Synthetic multi-exchange order-book generator (TEST/PIPELINE DATA ONLY).

The records use exactly the same schema as ``depth_recorder`` output but carry
``"data_source": "synthetic"`` and ``"synthetic": true`` so they can never be mistaken
for market observations. Results computed from this data are properties of the
generator's assumptions, not findings about real markets.

Generator assumptions (all configurable):
* a common mid price follows a random walk with occasional jumps;
* each exchange observes the common price with its own lag (``lag_ms``), so a jump
  creates a temporary cross-exchange mispricing that disappears once the lagging
  exchange catches up;
* each exchange has a small persistent price offset and its own spread/depth;
* receive times include a random request round trip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_LAG_MS = {"binance": 0.0, "bybit": 300.0, "okx": 700.0}
EXCHANGES_WITHOUT_EVENT_TIME = {"binance"}  # mirrors the real depth endpoint


@dataclass(frozen=True)
class SyntheticConfig:
    n_ticks: int = 3600
    interval_s: float = 1.0
    symbol: str = "BTC/USDT"
    start: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)
    start_price: float = 65_000.0
    seed: int = 42
    depth: int = 20
    walk_sigma_bps_per_s: float = 0.8
    jump_prob_per_s: float = 0.1
    jump_sigma_bps: float = 60.0
    offset_sigma_bps: float = 1.0
    lag_ms: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_LAG_MS))


def _common_path(cfg: SyntheticConfig, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    # Simulate on a grid at least as fine as the tick interval so lags can be interpolated.
    step = min(cfg.interval_s, 0.05)
    n = int(np.ceil((cfg.n_ticks * cfg.interval_s) / step)) + 1
    times = np.arange(n) * step
    walk = rng.normal(0, cfg.walk_sigma_bps_per_s * np.sqrt(step), n)
    jumps = (rng.random(n) < cfg.jump_prob_per_s * step) * rng.normal(0, cfg.jump_sigma_bps, n)
    log_bps = np.cumsum(walk + jumps)
    return times, cfg.start_price * np.exp(log_bps / 10_000)


def generate_records(cfg: SyntheticConfig | None = None) -> list[dict[str, Any]]:
    cfg = cfg or SyntheticConfig()
    rng = np.random.default_rng(cfg.seed)
    times, common = _common_path(cfg, rng)
    exchanges = list(cfg.lag_ms)
    offsets = {ex: 0.0 for ex in exchanges}
    last_received: dict[str, datetime] = {}
    records: list[dict[str, Any]] = []

    for k in range(cfg.n_ticks):
        t = k * cfg.interval_s
        request_base = cfg.start + timedelta(seconds=t)
        for ex in exchanges:
            offsets[ex] = 0.97 * offsets[ex] + rng.normal(0, cfg.offset_sigma_bps)
            seen_at = max(0.0, t - cfg.lag_ms[ex] / 1000)
            mid = float(np.interp(seen_at, times, common)) * (1 + offsets[ex] / 10_000)

            half_spread = mid * rng.uniform(0.5, 1.5) / 10_000
            level_step = mid * rng.uniform(0.6, 1.0) / 10_000
            base_qty = rng.uniform(0.2, 2.0) * 4_000 / mid  # varies so some books are shallow
            bids, asks = [], []
            for i in range(cfg.depth):
                qty = base_qty * rng.exponential(1.0) + 1e-6
                bids.append([round(mid - half_spread - i * level_step, 2), round(qty, 6)])
                qty = base_qty * rng.exponential(1.0) + 1e-6
                asks.append([round(mid + half_spread + i * level_step, 2), round(qty, 6)])

            requested = request_base + timedelta(milliseconds=float(rng.uniform(0, 5)))
            round_trip_ms = float(rng.lognormal(np.log(250), 0.4))
            received = requested + timedelta(milliseconds=round_trip_ms)
            # a real recorder awaits each cycle, so receive times never go backwards per exchange
            if ex in last_received and received <= last_received[ex]:
                received = last_received[ex] + timedelta(milliseconds=1)
            last_received[ex] = received
            event_time = None
            if ex not in EXCHANGES_WITHOUT_EVENT_TIME:
                event_time = (
                    received - timedelta(milliseconds=float(rng.uniform(5, 60)))
                ).isoformat()
            records.append(
                {
                    "exchange": ex,
                    "symbol": cfg.symbol,
                    "run_id": "synthetic",
                    "cycle": k,
                    "event_timestamp": event_time,
                    "received_timestamp": received.isoformat(),
                    "request_timestamp": requested.isoformat(),
                    "round_trip_ms": round(round_trip_ms, 3),
                    "timestamp_quality": "present" if event_time else "missing",
                    "sequence_id": None,
                    "data_source": "synthetic",
                    "synthetic": True,
                    "order_book_depth": cfg.depth,
                    "validation_status": "ok",
                    "validation_issues": [],
                    "bids": bids,
                    "asks": asks,
                }
            )
    return records


def write_synthetic(output_dir: Path | str, cfg: SyntheticConfig | None = None) -> Path:
    cfg = cfg or SyntheticConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"market_depth_{cfg.start:%Y%m%d}.ndjson"
    with path.open("w", encoding="utf-8") as handle:
        for record in generate_records(cfg):
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    return path
