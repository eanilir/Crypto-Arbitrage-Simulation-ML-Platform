"""Retention policy for recorded data (provisional values from docs/btc_usdt_pilot_report.md).

Files are removed by the date in their name (``..._YYYYMMDD.ndjson``), never by guesswork:
files newer than the cutoff, files without a date, ``.gitkeep`` and ``collector_stats.json``
are always kept, and nothing outside the given roots is touched. Dry-run is the default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATE_IN_NAME = re.compile(r"_(\d{8})\.(?:ndjson|csv|json)$")
PROTECTED_NAMES = {".gitkeep", "collector_stats.json"}


@dataclass(frozen=True)
class RetentionPolicy:
    raw_days: int = 7
    processed_days: int = 30

    def __post_init__(self) -> None:
        if self.raw_days < 1 or self.processed_days < 1:
            raise ValueError("retention must be at least one day")


def file_date(path: Path) -> date | None:
    match = DATE_IN_NAME.search(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def expired_files(root: Path, days: int, today: date | None = None) -> list[Path]:
    today = today or datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=days)
    expired: list[Path] = []
    if not root.is_dir():
        return expired
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in PROTECTED_NAMES:
            continue
        stamp = file_date(path)
        if stamp is not None and stamp < cutoff:
            expired.append(path)
    return expired


def apply_retention(
    raw_root: Path,
    processed_root: Path,
    policy: RetentionPolicy | None = None,
    *,
    today: date | None = None,
    dry_run: bool = True,
) -> list[Path]:
    policy = policy or RetentionPolicy()
    victims = expired_files(raw_root, policy.raw_days, today) + expired_files(
        processed_root, policy.processed_days, today
    )
    if not dry_run:
        for path in victims:
            path.unlink()
    return victims
