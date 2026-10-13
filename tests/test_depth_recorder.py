import asyncio
import json
from datetime import datetime, timezone

import pytest
from services.data_collector.app import depth_recorder as dr
from services.data_collector.app.depth_recorder import (
    DepthRecorder,
    DepthSnapshot,
    build_record,
    parse_binance,
    parse_bybit,
    parse_okx,
    validate_snapshot,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_parse_binance_has_no_event_timestamp() -> None:
    snapshot = parse_binance(
        {"lastUpdateId": 7, "bids": [["100.0", "1.5"]], "asks": [["100.5", "2.0"]]}
    )
    assert snapshot.bids == [[100.0, 1.5]]
    assert snapshot.event_timestamp_ms is None
    assert snapshot.sequence_id == 7


def test_parse_bybit_reads_event_time_and_update_id() -> None:
    snapshot = parse_bybit(
        {
            "retCode": 0,
            "result": {"b": [["100", "1"]], "a": [["101", "2"]], "ts": 1767225600000, "u": 9},
        }
    )
    assert snapshot.event_timestamp_ms == 1767225600000
    assert snapshot.sequence_id == 9


def test_parse_bybit_error_is_raised_not_swallowed() -> None:
    with pytest.raises(ValueError):
        parse_bybit({"retCode": 10001, "retMsg": "bad symbol"})


def test_parse_okx_ignores_extra_level_fields() -> None:
    snapshot = parse_okx(
        {
            "code": "0",
            "data": [
                {
                    "bids": [["100", "1", "0", "3"]],
                    "asks": [["101", "2", "0", "1"]],
                    "ts": "1767225600000",
                }
            ],
        }
    )
    assert snapshot.bids == [[100.0, 1.0]]
    assert snapshot.event_timestamp_ms == 1767225600000


def _snap(bids, asks) -> DepthSnapshot:
    return DepthSnapshot(bids=bids, asks=asks, event_timestamp_ms=None, sequence_id=None)


def test_valid_book_has_no_issues() -> None:
    assert validate_snapshot(_snap([[100, 1], [99, 1]], [[101, 1], [102, 1]])) == []


def test_crossed_book_is_flagged() -> None:
    assert "crossed_book" in validate_snapshot(_snap([[102, 1]], [[101, 1]]))


def test_invalid_values_are_flagged() -> None:
    issues = validate_snapshot(_snap([[0, 1]], [[101, -1]]))
    assert "bid_non_positive_price" in issues
    assert "ask_negative_quantity" in issues
    assert "bid_non_finite" in validate_snapshot(_snap([[float("nan"), 1]], [[101, 1]]))


def test_empty_and_unsorted_books_are_flagged() -> None:
    assert "empty_bids" in validate_snapshot(_snap([], [[101, 1]]))
    issues = validate_snapshot(_snap([[99, 1], [100, 1]], [[102, 1], [101, 1]]))
    assert "bids_not_sorted_descending" in issues
    assert "asks_not_sorted_ascending" in issues


def test_record_keeps_event_and_receive_times_separate() -> None:
    snapshot = DepthSnapshot([[100, 1]], [[101, 1]], 1767225600000, 5)
    record = build_record(
        exchange="bybit",
        symbol="BTC/USDT",
        snapshot=snapshot,
        requested_at=NOW,
        received_at=NOW,
        round_trip_ms=12.3456,
    )
    assert record["event_timestamp"] == "2026-01-01T00:00:00+00:00"
    assert record["received_timestamp"] == NOW.isoformat()
    assert record["timestamp_quality"] == "present"
    assert record["validation_status"] == "ok"
    assert record["round_trip_ms"] == 12.346


def test_missing_event_time_is_marked_not_invented() -> None:
    record = build_record(
        exchange="binance",
        symbol="BTC/USDT",
        snapshot=_snap([[100, 1]], [[101, 1]]),
        requested_at=NOW,
        received_at=NOW,
        round_trip_ms=1.0,
    )
    assert record["event_timestamp"] is None
    assert record["timestamp_quality"] == "missing"


def test_invalid_record_is_kept_but_marked() -> None:
    record = build_record(
        exchange="okx",
        symbol="BTC/USDT",
        snapshot=_snap([[102, 1]], [[101, 1]]),
        requested_at=NOW,
        received_at=NOW,
        round_trip_ms=1.0,
    )
    assert record["validation_status"] == "invalid"
    assert record["validation_issues"] == ["crossed_book"]


def test_recorder_rejects_unknown_exchange(tmp_path) -> None:
    with pytest.raises(ValueError):
        DepthRecorder(tmp_path, exchanges=("nope",))


def test_cycle_writes_records_and_logs_missing_exchange(tmp_path, monkeypatch) -> None:
    payloads = {
        "binance": {"lastUpdateId": 1, "bids": [["100", "1"]], "asks": [["101", "1"]]},
        "bybit": {
            "retCode": 0,
            "result": {"b": [["100", "1"]], "a": [["101", "1"]], "ts": 1767225600000, "u": 2},
        },
    }

    def fake_get(url: str, timeout: float):
        for name, payload in payloads.items():
            if name in url:
                return payload
        raise OSError("okx unreachable")

    monkeypatch.setattr(dr, "_http_get_json", fake_get)
    recorder = DepthRecorder(tmp_path)
    asyncio.run(recorder.run_cycle())

    depth_files = list(tmp_path.glob("market_depth_*.ndjson"))
    rows = [json.loads(line) for line in depth_files[0].read_text().splitlines()]
    assert sorted(row["exchange"] for row in rows) == ["binance", "bybit"]
    # the unreachable exchange is observable and no book was fabricated for it
    events = [
        json.loads(line)
        for line in next(tmp_path.glob("collector_events_*.ndjson")).read_text().splitlines()
    ]
    assert events[0]["exchange"] == "okx"
    assert recorder.stats.stale_gap_cycles == 1
    assert recorder.stats.records == 2
    assert recorder.stats.missing_event_timestamp == 1  # binance has no event time


def test_restart_appends_and_keeps_runs_separate(tmp_path, monkeypatch) -> None:
    from shared.market_data import load_ticks

    payload = {"lastUpdateId": 1, "bids": [["100", "1"]], "asks": [["101", "1"]]}
    monkeypatch.setattr(dr, "_http_get_json", lambda url, timeout: payload)

    for _ in range(2):  # two recorder processes writing to the same directory
        recorder = DepthRecorder(tmp_path, exchanges=("binance",))
        asyncio.run(recorder.run_cycle())
        asyncio.run(recorder.run_cycle())

    lines = next(tmp_path.glob("market_depth_*.ndjson")).read_text().splitlines()
    assert len(lines) == 4  # nothing was overwritten
    # cycle ids restart at 0 per run; ticks must not merge across runs
    assert len(load_ticks(tmp_path)) == 4
