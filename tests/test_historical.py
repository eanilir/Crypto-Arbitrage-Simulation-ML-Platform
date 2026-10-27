import urllib.parse

import pytest
from shared import historical as hist
from shared.historical import (
    MINUTE_MS,
    Candle,
    fetch_candles,
    parse_binance,
    parse_bybit,
    parse_okx,
    read_csv,
    validate_candles,
    write_csv,
)

T0 = 1_700_000_000_000 // MINUTE_MS * MINUTE_MS
TOTAL = 2_500  # minutes the fake exchange "has"


def price(i: int) -> float:
    return 100.0 + i * 0.01


def fake_exchange(skip: set[int] | None = None):
    """Fake REST server honouring each exchange's pagination semantics."""
    skip = skip or set()
    minutes = [i for i in range(TOTAL) if i not in skip]

    def row(i: int) -> tuple[int, float]:
        return T0 + i * MINUTE_MS, price(i)

    def fetch(url: str, timeout: float):
        parsed = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if "binance" in parsed.netloc:
            start, end = int(q["startTime"]), int(q["endTime"])
            sel = [i for i in minutes if start <= row(i)[0] <= end][: int(q["limit"])]
            return [
                [row(i)[0], str(p), str(p + 1), str(p - 1), str(p), "2", row(i)[0] + 59_999, "200"]
                for i in sel
                for p in [row(i)[1]]
            ]
        if "bybit" in parsed.netloc:
            start, end = int(q["start"]), int(q["end"])
            sel = [i for i in minutes if start <= row(i)[0] <= end][-int(q["limit"]) :]
            lst = [
                [str(row(i)[0]), str(p), str(p + 1), str(p - 1), str(p), "2", "200"]
                for i in reversed(sel)
                for p in [row(i)[1]]
            ]
            return {"retCode": 0, "result": {"list": lst}}
        after = int(q["after"])
        sel = [i for i in minutes if row(i)[0] < after][-int(q["limit"]) :]
        data = [
            [str(row(i)[0]), str(p), str(p + 1), str(p - 1), str(p), "2", "2", "200", "1"]
            for i in reversed(sel)
            for p in [row(i)[1]]
        ]
        return {"code": "0", "data": data}

    return fetch


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(hist.time, "sleep", lambda s: None)


@pytest.mark.parametrize("exchange", ["binance", "bybit", "okx"])
def test_pagination_returns_every_minute_exactly_once(exchange) -> None:
    candles = fetch_candles(exchange, "BTC/USDT", T0, T0 + TOTAL * MINUTE_MS, fake_exchange())
    assert len(candles) == TOTAL  # more than one page for every exchange's limit
    times = [c.open_time_ms for c in candles]
    assert times == sorted(set(times))
    assert candles[0].open == pytest.approx(price(0)) and candles[-1].open == pytest.approx(
        price(TOTAL - 1)
    )
    report = validate_candles(candles, T0, T0 + TOTAL * MINUTE_MS)
    assert report.coverage == 1.0 and report.invalid_rows == 0 and not report.gaps


@pytest.mark.parametrize("exchange", ["binance", "bybit", "okx"])
def test_missing_minutes_are_reported_not_filled(exchange) -> None:
    missing = {10, 11, 12, 700}
    candles = fetch_candles(
        exchange, "BTC/USDT", T0, T0 + TOTAL * MINUTE_MS, fake_exchange(missing)
    )
    report = validate_candles(candles, T0, T0 + TOTAL * MINUTE_MS)
    assert len(candles) == TOTAL - len(missing)
    assert report.missing_minutes == len(missing)
    assert sorted(report.gaps) == [(T0 + 10 * MINUTE_MS, 3), (T0 + 700 * MINUTE_MS, 1)]


def test_window_boundaries_are_respected() -> None:
    start, end = T0 + 100 * MINUTE_MS, T0 + 400 * MINUTE_MS
    for exchange in ("binance", "bybit", "okx"):
        candles = fetch_candles(exchange, "BTC/USDT", start, end, fake_exchange())
        assert candles[0].open_time_ms == start
        assert candles[-1].open_time_ms == end - MINUTE_MS
        assert len(candles) == 300


def test_okx_unfinished_candle_is_dropped() -> None:
    payload = {
        "code": "0",
        "data": [
            ["1", "1", "2", "1", "1", "1", "1", "1", "0"],
            ["2", "1", "2", "1", "1", "1", "1", "1", "1"],
        ],
    }
    assert [c.open_time_ms for c in parse_okx(payload)] == [2]


def test_exchange_errors_are_raised_not_swallowed() -> None:
    with pytest.raises(ValueError):
        parse_bybit({"retCode": 10001, "retMsg": "bad"})
    with pytest.raises(ValueError):
        parse_okx({"code": "51001", "msg": "bad instrument"})
    assert parse_binance([[1, "1", "2", "1", "1", "5", 2, "9"]])[0].volume_quote == 9.0
    with pytest.raises(ValueError):
        fetch_candles("kraken", "BTC/USDT", T0, T0 + MINUTE_MS)
    with pytest.raises(ValueError):
        fetch_candles("binance", "BTC/USDT", T0, T0)


def test_validation_flags_bad_and_unordered_rows() -> None:
    good = Candle(T0, 100, 101, 99, 100, 1, 100)
    bad_range = Candle(T0 + MINUTE_MS, 100, 99, 101, 100, 1, 100)  # high < low
    bad_price = Candle(T0 + 2 * MINUTE_MS, 0, 1, 0, 0, 1, 1)
    repeated = Candle(T0 + 2 * MINUTE_MS, 100, 101, 99, 100, 1, 100)
    report = validate_candles([good, bad_range, bad_price, repeated], T0, T0 + 4 * MINUTE_MS)
    assert report.invalid_rows == 2
    assert report.duplicate_or_unordered == 1


def test_csv_roundtrip(tmp_path) -> None:
    candles = [Candle(T0 + i * MINUTE_MS, 1.5, 2.5, 1.0, 2.0, 3.0, 4.0) for i in range(5)]
    path = tmp_path / "x" / "binance.csv"
    write_csv(path, candles)
    assert read_csv(path) == candles


def test_download_resumes_after_an_interruption_without_duplicates(tmp_path) -> None:
    path = tmp_path / "okx.csv"
    end = T0 + TOTAL * MINUTE_MS
    good = fake_exchange()
    calls = {"n": 0}

    def flaky(url: str, timeout: float):
        calls["n"] += 1
        if calls["n"] > 12:  # the connection dies partway through
            raise OSError("network down")
        return good(url, timeout)

    with pytest.raises(OSError):
        hist.download_to_csv("okx", "BTC/USDT", T0, end, path, flaky, window_minutes=600)
    saved = read_csv(path)
    assert 0 < len(saved) < TOTAL  # earlier windows were kept on disk

    hist.download_to_csv("okx", "BTC/USDT", T0, end, path, good, window_minutes=600)
    candles = read_csv(path)
    assert len(candles) == TOTAL
    assert [c.open_time_ms for c in candles] == [T0 + i * MINUTE_MS for i in range(TOTAL)]
    assert validate_candles(candles, T0, end).coverage == 1.0
