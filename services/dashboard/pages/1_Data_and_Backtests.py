from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Make `shared` and `services` importable no matter where streamlit is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.dashboard.auth import require_login  # noqa: E402
from services.dashboard.balance import show_balance_badge  # noqa: E402
from shared.data_quality import analyze  # noqa: E402

DATA_ROOT = Path(os.getenv("ARBITRAGE_DATA_ROOT", "data/raw"))
BACKTEST_DIR = Path(os.getenv("ARBITRAGE_BACKTEST_DIR", "experiments/results/api_backtests"))
RESULTS_DIR = Path(os.getenv("ARBITRAGE_RESULTS_DIR", "experiments/results"))

st.set_page_config(page_title="Data and backtests", layout="wide")
require_login()
st.title("Data collection health and backtests")
st.warning("All profit figures here are SIMULATED. No orders are placed and no real funds are used.")


@st.cache_data(ttl=30, show_spinner="Auditing recorded data...")
def audit(path: str) -> dict:
    return analyze(path).to_dict()


def data_sources() -> list[str]:
    if not DATA_ROOT.is_dir():
        return []
    return sorted(
        str(p.relative_to(DATA_ROOT))
        for p in DATA_ROOT.iterdir()
        if p.is_dir() and any(p.glob("market_depth_*.ndjson"))
    )


st.header("Market-data collection")
sources = data_sources()
if not sources:
    st.info(f"No recorded data under `{DATA_ROOT}`. Start the recorder: "
            "`python -m services.data_collector.app.depth_recorder --output-dir data/raw/live`")
else:
    source = st.selectbox("Data source", sources)
    report = audit(str(DATA_ROOT / source))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Records", f"{report['total_records']:,}")
    c2.metric("Invalid records", report["invalid_records"])
    availability = report["collector_availability"]
    c3.metric("Collector availability", "n/a" if availability is None else f"{availability:.2%}")
    c4.metric("Stale ticks (>%d ms skew)" % report["stale_threshold_ms"], report["stale_ticks"])
    st.caption(f"Period: {report['period_start']} → {report['period_end']}")
    if report["timestamps_consistent"]:
        st.success("Timestamps are consistent (no ordering or future-event anomalies).")
    else:
        st.error(f"Timestamp anomalies: {report['timestamp_anomalies']}")
    left, right = st.columns(2)
    left.subheader("Records and errors by exchange")
    left.dataframe(
        pd.DataFrame({
            "records": report["records_by_exchange"],
            "fetch_errors": report["fetch_errors_by_exchange"],
        }).fillna(0).astype(int),
        use_container_width=True,
    )
    right.subheader("Gaps and timing")
    right.json({"data_gaps": report["data_gaps"], "tick_spacing_ms": report["tick_spacing_ms"],
                "event_timestamp_missing": report["event_timestamp_missing"]})

st.header("Backtest runs")
runs = (
    sorted((p for p in BACKTEST_DIR.iterdir() if (p / "metrics.json").exists()),
           key=lambda p: p.stat().st_mtime, reverse=True)
    if BACKTEST_DIR.is_dir() else []
)
if not runs:
    st.info("No completed backtests yet. Submit one with `POST /backtest` on the API.")
else:
    run = st.selectbox("Run", runs, format_func=lambda p: p.name)
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    final_quote = metrics["final_quote_balances"]
    start_quote = config["config"]["initial_quote_per_exchange"] * len(final_quote)
    end_quote = sum(final_quote.values())
    final_base = metrics["final_base_balances"]
    start_base = config["config"]["initial_base_per_exchange"] * len(final_base)
    show_balance_badge(
        end_quote, end_quote - start_quote, sum(final_base.values()),
        f"Sanal bakiye (simülasyon). Başlangıç: $ {start_quote:,.2f} ve {start_base:,.4f} BTC, "
        f"{len(final_quote)} borsaya eşit dağıtılmış. Gerçek para değildir.",
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net simulated P&L", f"{metrics['total_net_pnl']:,.2f}")
    m2.metric("Trades", metrics["trades"])
    m3.metric("Max drawdown", f"{metrics['max_drawdown']:,.2f}")
    pct = metrics["pct_profitable_trades"]
    m4.metric("Profitable trades", "n/a" if pct is None else f"{pct:.1%}")
    st.caption(f"Selector: {config['selector']} {config['selector_params']} — {metrics['assumptions']}")
    equity = pd.read_csv(run / "equity.csv") if (run / "equity.csv").stat().st_size > 20 else pd.DataFrame()
    if not equity.empty:
        st.line_chart(equity.reset_index(drop=True)["cumulative_pnl"])
    trades = pd.read_csv(run / "trades.csv") if (run / "trades.csv").stat().st_size > 5 else pd.DataFrame()
    st.dataframe(trades.tail(200), use_container_width=True, hide_index=True)
    st.json(metrics["decision_outcomes"])

st.header("Experiment reports")
reports = sorted(RESULTS_DIR.glob("*/report.md")) if RESULTS_DIR.is_dir() else []
if not reports:
    st.info("No experiment reports yet. Run `python experiments/run_experiments.py`.")
else:
    chosen = st.selectbox("Report", reports, format_func=lambda p: p.parent.name)
    st.markdown((chosen).read_text(encoding="utf-8").replace("![", "\\!["))
    for image in sorted(chosen.parent.glob("*.png")):
        st.image(str(image), caption=image.name)
