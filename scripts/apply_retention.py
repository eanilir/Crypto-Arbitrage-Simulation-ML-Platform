"""Delete recorded files older than the retention policy. Dry-run unless --apply is given.

python scripts/apply_retention.py --raw data/raw --processed data/processed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.retention import RetentionPolicy, apply_retention  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed"))
    parser.add_argument("--raw-days", type=int, default=7)
    parser.add_argument("--processed-days", type=int, default=30)
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    args = parser.parse_args()
    victims = apply_retention(
        args.raw,
        args.processed,
        RetentionPolicy(args.raw_days, args.processed_days),
        dry_run=not args.apply,
    )
    verb = "deleted" if args.apply else "would delete"
    for path in victims:
        print(f"{verb}: {path}")
    print(f"{len(victims)} file(s) {verb}")


if __name__ == "__main__":
    main()
