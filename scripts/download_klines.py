"""Download historical 1-minute candles for Binance, Bybit and OKX (public REST, no keys).

python scripts/download_klines.py --days 183 --symbol BTC/USDT
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.historical import (  # noqa: E402
    MINUTE_MS,
    PAGINATORS,
    download_to_csv,
    read_csv,
    validate_candles,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--days", type=float, default=183.0)
    parser.add_argument("--exchanges", nargs="+", default=list(PAGINATORS))
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/historical/klines_1m"))
    args = parser.parse_args()

    now_ms = int(time.time() * 1000)
    end_ms = now_ms // MINUTE_MS * MINUTE_MS  # last fully closed minute boundary
    start_ms = end_ms - int(args.days * 24 * 60 * MINUTE_MS)
    summary = {
        "symbol": args.symbol,
        "start": datetime.fromtimestamp(start_ms / 1000, timezone.utc).isoformat(),
        "end": datetime.fromtimestamp(end_ms / 1000, timezone.utc).isoformat(),
        "exchanges": {},
    }

    for exchange in args.exchanges:
        began = time.time()
        last_print = [0.0]
        path = args.output_dir / f"{exchange}_{args.symbol.replace('/', '')}_1m.csv"

        def progress(
            done: int, total: int, name: str = exchange, last_print: list = last_print
        ) -> None:
            if time.time() - last_print[0] > 10:
                print(f"{name}: {done:,}/{total:,} minutes ({done / total:.0%})", flush=True)
                last_print[0] = time.time()

        # Saved in windows; re-running the same command resumes where it stopped.
        download_to_csv(exchange, args.symbol, start_ms, end_ms, path, progress=progress)
        candles = [c for c in read_csv(path) if start_ms <= c.open_time_ms < end_ms]
        report = validate_candles(candles, start_ms, end_ms)
        summary["exchanges"][exchange] = {
            "file": str(path),
            "rows": report.rows,
            "expected_rows": report.expected_rows,
            "coverage": round(report.coverage, 5),
            "missing_minutes": report.missing_minutes,
            "gaps": len(report.gaps),
            "largest_gap_minutes": max((g[1] for g in report.gaps), default=0),
            "invalid_rows": report.invalid_rows,
            "duplicate_or_unordered": report.duplicate_or_unordered,
            "seconds": round(time.time() - began, 1),
        }
        print(f"{exchange}: {json.dumps(summary['exchanges'][exchange])}", flush=True)

    (args.output_dir / "download_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
