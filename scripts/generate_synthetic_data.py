"""Write synthetic order-book data in the recorder format (pipeline testing only).

python scripts/generate_synthetic_data.py --output-dir data/raw/synthetic --ticks 20000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.synthetic import SyntheticConfig, write_synthetic  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/synthetic"))
    parser.add_argument("--ticks", type=int, default=20_000)
    parser.add_argument("--interval", type=float, default=0.25, help="seconds between ticks")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    path = write_synthetic(
        args.output_dir,
        SyntheticConfig(n_ticks=args.ticks, interval_s=args.interval, seed=args.seed),
    )
    print(f"wrote SYNTHETIC data (not market data): {path}")


if __name__ == "__main__":
    main()
