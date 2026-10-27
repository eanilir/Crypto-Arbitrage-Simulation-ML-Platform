"""Stream-normalize recorded market-depth NDJSON without changing the source files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REQUIRED_FIELDS = (
    "exchange",
    "symbol",
    "run_id",
    "cycle",
    "event_timestamp",
    "received_timestamp",
    "request_timestamp",
    "round_trip_ms",
    "timestamp_quality",
    "sequence_id",
    "data_source",
    "order_book_depth",
    "validation_status",
    "validation_issues",
    "bids",
    "asks",
)


class NormalizationError(ValueError):
    """A single record cannot be represented in the normalized schema."""


def _timestamp(value: Any, field: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise NormalizationError(f"{field} must be an ISO-8601 string or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise NormalizationError(f"{field} is not a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise NormalizationError(f"{field} must include a timezone")
    return parsed.isoformat()


def _number(value: Any, field: str, *, integer: bool = False) -> int | float:
    if isinstance(value, bool):
        raise NormalizationError(f"{field} must be numeric")
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError) as error:
        raise NormalizationError(f"{field} must be numeric") from error
    if not math.isfinite(parsed):
        raise NormalizationError(f"{field} must be finite")
    if integer and isinstance(value, float) and not value.is_integer():
        raise NormalizationError(f"{field} must be an integer")
    return parsed


def _levels(value: Any, field: str) -> list[list[float]]:
    if not isinstance(value, list):
        raise NormalizationError(f"{field} must be a list")
    normalized: list[list[float]] = []
    for index, level in enumerate(value):
        if not isinstance(level, list) or len(level) != 2:
            raise NormalizationError(f"{field}[{index}] must contain price and quantity")
        normalized.append(
            [
                _number(level[0], f"{field}[{index}].price"),
                _number(level[1], f"{field}[{index}].quantity"),
            ]
        )
    return normalized


def normalize_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise NormalizationError("record must be a JSON object")
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise NormalizationError(f"missing fields: {', '.join(missing)}")
    if not isinstance(record["exchange"], str) or not record["exchange"]:
        raise NormalizationError("exchange must be a non-empty string")
    if not isinstance(record["symbol"], str) or not record["symbol"]:
        raise NormalizationError("symbol must be a non-empty string")
    if not isinstance(record["run_id"], (str, type(None))):
        raise NormalizationError("run_id must be a string or null")
    if not isinstance(record["timestamp_quality"], str):
        raise NormalizationError("timestamp_quality must be a string")
    if not isinstance(record["data_source"], str):
        raise NormalizationError("data_source must be a string")
    if not isinstance(record["validation_status"], str):
        raise NormalizationError("validation_status must be a string")
    if not isinstance(record["validation_issues"], list):
        raise NormalizationError("validation_issues must be a list")
    if not isinstance(record["sequence_id"], (int, type(None))):
        raise NormalizationError("sequence_id must be an integer or null")

    depth = _number(record["order_book_depth"], "order_book_depth", integer=True)
    cycle = _number(record["cycle"], "cycle", integer=True)
    if depth < 0 or cycle < 0:
        raise NormalizationError("cycle and order_book_depth must be non-negative")

    normalized = {
        "exchange": record["exchange"],
        "symbol": record["symbol"],
        "run_id": record["run_id"],
        "cycle": cycle,
        "event_timestamp": _timestamp(record["event_timestamp"], "event_timestamp", allow_none=True),
        "received_timestamp": _timestamp(record["received_timestamp"], "received_timestamp"),
        "request_timestamp": _timestamp(record["request_timestamp"], "request_timestamp"),
        "round_trip_ms": _number(record["round_trip_ms"], "round_trip_ms"),
        "timestamp_quality": record["timestamp_quality"],
        "sequence_id": record["sequence_id"],
        "data_source": record["data_source"],
        "order_book_depth": depth,
        "validation_status": record["validation_status"],
        "validation_issues": record["validation_issues"],
        "bids": _levels(record["bids"], "bids"),
        "asks": _levels(record["asks"], "asks"),
    }
    if normalized["sequence_id"] is not None:
        normalized["sequence_id"] = _number(normalized["sequence_id"], "sequence_id", integer=True)
    return normalized


def _write_json_line(handle: Any, value: Any) -> None:
    handle.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False))
    handle.write("\n")


def normalize_file(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    errors_path = destination.with_suffix(".errors.ndjson")
    counts: Counter[str] = Counter()
    source_hash = hashlib.sha256()
    output_hash = hashlib.sha256()

    with (
        source.open("rb") as source_handle,
        destination.open("w", encoding="utf-8", newline="\n") as output_handle,
        errors_path.open("w", encoding="utf-8", newline="\n") as errors_handle,
    ):
        for line_number, raw_bytes in enumerate(source_handle, start=1):
            source_hash.update(raw_bytes)
            counts["input_lines"] += 1
            raw_line = raw_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
            if not raw_line.strip():
                counts["blank_lines"] += 1
                continue
            try:
                record = json.loads(raw_line)
                normalized = normalize_record(record)
            except (json.JSONDecodeError, NormalizationError) as error:
                counts["errors"] += 1
                _write_json_line(
                    errors_handle,
                    {"line": line_number, "error": str(error), "raw": raw_line},
                )
                continue
            encoded = json.dumps(normalized, separators=(",", ":"), ensure_ascii=False) + "\n"
            output_handle.write(encoded)
            output_hash.update(encoded.encode("utf-8"))
            counts["normalized_records"] += 1

    if counts["errors"] == 0:
        errors_path.unlink()

    counts.setdefault("input_lines", 0)
    counts.setdefault("normalized_records", 0)
    counts.setdefault("errors", 0)
    return {
        "source": str(source),
        "output": str(destination),
        "errors": str(errors_path) if errors_path.exists() else None,
        "source_sha256": source_hash.hexdigest(),
        "output_sha256": output_hash.hexdigest(),
        **dict(counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="raw directory or NDJSON file")
    parser.add_argument("--output", type=Path, required=True, help="separate normalized directory")
    args = parser.parse_args()

    sources = (
        [args.input]
        if args.input.is_file()
        else sorted(args.input.glob("market_depth_*.ndjson"))
    )
    if not sources:
        parser.error("input contains no market_depth_*.ndjson files")

    reports = []
    for source in sources:
        reports.append(normalize_file(source, args.output / source.name))
    manifest = {
        "input": str(args.input),
        "output": str(args.output),
        "files": reports,
        "input_lines": sum(report.get("input_lines", 0) for report in reports),
        "normalized_records": sum(report.get("normalized_records", 0) for report in reports),
        "errors": sum(report.get("errors", 0) for report in reports),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
