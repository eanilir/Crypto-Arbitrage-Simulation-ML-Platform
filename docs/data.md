# Data documentation

## Source

`services/data_collector/app/depth_recorder.py` polls public, unauthenticated REST order-book
endpoints of Binance, Bybit and OKX concurrently once per cycle (default 1 s, depth 20 per side).

```powershell
python -m services.data_collector.app.depth_recorder --output-dir data/raw/live
python -m services.data_collector.app.depth_recorder --duration 900 --interval 0.5 --symbols BTC/USDT ETH/USDT XRP/USDT
```

Output per UTC day: `market_depth_YYYYMMDD.ndjson`, `collector_events_YYYYMMDD.ndjson` (fetch errors)
and `collector_stats.json` (refreshed every 30 s).

## Record schema (`market_depth_*.ndjson`)

| Field | Meaning |
|---|---|
| `exchange`, `symbol` | normalized (`binance`, `BTC/USDT`) |
| `run_id`, `cycle` | recorder process id and cycle number; together identify a tick (cycles restart at 0 after a restart) |
| `event_timestamp` | exchange-provided time (Bybit `ts`, OKX `ts`); `null` for Binance, whose depth endpoint has none |
| `received_timestamp` | UTC time the response was received locally |
| `request_timestamp` | UTC time the request was issued |
| `round_trip_ms` | local request round trip. **Not a network latency measurement.** |
| `timestamp_quality` | `present` or `missing` (event time) |
| `sequence_id` | Binance `lastUpdateId`, Bybit `u`; `null` for OKX |
| `order_book_depth` | levels available on both sides |
| `validation_status`, `validation_issues` | `ok` or `invalid` with reasons (crossed book, bad price, ordering, ...) |
| `bids`, `asks` | `[price, quantity]`, best first |
| `data_source` | `rest_depth` (real) or `synthetic` |

Invalid records are kept in the files (so quality can be audited) but excluded from datasets.
Missing event times are marked, never invented. A failing exchange produces no book for that
cycle and one row in `collector_events_*.ndjson`.

## Timestamps and staleness

- Event time and receive time are stored separately and both are UTC.
- **Data age** (used in datasets, baselines and experiments) = decision time minus the oldest
  receive time among the two books of a candidate. It captures cross-exchange receive skew, not
  exchange or network latency, and is the same definition everywhere.
- **Simulated latency** is a separate experiment parameter (see [experiments.md](experiments.md)).

## Quality audit and retention

```powershell
python scripts/data_quality_report.py --input data/raw/live
python scripts/apply_retention.py                 # dry run
python scripts/apply_retention.py --apply
```

The audit reports record counts, invalid and malformed lines, fetch errors per exchange, missing
event times, timestamp anomalies (received before requested, per-exchange out-of-order receives,
event time in the future), data gaps, incomplete and stale ticks, collector availability, tick
spacing percentiles and storage growth.

Provisional retention (from the short pilot, to be revisited after the 3-7 day run): raw files 7
days, processed files 30 days. Only dated files older than the cutoff are removed.

## Observations from the first real sample (13 Oct 2026, 15 minutes, BTC/USDT, 1 s cycles)

Run with the recorder; reproduce with `scripts/data_quality_report.py`.

- 773 cycles, 2318 records, 0 invalid, 0 timestamp anomalies, availability 99.87 %.
- One Binance request timed out (5 s timeout at the time). Because a cycle waits for all exchanges,
  that stalled every exchange for about 5-6.6 s. The default timeout is now 3 s.
- About 15 % of ticks had more than 1 s of receive skew between exchanges.
- Storage: roughly 250 MB/day for one symbol and three exchanges at depth 20 and 1 s cycles.

## Limitations

- REST snapshots at about 1 s resolution cannot show sub-second order-book dynamics. Simulated
  latencies below one tick all map to the next snapshot.
- Order-book consistency cannot be checked with sequence numbers across all exchanges (OKX REST has
  none; Binance depth snapshots are not diff streams).
- Historical order-book data was not sourced. Historical experiments therefore use recorded
  snapshots only and are limited simulations, not reconstructions of past execution.
- The 3-7 day collection has not been run.
- `scripts/btc_usdt_pilot.py` (WebSocket `bookTicker`, Binance only, no depth) remains as the
  original connectivity pilot; see `docs/btc_usdt_pilot_report.md`.
