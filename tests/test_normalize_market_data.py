import json
from pathlib import Path

from scripts.normalize_market_data import normalize_file, normalize_record


def _record() -> dict:
    return {
        "exchange": "binance",
        "symbol": "BTC/USDT",
        "run_id": "run",
        "cycle": 1,
        "event_timestamp": None,
        "received_timestamp": "2026-10-26T00:00:00Z",
        "request_timestamp": "2026-10-26T00:00:00.100000+00:00",
        "round_trip_ms": 100,
        "timestamp_quality": "missing",
        "sequence_id": None,
        "data_source": "rest_depth",
        "order_book_depth": 1,
        "validation_status": "ok",
        "validation_issues": [],
        "bids": [["10.5", "2"]],
        "asks": [[10.6, 3]],
    }


def test_normalize_record_preserves_missing_event_timestamp() -> None:
    record = normalize_record(_record())

    assert record["event_timestamp"] is None
    assert record["received_timestamp"] == "2026-10-26T00:00:00+00:00"
    assert record["cycle"] == 1
    assert record["bids"] == [[10.5, 2.0]]


def test_normalize_file_streams_records_and_reports_bad_lines(tmp_path: Path) -> None:
    source = tmp_path / "market_depth_20261026.ndjson"
    source.write_text(json.dumps(_record()) + "\n" + '{"broken"\n', encoding="utf-8")

    report = normalize_file(source, tmp_path / "normalized.ndjson")

    assert report["input_lines"] == 2
    assert report["normalized_records"] == 1
    assert report["errors"] == 1
    assert json.loads((tmp_path / "normalized.ndjson").read_text())["cycle"] == 1
    assert (tmp_path / "normalized.errors.ndjson").exists()
