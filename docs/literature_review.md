# Literature review

**Status: NOT DONE.** The project plan requires a literature review before any claim that the
research question is novel (project_plan.md §3.3, Phase 8). No papers were read or cited for this
repository, and none are listed here on purpose: unverified citations would be worse than none.

Until this review is completed, the project makes **no novelty claim**. It may only claim an
experimental comparison under stated assumptions.

## Research question

How do market-data staleness and simulated execution latency affect the net profitability of
cross-exchange cryptocurrency arbitrage, and can a machine-learning filter improve performance over
a rule-based baseline?

## Protocol to follow

1. Search (Google Scholar, arXiv, SSRN, ACM/IEEE) for: cross-exchange / cross-market cryptocurrency
   arbitrage; price discrepancies and market segmentation across crypto exchanges; latency and
   stale quotes in arbitrage; limit-order-book slippage models; machine learning for trade
   filtering or opportunity classification; backtesting pitfalls (look-ahead, overfitting,
   purged/walk-forward validation for financial time series).
2. Record for each source: authors, year, venue, data (exchanges, period, resolution), costs
   modeled, latency/staleness treatment, ML methods, evaluation protocol, main finding, limitations.
3. Compare their assumptions with those in `docs/experiments.md`: fees, inventory/transfer
   handling, depth walking, latency model, label definition, split strategy.
4. Decide what, if anything, is new here (for example the specific staleness/latency definitions,
   the replayed-execution label, or the fair comparison against rule baselines) and state it
   conservatively.
5. Add the verified references and a short related-work section to the final report.

## Checklist

- [ ] Sources collected and read
- [ ] Comparison table written
- [ ] Contribution statement written
- [ ] Novelty claims reviewed against the table
