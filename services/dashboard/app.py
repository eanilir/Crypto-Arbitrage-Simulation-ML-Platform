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

from shared.domain.models import MarketQuote, SpreadOpportunity  # noqa: E402

EXCHANGES = ["Binance", "Kraken", "Coinbase", "OKX"]
BASE_PRICES = {"BTC/USDT": 65000.0, "ETH/USDT": 3200.0, "SOL/USDT": 150.0}

# Default public spot taker fees (%) of each exchange's entry fee tier.
# Your real fee depends on your account's volume tier / fee-token discounts: edit in the sidebar.
DEFAULT_TAKER_FEE_PCT = {"Binance": 0.10, "Kraken": 0.40, "Coinbase": 0.60, "OKX": 0.10}

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


def walk(levels: list[Level], base_qty: float) -> float | None:
    """Quote-currency value of filling `base_qty` through `levels`; None if too shallow."""
    remaining, value = base_qty, 0.0
    for price, qty in levels:
        take = min(remaining, qty)
        value += take * price
        remaining -= take
        if remaining <= 1e-12:
            return value
    return None


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
) -> list[SpreadOpportunity]:
    found = []
    now = datetime.now(timezone.utc)
    for (buy_ex, symbol), (_, buy_asks) in books.items():
        for (sell_ex, sell_symbol), (sell_bids, _) in books.items():
            if sell_symbol != symbol or sell_ex == buy_ex or not buy_asks or not sell_bids:
                continue
            qty = notional / buy_asks[0][0]
            cost = walk(buy_asks, qty)
            proceeds = walk(sell_bids, qty)
            if cost is None or proceeds is None:
                continue  # order book too shallow for this trade size
            top_cost, top_proceeds = qty * buy_asks[0][0], qty * sell_bids[0][0]
            fees = cost * fees_pct[buy_ex] / 100 + proceeds * fees_pct[sell_ex] / 100
            slippage = (cost - top_cost) + (top_proceeds - proceeds)
            latency = cost * latency_bps / 10_000
            found.append(
                SpreadOpportunity(
                    symbol=symbol,
                    buy_exchange=buy_ex,
                    sell_exchange=sell_ex,
                    spread=top_proceeds - top_cost,
                    spread_percent=(top_proceeds - top_cost) / top_cost * 100,
                    estimated_fees=fees,
                    estimated_slippage=slippage,
                    estimated_latency_cost=latency,
                    net_profit=proceeds - cost - fees - latency,
                    detected_at=now,
                )
            )
    return sorted(found, key=lambda o: o.net_profit, reverse=True)


st.set_page_config(page_title="Crypto Arbitrage Simulation", layout="wide")
st.title("Crypto Arbitrage Simulation")

with st.sidebar:
    st.header("Parameters")
    live = st.radio("Data source", ["Live (public APIs)", "Simulated"]).startswith("Live")
    symbols = st.multiselect("Symbols", list(BASE_PRICES), default=list(BASE_PRICES))
    notional = st.number_input("Trade size (USDT)", 100.0, 1_000_000.0, 10_000.0, 500.0)
    latency_bps = st.slider("Latency cost (bps)", 0.0, 20.0, 1.0, 0.5)
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

best = opps[0]
profitable = [o for o in opps if o.net_profit > 0]
c1, c2, c3 = st.columns(3)
c1.metric("Opportunities scanned", len(opps))
c2.metric("Profitable after costs", len(profitable))
c3.metric(
    "Best net profit",
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
opp_df = pd.DataFrame([vars(o) for o in opps]).drop(columns=["detected_at"])
st.dataframe(opp_df, use_container_width=True, hide_index=True)

st.subheader("Net profit by route")
chart_df = opp_df.assign(route=opp_df.buy_exchange + " → " + opp_df.sell_exchange)
st.bar_chart(chart_df.pivot_table(index="route", columns="symbol", values="net_profit"))
