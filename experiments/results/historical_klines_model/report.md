# 1-minute candle model: will next minute's cross-exchange gap exceed the cost?

_Generated 2026-10-14T14:10:38.973580+00:00_

> **Limited, assumption-based simulation.** Candles hold no bid/ask or depth. The target is a close-to-close gap versus an assumed round-trip cost; 'upper-bound P&L' ignores fills, inventory, latency and how long a gap lasts. It is not achievable profit (project_plan.md §8.5).

## Setup

- Exchanges: binance, bybit, okx; 263,520 aligned minutes (nothing filled in)
- Target at minute t: best buy->sell close gap at minute t+1 > round-trip cost
- Features at minute t: current and lagged gaps, rolling gap mean/std, volatility, volume, hour/weekday (only minutes <= t)
- Split: chronological 60/20/20 with a purge of 1 minute; threshold chosen on validation only; test evaluated once
- Methods: persistence rule, Logistic Regression, Random Forest, Gradient Boosting, never trade

## Results (test period)

### Round-trip cost 1.0 bps

- Period: 2026-04-14T11:03:00+00:00 -> 2026-10-14T10:01:00+00:00
- Rows (train/validation/test): 158,074 / 52,691 / 52,692
- Positive examples (train/validation/test): 57391 / 16135 / 16744

| method | selected | precision | recall | PR-AUC | upper-bound P&L per 10k | threshold |
|---|---|---|---|---|---|---|
| rule_persistence (gap now > cost) | 16744 | 0.475 | 0.475 | 0.484 | 345 |  |
| logistic_regression | 9572 | 0.615 | 0.351 | 0.557 | 1.91e+03 | 0.6 |
| random_forest | 9149 | 0.625 | 0.342 | 0.564 | 1.92e+03 | 0.6 |
| gradient_boosting | 10318 | 0.607 | 0.374 | 0.567 | 1.9e+03 | 0.45 |
| trade_never | 0 |  |  |  | 0 |  |

### Round-trip cost 2.0 bps

- Period: 2026-04-14T11:03:00+00:00 -> 2026-10-14T10:01:00+00:00
- Rows (train/validation/test): 158,074 / 52,691 / 52,692
- Positive examples (train/validation/test): 4760 / 1097 / 1044

| method | selected | precision | recall | PR-AUC | upper-bound P&L per 10k | threshold |
|---|---|---|---|---|---|---|
| rule_persistence (gap now > cost) | 1044 | 0.276 | 0.276 | 0.202 | -409 |  |
| logistic_regression | 51 | 0.745 | 0.0364 | 0.282 | 36 | 0.998 |
| random_forest | 216 | 0.667 | 0.138 | 0.286 | 85 | 0.95 |
| gradient_boosting | 201 | 0.711 | 0.137 | 0.296 | 104 | 0.6 |
| trade_never | 0 |  |  |  | 0 |  |

### Round-trip cost 3.0 bps

- Period: 2026-04-14T11:03:00+00:00 -> 2026-10-14T10:01:00+00:00
- Rows (train/validation/test): 158,074 / 52,691 / 52,692
- Positive examples (train/validation/test): 600 / 110 / 101

| method | selected | precision | recall | PR-AUC | upper-bound P&L per 10k | threshold |
|---|---|---|---|---|---|---|
| rule_persistence (gap now > cost) | 101 | 0.267 | 0.267 | 0.195 | -55.5 |  |
| logistic_regression | 53 | 0.377 | 0.198 | 0.22 | -11.5 | 0.995 |
| random_forest | 29 | 0.31 | 0.0891 | 0.141 | -10 | 0.95 |
| gradient_boosting | 4 | 0.5 | 0.0198 | 0.191 | -0.301 | 0.7 |
| trade_never | 0 |  |  |  | 0 |  |

### Round-trip cost 5.0 bps

- Period: 2026-04-14T11:03:00+00:00 -> 2026-10-14T10:01:00+00:00
- Rows (train/validation/test): 158,074 / 52,691 / 52,692
- Positive examples (train/validation/test): 35 / 5 / 8

| method | selected | precision | recall | PR-AUC | upper-bound P&L per 10k | threshold |
|---|---|---|---|---|---|---|
| rule_persistence (gap now > cost) | 8 | 0.25 | 0.25 | 0.232 | -10.9 |  |
| logistic_regression | 0 |  | 0 | 0.0177 | 0 | 1 |
| random_forest | 10 | 0.1 | 0.125 | 0.0332 | -19.3 | 0.55 |
| gradient_boosting | 14 | 0 | 0 | 0.000211 | -48.8 | 0.85 |
| trade_never | 0 |  |  |  | 0 |  |

### Round-trip cost 20.0 bps

- Period: 2026-04-14T11:03:00+00:00 -> 2026-10-14T10:01:00+00:00
- Rows (train/validation/test): 158,074 / 52,691 / 52,692
- Positive examples (train/validation/test): 0 / 1 / 0

**Not trained:** not enough positive examples (train 0, validation 1, test 0); a model cannot learn from this and any result would be noise.

## How to read this

- If a scenario was not trained, that is the finding for that cost level: there were too few positive minutes to learn from.
- A model is only useful if it beats the persistence rule AND trade-never on the test period.
- Fees are assumptions; real tiers differ by account.
