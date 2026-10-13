"""Build the labeled candidate dataset from recorded order books.

python scripts/build_dataset.py --input data/raw/real_sample --latency-ms 0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.arbitrage_engine.app.candidates import CostModel  # noqa: E402
from services.ml_service.app.dataset import DatasetConfig, build_dataset  # noqa: E402
from shared.market_data import LoadReport, load_ticks, ticks_by_symbol  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="dir or ndjson file")
    parser.add_argument("--output", type=Path, default=Path("data/processed/dataset.csv"))
    parser.add_argument("--notional", type=float, default=10_000.0)
    parser.add_argument("--latency-ms", type=float, default=0.0)
    parser.add_argument("--fee-rate", type=float, default=0.001, help="taker fee fraction")
    parser.add_argument("--latency-bps", type=float, default=0.0)
    parser.add_argument("--max-data-age-ms", type=float, default=None)
    args = parser.parse_args()

    load_report = LoadReport()
    ticks = load_ticks(args.input, report=load_report)
    cfg = DatasetConfig(
        notional=args.notional,
        latency_ms=args.latency_ms,
        cost_model=CostModel(default_fee_rate=args.fee_rate, latency_bps=args.latency_bps),
        max_data_age_ms=args.max_data_age_ms,
    )
    frames, reports = [], {}
    for symbol, symbol_ticks in ticks_by_symbol(ticks).items():
        frame, report = build_dataset(symbol_ticks, cfg)
        frames.append(frame)
        reports[symbol] = report.to_dict()

    import pandas as pd

    dataset = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(args.output, index=False)
    summary = {
        "input": str(args.input),
        "load": {
            "files": load_report.files,
            "records": load_report.records,
            "invalid_records": load_report.invalid_records,
            "malformed_lines": load_report.malformed_lines,
            "by_exchange": dict(load_report.by_exchange),
        },
        "config": {
            "notional": cfg.notional,
            "latency_ms": cfg.latency_ms,
            "fee_rate": args.fee_rate,
            "latency_bps": args.latency_bps,
            "max_data_age_ms": cfg.max_data_age_ms,
        },
        "symbols": reports,
        "rows": int(len(dataset)),
    }
    args.output.with_suffix(".report.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
