import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from shared.data_quality import analyze
from shared.retention import RetentionPolicy, apply_retention, expired_files, file_date
from shared.synthetic import SyntheticConfig, generate_records, write_synthetic

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def record(exchange, cycle, received_offset_ms=300, event=None, status="ok") -> dict:
    requested = T0 + timedelta(seconds=cycle)
    received = requested + timedelta(milliseconds=received_offset_ms)
    return {
        "exchange": exchange,
        "symbol": "BTC/USDT",
        "run_id": "r",
        "cycle": cycle,
        "event_timestamp": event,
        "received_timestamp": received.isoformat(),
        "request_timestamp": requested.isoformat(),
        "round_trip_ms": received_offset_ms,
        "validation_status": status,
        "bids": [[100.0, 1.0]],
        "asks": [[101.0, 1.0]],
    }


def write(path: Path, records) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_clean_data_reports_consistent_timestamps_and_full_availability(tmp_path) -> None:
    write_synthetic(tmp_path, SyntheticConfig(n_ticks=300, interval_s=0.5, seed=1))
    report = analyze(tmp_path)
    assert report.timestamps_consistent
    assert report.collector_availability == 1.0
    assert report.invalid_records == 0
    assert report.event_timestamp_missing == 300  # binance carries no event time
    assert report.storage_bytes > 0 and report.estimated_bytes_per_day > 0
    assert report.tick_spacing_ms["median"] == pytest.approx(500, abs=30)


def test_anomalies_gaps_and_incomplete_ticks_are_detected(tmp_path) -> None:
    rows = [record("a", c) for c in range(5)] + [record("b", c) for c in range(5) if c != 3]
    rows.append(record("a", 20))  # a 15 s gap for exchange a
    rows.append(record("b", 1, received_offset_ms=-50))  # received before request
    rows.append(record("b", 2, event=(T0 + timedelta(hours=1)).isoformat()))  # event in the future
    rows.append(record("a", 6, status="invalid"))
    path = tmp_path / "market_depth_20260101.ndjson"
    write(path, rows)
    with path.open("a") as handle:
        handle.write("not json\n")
    (tmp_path / "collector_events_20260101.ndjson").write_text(
        json.dumps({"type": "fetch_error", "exchange": "b"}) + "\n"
    )

    report = analyze(tmp_path, gap_seconds=5.0)
    assert report.malformed_lines == 1
    assert report.invalid_records == 1
    assert not report.timestamps_consistent
    assert report.timestamp_anomalies["received_before_request"] == 1
    assert report.timestamp_anomalies["event_after_receive"] == 1
    assert report.data_gaps["by_exchange"]["a"]["gaps_over_threshold"] == 1
    assert report.incomplete_ticks >= 1
    assert report.collector_availability < 1.0
    assert report.fetch_errors_by_exchange == {"b": 1}


def test_stale_ticks_use_cross_exchange_receive_skew(tmp_path) -> None:
    write(tmp_path / "market_depth_20260101.ndjson", [record("a", 0, 100), record("b", 0, 2500)])
    assert analyze(tmp_path, stale_ms=1000).stale_ticks == 1
    assert analyze(tmp_path, stale_ms=5000).stale_ticks == 0


def test_file_date_parsing() -> None:
    assert file_date(Path("market_depth_20260105.ndjson")) == date(2026, 1, 5)
    assert file_date(Path("notes.txt")) is None
    assert file_date(Path("market_depth_20269999.ndjson")) is None


def test_retention_dry_run_lists_but_does_not_delete(tmp_path) -> None:
    raw, processed = tmp_path / "raw", tmp_path / "processed"
    raw.mkdir()
    processed.mkdir()
    old = raw / "market_depth_20260101.ndjson"
    fresh = raw / "market_depth_20260110.ndjson"
    for path in (old, fresh):
        path.write_text("x")
    old_processed = processed / "dataset_20251201.csv"
    old_processed.write_text("x")
    (raw / ".gitkeep").write_text("")
    (raw / "collector_stats.json").write_text("{}")
    today = date(2026, 1, 10)

    victims = apply_retention(raw, processed, RetentionPolicy(7, 30), today=today, dry_run=True)
    assert set(victims) == {old, old_processed}
    assert old.exists() and old_processed.exists()

    apply_retention(raw, processed, RetentionPolicy(7, 30), today=today, dry_run=False)
    assert not old.exists() and not old_processed.exists()
    assert fresh.exists()
    assert (raw / ".gitkeep").exists() and (raw / "collector_stats.json").exists()


def test_retention_never_touches_todays_file_or_undated_files(tmp_path) -> None:
    today = date(2026, 1, 10)
    (tmp_path / "market_depth_20260110.ndjson").write_text("x")
    (tmp_path / "scratch.ndjson").write_text("x")
    assert expired_files(tmp_path, 1, today) == []
    with pytest.raises(ValueError):
        RetentionPolicy(raw_days=0)


def test_record_count_matches_generated_data(tmp_path) -> None:
    cfg = SyntheticConfig(n_ticks=50, seed=2)
    write_synthetic(tmp_path, cfg)
    assert analyze(tmp_path).total_records == len(generate_records(cfg))
