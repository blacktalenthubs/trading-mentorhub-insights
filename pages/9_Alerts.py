"""Alert Reports — Daily alert history grouped by date."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from alerting.alert_store import (
    get_alerts_today,
    get_session_dates,
    get_session_summary,
)
import ui_theme

from ui_theme import get_current_tier, render_inline_upgrade

user = ui_theme.setup_page("alerts", tier_required="pro", tier_preview="free")

_is_free = get_current_tier() == "free"
_tier = get_current_tier()
# Admin sees ALL alerts (worker may record under a different user_id)
_uid = None if _tier == "admin" else (user["id"] if user else None)

ui_theme.page_header(
    "Alert Reports",
    "Daily alert history — browse signals fired each trading session",
)

# ── Available dates ───────────────────────────────────────────────────────

session_dates = get_session_dates(user_id=_uid)  # newest first

if not session_dates:
    ui_theme.empty_state("No alerts recorded yet. The monitor will populate alerts during market hours.")
    st.stop()

# ── Sidebar controls ─────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Date Range")
    if _is_free:
        # Free users: latest day only
        dates_to_show = session_dates[:1]
        st.caption(f"1 session (free tier) · {len(session_dates)} total")
        render_inline_upgrade("Full alert history — browse all sessions", "pro")
    else:
        view_mode = st.radio(
            "View",
            ["Pick a date", "Latest day", "Last 3 days", "Last 7 days", "All dates"],
            index=0,
            label_visibility="collapsed",
        )

        if view_mode == "Pick a date":
            # Convert session_date strings to date objects for the picker
            import datetime as _dt

            _date_objs = []
            for ds in session_dates:
                try:
                    _date_objs.append(_dt.date.fromisoformat(ds))
                except Exception:
                    pass

            if _date_objs:
                picked = st.date_input(
                    "Session date",
                    value=_date_objs[0],
                    min_value=_date_objs[-1],
                    max_value=_date_objs[0],
                )
                picked_str = str(picked)
                if picked_str in session_dates:
                    dates_to_show = [picked_str]
                else:
                    # Show nearest available date
                    st.warning(f"No alerts on {picked_str}")
                    dates_to_show = session_dates[:1]
            else:
                dates_to_show = session_dates[:1]
        elif view_mode == "Latest day":
            dates_to_show = session_dates[:1]
        elif view_mode == "Last 3 days":
            dates_to_show = session_dates[:3]
        elif view_mode == "Last 7 days":
            dates_to_show = session_dates[:7]
        else:
            dates_to_show = session_dates

        st.caption(f"{len(dates_to_show)} session(s) · {len(session_dates)} total")

# ── Collect all alerts across selected dates ─────────────────────────────

all_alerts: list[dict] = []
summaries_by_date: dict[str, dict] = {}

for d in dates_to_show:
    s = get_session_summary(session_date=d, user_id=_uid)
    summaries_by_date[d] = s
    for a in s["alerts"]:
        a["_session_date"] = d
        all_alerts.append(a)

if not all_alerts:
    ui_theme.empty_state("No alerts in the selected date range.")
    st.stop()

# ── Global KPIs ──────────────────────────────────────────────────────────

total_buy = sum(s["buy_count"] for s in summaries_by_date.values())
total_sell = sum(s["sell_count"] for s in summaries_by_date.values())
total_t1 = sum(s["t1_hits"] for s in summaries_by_date.values())
total_t2 = sum(s["t2_hits"] for s in summaries_by_date.values())
total_stopped = sum(s["stopped_out"] for s in summaries_by_date.values())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total", len(all_alerts))
c2.metric("Entries", total_buy)
c3.metric("Exits", total_sell)
c4.metric("T1 Hits", total_t1)
c5.metric("T2 Hits", total_t2)
c6.metric("Stopped", total_stopped)

st.divider()

# ── Filters ──────────────────────────────────────────────────────────────

filter_cols = st.columns(3)

with filter_cols[0]:
    all_symbols = sorted(set(a["symbol"] for a in all_alerts))
    selected_symbols = st.multiselect(
        "Symbol", all_symbols, default=None, placeholder="All symbols",
    )
    if not selected_symbols:
        selected_symbols = all_symbols

with filter_cols[1]:
    all_directions = sorted(set(a["direction"] for a in all_alerts))
    selected_directions = st.multiselect(
        "Direction", all_directions, default=None, placeholder="All directions",
    )
    if not selected_directions:
        selected_directions = all_directions

with filter_cols[2]:
    all_types = sorted(set(a["alert_type"] for a in all_alerts))
    selected_types = st.multiselect(
        "Alert Type", all_types, default=None, placeholder="All types",
        format_func=lambda t: t.replace("_", " ").title(),
    )
    if not selected_types:
        selected_types = all_types

filtered = [
    a for a in all_alerts
    if a["symbol"] in selected_symbols
    and a["direction"] in selected_directions
    and a["alert_type"] in selected_types
]

st.caption(f"Showing {len(filtered)} of {len(all_alerts)} alerts")

# ── PDF download ────────────────────────────────────────────────────
from alerts_pdf import generate_alerts_pdf

pdf_bytes = generate_alerts_pdf(filtered, summaries_by_date, dates_to_show)
st.download_button(
    label="Download PDF Report",
    data=pdf_bytes,
    file_name=f"tradecopilot_alerts_{dates_to_show[0]}.pdf",
    mime="application/pdf",
)

# ── Helpers ──────────────────────────────────────────────────────────────

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


def _render_card(alert: dict) -> None:
    """Render a single alert card."""
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

    if direction == "BUY":
        dir_bg = "rgba(63,185,80,0.15)"
    elif direction in ("SELL", "SHORT"):
        dir_bg = "rgba(248,81,73,0.15)"
    else:
        dir_bg = "rgba(210,153,34,0.15)"

    entry = alert.get("entry")
    stop = alert.get("stop")
    t1 = alert.get("target_1")
    t2 = alert.get("target_2")
    price = alert.get("price", 0)

    levels_parts = [f"Price: ${price:,.2f}"]
    if entry:
        levels_parts.append(f"Entry: ${entry:,.2f}")
    if stop:
        levels_parts.append(f"Stop: ${stop:,.2f}")
    if t1:
        levels_parts.append(f"T1: ${t1:,.2f}")
    if t2:
        levels_parts.append(f"T2: ${t2:,.2f}")
    levels_text = " · ".join(levels_parts)

    message = alert.get("message", "")
    narrative = alert.get("narrative", "")
    narrative_block = (
        f"<br><span style='color:#8b949e;font-style:italic'>{narrative}</span>"
        if narrative else ""
    )

    st.markdown(
        f"<div style='background:#161b22;border:1px solid #30363d;border-left:3px solid {dir_color};"
        f"border-radius:6px;padding:0.9rem 1.1rem;margin-bottom:0.6rem'>"
        f"<span style='font-weight:700;font-size:1.05rem'>{symbol}</span> "
        f"<span style='background:{dir_bg};color:{dir_color};padding:2px 8px;border-radius:10px;"
        f"font-size:0.75rem;font-weight:600'>{ui_theme.display_direction(direction)[0]}</span> "
        f"<span style='color:#8b949e;font-size:0.8rem'>{alert_type_display}</span>"
        f"<span style='float:right'>"
        f"<span style='color:{score_color};font-weight:700;font-size:0.85rem'>{score_lbl} ({score})</span> "
        f"<span style='color:#8b949e;font-size:0.8rem'>{confidence}</span> "
        f"<span style='color:#58a6ff;font-size:0.8rem'>{time_str}</span>"
        f"</span>"
        f"<br><span style='font-size:0.82rem;color:#8b949e'>{levels_text}</span>"
        f"<br><span style='font-size:0.85rem;color:#b1bac4;line-height:1.5'>{message}</span>"
        f"{narrative_block}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ── Alerts grouped by date ───────────────────────────────────────────────

# Group filtered alerts by session date
from collections import defaultdict

grouped: dict[str, list[dict]] = defaultdict(list)
for a in filtered:
    grouped[a["_session_date"]].append(a)

for session_date in dates_to_show:
    day_alerts = grouped.get(session_date, [])
    if not day_alerts:
        continue

    day_summary = summaries_by_date[session_date]
    date_display = pd.Timestamp(session_date).strftime("%A, %b %d %Y")

    # Date header with mini KPIs
    buy_c = sum(1 for a in day_alerts if a.get("direction") == "BUY")
    sell_c = sum(1 for a in day_alerts if a.get("direction") in ("SELL", "SHORT", "NOTICE"))

    st.markdown(
        f"<div style='background:linear-gradient(90deg,#1e3a5f,#16213e);padding:10px 16px;"
        f"border-radius:8px;margin:1rem 0 0.5rem 0;display:flex;justify-content:space-between;"
        f"align-items:center'>"
        f"<span style='font-weight:700;font-size:1.1rem'>{date_display}</span>"
        f"<span style='font-size:0.85rem;color:#8b949e'>"
        f"{len(day_alerts)} alerts · "
        f"<span style='color:#3fb950'>{buy_c} Entry</span> · "
        f"<span style='color:#f85149'>{sell_c} Exit</span>"
        f"</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    for alert in day_alerts:
        _render_card(alert)

# Free tier footer CTA
if _is_free:
    st.divider()
    render_inline_upgrade(
        f"Unlock {len(session_dates)} days of alert history with filters & PDF export",
        "pro",
    )

# ── Raw data table ───────────────────────────────────────────────────────

st.divider()

with st.expander("Raw Data Table"):
    if not filtered:
        st.caption("No alerts match the current filters.")
    else:
        display_cols = [
            "created_at", "_session_date", "symbol", "alert_type", "direction",
            "price", "entry", "stop", "target_1", "target_2", "confidence",
            "score", "message",
        ]
        available_cols = [c for c in display_cols if c in filtered[0]]
        df = pd.DataFrame(filtered)[available_cols]
        df.columns = [c.replace("_", " ").title() for c in available_cols]
        if "Direction" in df.columns:
            df["Direction"] = df["Direction"].map(
                lambda d: ui_theme.display_direction(d)[0]
            )

        money_cols = ["Price", "Entry", "Stop", "Target 1", "Target 2"]
        fmt = {c: "${:,.2f}" for c in money_cols if c in df.columns}
        st.dataframe(
            df.style.format(fmt, na_rep="—"),
            use_container_width=True,
            hide_index=True,
        )
