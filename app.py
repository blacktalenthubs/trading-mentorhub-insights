"""TradeSignal — Trade smarter, not longer."""

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime

from streamlit_autorefresh import st_autorefresh

from db import init_db
from auth import auto_login
from config import DEFAULT_WATCHLIST
from analytics.intraday_data import fetch_intraday, fetch_prior_day, get_spy_context
from analytics.intraday_rules import evaluate_rules, AlertSignal
from analytics.market_hours import is_market_hours
from alerting.notifier import send_email, send_sms
from alert_config import POLL_INTERVAL_MINUTES

st.set_page_config(
    page_title="TradeSignal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
user = auto_login()

st.title("TradeSignal")
st.caption("Trade smarter, not longer.")

# ── Auto-refresh during market hours ──────────────────────────────────────
_market_open = is_market_hours()
if _market_open:
    st_autorefresh(interval=180_000, key="alert_refresh")  # 3 min

# ── Shared watchlist (from Scanner or default) ────────────────────────────
watchlist = st.session_state.get("watchlist", list(DEFAULT_WATCHLIST))
st.caption(f"Watchlist: {', '.join(watchlist)} | Refresh: {POLL_INTERVAL_MINUTES} min")

st.divider()

# ---------------------------------------------------------------------------
# Cached helpers
# ---------------------------------------------------------------------------


@st.cache_data(ttl=180, show_spinner=False)
def _cached_intraday(symbol: str) -> pd.DataFrame:
    return fetch_intraday(symbol)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_prior_day(symbol: str) -> dict | None:
    return fetch_prior_day(symbol)


# ---------------------------------------------------------------------------
# Live Alerts (inline scanning)
# ---------------------------------------------------------------------------

st.subheader("Live Alerts")

if not _market_open:
    st.info("Market is closed — alerts resume at 9:30 AM ET on the next trading day.")
    st.caption(f"Last check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
else:
    # Initialize alert history in session state
    if "alert_history" not in st.session_state:
        st.session_state["alert_history"] = []
    if "auto_stop_entries" not in st.session_state:
        st.session_state["auto_stop_entries"] = {}

    # Collect active positions from Scanner for SELL rule evaluation
    active_positions = st.session_state.get("active_positions", {})

    all_signals: list[AlertSignal] = []

    with st.spinner(f"Scanning {len(watchlist)} symbols..."):
        for symbol in watchlist:
            intra = _cached_intraday(symbol)
            prior = _cached_prior_day(symbol)

            if intra.empty:
                continue

            # Build active entries from tracked positions
            active_entries = []
            if symbol in active_positions:
                pos = active_positions[symbol]
                active_entries.append({
                    "entry_price": pos["entry"],
                    "stop_price": 0,  # filled by rule if needed
                    "target_1": 0,
                    "target_2": 0,
                })

            _spy_ctx = get_spy_context()
            auto_stop = st.session_state.get("auto_stop_entries", {})
            signals = evaluate_rules(
                symbol, intra, prior, active_entries,
                spy_context=_spy_ctx,
                auto_stop_entries=auto_stop.get(symbol),
            )
            all_signals.extend(signals)

    # Dedup against session history
    existing_keys = {
        (a["symbol"], a["alert_type"], a["direction"])
        for a in st.session_state["alert_history"]
    }

    new_signals = []
    notifications_sent = 0
    for sig in all_signals:
        key = (sig.symbol, sig.alert_type.value, sig.direction)
        if key not in existing_keys:
            new_signals.append(sig)

            # Send notifications for new signals
            if send_email(sig):
                notifications_sent += 1
            send_sms(sig)

            st.session_state["alert_history"].append({
                "symbol": sig.symbol,
                "alert_type": sig.alert_type.value,
                "direction": sig.direction,
                "price": sig.price,
                "entry": sig.entry,
                "stop": sig.stop,
                "target_1": sig.target_1,
                "target_2": sig.target_2,
                "message": sig.message,
                "time": datetime.now().strftime("%H:%M:%S"),
                "emailed": True,
            })

            # Track BUY signals for auto-stop-out
            if sig.direction == "BUY" and sig.entry and sig.stop:
                st.session_state.setdefault("auto_stop_entries", {})[sig.symbol] = {
                    "entry_price": sig.entry,
                    "stop_price": sig.stop,
                    "alert_type": sig.alert_type.value,
                }

            # Clean up on stop-out
            if sig.alert_type.value == "auto_stop_out":
                st.session_state.get("auto_stop_entries", {}).pop(sig.symbol, None)

    if new_signals and notifications_sent:
        st.toast(f"Sent {notifications_sent} new alert(s)")

    # Display all current signals as colored cards
    if all_signals:
        for sig in all_signals:
            color = "#2ecc71" if sig.direction == "BUY" else "#9b59b6" if sig.direction == "SHORT" else "#e74c3c"
            is_new = sig in new_signals
            new_badge = " <span style='background:#f39c12;color:white;padding:2px 6px;border-radius:3px;font-size:0.75em'>NEW</span>" if is_new else ""

            st.markdown(
                f"<div style='padding:10px 14px;border-left:4px solid {color};"
                f"background:{color}10;margin-bottom:8px;border-radius:4px'>"
                f"<strong style='color:{color};font-size:1.1em'>{sig.direction}</strong>"
                f"{new_badge} "
                f"<strong>{sig.symbol}</strong> — "
                f"{sig.alert_type.value.replace('_', ' ').title()} @ ${sig.price:,.2f}"
                f"<br><span style='color:#888'>{sig.message}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            if sig.entry:
                with st.expander(f"{sig.symbol} — Details"):
                    dc1, dc2, dc3, dc4 = st.columns(4)
                    dc1.metric("Entry", f"${sig.entry:,.2f}")
                    if sig.stop:
                        dc2.metric("Stop", f"${sig.stop:,.2f}")
                    if sig.target_1:
                        dc3.metric("T1", f"${sig.target_1:,.2f}")
                    if sig.target_2:
                        dc4.metric("T2", f"${sig.target_2:,.2f}")

        # Summary KPIs
        buy_count = sum(1 for s in all_signals if s.direction == "BUY")
        sell_count = sum(1 for s in all_signals if s.direction == "SELL")
        short_count = sum(1 for s in all_signals if s.direction == "SHORT")

        st.divider()
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Active Signals", len(all_signals))
        kpi2.metric("BUY Signals", buy_count)
        kpi3.metric("SELL Signals", sell_count)
        kpi4.metric("SHORT Signals", short_count)
    else:
        st.info("No signals firing right now. Scanning every 3 minutes.")

    st.caption(f"Last scan: {datetime.now().strftime('%H:%M:%S')} ET | "
               f"{len(watchlist)} symbols checked")

st.divider()

# ---------------------------------------------------------------------------
# Alert History (session)
# ---------------------------------------------------------------------------

st.subheader("Alert History (This Session)")

history = st.session_state.get("alert_history", [])

if history:
    # Show most recent first
    hist_df = pd.DataFrame(reversed(history))
    st.dataframe(
        hist_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "price": st.column_config.NumberColumn(format="$%.2f"),
            "entry": st.column_config.NumberColumn(format="$%.2f"),
            "stop": st.column_config.NumberColumn(format="$%.2f"),
            "target_1": st.column_config.NumberColumn(format="$%.2f"),
            "target_2": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    if st.button("Clear History", key="clear_hist"):
        st.session_state["alert_history"] = []
        st.rerun()
else:
    st.info("No alerts fired this session.")

# ---------------------------------------------------------------------------
# Test Notifications (kept for desktop use)
# ---------------------------------------------------------------------------

st.divider()
with st.expander("Test Notifications"):
    st.caption("Send a test alert to verify your email and SMS configuration.")

    if st.button("Send Test Alert"):
        from analytics.intraday_rules import AlertType
        from alerting.notifier import send_email, send_sms

        test_signal = AlertSignal(
            symbol="TEST",
            alert_type=AlertType.MA_BOUNCE_20,
            direction="BUY",
            price=100.00,
            entry=100.00,
            stop=99.00,
            target_1=101.00,
            target_2=102.00,
            confidence="high",
            message="Test alert from TradeSignal — ignore this message",
        )

        with st.spinner("Sending test email..."):
            email_ok = send_email(test_signal)

        with st.spinner("Sending test SMS..."):
            sms_ok = send_sms(test_signal)

        if email_ok:
            st.success("Test email sent successfully!")
        else:
            st.warning("Email failed — check .env SMTP settings")

        if sms_ok:
            st.success("Test SMS sent successfully!")
        else:
            st.warning("SMS failed — check .env Twilio settings")
