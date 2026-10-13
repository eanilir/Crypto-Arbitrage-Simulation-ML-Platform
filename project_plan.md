# Crypto Arbitrage Simulation & ML Platform

## 1. Project Overview

**Project Name:** Crypto Arbitrage Simulation & ML Platform

**Project Type:** Simulation / Backtesting / Paper Trading

**Real Money:** No

**Real Trading:** No

**Architecture:** Containerized Service-Based Architecture

**Primary Language:** Python

**Initial Environment:** Local Development

**Container Environment:** Docker / Docker Compose

**Future Deployment Target:** AWS Cloud

**Project Status:** Under Development

This project aims to develop a modular platform that collects cryptocurrency market data from multiple exchanges, identifies potential cross-exchange arbitrage opportunities, estimates transaction costs, evaluates opportunities using machine learning, and simulates trading outcomes without executing real trades.

The platform will support reproducible experiments, historical backtesting, performance evaluation, and monitoring through a dashboard.

The initial implementation will prioritize data quality, correct financial calculations, and a reliable simulation pipeline before expanding into cloud deployment and advanced experiments.

---

## 2. Project Objectives

The main objectives are:

- Collect public cryptocurrency market data from Binance, Bybit, and OKX.
- Standardize market data into a common schema.
- Monitor bid and ask prices across exchanges.
- Identify potential cross-exchange arbitrage candidates.
- Estimate fees, order-book slippage, data staleness, and simulated execution costs.
- Build a rule-based baseline for evaluating candidate opportunities.
- Create a labeled dataset for machine learning.
- Train and evaluate classification models that estimate whether a candidate is likely to be profitable under defined simulation assumptions.
- Compare ML-based filtering against rule-based baselines.
- Simulate virtual trades and calculate net profit and loss.
- Backtest the strategy using historical or replayed market data.
- Store market data, opportunities, predictions, simulated trades, and experiment results.
- Visualize system behavior and performance through Grafana.
- Containerize the application and its supporting services.
- Prepare the architecture for a later, cost-controlled AWS deployment.

The project must remain a simulation and research platform. It must not execute real trades or use real funds.

---

## 3. Research Objective

### 3.1 Research Question

**How do market-data staleness and simulated execution latency affect the net profitability of cross-exchange cryptocurrency arbitrage, and can a machine-learning filter improve performance over a rule-based baseline?**

Turkish interpretation:

Piyasa verisinin eskiliği ve simüle edilen işlem gecikmesi, borsalar arası kripto arbitrajının maliyet sonrası kârlılığını nasıl etkiler ve makine öğrenmesi filtresi kural tabanlı bir yönteme kıyasla performansı artırabilir mi?

### 3.2 Research Motivation

A positive price difference between two exchanges does not necessarily represent a profitable arbitrage opportunity.

Transaction fees, order-book depth, slippage, stale market data, and the delay between observing a price and hypothetically executing a trade can reduce or eliminate the apparent profit.

This project will investigate these factors in a controlled simulation environment and determine whether an ML model can help filter out candidates that are unlikely to remain profitable after the modeled costs.

The project must not assume that machine learning will outperform the rule-based baseline. That conclusion must be supported by experimental results.

### 3.3 Research Scope

The research will focus on:

- Cross-exchange arbitrage candidates.
- Bid and ask prices and available quantities.
- Market-data age.
- Simulated decision and execution delays.
- Trading fees and estimated order-book slippage.
- Net simulated profitability.
- Rule-based versus ML-based opportunity filtering.

A literature review must be completed before claiming that the research question is novel. The project may contribute an experimental comparison without claiming that the underlying idea has never been studied.

---

## 4. Project Scope and Limitations

### Included

- Public market-data collection.
- Historical data retrieval where suitable data is available.
- Live WebSocket data collection.
- Market-data normalization and validation.
- Cross-exchange candidate detection.
- Fee and order-book cost estimation.
- Dataset generation and feature engineering.
- Rule-based baselines.
- ML classification.
- Virtual portfolio simulation.
- Historical replay and backtesting.
- Performance and experiment reporting.
- API development.
- Dashboard development.
- Docker-based local deployment.
- Security, testing, monitoring, and logging.
- Future AWS deployment preparation.

### Excluded

- Real-money trading.
- Real exchange order execution.
- Deposits or withdrawals.
- Exchange API permissions for trading.
- Guaranteed-profit claims.
- Claims that simulated execution perfectly reproduces real-world execution.
- Unverified claims about actual exchange network latency.
- Unnecessary cloud expenses during early development.

---

## 5. Initial Exchanges and Trading Pairs

### Exchanges

- Binance
- Bybit
- OKX

### Initial Trading Pairs

- BTC/USDT
- ETH/USDT
- XRP/USDT

### Development Strategy

The intended project scope includes all three exchanges and all three trading pairs. However, data collection and validation will begin with BTC/USDT.

The initial pilot will test:

- WebSocket connectivity.
- Message frequency.
- Timestamp quality.
- Missing updates and data gaps.
- Reconnection behavior.
- Order-book consistency.
- Storage growth.
- Candidate detection reliability.

ETH/USDT, XRP/USDT, and additional exchanges will be added after the initial pipeline is stable.

---

## 6. System Architecture

The platform will use a modular, containerized, service-based architecture.

### Main Components

1. API Service
2. Data Collector
3. Arbitrage Engine
4. ML Service
5. Simulation and Backtesting Engine
6. PostgreSQL
7. InfluxDB
8. Redis
9. Grafana Dashboard

### High-Level Architecture

```text
Binance WebSocket / REST
Bybit WebSocket / REST
OKX WebSocket / REST
             |
             v
       Data Collector
             |
             v
 Data Validation and Normalization
             |
       +-----+------+
       |            |
       v            v
   InfluxDB      Redis
       |
       v
   Arbitrage Engine
       |
       v
 Candidate Opportunities
       |
       +----------------------+
       |                      |
       v                      v
 Rule-Based Evaluation    Feature Pipeline
                              |
                              v
                         ML Service
                              |
                              v
                      Opportunity Filtering
                              |
                              v
                   Simulation / Backtesting
                              |
                              v
                          PostgreSQL
                              |
                              v
                         FastAPI
                              |
                              v
                      Grafana Dashboard
```

This diagram describes the logical data flow. The exact service boundaries may evolve during implementation, but changes must preserve modularity and the separation between data collection, opportunity detection, ML inference, and simulation.

---

## 7. Service Responsibilities

### 7.1 Data Collector

Responsibilities:

- Connect to supported public market-data endpoints.
- Retrieve historical data through REST APIs where available.
- Subscribe to live WebSocket market-data streams.
- Collect best bid and ask prices.
- Collect corresponding bid and ask quantities.
- Collect limited order-book depth when required and supported.
- Record exchange event timestamps.
- Record local receive timestamps.
- Normalize symbols and exchange identifiers.
- Handle reconnects and temporary exchange failures.
- Detect missing or out-of-order updates where possible.
- Publish validated market data to downstream components.

The collector must not require private trading credentials for public market-data access.

### 7.2 Arbitrage Engine

Responsibilities:

- Read normalized order books.
- Compare executable buy and sell prices across exchanges.
- Generate candidate opportunities.
- Estimate gross spread.
- Estimate transaction fees.
- Estimate order-book slippage.
- Calculate modeled latency costs where applicable.
- Calculate estimated net profit.
- Record market-data age and calculation timestamps.
- Preserve unprofitable candidates for dataset construction and analysis.

The engine must distinguish between a candidate opportunity and a candidate that remains profitable after modeled costs.

### 7.3 ML Service

Responsibilities:

- Load a versioned trained model.
- Validate input features.
- Generate profitability predictions or scores.
- Return predictions with model version and timestamp.
- Avoid using future information unavailable at decision time.
- Support comparison with rule-based baselines.
- Record enough metadata to reproduce predictions.

The ML service must not independently execute or initiate real trades.

### 7.4 Simulation and Backtesting Engine

Responsibilities:

- Replay historical or recorded market data in chronological order.
- Simulate candidate selection and hypothetical execution.
- Apply configured fees and slippage assumptions.
- Apply documented latency and market-data staleness scenarios.
- Maintain a virtual portfolio.
- Calculate realized and unrealized simulated P&L as appropriate.
- Record rejected, selected, and simulated opportunities.
- Produce reproducible backtest results.

### 7.5 API Service

Responsibilities:

- Expose health and application endpoints.
- Provide access to market data and candidate opportunities.
- Return ML predictions.
- Return virtual portfolio and simulation results.
- Provide backtesting and performance summaries.
- Validate request parameters.
- Handle errors consistently.

### 7.6 Dashboard

Responsibilities:

- Display market prices and order-book summaries.
- Display candidate opportunities.
- Display gross spread and estimated net profit.
- Display fees, slippage, data age, and configured latency assumptions.
- Display ML predictions and rule-based decisions.
- Display simulation and backtesting results.
- Display data-collection health and system errors.

---

## 8. Market Data Collection Strategy

### 8.1 Historical Data

Historical REST endpoints or suitable public archives will be used where available.

Historical data may include:

- OHLCV candles.
- Historical trades.
- Historical order-book snapshots or updates, where available.
- Other relevant market data supported by the source.

Data availability, resolution, retention, and download limits must be verified before planning a large historical dataset.

A year of tick-level or order-book data must not be assumed to be readily available from every exchange.

### 8.2 Live WebSocket Data

The live collector will initially focus on BTC/USDT.

The preferred data fields are:

- Exchange.
- Symbol.
- Best bid price.
- Best bid quantity.
- Best ask price.
- Best ask quantity.
- Exchange event timestamp, when provided.
- Local receive timestamp.
- Order-book sequence or update identifiers, when available.
- Connection and reconnection events.
- Data validation status.
- Limited order-book depth, when required.

The schema must preserve the distinction between event time and local receive time.

Both timestamps must be normalized to UTC where possible. Their difference must not automatically be described as network latency because clock synchronization, timestamp semantics, and exchange behavior may affect the measurement.

### 8.3 Pilot Collection

Run a controlled **3–7 day BTC/USDT pilot** before expanding the data-collection workload.

The pilot must measure:

- Number of messages received.
- Update frequency.
- Missing updates and sequence gaps.
- Reconnection frequency.
- Invalid or out-of-order records.
- Storage consumption.
- Collector CPU and memory usage.
- Availability of the required fields.

Use these measurements to determine the appropriate storage and retention strategy.

### 8.4 Opportunity-Focused Logging

Detailed records should be captured around candidate opportunities, but the system must also retain samples from periods without apparent opportunities.

Keeping only profitable-looking periods would create selection bias and could make the ML model misleading.

The dataset should include:

- Profitable candidates.
- Unprofitable candidates.
- Candidates that become unprofitable after costs.
- Periods with no candidate opportunity.
- Stale or incomplete data events where relevant to quality analysis.

### 8.5 Data Resolution Limitations

Fifteen-minute OHLCV candles may be useful for coarse historical analysis, but they cannot reliably reconstruct sub-second order-book changes or actual execution outcomes.

The project must not use candle data alone to claim that high-frequency execution or latency effects have been accurately reproduced.

If historical order-book data is unavailable, the relevant experiments must be described as limited simulations rather than empirical reconstruction of actual historical order-book execution.

---

## 9. Data Standardization and Validation

All supported exchanges must use a common internal representation.

### 9.1 Common Market Data Schema

The schema should support fields such as:

```text
exchange
symbol
event_timestamp
received_timestamp
best_bid_price
best_bid_quantity
best_ask_price
best_ask_quantity
order_book_depth
sequence_id
data_source
validation_status
```

Fields that are unavailable from a particular source may be nullable, provided that the missingness is documented and downstream calculations handle it correctly.

Additional raw fields may be retained when needed for debugging or exchange-specific validation.

### 9.2 Validation Rules

Validate:

- Required fields.
- Numeric types.
- Finite price and quantity values.
- Positive prices.
- Non-negative quantities.
- Timestamp format and ordering.
- Symbol normalization.
- Exchange identifiers.
- Order-book consistency.
- Duplicate or repeated updates where detectable.
- Sequence continuity where supported.

For a valid non-crossed local order book, the best bid should generally not exceed the best ask. Any violation should be investigated or flagged according to the exchange feed's semantics rather than silently accepted.

Missing or invalid data must not be replaced with invented prices.

### 9.3 Data Quality Handling

Invalid records must be rejected or marked according to documented rules.

Data gaps, reconnects, stale snapshots, and missing quantities must be observable through logs and metrics.

The system must not treat missing information as zero-cost execution.

---

## 10. Market Data Staleness and Simulated Latency

These are separate concepts and must be recorded independently.

### 10.1 Market Data Staleness

Market-data staleness describes how old the available market observation is when the system makes a decision.

The system should calculate data age using suitable timestamps and documented clock assumptions.

The selected data-age definition must remain consistent across experiments.

### 10.2 Simulated Decision or Execution Latency

Simulated latency represents an assumed delay between observing data, making a decision, and hypothetically executing the trade.

Possible experimental settings include:

- 0 ms.
- 50 ms.
- 100 ms.
- 250 ms.
- 500 ms.

These are experimental parameters, not claims about the actual latency of any exchange.

The configured delay should be applied consistently in the replay or simulation pipeline. When suitable time-series or order-book updates exist, the simulation should use later observations to estimate whether the opportunity would still be executable after the delay.

If the data resolution is insufficient to reconstruct the effect, the result must be reported as an assumption-based approximation.

### 10.3 Latency Cost Approximation

A simplified basis-point cost may be used for an initial baseline:

```python
latency_cost = reference_cost * latency_bps / 10_000
```

This is a modeled cost approximation. It is not a direct measurement of network latency or a reliable substitute for replaying subsequent market prices.

The formula, reference amount, and assumed basis points must be documented in experiment configuration.

---

## 11. Arbitrage Detection and Spread Definitions

### 11.1 Cross-Exchange Candidate

For a given trading pair:

- Buy at the exchange with the lower executable ask price.
- Sell at another exchange with the higher executable bid price.

At the top of the order book, the gross price difference per unit is:

```text
gross_spread_per_unit = sell_best_bid - buy_best_ask
```

For a chosen quantity:

```text
gross_spread = quantity * (
    sell_best_bid - buy_best_ask
)
```

The gross spread can be negative.

A negative spread means that the selected buy and sell prices are economically unfavorable under the current observations. It does not automatically mean that the data or calculation is invalid.

### 11.2 Executable Quantity

The target quantity must be compatible with:

- The configured notional amount.
- The buy-side available quantity.
- The sell-side available quantity.
- The selected order-book depth.
- Exchange quantity limits and precision, when modeled.

If the book does not contain enough depth for the requested quantity, the candidate must be skipped or marked as insufficient-depth. The engine must not assume that unavailable liquidity can be executed at the last visible price.

### 11.3 Order-Book Cost Estimation

The engine should estimate buy cost and sell proceeds by walking the available order-book levels for the target quantity.

```text
buy_cost = cost of consuming the required ask-side quantity
sell_proceeds = proceeds from consuming the required bid-side quantity
```

If the available depth is insufficient, the calculation must not invent additional levels.

### 11.4 Estimated Fees

```text
estimated_fees =
    buy_cost * buy_exchange_fee_rate
    + sell_proceeds * sell_exchange_fee_rate
```

Fee rates must be configurable per exchange and documented. The rates are assumptions unless verified for the relevant account and market.

### 11.5 Estimated Slippage

For the same quantity:

```text
top_of_book_buy_cost =
    quantity * buy_best_ask

top_of_book_sell_proceeds =
    quantity * sell_best_bid

estimated_slippage =
    (buy_cost - top_of_book_buy_cost)
    + (top_of_book_sell_proceeds - sell_proceeds)
```

The result estimates the difference between top-of-book execution and consuming the available book depth. It does not capture all possible real-world execution effects.

### 11.6 Estimated Net Profit

A basic model is:

```text
estimated_net_profit =
    sell_proceeds
    - buy_cost
    - estimated_fees
    - estimated_latency_cost
    - other_explicitly_modeled_costs
```

Every cost must be defined once and applied consistently. Do not subtract slippage twice if the buy cost and sell proceeds already include order-book walking.

If the project adds transfer fees, inventory rebalancing, funding, or other costs, each must be introduced as an explicit model component with documented assumptions.

### 11.7 Candidate Versus Profitable Opportunity

The engine should distinguish:

- **Candidate:** A cross-exchange price comparison that meets basic data and quantity requirements.
- **Gross-positive candidate:** A candidate with a positive gross spread.
- **Net-profitable candidate:** A candidate with positive estimated net profit under the configured assumptions.
- **Rejected candidate:** A candidate excluded because of invalid data, insufficient depth, staleness rules, or other documented eligibility criteria.

The system should preserve valid unprofitable candidates for analysis and ML training.

### 11.8 Negative Spread Validation

The data model must not reject a candidate solely because `spread` or `spread_percent` is negative.

For example:

```text
buy_best_ask = 100.00
sell_best_bid = 99.50
```

The resulting gross spread is negative and represents an unprofitable candidate.

The model should validate data types, finite values, valid prices, and calculation integrity. Economic profitability should be evaluated separately.

The existing validation rule that raises an error whenever `spread < 0` or `spread_percent < 0` must be revised.

Tests must confirm that a negative spread can be stored and evaluated without an invalid-spread exception.

---

## 12. Storage Architecture

### 12.1 InfluxDB

Primary purpose: time-series market data.

Potential data:

- Normalized market observations.
- Best bid and ask updates.
- Selected order-book measurements.
- Data-quality and collection metrics, if suitable.

High-frequency data retention must be designed according to measured storage growth.

### 12.2 PostgreSQL

Primary purpose: structured application and research records.

Potential tables or entities:

- Exchanges and trading pairs.
- Candidate opportunities.
- Candidate features.
- ML predictions.
- Simulated trades.
- Virtual portfolio snapshots.
- Backtest runs.
- Performance metrics.
- Model versions.
- Experiment configurations.
- Experiment results.

The schema should support reproducibility and traceability between data, model versions, and simulation results.

### 12.3 Redis

Primary purpose: low-latency access to frequently updated values.

Potential uses:

- Latest market prices.
- Latest validated order-book snapshots.
- Short-lived application cache.
- Temporary coordination state where required.

Redis must not be treated as the sole permanent store of historical market data or experiment results.

---

## 13. Dataset Design and Target Definition

The dataset and target definition must be established before final ML training.

### 13.1 Unit of Observation

Each dataset row should represent a candidate opportunity evaluated at a defined decision time.

The record should identify:

- The candidate timestamp.
- Buy exchange.
- Sell exchange.
- Trading pair.
- Observed market-data state.
- Market-data age.
- Configured execution delay.
- Estimated costs.
- Candidate eligibility.
- Eventual simulated outcome, where available.

The exact unit of observation must be documented and applied consistently.

### 13.2 Candidate Labels

An initial binary target may be defined as:

```text
1 = simulated net profit is positive after the
    configured execution assumptions and costs

0 = simulated net profit is zero or negative
    under those assumptions
```

This definition must be tied to a specific simulated execution policy and evaluation horizon.

If the simulation cannot reliably estimate the future outcome because of insufficient data resolution, the label must be described as an approximation.

Do not label candidates as profitable based only on the initial observed spread if the intended target is post-cost profitability after a delay.

### 13.3 Feature Candidates

Potential features include:

- Gross spread.
- Gross spread percentage.
- Best bid and ask prices.
- Bid and ask quantities.
- Estimated order-book execution cost.
- Estimated fees.
- Estimated slippage.
- Market-data age.
- Difference in event timestamps across exchanges.
- Configured simulation latency.
- Order-book depth and imbalance, where available.
- Short-term price changes computed only from data available at decision time.
- Exchange and symbol identifiers, encoded appropriately.

Features must be selected based on data availability, the research question, and the chosen model.

### 13.4 Avoiding Data Leakage

Features must contain only information that would have been available at the decision time.

The future simulated result may determine the target label, but it must not be included as an input feature.

The following must be avoided:

- Using future prices as current features.
- Calculating features with future observations.
- Using the final simulated P&L as a model input.
- Randomly mixing temporally adjacent records across training and test sets without considering leakage.
- Selecting a model based on the final test set.

Dataset construction must be tested for temporal correctness.

---

## 14. Rule-Based Baselines

The ML model must be compared against understandable non-ML approaches.

### Baseline A: Gross-Spread Rule

Select candidates based on gross spread alone.

This is a deliberately simple baseline and may select opportunities that are unprofitable after costs.

### Baseline B: Fee-Aware Rule

Select candidates based on estimated gross profit after transaction fees.

### Baseline C: Cost-Aware Rule

Select candidates using the configured model for:

- Transaction fees.
- Order-book depth and slippage.
- Data staleness.
- Simulated execution latency.
- Other explicitly modeled costs.

### Baseline D: ML-Filtered Rule

Apply the ML model to eligible candidates and select candidates according to a threshold chosen using training and validation data.

All baselines must use the same underlying candidate data and comparable execution assumptions.

The ML filter should not receive an unfair advantage from different data, different fees, or a more favorable simulation policy.

---

## 15. Machine Learning Models

The initial model candidates are:

- Logistic Regression.
- Random Forest.
- Gradient Boosting.

A simple baseline model should be implemented before more complex models are considered.

The final model must be selected based on validation performance and the project's research objectives, not on model complexity.

### 15.1 Logistic Regression

Purpose:

- Establish a simple and interpretable classification baseline.
- Evaluate whether basic features contain useful predictive information.

### 15.2 Random Forest

Purpose:

- Capture nonlinear relationships between market features and simulated profitability.
- Compare against the simpler baseline.

### 15.3 Gradient Boosting

Purpose:

- Evaluate whether boosted decision trees improve predictive and practical performance.

The implementation may use an appropriate maintained Python ML library.

The project must document:

- Model configuration.
- Feature set.
- Target definition.
- Training period.
- Validation period.
- Test period.
- Model version.
- Random seeds where applicable.
- Evaluation metrics.

---

## 16. Training, Validation, and Testing

Financial time-series data must be split chronologically.

### Required Approach

1. Training period: earlier observations.
2. Validation period: later observations used for model and threshold selection.
3. Test period: a still later period reserved for final evaluation.

A walk-forward evaluation may be added to test whether the findings remain stable across different market periods.

Random train/test splitting must not be the only evaluation method.

Where overlapping opportunities or outcome horizons create dependencies, the split strategy must prevent future information from leaking into training.

The test set must not be repeatedly used to tune the model or its selection threshold.

---

## 17. Simulation and Backtesting

The simulation engine will evaluate candidate opportunities without executing real exchange orders.

### 17.1 Simulation Responsibilities

- Replay market data in chronological order.
- Evaluate candidates using a specified policy.
- Apply documented transaction fees.
- Apply order-book depth and slippage calculations.
- Apply configured staleness and latency assumptions.
- Record candidate decisions.
- Simulate eligible trades.
- Track virtual balances and positions.
- Calculate net simulated P&L.
- Export reproducible experiment results.

### 17.2 Virtual Portfolio

The virtual portfolio should track:

- Starting virtual balance.
- Simulated cash balances.
- Simulated positions, if modeled.
- Simulated buys and sells.
- Transaction costs.
- Net P&L.
- Equity curve.
- Drawdown, where meaningful.

The simulation must define whether inventory is assumed to be available on both exchanges. If it assumes pre-positioned assets and quote currency on both exchanges, that assumption must be explicit.

Cross-exchange arbitrage may require inventory on both exchanges. The project must not imply that buying on one exchange and selling on another is operationally equivalent to an atomic transaction.

### 17.3 Execution Assumptions

The backtester must document:

- Whether both legs are assumed to execute.
- How the target quantity is chosen.
- How insufficient depth is handled.
- How latency affects the decision or execution price.
- Whether partial fills are modeled.
- How fees are applied.
- How inventory constraints are handled.
- What happens when market data is missing or stale.

Any execution behavior that is not modeled must be listed as a limitation.

---

## 18. Research Experiments

Experiments should answer the research question rather than simply demonstrate that the code runs.

### Experiment 1: Gross Spread Versus Net Profit

Compare gross spread with simulated net profit after fees and other configured costs.

Goal:

- Quantify how many gross-positive candidates become unprofitable after costs.

### Experiment 2: Market-Data Staleness

Evaluate candidate outcomes under different data-age limits or staleness scenarios.

Goal:

- Determine how data freshness affects candidate eligibility and net simulated profitability.

The tested limits must be selected based on observed data and documented experimental design, not presented as universal thresholds.

### Experiment 3: Simulated Execution Latency

Compare scenarios such as 0, 50, 100, 250, and 500 ms where the available data supports the experiment.

Goal:

- Measure how assumed execution delay affects opportunity survival and simulated net profit.

These values are simulation settings, not measured exchange latency benchmarks.

### Experiment 4: Rule-Based Versus ML Filtering

Compare:

- Gross-spread baseline.
- Fee-aware baseline.
- Cost-aware baseline.
- ML-filtered baseline.

Goal:

- Determine whether ML improves candidate selection or practical simulated performance under comparable assumptions.

### Experiment 5: Feature Ablation

Where sufficient data exists, compare the ML model with and without selected feature groups, such as:

- Market-data age.
- Order-book depth and slippage features.
- Short-term market movement features.

Goal:

- Investigate whether these feature groups add useful predictive information.

### Experiment 6: Cross-Period Evaluation

Evaluate the selected method on separate chronological periods or through walk-forward testing.

Goal:

- Determine whether the results remain reasonably stable outside the period used for model selection.

Do not claim generalization based on one favorable test period.

---

## 19. Evaluation Metrics

### 19.1 Classification Metrics

Use appropriate metrics for the profitability target:

- Precision.
- Recall.
- F1-score.
- Confusion matrix.
- PR-AUC, especially when classes are imbalanced.
- ROC-AUC where appropriate.

Accuracy alone is insufficient because profitable candidates may be relatively rare.

### 19.2 Simulation Metrics

Report:

- Total net simulated P&L.
- Average net profit per selected candidate or simulated trade.
- Number of candidates observed.
- Number of candidates selected.
- Number of simulated trades.
- Percentage of selected candidates that were profitable.
- Gross profit compared with net profit.
- Total estimated transaction fees.
- Total estimated slippage.
- Modeled latency cost.
- Maximum drawdown, where the portfolio simulation makes this meaningful.
- Missed profitable candidates, under the chosen target definition.

### 19.3 Data Quality Metrics

Report:

- Total market-data messages.
- Missing or invalid records.
- Data gaps.
- Reconnection events.
- Stale observations.
- Timestamp anomalies.
- Storage consumption.
- Collector availability.

### 19.4 Reporting Requirements

Every experiment report must include:

- Dataset period.
- Data source and resolution.
- Model or baseline version.
- Feature set.
- Target definition.
- Fees and simulation assumptions.
- Latency and staleness settings.
- Evaluation metrics.
- Known limitations.

Results must be reproducible from saved configuration and version information.

---

## 20. API Design

The FastAPI service will expose endpoints for system health, market data, candidate opportunities, ML predictions, simulation, and backtesting.

Initial endpoint plan:

```text
GET  /health
GET  /markets
GET  /prices
GET  /opportunities
GET  /predictions
GET  /trades
GET  /portfolio
GET  /performance
POST /backtest
GET  /backtest/{run_id}
```

Endpoint methods and request/response schemas may be refined during implementation.

The API must:

- Validate incoming parameters.
- Return consistent response structures.
- Handle missing records and service failures.
- Avoid exposing secrets.
- Distinguish unavailable data from empty results.
- Return sufficient metadata to identify the model or backtest run where relevant.

Long-running backtests may require background execution rather than blocking an API request.

---

## 21. Dashboard and Monitoring

Grafana will be used for visualization where appropriate.

### Market Monitoring

- Latest bid and ask prices.
- Exchange comparison.
- Data age.
- Data-collection status.
- Connection and reconnection events.

### Arbitrage Monitoring

- Candidate count.
- Gross spread.
- Estimated net profit.
- Fees and slippage.
- Candidate eligibility.
- Staleness and latency settings.

### ML Monitoring

- Prediction counts.
- Predicted profitability distribution.
- Model version.
- Classification metrics from completed evaluations.
- Comparison with rule-based baselines.

### Simulation Monitoring

- Virtual portfolio value.
- Net simulated P&L.
- Simulated trade count.
- Equity curve.
- Drawdown where applicable.
- Backtest run summaries.

Dashboards must clearly label simulated values and must not present them as real trading performance.

---

## 22. Docker and Containerization

The project will use Docker and Docker Compose for local development and integration.

Planned services:

```text
api
data-collector
arbitrage-engine
ml-service
simulation
postgres
influxdb
redis
dashboard
```

Service boundaries may be combined or split during development when justified. Avoid introducing unnecessary distributed-system complexity before the core workflow is reliable.

### Docker Requirements

- Use a consistent Python version.
- Use dependency files with controlled versions.
- Use environment variables for configuration.
- Include health checks where appropriate.
- Configure restart behavior deliberately.
- Use persistent volumes for required data.
- Keep secrets out of source control.
- Use service names rather than hard-coded container IP addresses.
- Add logs that identify the relevant service and operation.
- Ensure that the application can start and stop safely.

### Local Development Goal

The entire platform should eventually be runnable using a documented Docker Compose workflow.

Individual services may be developed and tested independently before full integration.

---

## 23. Security Requirements

Security must be considered throughout development.

### Credentials and Secrets

- Do not commit API keys, passwords, tokens, or cloud credentials.
- Provide `.env.example` with placeholder values only.
- Use environment variables or a suitable secrets manager.
- Do not request exchange trading permissions.
- Public market-data collection should use unauthenticated endpoints wherever possible.

### Application Security

- Validate all external input.
- Use least-privilege permissions.
- Restrict database access.
- Avoid exposing internal services publicly without a clear need.
- Keep dependencies maintained.
- Record errors without logging secrets.
- Use non-root containers where practical.
- Separate development and production configuration.

### AWS Security

- Use IAM least privilege.
- Keep databases private.
- Restrict security-group ingress.
- Store secrets securely.
- Enable appropriate monitoring and billing alerts.
- Review public exposure before deployment.

---

## 24. Testing Strategy

Testing must cover calculation correctness, data quality, service behavior, and research validity.

### 24.1 Unit Tests

Test:

- Market-data validation.
- Symbol normalization.
- Timestamp parsing.
- Spread calculation.
- Fee calculation.
- Order-book walking.
- Slippage estimation.
- Net profit calculation.
- Candidate eligibility.
- ML feature construction.
- Target-label construction.

### 24.2 Required Spread and Profit Tests

At minimum, include the following cases:

**Case A: Negative spread is valid**

```text
buy_best_ask = 100.00
sell_best_bid = 99.50
```

Expected result:

- Gross spread is negative.
- Candidate can be represented as unprofitable.
- No exception is raised solely because the spread is negative.

**Case B: Positive gross spread but negative net profit**

```text
gross_spread > 0
estimated_fees + other_costs > gross_spread
```

Expected result:

- Gross spread remains positive.
- Net profit is negative.
- Candidate is not labeled as net-profitable under the defined target.

**Case C: Insufficient order-book depth**

Expected result:

- Candidate is skipped or marked as insufficient-depth.
- The engine does not invent unavailable liquidity.

**Case D: Invalid market data**

Expected result:

- Invalid prices, malformed records, and invalid timestamps are rejected or flagged according to the documented validation policy.

**Case E: Stale market data**

Expected result:

- Staleness is calculated according to the chosen definition.
- The configured eligibility policy is applied consistently.

**Case F: Missing exchange data**

Expected result:

- The engine does not fabricate a missing order book.
- The missing data is observable through logs or metrics.

**Case G: Positive net profit**

Expected result:

- Fees, slippage, and configured costs are applied exactly once.
- The net profit matches an independently calculated expected result.

### 24.3 Integration Tests

Test:

- Collector to storage.
- Storage to arbitrage engine.
- Candidate generation to database.
- Feature generation to ML inference.
- ML predictions to simulation.
- API to database.
- Dashboard data retrieval.
- Docker Compose startup and health checks.

### 24.4 Backtesting Tests

Verify:

- Chronological replay.
- No future information in features.
- Correct label construction.
- Correct fee and cost handling.
- Reproducibility with the same configuration.
- Consistent comparison between baselines.
- Appropriate handling of missing data.

---

## 25. Logging and Observability

Use structured logging where practical.

Logs should include:

- Timestamp.
- Service name.
- Severity.
- Operation or event type.
- Exchange and symbol when relevant.
- Error details.
- Backtest or experiment identifier where relevant.

Important events include:

- WebSocket connection and disconnection.
- Reconnection attempts.
- Invalid or stale data.
- Order-book gaps.
- Candidate generation.
- Insufficient depth.
- Simulation completion.
- Model loading and prediction failures.
- Database errors.
- API failures.

Do not log secrets or unnecessarily sensitive configuration.

Monitoring must help distinguish a market-data problem from a calculation, storage, or ML problem.

---

## 26. Configuration Management

Use configuration files and environment variables for settings that may change between experiments.

Potential configuration fields:

```text
EXCHANGES
TRADING_PAIRS
INITIAL_NOTIONAL
EXCHANGE_FEE_RATES
MAX_MARKET_DATA_AGE
SIMULATED_LATENCY_MS
LATENCY_COST_BPS
MIN_NET_PROFIT
ORDER_BOOK_DEPTH
DATA_RETENTION_POLICY
DATABASE_URL
INFLUXDB_URL
REDIS_URL
MODEL_PATH
```

These are illustrative configuration names. The final configuration must match the implementation.

Experimental parameters must be saved with each backtest or experiment run.

Avoid hard-coding fee rates, thresholds, and simulation assumptions throughout the codebase.

---

## 27. Suggested Repository Structure

The repository may follow this structure, adapting to the existing project where necessary:

```text
crypto-arbitrage-platform/
|
|-- app/
|   |-- api/
|   |-- collector/
|   |-- arbitrage/
|   |-- ml/
|   |-- simulation/
|   |-- storage/
|   |-- common/
|   |-- config/
|   |-- main.py
|
|-- tests/
|   |-- unit/
|   |-- integration/
|   |-- backtesting/
|
|-- data/
|   |-- raw/
|   |-- processed/
|   |-- samples/
|
|-- models/
|
|-- experiments/
|   |-- configs/
|   |-- results/
|
|-- dashboard/
|
|-- scripts/
|
|-- docs/
|
|-- Dockerfile
|-- docker-compose.yml
|-- requirements.txt
|-- .env.example
|-- .gitignore
|-- README.md
|-- PROJECT_PLAN.md
|-- AI_WORKFLOW.md
```

This is a target structure, not a requirement to restructure existing code unnecessarily. Preserve working modules and existing interfaces unless a specific change is needed and justified.

Large raw datasets and generated model files should not automatically be committed to Git. Use appropriate sample data, external storage, or documented data-generation steps.

---

## 28. AI-Assisted Development Workflow

AI tools may be used to assist with coding, debugging, testing, documentation, and reviewing architecture.

AI-generated code must not be accepted without understanding and testing it.

### Required Workflow

1. Inspect the current repository and relevant files.
2. Read the project plan and existing interfaces.
3. Identify the specific problem or task.
4. Explain the proposed change before making broad modifications.
5. Make the smallest coherent change.
6. Add or update tests.
7. Run the relevant tests and checks.
8. Review the diff for unintended changes.
9. Update documentation when behavior or interfaces change.
10. Commit a working and understandable state.

### AI Development Rules

- Do not rewrite the project architecture without explicit justification.
- Do not replace existing working implementations merely for stylistic reasons.
- Do not invent functions, files, schemas, or dependencies without checking the repository.
- Do not claim that tests passed unless they were actually executed.
- Do not hide failing tests or silently weaken validation.
- Do not introduce real-trading functionality.
- Do not place credentials in source code.
- Do not label an opportunity profitable solely because its gross spread is positive.
- Do not reject negative spreads as invalid solely because they are negative.
- Do not use future data as an ML feature.
- Explain unfamiliar concepts and important implementation decisions.
- Keep each task small enough to review and test.
- If a change conflicts with the plan, explain the conflict before proceeding.

The separate `AI_WORKFLOW.md` file should contain the detailed instructions intended to be used repeatedly with coding assistants.

---

## 29. Development Phases

Development will proceed incrementally. The order below defines the main dependencies, while allowing small independent tasks to proceed in parallel.

### Phase 0 — Repository and Development Standards

Tasks:

- [ ] Confirm the repository structure.
- [ ] Configure the Python environment.
- [ ] Add or review `.gitignore`.
- [ ] Add `.env.example`.
- [ ] Establish dependency management.
- [ ] Establish logging and configuration conventions.
- [ ] Add an initial README.
- [ ] Review the existing code before restructuring.

**Completion criteria:** The project can be set up locally using documented instructions, and secrets and generated data are excluded from version control.

### Phase 1 — Market Data Contract and Collector Pilot

Tasks:

- [ ] Define the normalized market-data schema.
- [ ] Verify public REST and WebSocket interfaces.
- [ ] Implement the BTC/USDT collector.
- [ ] Capture bid/ask prices and quantities.
- [ ] Record exchange event and local receive timestamps.
- [ ] Add reconnect and error handling.
- [ ] Validate incoming data.
- [x] Run a short controlled BTC/USDT pilot; schedule the 3–7 day production run.
- [x] Measure message frequency, gaps, storage, and data quality for the short pilot.
- [ ] Document available historical data sources and limitations.

The short pilot results and its limitations are documented in `docs/btc_usdt_pilot_report.md`. The 3–7 day production run remains required before expanding the collection workload.

**Completion criteria:** The collector produces validated records, and the pilot provides sufficient evidence to choose the next collection and retention settings.

### Phase 2 — Storage and Data Quality

Tasks:

- [ ] Set up InfluxDB for appropriate time-series data.
- [ ] Set up PostgreSQL for structured research and application records.
- [ ] Set up Redis for latest values and caching where needed.
- [ ] Persist normalized market data.
- [ ] Define retention and cleanup policies.
- [ ] Add data-quality metrics.
- [ ] Test restart and recovery behavior.
- [ ] Verify timestamp consistency.

**Completion criteria:** Market observations can be stored and retrieved consistently, with documented data-quality behavior.

### Phase 3 — Arbitrage Engine and Financial Calculations

Tasks:

- [ ] Implement cross-exchange candidate detection.
- [ ] Implement order-book walking.
- [ ] Implement gross spread calculations.
- [ ] Implement configurable transaction fees.
- [ ] Implement slippage estimation.
- [ ] Implement the documented latency-cost approximation.
- [ ] Calculate estimated net profit.
- [ ] Distinguish candidates from net-profitable candidates.
- [ ] Permit valid negative spread values.
- [ ] Add tests for negative spread, positive gross but negative net profit, and insufficient depth.

**Completion criteria:** Candidate and cost calculations pass unit tests and use consistent definitions.

### Phase 4 — Dataset Generation and Target Definition

Tasks:

- [ ] Define the unit of observation.
- [ ] Define the simulated outcome horizon and execution assumptions.
- [ ] Define the binary target label.
- [ ] Build the initial feature pipeline.
- [ ] Include both profitable and unprofitable candidates.
- [ ] Include non-opportunity periods where useful.
- [ ] Validate timestamp ordering.
- [ ] Check for future-data leakage.
- [ ] Create reproducible dataset-generation scripts.
- [ ] Document dataset coverage and limitations.

**Completion criteria:** A reproducible dataset can be generated, and its features and labels have clear, testable definitions.

### Phase 5 — Rule-Based Baselines

Tasks:

- [ ] Implement the gross-spread baseline.
- [ ] Implement the fee-aware baseline.
- [ ] Implement the cost-aware baseline.
- [ ] Define common candidate and execution assumptions.
- [ ] Generate baseline evaluation reports.
- [ ] Verify that all methods use comparable data.

**Completion criteria:** The project can evaluate candidates without ML and produce a reproducible baseline report.

### Phase 6 — Simulation and Backtesting Engine

Tasks:

- [ ] Implement chronological market-data replay.
- [ ] Implement simulated candidate selection.
- [ ] Apply fees and documented cost assumptions.
- [ ] Apply supported latency and staleness scenarios.
- [ ] Implement the virtual portfolio.
- [ ] Calculate net simulated P&L.
- [ ] Record simulated decisions and trades.
- [ ] Save backtest configurations and results.
- [ ] Test chronological correctness and reproducibility.

**Completion criteria:** Rule-based methods can be evaluated through a repeatable simulation pipeline.

### Phase 7 — ML Models and Evaluation

Tasks:

- [ ] Implement Logistic Regression.
- [ ] Implement Random Forest.
- [ ] Implement Gradient Boosting.
- [ ] Define chronological training, validation, and test periods.
- [ ] Tune models using training and validation data only.
- [ ] Evaluate classification metrics.
- [ ] Evaluate simulated performance using the same simulation policy.
- [ ] Compare ML against all rule-based baselines.
- [ ] Save model versions and experiment metadata.
- [ ] Document cases where ML does not improve results.

**Completion criteria:** Model performance and simulated outcomes can be compared fairly with rule-based methods, without data leakage.

### Phase 8 — Research Experiments and Reporting

Tasks:

- [ ] Compare gross spread with net simulated profitability.
- [ ] Run data-staleness experiments.
- [ ] Run supported simulated-latency experiments.
- [ ] Compare rule-based and ML-filtered results.
- [ ] Run feature-ablation experiments where sufficient data exists.
- [ ] Evaluate across chronological periods.
- [ ] Produce tables and plots.
- [ ] Document assumptions, limitations, and results.
- [ ] Complete the literature review before making novelty claims.

**Completion criteria:** Results directly address the research question and can be reproduced from saved configurations.

### Phase 9 — API and Dashboard Integration

Tasks:

- [ ] Implement health and status endpoints.
- [ ] Implement market-data endpoints.
- [ ] Implement opportunity endpoints.
- [ ] Implement prediction endpoints.
- [ ] Implement portfolio and performance endpoints.
- [ ] Add backtest submission and result retrieval.
- [ ] Connect the dashboard to the relevant data sources.
- [ ] Display simulated values clearly.
- [ ] Add integration tests.

**Completion criteria:** The system exposes its results through a documented API and a usable monitoring dashboard.

### Phase 10 — Docker Integration and Hardening

Tasks:

- [ ] Build service containers.
- [ ] Configure Docker Compose.
- [ ] Configure health checks and dependencies.
- [ ] Add persistent storage.
- [ ] Verify service-to-service communication.
- [ ] Verify startup, shutdown, and restart behavior.
- [ ] Run unit and integration tests.
- [ ] Review security and dependency configuration.
- [ ] Document the complete local startup workflow.

**Completion criteria:** The local platform can be started, tested, and operated using documented container workflows.

### Phase 11 — AWS Preparation and Deployment

AWS deployment should happen after the local system works reliably and the expected costs are understood.

Potential services:

- EC2 or ECS for application workloads.
- Application Load Balancer if required.
- VPC and private networking.
- IAM for least-privilege access.
- CloudWatch for logs and monitoring.
- RDS for managed relational storage if justified.
- ElastiCache for managed Redis if justified.
- Appropriate storage for time-series data and historical records.

Tasks:

- [ ] Select a deployment architecture based on actual requirements.
- [ ] Estimate ongoing and variable costs.
- [ ] Configure billing alerts and budgets.
- [ ] Configure IAM and network security.
- [ ] Keep databases private where possible.
- [ ] Store secrets securely.
- [ ] Deploy a minimal environment first.
- [ ] Verify health checks, logs, and recovery behavior.
- [ ] Confirm that resources can be stopped or deleted safely.
- [ ] Document deployment and cleanup procedures.

**Completion criteria:** The application can be deployed to AWS with documented security controls, cost assumptions, and cleanup steps.

AWS managed services are options, not mandatory components. Avoid deploying every service to AWS unless it provides a clear benefit.

---

## 30. Project Milestones

| Milestone | Expected Result |
|---|---|
| M1 | Repository and development standards are ready |
| M2 | BTC/USDT data-collection pilot is validated |
| M3 | Market data is standardized and stored |
| M4 | Arbitrage calculations pass financial tests |
| M5 | Dataset and target definition are reproducible |
| M6 | Rule-based baselines are available |
| M7 | Simulation and backtesting work end to end |
| M8 | ML models are evaluated against the baselines |
| M9 | Research experiments and reports are complete |
| M10 | API and dashboard are integrated |
| M11 | Local Docker deployment is reliable |
| M12 | AWS deployment is prepared and cost-controlled |

The milestones are outcome-based. They should not be considered complete merely because a file or class has been created.

---

## 31. Success Criteria

The project will be considered successful when:

- Market data can be collected and validated consistently.
- Exchange data is represented using a common schema.
- Data staleness and simulated latency are recorded separately.
- Cross-exchange candidates are calculated correctly.
- Negative spreads are represented as valid unprofitable outcomes.
- Fees and slippage are applied consistently.
- Insufficient liquidity is handled without inventing prices or quantities.
- The dataset has a documented target and no known future-data leakage.
- Rule-based baselines and ML models can be compared fairly.
- Backtests are reproducible.
- Results include net simulated performance, not just gross spread or classification accuracy.
- Research assumptions and limitations are documented.
- The services can be tested and run locally using Docker.
- Security and cloud-cost controls are documented before AWS deployment.

ML improvement is not a required outcome. A well-supported finding that ML does not improve on the cost-aware baseline is also a valid research result.

---

## 32. Key Risks and Mitigations

### Data Availability

**Risk:** Historical tick or order-book data may be unavailable, restricted, or too expensive to retain.

**Mitigation:** Verify sources early, run a small pilot, and use a clearly documented combination of historical and live data.

### Data Quality

**Risk:** Missing, stale, or inconsistent order-book updates can create false candidates.

**Mitigation:** Validate data, track gaps, record timestamps, and reject or flag invalid observations.

### Simulation Realism

**Risk:** Simulated trades may overestimate achievable real-world profitability.

**Mitigation:** Document execution assumptions, model costs consistently, and avoid presenting results as real trading performance.

### Data Leakage

**Risk:** Future observations may accidentally enter model features or influence model selection.

**Mitigation:** Use chronological splits, feature-availability checks, and separate test periods.

### Class Imbalance

**Risk:** Profitable candidates may be much less common than unprofitable candidates.

**Mitigation:** Report precision, recall, F1, and PR-AUC where appropriate. Do not rely on accuracy alone.

### Overfitting

**Risk:** Model thresholds or strategy rules may fit one market period.

**Mitigation:** Use chronological validation, a held-out test period, and walk-forward evaluation where practical.

### Cloud Costs

**Risk:** Unnecessary compute, networking, or managed storage may create unexpected charges.

**Mitigation:** Complete local development first, configure billing alerts, choose services carefully, and document resource cleanup.

### Scope Expansion

**Risk:** Adding too many services, models, exchanges, or deployment features can delay a working research pipeline.

**Mitigation:** Follow the development phases, validate BTC/USDT first, and expand only after the current milestone meets its completion criteria.

---

## 33. Documentation Requirements

The repository should include:

- `README.md`: project purpose, setup, architecture, and local run instructions.
- `PROJECT_PLAN.md`: this development and research plan.
- `AI_WORKFLOW.md`: rules for AI-assisted development.
- `.env.example`: configuration placeholders without secrets.
- Architecture documentation: service responsibilities and data flow.
- Data documentation: schema, sources, timestamps, and retention.
- Experiment documentation: target definitions, model configurations, and evaluation assumptions.
- Deployment documentation: local Docker and eventual AWS deployment.
- Results documentation: reproducible experiment outputs and limitations.

Documentation must be updated when an implementation change alters behavior, configuration, interfaces, or research assumptions.

---

## 34. Definition of Done

A task is complete only when:

1. The implementation meets the task's stated requirements.
2. Relevant tests have been added or updated.
3. Relevant tests have actually been run.
4. The result has been reviewed for unintended changes.
5. Configuration and security implications have been checked.
6. Documentation has been updated when necessary.
7. Remaining limitations are explicitly recorded.

A task must not be marked complete merely because AI-generated code looks correct or compiles.

---

## 35. Final Development Principles

The project must follow these principles throughout development:

1. Simulation only; no real-money trading.
2. Correct data and financial calculations take priority over model complexity.
3. Negative spread is a valid economic outcome, not automatically invalid data.
4. Market-data staleness and simulated execution latency are separate variables.
5. Gross spread and net profitability must not be confused.
6. ML must be evaluated against fair, reproducible rule-based baselines.
7. Future information must not leak into model features.
8. Experimental assumptions must be documented.
9. Local functionality and testing come before AWS deployment.
10. AI-assisted changes must be reviewed and tested.
11. The architecture should remain modular without adding unnecessary complexity.
12. Results must be reported honestly, including negative or inconclusive findings.

The ultimate goal is to build a reliable, reproducible, containerized research platform that evaluates cross-exchange cryptocurrency arbitrage candidates under clearly defined market-data, cost, and execution assumptions.
