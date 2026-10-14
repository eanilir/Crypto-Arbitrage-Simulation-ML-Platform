"""Limited, assumption-based analysis of cross-exchange price gaps from 1-minute candles.

    python experiments/historical_klines_analysis.py \
        --klines data/raw/historical/klines_1m --calibration data/raw/real_sample \
        --output experiments/results/historical_klines

WHAT THIS IS NOT: candles carry no bid/ask and no depth, so executable spreads, slippage and
sub-minute latency cannot be reproduced (project_plan.md §8.5). The close of a candle is the last
trade price, which sits on either side of the spread (bid/ask bounce). Costs that candles cannot
show are *assumed*, calibrated from a short recorded order-book sample, and the result is reported
as a sensitivity table, not as achievable profit.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.domain.orderbook import walk_levels  # noqa: E402
from shared.historical import MINUTE_MS, read_csv  # noqa: E402
from shared.market_data import load_ticks  # noqa: E402

FEE_BPS_GRID = [0.0, 1.0, 2.5, 5.0, 7.5, 10.0]  # per side, in basis points
NOTIONAL = 10_000.0


def load_aligned(klines_dir: Path, exchanges: list[str]) -> pd.DataFrame:
    """Minutes present on ALL exchanges (inner join); missing minutes are not filled."""
    frames = []
    for exchange in exchanges:
        path = next(klines_dir.glob(f"{exchange}_*_1m.csv"))
        candles = read_csv(path)
        frames.append(
            pd.DataFrame(
                {
                    "open_time_ms": [c.open_time_ms for c in candles],
                    exchange: [c.close for c in candles],
                }
            ).set_index("open_time_ms")
        )
    return pd.concat(frames, axis=1, join="inner").sort_index()


def calibrate_execution_costs(calibration_dir: Path, exchanges: list[str]) -> dict:
    """One-side execution cost versus mid, in bps, from recorded order books at NOTIONAL."""
    buy: dict[str, list[float]] = {ex: [] for ex in exchanges}
    sell: dict[str, list[float]] = {ex: [] for ex in exchanges}
    half_spread: dict[str, list[float]] = {ex: [] for ex in exchanges}
    for tick in load_ticks(calibration_dir):
        for exchange, book in tick.books.items():
            if exchange not in buy or not book.is_valid():
                continue
            mid = (book.bids[0][0] + book.asks[0][0]) / 2
            quantity = NOTIONAL / mid
            cost = walk_levels(book.asks, quantity)
            proceeds = walk_levels(book.bids, quantity)
            if cost is None or proceeds is None:
                continue
            buy[exchange].append((cost / quantity / mid - 1) * 1e4)
            sell[exchange].append((1 - proceeds / quantity / mid) * 1e4)
            half_spread[exchange].append((book.asks[0][0] - book.bids[0][0]) / 2 / mid * 1e4)
    return {
        ex: {
            "buy_cost_bps": statistics.median(buy[ex]) if buy[ex] else None,
            "sell_cost_bps": statistics.median(sell[ex]) if sell[ex] else None,
            "half_spread_bps": statistics.median(half_spread[ex]) if half_spread[ex] else None,
            "samples": len(buy[ex]),
        }
        for ex in exchanges
    }


def pair_gross_bps(aligned: pd.DataFrame) -> pd.DataFrame:
    """Gross gap in bps for every ordered (buy, sell) pair: sell close / buy close - 1."""
    out = {}
    for buy, sell in permutations(aligned.columns, 2):
        out[f"{buy}->{sell}"] = (aligned[sell] / aligned[buy] - 1) * 1e4
    return pd.DataFrame(out)


def pair_extra_cost(costs: dict, pair: str) -> float:
    buy, sell = pair.split("->")
    return costs[buy]["buy_cost_bps"] + costs[sell]["sell_cost_bps"]


def episodes(mask: pd.Series) -> tuple[int, float]:
    """Count runs of consecutive True minutes and their mean length (minutes)."""
    values = mask.to_numpy().astype(int)
    if values.sum() == 0:
        return 0, 0.0
    starts = np.flatnonzero(np.diff(np.concatenate([[0], values])) == 1)
    return len(starts), float(values.sum() / len(starts))


def scenario_table(gross: pd.DataFrame, costs: dict | None) -> pd.DataFrame:
    rows = []
    for fee_bps in FEE_BPS_GRID:
        for label, use_extra in (("fees only", False), ("fees + calibrated spread/slippage", True)):
            if use_extra and costs is None:
                continue
            net = pd.DataFrame(
                {
                    pair: gross[pair]
                    - 2 * fee_bps
                    - (pair_extra_cost(costs, pair) if use_extra else 0.0)
                    for pair in gross.columns
                }
            )
            best = net.max(axis=1)
            profitable = best > 0
            n_episodes, mean_len = episodes(profitable)
            rows.append(
                {
                    "fee_bps_per_side": fee_bps,
                    "cost_assumption": label,
                    "minutes": len(best),
                    "profitable_minutes": int(profitable.sum()),
                    "pct_profitable": float(profitable.mean() * 100),
                    "episodes": n_episodes,
                    "mean_episode_minutes": mean_len,
                    "mean_net_bps_when_profitable": float(best[profitable].mean())
                    if profitable.any()
                    else None,
                    "upper_bound_pnl_per_10k": float((best[profitable] * NOTIONAL / 1e4).sum()),
                }
            )
    return pd.DataFrame(rows)


def md_table(frame: pd.DataFrame, digits: int = 4) -> str:
    if frame.empty:
        return "_no rows_"
    shown = frame.copy()
    for column in shown.columns:
        if pd.api.types.is_float_dtype(shown[column]):
            shown[column] = shown[column].map(lambda v: "" if pd.isna(v) else f"{v:.{digits}g}")
    head = "| " + " | ".join(map(str, shown.columns)) + " |"
    rule = "|" + "|".join("---" for _ in shown.columns) + "|"
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in shown.itertuples(index=False)]
    return "\n".join([head, rule, *body])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--klines", type=Path, default=Path("data/raw/historical/klines_1m"))
    parser.add_argument("--calibration", type=Path, default=Path("data/raw/real_sample"))
    parser.add_argument(
        "--output", type=Path, default=Path("experiments/results/historical_klines")
    )
    parser.add_argument("--exchanges", nargs="+", default=["binance", "bybit", "okx"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    aligned = load_aligned(args.klines, args.exchanges)
    gross = pair_gross_bps(aligned)
    costs = (
        calibrate_execution_costs(args.calibration, args.exchanges)
        if args.calibration.exists()
        else None
    )
    if costs and any(v["buy_cost_bps"] is None for v in costs.values()):
        costs = None  # calibration sample lacks an exchange; do not guess

    index = pd.to_datetime(aligned.index, unit="ms", utc=True)
    per_pair = pd.DataFrame(
        {
            "pair": gross.columns,
            "median_gross_bps": [gross[c].median() for c in gross.columns],
            "std_bps": [gross[c].std() for c in gross.columns],
            "p01_bps": [gross[c].quantile(0.01) for c in gross.columns],
            "p99_bps": [gross[c].quantile(0.99) for c in gross.columns],
            "max_bps": [gross[c].max() for c in gross.columns],
            "pct_minutes_gross_positive": [(gross[c] > 0).mean() * 100 for c in gross.columns],
        }
    )
    scenarios = scenario_table(gross, costs)
    main_fee = 5.0  # a plausible discounted taker tier; shown next to the 10 bp default for context
    monthly = None
    if costs:
        net = pd.DataFrame(
            {p: gross[p] - 2 * main_fee - pair_extra_cost(costs, p) for p in gross.columns}
        ).max(axis=1)
        monthly = (
            pd.DataFrame({"month": index.strftime("%Y-%m"), "profitable": net.to_numpy() > 0})
            .groupby("month")["profitable"]
            .agg(["sum", "count"])
            .reset_index()
            .rename(columns={"sum": "profitable_minutes", "count": "minutes"})
        )
        monthly["pct_profitable"] = monthly["profitable_minutes"] / monthly["minutes"] * 100

    per_pair.to_csv(args.output / "pair_gap_stats.csv", index=False)
    scenarios.to_csv(args.output / "scenarios.csv", index=False)

    best_gross = gross.max(axis=1)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(best_gross.clip(-30, 30), bins=120)
    axes[0].set_title("Best-pair gross gap per minute (bps, clipped to +/-30)")
    axes[0].set_xlabel("bps")
    for label, group in scenarios.groupby("cost_assumption"):
        axes[1].plot(group["fee_bps_per_side"], group["pct_profitable"], marker="o", label=label)
    axes[1].set_xlabel("taker fee per side (bps)")
    axes[1].set_ylabel("% of minutes with a net-positive pair")
    axes[1].set_title("Sensitivity to costs")
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(args.output / "gaps.png", dpi=120)
    plt.close(fig)

    period = f"{index[0].isoformat()} -> {index[-1].isoformat()}"
    lines = [
        "# 1-minute candle analysis: cross-exchange price gaps",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        "> **Limited, assumption-based simulation.** Candles contain no bid/ask and no depth. The numbers",
        "> below show how large close-to-close gaps between exchanges were, and how sensitive any",
        "> 'profit' is to cost assumptions. They are NOT achievable profit and NOT evidence about",
        "> latency effects (project_plan.md §8.5).",
        "",
        "## Data",
        "",
        f"- Exchanges: {', '.join(args.exchanges)}; 1-minute candles; period {period}",
        f"- Minutes present on all exchanges (inner join, nothing filled): {len(aligned):,}",
        "- Price used: candle close (last trade). It lies on either side of the spread, so gaps include "
        "bid/ask bounce noise.",
        "",
        "## Gap statistics per ordered pair (buy -> sell), in basis points",
        "",
        md_table(per_pair),
        "",
        "A persistent non-zero median gap is a structural offset (for example quote-currency or venue "
        "premium), not by itself an opportunity: exploiting it needs inventory transfers that are not "
        "modeled.",
        "",
        "## Calibrated one-side execution costs (from recorded order books at 10,000 notional)",
        "",
        f"```json\n{json.dumps(costs, indent=2)}\n```"
        if costs
        else "_not available (no calibration sample)_",
        "",
        "## Sensitivity: minutes where the best pair has net gap > 0",
        "",
        "Net gap = gross gap - 2 x fee per side - (assumed spread/slippage). `episodes` merges consecutive "
        "profitable minutes; `upper_bound_pnl_per_10k` counts every profitable minute as a trade at 10,000 "
        "and ignores persistence, inventory, latency and fills, so it is an upper bound.",
        "",
        md_table(scenarios),
        "",
        "![gaps](gaps.png)",
        "",
    ]
    if monthly is not None:
        lines += [
            f"## Month by month (fee {main_fee} bps per side + calibrated costs)",
            "",
            md_table(monthly),
            "",
        ]
    lines += [
        "## Limitations",
        "",
        "- No bid/ask, no depth: spreads and slippage are assumed from a 15-minute sample, not observed "
        "over the period.",
        "- One-minute resolution cannot show how long a gap lasted or whether it survived a delay.",
        "- Fee rates are assumptions; real tiers differ by account.",
        "- Cross-exchange USDT pricing differences are treated as price gaps; transfer, rebalancing and "
        "withdrawal costs are ignored.",
        "- Only BTC/USDT was analysed.",
        "",
    ]
    (args.output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"report written to {args.output / 'report.md'}")


if __name__ == "__main__":
    main()
