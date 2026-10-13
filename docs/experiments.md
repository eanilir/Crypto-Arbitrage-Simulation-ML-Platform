# Experiments: definitions and assumptions

All definitions are implemented once in code; this page summarises them.

## Spread and profit (`services/arbitrage_engine/app/candidates.py`)

```text
quantity        = notional / buy_best_ask
gross_spread    = quantity * (sell_best_bid - buy_best_ask)           # may be negative
buy_cost        = cost of walking the ask side for `quantity`
sell_proceeds   = proceeds of walking the bid side for `quantity`
fees            = buy_cost * buy_fee + sell_proceeds * sell_fee
slippage        = (buy_cost - top_buy_cost) + (top_sell_proceeds - sell_proceeds)   # informational
latency_cost    = buy_cost * latency_bps / 10_000                     # modeled approximation
net_profit      = sell_proceeds - buy_cost - fees - latency_cost      # slippage not subtracted twice
```

Statuses: `net_profitable`, `gross_positive` (gross > 0, net not above the minimum), `unprofitable`
(gross <= 0), and rejected: `rejected_insufficient_depth`, `rejected_invalid_data`,
`rejected_stale`. Negative spreads are valid unprofitable candidates; no liquidity is invented.

## Dataset (`services/ml_service/app/dataset.py`)

- **Unit of observation:** one priced candidate (buy exchange, sell exchange, symbol) at one tick,
  for every ordered exchange pair, profitable or not. Rejected candidates are counted, not emitted.
- **Execution policy for the label:** execute at the first later tick at least `latency_ms` after
  the decision tick (same tick for 0 ms), with the quantity fixed at decision time, both legs
  filled by walking the execution tick's books.
- **Target:** `label = 1` if `outcome_net_profit = proceeds - cost - fees > 0`, else `0`. If the
  execution books cannot fill the quantity the trade is not executed (label 0,
  `outcome_status = exec_insufficient_depth`). Missing exchange or invalid execution book, or no
  execution tick within 2 s: the row is dropped, not guessed.
- The modeled `latency_bps` cost is not applied in the label because replaying a later book already
  captures price movement. It is used by the decision-time cost-aware baseline only.
- At latency 0 the label is identical to the decision-time net edge, so rule C and the models look
  perfect by construction; only latency > 0 tests prediction.

### Features

Computed only from the decision tick and earlier ticks (`FEATURE_GROUPS` in `dataset.py`):

| Group | Features |
|---|---|
| core | gross_spread_bps, net_edge_bps, fees_bps, latency_cost_bps, top_qty_ratio, configured_latency_ms, buy_exchange, sell_exchange |
| data_age | data_age_ms, event_skew_ms |
| depth | slippage_bps, depth_ratio, imbalance_buy, imbalance_sell |
| movement | mid_change_buy_bps, mid_change_sell_bps, spread_change_bps (5-tick history) |

`outcome_*`, `label` and `candidate_net_profit` are never features. Tests verify that features
for a tick are identical when later ticks are removed, that datasets are deterministic, and that
labels use the execution tick.

## Baselines (`services/simulation_engine/app/selectors.py`)

A gross spread > 0; B gross spread minus fees > 0; C net edge (fees, slippage, modeled latency)
> 0, optionally with a maximum data age; D ML probability >= threshold. All run on the same rows.

## Models and validation (`services/ml_service/app/training.py`)

Logistic Regression, Random Forest and (histogram) Gradient Boosting with imputation, scaling
(LR) and one-hot exchange encoding. Chronological 60/20/20 split by tick with a **purge**: rows
whose outcome time reaches into the next period are dropped. Hyper-parameters (small grids, PR-AUC)
and the decision threshold (maximum validation net P&L) use the validation period only; the test
period is evaluated once. Models are saved as `models/<name>-<fingerprint>-s<seed>/` with
`metadata.json` (seed, parameters, split boundaries, data fingerprint, metrics). Walk-forward
(expanding window) folds are available for cross-period evaluation.

## Backtest (`services/simulation_engine/app/backtest.py`)

Chronological replay over the dataset. Assumptions: inventory pre-positioned on every exchange and
never rebalanced (trades are skipped when inventory runs out); both legs fully fill at visible
depth; no partial fills, queue position or transfer fees; one trade per tick and a per-pair
cooldown; reported P&L is realized trade P&L (inventory price risk excluded). Runs are
reproducible: the run id is a hash of configuration, selector and dataset fingerprint, and
`save_backtest` writes config, metrics, trades, equity and decisions.

## Running the experiments

```powershell
python scripts/generate_synthetic_data.py --output-dir data/raw/synthetic --ticks 12000 --interval 0.25
python experiments/run_experiments.py --input data/raw/synthetic --output experiments/results/synthetic
python experiments/run_experiments.py --input data/raw/live --output experiments/results/live
```

The report states whether the input is synthetic. **Synthetic results describe the generator's
assumptions, not real markets.** ML is not assumed to beat the cost-aware rule; the runner skips
ML experiments (and says why) when there are too few positive labels.

## Honest status of the results

- `experiments/results/synthetic/`: pipeline validation only.
- `experiments/results/real_sample_15min/`: 15 minutes of real data at 1 s resolution. After a 0.1 %
  taker fee assumption no candidate was net profitable, so no ML conclusion is possible. This is a
  property of that sample, not evidence about other periods.
- The research question needs the 3-7 day (or longer) recording and the literature review.
