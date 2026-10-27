from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

# Make `shared` importable no matter where streamlit is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.arbitrage_engine.app.candidates import (  # noqa: E402
    Candidate,
    CandidateStatus,
    CostModel,
    OrderBook,
    find_candidates,
    rank_by_net_profit,
)
from services.dashboard.auth import require_login  # noqa: E402
from services.dashboard.balance import show_balance_badge  # noqa: E402
from shared.domain.models import MarketQuote  # noqa: E402

EXCHANGES = ["Binance", "Bybit", "Kraken", "Coinbase", "OKX"]
BASE_PRICES = {"BTC/USDT": 65000.0, "ETH/USDT": 3200.0, "SOL/USDT": 150.0}

# Default public spot taker fees (%) of each exchange's entry fee tier.
# Your real fee depends on your account's volume tier / fee-token discounts: edit in the sidebar.
DEFAULT_TAKER_FEE_PCT = {
    "Binance": 0.10,
    "Bybit": 0.10,
    "Kraken": 0.40,
    "Coinbase": 0.60,
    "OKX": 0.10,
}

Level = tuple[float, float]  # (price, base quantity)
Book = tuple[list[Level], list[Level]]  # (bids best-first, asks best-first)


def _levels(rows: list) -> list[Level]:
    return [(float(r[0]), float(r[1])) for r in rows]


def _fetch_book(exchange: str, symbol: str) -> Book:
    base, quote = symbol.split("/")
    if exchange == "Binance":
        r = requests.get(
            "https://api.binance.com/api/v3/depth",
            params={"symbol": base + quote, "limit": 100},
            timeout=5,
        )
        r.raise_for_status()
        d = r.json()
        return _levels(d["bids"]), _levels(d["asks"])
    if exchange == "Bybit":
        r = requests.get(
            "https://api.bybit.com/v5/market/orderbook",
            params={"category": "spot", "symbol": base + quote, "limit": 50},
            timeout=5,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("retCode") != 0:
            raise RuntimeError(body.get("retMsg"))
        d = body["result"]
        return _levels(d["b"]), _levels(d["a"])
    if exchange == "Kraken":
        kraken_base = "XBT" if base == "BTC" else base
        r = requests.get(
            "https://api.kraken.com/0/public/Depth",
            params={"pair": kraken_base + quote, "count": 100},
            timeout=5,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("error"):
            raise RuntimeError(body["error"])
        d = next(iter(body["result"].values()))
        return _levels(d["bids"]), _levels(d["asks"])
    if exchange == "Coinbase":
        r = requests.get(
            f"https://api.exchange.coinbase.com/products/{base}-{quote}/book",
            params={"level": 2},
            timeout=5,
        )
        r.raise_for_status()
        d = r.json()
        return _levels(d["bids"]), _levels(d["asks"])
    if exchange == "OKX":
        r = requests.get(
            "https://www.okx.com/api/v5/market/books",
            params={"instId": f"{base}-{quote}", "sz": 100},
            timeout=5,
        )
        r.raise_for_status()
        d = r.json()["data"][0]
        return _levels(d["bids"]), _levels(d["asks"])
    raise ValueError(exchange)


@st.cache_data(ttl=5, show_spinner="Fetching live order books...")
def fetch_live_books(symbols: tuple[str, ...]) -> tuple[dict[tuple[str, str], Book], list[str]]:
    books, errors = {}, []
    for symbol in symbols:
        for exchange in EXCHANGES:
            try:
                books[(exchange, symbol)] = _fetch_book(exchange, symbol)
            except Exception as exc:  # one failing exchange must not break the page
                errors.append(f"{exchange} {symbol}: {exc}")
    return books, errors


def simulate_books(
    symbols: list[str], seed: int, noise_bps: float
) -> dict[tuple[str, str], Book]:
    rng = np.random.default_rng(seed)
    books = {}
    for symbol in symbols:
        mid = BASE_PRICES[symbol]
        for exchange in EXCHANGES:
            price = mid * (1 + rng.normal(0, noise_bps / 10_000))
            half = price * rng.uniform(0.0001, 0.0004)
            step = price * 0.0001
            qty = 5_000 / price
            bids = [(price - half - i * step, qty * rng.uniform(0.5, 1.5)) for i in range(30)]
            asks = [(price + half + i * step, qty * rng.uniform(0.5, 1.5)) for i in range(30)]
            books[(exchange, symbol)] = (bids, asks)
    return books


def to_quotes(books: dict[tuple[str, str], Book]) -> list[MarketQuote]:
    now = datetime.now(timezone.utc)
    return [
        MarketQuote(ex, sym, now, bid=bids[0][0], ask=asks[0][0])
        for (ex, sym), (bids, asks) in books.items()
        if bids and asks
    ]


def find_opportunities(
    books: dict[tuple[str, str], Book],
    notional: float,
    fees_pct: dict[str, float],
    latency_bps: float,
) -> list[Candidate]:
    """All cross-exchange candidates (incl. unprofitable/rejected), best net profit first."""
    now = datetime.now(timezone.utc)
    order_books = [
        OrderBook(ex, sym, tuple(bids), tuple(asks), received_at=now)
        for (ex, sym), (bids, asks) in books.items()
    ]
    model = CostModel(
        fee_rates={ex: pct / 100 for ex, pct in fees_pct.items()}, latency_bps=latency_bps
    )
    return rank_by_net_profit(find_candidates(order_books, notional, model, decision_time=now))


st.set_page_config(page_title="Crypto Arbitrage Simulation", layout="wide")
require_login()
st.title("Crypto Arbitrage Simulation")

with st.sidebar:
    st.header("Parameters")
    live = st.radio("Data source", ["Live (public APIs)", "Simulated"]).startswith("Live")
    symbols = st.multiselect("Symbols", list(BASE_PRICES), default=list(BASE_PRICES))
    notional = st.number_input("Trade size (USDT)", 100.0, 1_000_000.0, 10_000.0, 500.0)
    virtual_balance = st.number_input("Virtual balance (USDT)", 100.0, 100_000_000.0, 100_000.0, 1_000.0)
    latency_bps = st.slider("Latency cost (bps)", 0.0, 20.0, 1.0, 0.5)
    only_profitable = st.checkbox("Show only profitable routes", value=True)
    with st.expander("Taker fee per exchange (%)", expanded=True):
        fees_pct = {
            ex: st.number_input(ex, 0.0, 1.0, DEFAULT_TAKER_FEE_PCT[ex], 0.01, format="%.3f")
            for ex in EXCHANGES
        }
    if not live:
        noise_bps = st.slider("Cross-exchange price noise (bps)", 1, 50, 12)
        seed = st.number_input("Random seed", value=42, step=1)
        if st.button("New market snapshot"):
            seed = int(np.random.default_rng().integers(0, 1_000_000))

if not symbols:
    st.info("Pick at least one symbol.")
    st.stop()

if live:
    st.caption(
        "Live order books from public exchange APIs. Analysis only, no orders are placed. "
        "Withdrawal/transfer fees are not included."
    )
    books, errors = fetch_live_books(tuple(symbols))
    if errors:
        st.warning("Some books could not be fetched:\n\n" + "\n".join(f"- {e}" for e in errors))
else:
    st.caption("Simulated prices — no real exchange connection.")
    books = simulate_books(symbols, int(seed), noise_bps)

opps = find_opportunities(books, notional, fees_pct, latency_bps)
if not opps:
    st.error("Need order books from at least two exchanges for the same symbol.")
    st.stop()

priced = [o for o in opps if not o.is_rejected]
profitable = [o for o in opps if o.is_net_profitable]
gross_positive = [o for o in opps if o.gross_spread is not None and o.gross_spread > 0]
rejected = [o for o in opps if o.is_rejected]
best_gain = priced[0].net_profit if priced and priced[0].is_net_profitable else 0.0
show_balance_badge(
    virtual_balance + best_gain, best_gain, None,
    "Sanal bakiye (simülasyon). Değişim: bu anda net kârlı en iyi fırsat tek seferlik "
    "uygulansaydı beklenen kazanç. Gerçek para değildir.",
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Candidates scanned", len(opps))
c2.metric("Gross-positive", len(gross_positive))
c3.metric("Net-profitable after costs", len(profitable))
c4.metric("Rejected (depth/data)", len(rejected))
if priced:
    best = priced[0]
    st.metric(
        "Best net profit (simulated)",
        f"{best.net_profit:,.2f} USDT",
        f"{best.symbol}: {best.buy_exchange} → {best.sell_exchange}",
    )

st.subheader("Top of book")
st.dataframe(
    pd.DataFrame(
        [{"symbol": q.symbol, "exchange": q.exchange, "bid": q.bid, "ask": q.ask}
         for q in to_quotes(books)]
    ),
    use_container_width=True,
    hide_index=True,
)

st.subheader(f"Opportunities for {notional:,.0f} USDT (ranked by net profit)")
shown = profitable if only_profitable else opps
if not shown:
    st.info("No profitable routes right now. Untick the filter to see all scanned routes.")
    st.stop()

opp_df = pd.DataFrame([o.to_dict() for o in shown]).drop(columns=["decision_time"])
st.dataframe(opp_df, use_container_width=True, hide_index=True)

priced_df = opp_df.dropna(subset=["net_profit"])
if not priced_df.empty:
    st.subheader("Net profit by route")
    chart_df = priced_df.assign(route=priced_df.buy_exchange + " → " + priced_df.sell_exchange)
    st.bar_chart(chart_df.pivot_table(index="route", columns="symbol", values="net_profit"))
st.caption("All values are simulated analysis, not real trading performance.")
