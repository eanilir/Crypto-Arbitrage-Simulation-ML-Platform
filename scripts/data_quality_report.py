"""Audit recorded order-book data and write a JSON quality report.

python scripts/data_quality_report.py --input data/raw/real_sample
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.data_quality import analyze  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--stale-ms", type=float, default=1000.0)
    parser.add_argument("--gap-seconds", type=float, default=5.0)
    args = parser.parse_args()
    report = analyze(args.input, stale_ms=args.stale_ms, gap_seconds=args.gap_seconds).to_dict()
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
