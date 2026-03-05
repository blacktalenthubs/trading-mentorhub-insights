"""Alert Reports — Daily alert history with summaries and details."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from alerting.alert_store import (
    get_alerts_today,
    get_session_dates,
    get_session_summary,
)
import ui_theme

user = ui_theme.setup_page("alerts")

ui_theme.page_header(
    "Alert Reports",
    "Daily alert history — browse signals fired each trading session",
)

# ── Session date picker ─────────────────────────────────────────────────────

session_dates = get_session_dates()

if not session_dates:
    ui_theme.empty_state("No alerts recorded yet. The monitor will populate alerts during market hours.")
    st.stop()

# Sidebar: date selector
with st.sidebar:
    st.subheader("Session Date")
    selected_date = st.selectbox(
        "Select date",
        session_dates,
        index=0,
        format_func=lambda d: pd.Timestamp(d).strftime("%a %b %d, %Y"),
        label_visibility="collapsed",
    )

# ── Session summary ─────────────────────────────────────────────────────────

summary = get_session_summary(session_date=selected_date)
alerts = summary["alerts"]

if not alerts:
    ui_theme.empty_state(f"No alerts fired on {selected_date}.")
    st.stop()

# KPI row
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total", summary["total"])
c2.metric("BUY", summary["buy_count"])
c3.metric("SELL", summary["sell_count"])
c4.metric("T1 Hits", summary["t1_hits"])
c5.metric("T2 Hits", summary["t2_hits"])
c6.metric("Stopped", summary["stopped_out"])

st.divider()

# ── Filters ─────────────────────────────────────────────────────────────────

filter_cols = st.columns(3)

with filter_cols[0]:
    symbols_in_session = sorted(set(a["symbol"] for a in alerts))
    selected_symbols = st.multiselect(
        "Symbol",
        symbols_in_session,
        default=symbols_in_session,
    )

with filter_cols[1]:
    directions = sorted(set(a["direction"] for a in alerts))
    selected_directions = st.multiselect(
        "Direction",
        directions,
        default=directions,
    )

with filter_cols[2]:
    alert_types = sorted(set(a["alert_type"] for a in alerts))
    selected_types = st.multiselect(
        "Alert Type",
        alert_types,
        default=alert_types,
        format_func=lambda t: t.replace("_", " ").title(),
    )

# Apply filters
filtered = [
    a for a in alerts
    if a["symbol"] in selected_symbols
    and a["direction"] in selected_directions
    and a["alert_type"] in selected_types
]

st.caption(f"Showing {len(filtered)} of {len(alerts)} alerts")

# ── Signal type breakdown ───────────────────────────────────────────────────

if summary["signals_by_type"]:
    with st.expander("Signal Breakdown", expanded=False):
        type_df = pd.DataFrame(
            [
                {"Alert Type": k.replace("_", " ").title(), "Count": v}
                for k, v in sorted(
                    summary["signals_by_type"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ]
        )
        st.dataframe(type_df, use_container_width=True, hide_index=True)

# ── Alert cards ─────────────────────────────────────────────────────────────

DIR_COLORS = {
    "BUY": "#3fb950",
    "SELL": "#f85149",
    "SHORT": "#bc8cff",
    "NOTICE": "#d29922",
}

SCORE_COLORS = {
    "A+": "#3fb950",
    "A": "#3fb950",
    "B": "#d29922",
    "C": "#8b949e",
}


def _score_label(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 50:
        return "B"
    return "C"


for alert in filtered:
    direction = alert.get("direction", "")
    dir_color = DIR_COLORS.get(direction, "#8b949e")
    score = alert.get("score", 0)
    score_lbl = _score_label(score)
    score_color = SCORE_COLORS.get(score_lbl, "#8b949e")
    alert_type_display = alert.get("alert_type", "").replace("_", " ").title()
    confidence = alert.get("confidence", "")
    symbol = alert.get("symbol", "")
    created = alert.get("created_at", "")
    time_str = ""
    if created:
        try:
            time_str = pd.Timestamp(created).strftime("%I:%M %p")
        except Exception:
            time_str = str(created)[:16]

    # Header line
    header = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
        <div style="display:flex; align-items:center; gap:0.6rem;">
            <span style="font-weight:700; font-size:1.05rem;">{symbol}</span>
            <span style="background:{'rgba(63,185,80,0.15)' if direction=='BUY' else 'rgba(248,81,73,0.15)' if direction in ('SELL','SHORT') else 'rgba(210,153,34,0.15)'};
                   color:{dir_color}; padding:2px 8px; border-radius:10px; font-size:0.75rem; font-weight:600;">
                {direction}
            </span>
            <span style="color:#8b949e; font-size:0.8rem;">{alert_type_display}</span>
        </div>
        <div style="display:flex; align-items:center; gap:0.6rem;">
            <span style="color:{score_color}; font-weight:700; font-size:0.85rem;">{score_lbl} ({score})</span>
            <span style="color:#8b949e; font-size:0.8rem;">{confidence}</span>
            <span style="color:#58a6ff; font-size:0.8rem;">{time_str}</span>
        </div>
    </div>
    """

    # Levels line
    entry = alert.get("entry")
    stop = alert.get("stop")
    t1 = alert.get("target_1")
    t2 = alert.get("target_2")
    price = alert.get("price", 0)

    levels_parts = [f"Price: <span style='color:#e6edf3'>${price:,.2f}</span>"]
    if entry:
        levels_parts.append(f"Entry: <span style='color:#3fb950'>${entry:,.2f}</span>")
    if stop:
        levels_parts.append(f"Stop: <span style='color:#f85149'>${stop:,.2f}</span>")
    if t1:
        levels_parts.append(f"T1: <span style='color:#58a6ff'>${t1:,.2f}</span>")
    if t2:
        levels_parts.append(f"T2: <span style='color:#bc8cff'>${t2:,.2f}</span>")

    levels_html = " &nbsp;&middot;&nbsp; ".join(levels_parts)

    # Message
    message = alert.get("message", "")
    narrative = alert.get("narrative", "")

    card_html = f"""
    <div style="background:#161b22; border:1px solid #30363d; border-left:3px solid {dir_color};
                border-radius:6px; padding:0.9rem 1.1rem; margin-bottom:0.6rem;">
        {header}
        <div style="font-size:0.82rem; color:#8b949e; margin-top:0.5rem;">
            {levels_html}
        </div>
        <div style="font-size:0.85rem; color:#b1bac4; margin-top:0.5rem; line-height:1.5;">
            {message}
        </div>
        {"<div style='font-size:0.83rem; color:#8b949e; margin-top:0.4rem; font-style:italic; border-top:1px solid #30363d; padding-top:0.4rem;'>" + narrative + "</div>" if narrative else ""}
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

# ── Raw data table ──────────────────────────────────────────────────────────

with st.expander("Raw Data Table"):
    display_cols = [
        "created_at", "symbol", "alert_type", "direction", "price",
        "entry", "stop", "target_1", "target_2", "confidence", "score", "message",
    ]
    available_cols = [c for c in display_cols if c in filtered[0]]
    df = pd.DataFrame(filtered)[available_cols]
    df.columns = [c.replace("_", " ").title() for c in available_cols]

    money_cols = ["Price", "Entry", "Stop", "Target 1", "Target 2"]
    fmt = {c: "${:,.2f}" for c in money_cols if c in df.columns}
    st.dataframe(
        df.style.format(fmt, na_rep="—"),
        use_container_width=True,
        hide_index=True,
    )
