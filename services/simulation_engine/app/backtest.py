"""Chronological backtest over a labeled candidate dataset (project_plan.md §17).

Execution assumptions (documented limitations, not facts about real exchanges):
* Inventory is PRE-POSITIONED on every exchange (quote currency and base asset). A trade
  buys base on one exchange and sells base on the other; it is not atomic in reality.
* Both legs are assumed to fill completely at the execution tick's visible depth
  (no partial fills, no queue position). If depth is insufficient the trade is not
  executed and no P&L is booked.
* The execution tick is the first snapshot at least ``latency_ms`` after the decision
  (see ``dataset.py``); a trade that has no usable execution snapshot is not in the data.
* Inventory is never rebalanced and transfer/withdrawal fees are ignored. When an
  exchange runs out of quote currency or base asset the trade is skipped
  (``skipped_inventory``) rather than assumed possible.
* Reported P&L is realized trade P&L. Mark-to-market inventory price risk is excluded.
* At most ``max_trades_per_tick`` trades per tick, and a (buy, sell) pair cannot trade
  again within ``cooldown_ticks`` ticks, so one persistent mispricing is not counted as
  many independent opportunities.

Decisions use only decision-time feature columns; the execution outcome columns are
read only AFTER a trade has been chosen, in chronological order.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from services.arbitrage_engine.app.candidates import CostModel
from services.simulation_engine.app.selectors import Selector


@dataclass(frozen=True)
class BacktestConfig:
    initial_quote_per_exchange: float = 100_000.0
    initial_base_per_exchange: float = 1.5
    max_trades_per_tick: int = 1
    cooldown_ticks: int = 0
    cost_model: CostModel = field(default_factory=CostModel)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["cost_model"] = {
            "fee_rates": dict(self.cost_model.fee_rates),
            "default_fee_rate": self.cost_model.default_fee_rate,
            "latency_bps": self.cost_model.latency_bps,
            "min_net_profit": self.cost_model.min_net_profit,
        }
        return data


@dataclass
class BacktestResult:
    run_id: str
    selector: str
    selector_params: dict[str, Any]
    config: dict[str, Any]
    data_fingerprint: str
    metrics: dict[str, Any]
    decisions: pd.DataFrame
    trades: pd.DataFrame
    equity: pd.DataFrame


def dataset_fingerprint(frame: pd.DataFrame) -> str:
    key = frame[["decision_time", "tick_index", "buy_exchange", "sell_exchange", "label"]]
    digest = hashlib.sha1(pd.util.hash_pandas_object(key, index=False).to_numpy().tobytes())
    return f"{len(frame)}-{digest.hexdigest()[:12]}"


def _max_drawdown(curve: pd.Series) -> float:
    if curve.empty:
        return 0.0
    running_peak = curve.cummax().clip(lower=0.0)
    return float((running_peak - curve).max())


def run_backtest(
    frame: pd.DataFrame, selector: Selector, config: BacktestConfig | None = None
) -> BacktestResult:
    cfg = config or BacktestConfig()
    data = frame.sort_values(["tick_index", "buy_exchange", "sell_exchange"], kind="stable")
    data = data.reset_index(drop=True)
    selected = selector.select(data).fillna(False).astype(bool)
    score = selector.score(data)

    exchanges = sorted(set(data["buy_exchange"]) | set(data["sell_exchange"]))
    quote = {ex: cfg.initial_quote_per_exchange for ex in exchanges}
    base = {ex: cfg.initial_base_per_exchange for ex in exchanges}
    last_trade_tick: dict[tuple[str, str], int] = {}
    decisions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    cumulative = 0.0

    for tick_index, group in data[selected].groupby("tick_index", sort=True):
        ordered = group.assign(score_value=score.loc[group.index]).sort_values(
            "score_value", ascending=False, kind="stable"
        )
        done = 0
        for row in ordered.itertuples():
            pair = (row.buy_exchange, row.sell_exchange)
            outcome = "executed"
            if done >= cfg.max_trades_per_tick:
                outcome = "skipped_tick_limit"
            elif (
                pair in last_trade_tick and tick_index - last_trade_tick[pair] <= cfg.cooldown_ticks
            ):
                outcome = "skipped_cooldown"
            elif row.outcome_status != "executed":
                outcome = "not_executed_" + row.outcome_status.removeprefix("exec_")
            else:
                fee_buy = row.outcome_buy_cost * cfg.cost_model.fee_rate(row.buy_exchange)
                fee_sell = row.outcome_sell_proceeds * cfg.cost_model.fee_rate(row.sell_exchange)
                if (
                    quote[row.buy_exchange] < row.outcome_buy_cost + fee_buy
                    or base[row.sell_exchange] < row.quantity
                ):
                    outcome = "skipped_inventory"
                else:
                    net = row.outcome_sell_proceeds - row.outcome_buy_cost - fee_buy - fee_sell
                    quote[row.buy_exchange] -= row.outcome_buy_cost + fee_buy
                    base[row.buy_exchange] += row.quantity
                    base[row.sell_exchange] -= row.quantity
                    quote[row.sell_exchange] += row.outcome_sell_proceeds - fee_sell
                    cumulative += net
                    done += 1
                    last_trade_tick[pair] = tick_index
                    trades.append(
                        {
                            "tick_index": tick_index,
                            "decision_time": row.decision_time,
                            "outcome_time": row.outcome_time,
                            "symbol": row.symbol,
                            "buy_exchange": row.buy_exchange,
                            "sell_exchange": row.sell_exchange,
                            "quantity": row.quantity,
                            "buy_cost": row.outcome_buy_cost,
                            "sell_proceeds": row.outcome_sell_proceeds,
                            "fees": fee_buy + fee_sell,
                            "net_pnl": net,
                            "cumulative_pnl": cumulative,
                            "score": row.score_value,
                        }
                    )
            decisions.append(
                {
                    "tick_index": tick_index,
                    "decision_time": row.decision_time,
                    "buy_exchange": row.buy_exchange,
                    "sell_exchange": row.sell_exchange,
                    "score": row.score_value,
                    "outcome": outcome,
                }
            )

    trades_df = pd.DataFrame(trades)
    decisions_df = pd.DataFrame(decisions)
    equity = (
        trades_df[["outcome_time", "cumulative_pnl"]].rename(columns={"outcome_time": "time"})
        if not trades_df.empty
        else pd.DataFrame(columns=["time", "cumulative_pnl"])
    )
    counts = decisions_df["outcome"].value_counts().to_dict() if not decisions_df.empty else {}
    n_trades = len(trades_df)
    wins = int((trades_df["net_pnl"] > 0).sum()) if n_trades else 0
    metrics: dict[str, Any] = {
        "candidates": int(len(data)),
        "selected": int(selected.sum()),
        "trades": n_trades,
        "decision_outcomes": counts,
        "total_net_pnl": float(trades_df["net_pnl"].sum()) if n_trades else 0.0,
        "gross_pnl": float((trades_df["sell_proceeds"] - trades_df["buy_cost"]).sum())
        if n_trades
        else 0.0,
        "total_fees": float(trades_df["fees"].sum()) if n_trades else 0.0,
        "avg_net_per_trade": float(trades_df["net_pnl"].mean()) if n_trades else None,
        "pct_profitable_trades": wins / n_trades if n_trades else None,
        "max_drawdown": _max_drawdown(trades_df["cumulative_pnl"]) if n_trades else 0.0,
        "final_quote_balances": quote,
        "final_base_balances": base,
        "assumptions": "pre-positioned inventory; full fills at visible depth; no transfers",
    }
    fingerprint = dataset_fingerprint(data)
    config_dict = cfg.to_dict()
    run_id = hashlib.sha1(
        json.dumps(
            [config_dict, selector.name, selector.params(), fingerprint],
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:12]
    return BacktestResult(
        run_id=run_id,
        selector=selector.name,
        selector_params=selector.params(),
        config=config_dict,
        data_fingerprint=fingerprint,
        metrics=metrics,
        decisions=decisions_df,
        trades=trades_df,
        equity=equity,
    )


def save_backtest(result: BacktestResult, root: Path | str) -> Path:
    """Persist config, metrics and tables so the run can be audited and reproduced."""
    out = Path(root) / result.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(
        json.dumps(
            {
                "run_id": result.run_id,
                "selector": result.selector,
                "selector_params": result.selector_params,
                "config": result.config,
                "data_fingerprint": result.data_fingerprint,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (out / "metrics.json").write_text(
        json.dumps(result.metrics, indent=2, default=str), encoding="utf-8"
    )
    result.trades.to_csv(out / "trades.csv", index=False)
    result.equity.to_csv(out / "equity.csv", index=False)
    result.decisions.to_csv(out / "decisions.csv", index=False)
    return out
