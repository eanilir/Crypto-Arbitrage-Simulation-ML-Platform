"""Virtual-balance badge pinned in the top bar, just left of Streamlit's Deploy button."""

from __future__ import annotations

import html


def badge_html(quote_total: float, quote_change: float, base_total: float | None, tooltip: str) -> str:
    color = "#3fb950" if quote_change >= 0 else "#f85149"
    return (
        "<style>.balance-badge{position:fixed;top:12px;right:150px;z-index:1000000;"
        "display:flex;gap:12px;align-items:center;padding:4px 12px;border-radius:8px;"
        "border:1px solid rgba(128,128,128,.4);background:rgba(20,22,28,.92);color:#fafafa;"
        "font:600 14px 'Source Sans Pro',sans-serif;white-space:nowrap}"
        ".balance-badge small{font-weight:400;opacity:.8}</style>"
        f'<div class="balance-badge" title="{html.escape(tooltip)}">'
        f"<span>$ {quote_total:,.2f}</span>"
        f'<small style="color:{color}">{quote_change:+,.2f}</small>'
        + (f"<small>{base_total:,.4f} BTC</small>" if base_total is not None else "")
        + "</div>"
    )


def show_balance_badge(quote_total: float, quote_change: float, base_total: float | None, tooltip: str) -> None:
    import streamlit as st

    st.markdown(badge_html(quote_total, quote_change, base_total, tooltip), unsafe_allow_html=True)
