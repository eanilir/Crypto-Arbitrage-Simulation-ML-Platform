"""Container health check: the recorder must have refreshed its stats file recently.

Exit code 0 = healthy, 1 = stale or missing.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATS = Path(os.getenv("COLLECTOR_STATS", "data/raw/live/collector_stats.json"))
MAX_AGE_SECONDS = float(os.getenv("COLLECTOR_MAX_STATS_AGE", "120"))


def main() -> int:
    try:
        updated = datetime.fromisoformat(
            json.loads(STATS.read_text(encoding="utf-8"))["updated_at"]
        )
    except (OSError, KeyError, ValueError):
        print("collector stats missing or unreadable")
        return 1
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    print(f"collector stats age: {age:.0f}s")
    return 0 if age <= MAX_AGE_SECONDS else 1


if __name__ == "__main__":
    sys.exit(main())
