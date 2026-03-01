"""TradeSignal — Trade smarter, not longer."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from streamlit_autorefresh import st_autorefresh

from db import init_db
from auth import auto_login
from config import DEFAULT_WATCHLIST
from analytics.intraday_data import (
    fetch_intraday, fetch_prior_day, get_spy_context, compute_vwap,
)
from analytics.intraday_rules import evaluate_rules, AlertSignal
from analytics.market_hours import is_market_hours, get_session_phase
from alerting.alert_store import (
    get_active_cooldowns, get_alert_id, get_alerts_today, get_session_summary,
    today_session,
)
from alerting.real_trade_store import (
    calculate_shares, has_open_trade, open_real_trade,
)
from alert_config import (
    POLL_INTERVAL_MINUTES,
    REAL_TRADE_POSITION_SIZE, REAL_TRADE_SPY_POSITION_SIZE,
)
import ui_theme

st.set_page_config(
    page_title="TradeSignal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
user = auto_login()
ui_theme.inject_custom_css()

ui_theme.page_header("TradeSignal", "Trade smarter, not longer.")

# ── Auto-refresh during market hours ──────────────────────────────────────
_market_open = is_market_hours()
if _market_open:
    st_autorefresh(interval=180_000, key="alert_refresh")  # 3 min

# ── Shared watchlist (from Scanner or default) ────────────────────────────
watchlist = st.session_state.get("watchlist", list(DEFAULT_WATCHLIST))
st.caption(f"Watchlist: {', '.join(watchlist)} | Refresh: {POLL_INTERVAL_MINUTES} min")

# ── F9: Session Stats Bar ────────────────────────────────────────────────
if _market_open:
    history = st.session_state.get("alert_history", [])
    buy_hist = sum(1 for a in history if a.get("direction") == "BUY")
    sell_hist = sum(1 for a in history if a.get("direction") == "SELL")
    short_hist = sum(1 for a in history if a.get("direction") == "SHORT")

    # Win/loss from session history
    t1_wins = sum(1 for a in history if a.get("alert_type") == "target_1_hit")
    stopped = sum(1 for a in history if a.get("alert_type") in ("stop_loss_hit", "auto_stop_out"))
    total_decided = t1_wins + stopped
    win_rate = f"{t1_wins / total_decided * 100:.0f}%" if total_decided > 0 else "N/A"

    # Active cooldowns (from DB — persistent across restarts)
    active_cd_symbols = get_active_cooldowns()
    cd_text = ", ".join(sorted(active_cd_symbols)) if active_cd_symbols else "None"

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.markdown(f"**Signals:** {buy_hist} BUY / {sell_hist} SELL / {short_hist} SHORT")
    sc2.markdown(f"**Win Rate:** {t1_wins}W / {stopped}L ({win_rate})")
    sc3.markdown(f"**Cooldowns:** {cd_text}")
    sc4.markdown(f"**Refresh:** {POLL_INTERVAL_MINUTES * 60}s")

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
# F6: Signal chart overlay helper
# ---------------------------------------------------------------------------


def _draw_signal_chart(symbol: str, sig: AlertSignal):
    """5-min candlestick chart with entry/stop/T1/T2 overlays and VWAP."""
    bars = _cached_intraday(symbol)
    if bars.empty:
        return

    prior = _cached_prior_day(symbol)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=bars.index.strftime("%H:%M"),
        open=bars["Open"], high=bars["High"],
        low=bars["Low"], close=bars["Close"],
        name=symbol,
        increasing_line_color="#2ecc71",
        decreasing_line_color="#e74c3c",
    ))

    # VWAP line
    vwap = compute_vwap(bars)
    if not vwap.empty:
        fig.add_trace(go.Scatter(
            x=bars.index.strftime("%H:%M"), y=vwap.values,
            mode="lines", name="VWAP",
            line=dict(color="#9b59b6", width=1.5, dash="dash"),
        ))

    # Prior day high/low
    if prior:
        fig.add_hline(y=prior["high"], line_dash="dot", line_color="#e74c3c", line_width=1,
                      annotation_text=f"  Prior High ${prior['high']:,.2f}  ",
                      annotation_font=dict(size=10, color="white"),
                      annotation_bgcolor="#e74c3c", annotation_borderpad=2,
                      annotation_position="top left")
        fig.add_hline(y=prior["low"], line_dash="dot", line_color="#2ecc71", line_width=1,
                      annotation_text=f"  Prior Low ${prior['low']:,.2f}  ",
                      annotation_font=dict(size=10, color="white"),
                      annotation_bgcolor="#2ecc71", annotation_borderpad=2,
                      annotation_position="bottom left")

    # Signal levels
    if sig.entry:
        fig.add_hline(y=sig.entry, line_dash="dash", line_color="#3498db", line_width=1.5,
                      annotation_text=f"  Entry ${sig.entry:,.2f}  ",
                      annotation_font=dict(size=10, color="white"),
                      annotation_bgcolor="#3498db", annotation_borderpad=2,
                      annotation_position="top left")
    if sig.stop:
        fig.add_hline(y=sig.stop, line_dash="dash", line_color="#e74c3c", line_width=1.5,
                      annotation_text=f"  Stop ${sig.stop:,.2f}  ",
                      annotation_font=dict(size=10, color="white"),
                      annotation_bgcolor="#e74c3c", annotation_borderpad=2,
                      annotation_position="bottom left")
    if sig.target_1:
        fig.add_hline(y=sig.target_1, line_dash="dash", line_color="#2ecc71", line_width=1.5,
                      annotation_text=f"  T1 ${sig.target_1:,.2f}  ",
                      annotation_font=dict(size=10, color="white"),
                      annotation_bgcolor="#2ecc71", annotation_borderpad=2,
                      annotation_position="top left")
    if sig.target_2:
        fig.add_hline(y=sig.target_2, line_dash="dash", line_color="#27ae60", line_width=1,
                      annotation_text=f"  T2 ${sig.target_2:,.2f}  ",
                      annotation_font=dict(size=10, color="white"),
                      annotation_bgcolor="#27ae60", annotation_borderpad=2,
                      annotation_position="top left")

    # Signal marker
    if sig.entry:
        fig.add_trace(go.Scatter(
            x=[bars.index[-1].strftime("%H:%M")], y=[sig.entry],
            mode="markers", name="Signal",
            marker=dict(symbol="triangle-up", size=14, color="#f39c12"),
        ))

    fig.update_layout(
        height=300, xaxis_rangeslider_visible=False,
        yaxis_title="Price ($)", title=f"{symbol} — 5m with Signals",
        margin=dict(l=40, r=20, t=40, b=30),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Live Alerts (inline scanning)
# ---------------------------------------------------------------------------

ui_theme.section_header("Live Alerts")

if not _market_open:
    ui_theme.empty_state("Market is closed — alerts resume at 9:30 AM ET on the next trading day.")
    st.caption(f"Last check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
else:
    # Initialize alert history in session state
    if "alert_history" not in st.session_state:
        st.session_state["alert_history"] = []
    if "auto_stop_entries" not in st.session_state:
        st.session_state["auto_stop_entries"] = {}

    # Build fired_today from DB (authoritative, persistent across restarts)
    db_alerts = get_alerts_today()
    fired_today: set[tuple[str, str]] = {
        (a["symbol"], a["alert_type"]) for a in db_alerts
    }

    # Build active cooldown set from DB
    cooled_symbols: set[str] = get_active_cooldowns()

    # Collect active positions from Scanner for SELL rule evaluation
    active_positions = st.session_state.get("active_positions", {})

    all_signals: list[AlertSignal] = []
    # Track intraday data per symbol for heat map
    _symbol_intraday: dict[str, pd.DataFrame] = {}

    with st.spinner(f"Scanning {len(watchlist)} symbols..."):
        for symbol in watchlist:
            intra = _cached_intraday(symbol)
            prior = _cached_prior_day(symbol)
            _symbol_intraday[symbol] = intra

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
                is_cooled_down=symbol in cooled_symbols,
                fired_today=fired_today,
            )
            all_signals.extend(signals)

    # ── F7: Watchlist Heat Map ────────────────────────────────────────────
    signal_symbols = {s.symbol for s in all_signals}

    st.markdown("**Watchlist**")
    hm_cols = st.columns(min(5, len(watchlist)) if watchlist else 1)
    for i, sym in enumerate(watchlist):
        col = hm_cols[i % len(hm_cols)]
        intra = _symbol_intraday.get(sym, pd.DataFrame())
        if not intra.empty:
            current_price = intra["Close"].iloc[-1]
            sym_open = intra["Open"].iloc[0]
            change_pct = (current_price - sym_open) / sym_open * 100 if sym_open > 0 else 0
        else:
            current_price = 0
            change_pct = 0

        # Color: green for positive, red for negative; darker for bigger moves
        if change_pct >= 1:
            bg = "#1a7a3a"
        elif change_pct >= 0:
            bg = "#2ecc7140"
        elif change_pct > -1:
            bg = "#e74c3c40"
        else:
            bg = "#a93226"
        text_color = "white" if abs(change_pct) >= 1 else "#ddd"

        # Badges
        badges = ""
        if sym in signal_symbols:
            badges += " <span style='background:#f39c12;color:white;padding:1px 5px;border-radius:3px;font-size:0.7em'>SIGNAL</span>"
        if sym in cooled_symbols:
            badges += " <span style='background:#888;color:white;padding:1px 5px;border-radius:3px;font-size:0.7em'>COOL</span>"

        border = "2px solid #f39c12" if sym in signal_symbols else "1px solid #444"
        col.markdown(
            f"<div style='padding:8px;background:{bg};border:{border};"
            f"border-radius:6px;text-align:center;margin-bottom:4px'>"
            f"<strong style='color:{text_color};font-size:1.1em'>{sym}</strong>{badges}<br>"
            f"<span style='color:{text_color}'>${current_price:,.2f}</span><br>"
            f"<span style='color:{text_color};font-size:0.9em'>{change_pct:+.2f}%</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown("")

    # Dedup against DB (authoritative) + session history (fast for display)
    existing_keys = {
        (a["symbol"], a["alert_type"], a["direction"])
        for a in db_alerts
    } | {
        (a["symbol"], a["alert_type"], a["direction"])
        for a in st.session_state["alert_history"]
    }

    new_signals = []
    for sig in all_signals:
        key = (sig.symbol, sig.alert_type.value, sig.direction)
        if key not in existing_keys:
            new_signals.append(sig)

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
            })

            # Track BUY signals for auto-stop-out (display only)
            if sig.direction == "BUY" and sig.entry and sig.stop:
                st.session_state.setdefault("auto_stop_entries", {})[sig.symbol] = {
                    "entry_price": sig.entry,
                    "stop_price": sig.stop,
                    "alert_type": sig.alert_type.value,
                }

            # Clean up on stop-out (cooldown is handled by monitor.py via DB)
            if sig.alert_type.value in ("auto_stop_out", "stop_loss_hit"):
                st.session_state.get("auto_stop_entries", {}).pop(sig.symbol, None)

    if new_signals:
        st.toast(f"{len(new_signals)} new signal(s) detected")

    # ── F8: Sort signals by score descending ──────────────────────────────
    all_signals.sort(key=lambda s: s.score, reverse=True)

    # Display all current signals as colored cards
    if all_signals:
        for sig in all_signals:
            color = "#2ecc71" if sig.direction == "BUY" else "#9b59b6" if sig.direction == "SHORT" else "#e74c3c"
            is_new = sig in new_signals

            # F8: Score badge styling
            if sig.score >= 90:
                score_badge = f"<span style='background:#2ecc71;color:white;padding:2px 6px;border-radius:3px;font-size:0.75em;font-weight:bold'>A+</span>"
            elif sig.score >= 75:
                score_badge = f"<span style='background:#27ae60;color:white;padding:2px 6px;border-radius:3px;font-size:0.75em'>A</span>"
            elif sig.score >= 50:
                score_badge = f"<span style='background:#f39c12;color:white;padding:2px 6px;border-radius:3px;font-size:0.75em'>B</span>"
            else:
                score_badge = f"<span style='background:#888;color:white;padding:2px 6px;border-radius:3px;font-size:0.75em'>C</span>"

            new_badge = " <span style='background:#f39c12;color:white;padding:2px 6px;border-radius:3px;font-size:0.75em'>NEW</span>" if is_new else ""

            opacity = "0.6" if sig.score < 50 else "1.0"
            padding = "14px 18px" if sig.score >= 90 else "10px 14px"
            font_size = "1.2em" if sig.score >= 90 else "1.1em"

            st.markdown(
                f"<div style='padding:{padding};border-left:4px solid {color};"
                f"background:{color}10;margin-bottom:8px;border-radius:4px;opacity:{opacity}'>"
                f"{score_badge} "
                f"<strong style='color:{color};font-size:{font_size}'>{sig.direction}</strong>"
                f"{new_badge} "
                f"<strong>{sig.symbol}</strong> — "
                f"{sig.alert_type.value.replace('_', ' ').title()} @ ${sig.price:,.2f}"
                f"<br><span style='color:#888'>{sig.message}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            if sig.entry:
                # F8: Auto-expand for A+ signals
                expanded = sig.score >= 90
                with st.expander(f"{sig.symbol} — Details", expanded=expanded):
                    dc1, dc2, dc3, dc4 = st.columns(4)
                    dc1.metric("Entry", f"${sig.entry:,.2f}")
                    if sig.stop:
                        dc2.metric("Stop", f"${sig.stop:,.2f}")
                    if sig.target_1:
                        dc3.metric("T1", f"${sig.target_1:,.2f}")
                    if sig.target_2:
                        dc4.metric("T2", f"${sig.target_2:,.2f}")

                    # Real trade: "Took It" / "Skip" buttons
                    if sig.direction in ("BUY", "SHORT") and sig.entry and sig.stop:
                        shares = calculate_shares(sig.symbol, sig.entry)
                        cap = REAL_TRADE_SPY_POSITION_SIZE if sig.symbol == "SPY" else REAL_TRADE_POSITION_SIZE
                        exposure = shares * sig.entry
                        st.caption(
                            f"{shares} shares x ${sig.entry:,.2f} = "
                            f"${exposure:,.0f} (cap: ${cap / 1000:.0f}k)"
                        )

                        if has_open_trade(sig.symbol):
                            st.info("Already in this trade")
                        else:
                            tk_key = f"took_{sig.symbol}_{sig.alert_type.value}"
                            sk_key = f"skip_{sig.symbol}_{sig.alert_type.value}"
                            bc1, bc2 = st.columns(2)
                            if bc1.button("Took It", key=tk_key, type="primary"):
                                alert_id = get_alert_id(
                                    sig.symbol, sig.alert_type.value, today_session(),
                                )
                                open_real_trade(
                                    symbol=sig.symbol,
                                    direction=sig.direction,
                                    entry_price=sig.entry,
                                    stop_price=sig.stop,
                                    target_price=sig.target_1,
                                    target_2_price=sig.target_2,
                                    alert_type=sig.alert_type.value,
                                    alert_id=alert_id,
                                    session_date=today_session(),
                                )
                                st.toast(f"Opened {sig.direction} on {sig.symbol}")
                                st.rerun()
                            if bc2.button("Skip", key=sk_key):
                                st.toast(f"Skipped {sig.symbol}")

                    # F6: Intraday chart with signal overlays for BUY signals
                    if sig.direction == "BUY":
                        _draw_signal_chart(sig.symbol, sig)

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
        ui_theme.empty_state("No signals firing right now. Scanning every 3 minutes.")

    st.caption(f"Last scan: {datetime.now().strftime('%H:%M:%S')} ET | "
               f"{len(watchlist)} symbols checked")

    # ── F5: Live P&L Tracker ──────────────────────────────────────────────
    auto_stop = st.session_state.get("auto_stop_entries", {})
    if auto_stop:
        st.divider()
        ui_theme.section_header("Live P&L Tracker")

        total_pnl = 0.0
        winning = 0
        losing = 0
        pnl_rows = []

        for sym, entry_info in auto_stop.items():
            intra = _symbol_intraday.get(sym, pd.DataFrame())
            if intra.empty:
                continue
            current = intra["Close"].iloc[-1]
            ep = entry_info["entry_price"]
            sp = entry_info["stop_price"]

            pnl_dollar = current - ep
            pnl_pct = (pnl_dollar / ep * 100) if ep > 0 else 0
            to_stop = current - sp if sp > 0 else 0

            # Look up T1/T2 from alert history
            t1 = 0.0
            t2 = 0.0
            for a in st.session_state.get("alert_history", []):
                if a["symbol"] == sym and a["direction"] == "BUY" and a.get("target_1"):
                    t1 = a["target_1"]
                    t2 = a.get("target_2", 0)
                    break

            to_t1 = t1 - current if t1 > 0 else 0
            to_t2 = t2 - current if t2 > 0 else 0

            total_pnl += pnl_dollar
            if pnl_dollar >= 0:
                winning += 1
            else:
                losing += 1

            pnl_rows.append({
                "Symbol": sym,
                "Type": entry_info.get("alert_type", "").replace("_", " ").title(),
                "Entry": ep,
                "Current": current,
                "P&L $": round(pnl_dollar, 2),
                "P&L %": round(pnl_pct, 2),
                "To Stop": round(to_stop, 2),
                "To T1": round(to_t1, 2),
                "To T2": round(to_t2, 2),
            })

        # KPIs
        pnl_color = "#2ecc71" if total_pnl >= 0 else "#e74c3c"
        pk1, pk2, pk3 = st.columns(3)
        pk1.markdown(f"**Paper P&L:** <span style='color:{pnl_color}'>${total_pnl:+,.2f}</span>",
                     unsafe_allow_html=True)
        pk2.markdown(f"**Winning:** {winning}")
        pk3.markdown(f"**Losing:** {losing}")

        if pnl_rows:
            st.dataframe(
                pd.DataFrame(pnl_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Entry": st.column_config.NumberColumn(format="$%.2f"),
                    "Current": st.column_config.NumberColumn(format="$%.2f"),
                    "P&L $": st.column_config.NumberColumn(format="$%.2f"),
                    "P&L %": st.column_config.NumberColumn(format="%.2f%%"),
                    "To Stop": st.column_config.NumberColumn(format="$%.2f"),
                    "To T1": st.column_config.NumberColumn(format="$%.2f"),
                    "To T2": st.column_config.NumberColumn(format="$%.2f"),
                },
            )

st.divider()

# ---------------------------------------------------------------------------
# Alert History (session)
# ---------------------------------------------------------------------------

ui_theme.section_header("Alert History (This Session)")

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
    ui_theme.empty_state("No alerts fired this session.")

# ---------------------------------------------------------------------------
# F10: End-of-Day Summary
# ---------------------------------------------------------------------------

_session_phase = get_session_phase()
_show_eod = _session_phase in ("closed", "last_30", "power_hour")

st.divider()
if _show_eod or st.button("Generate Summary Now", key="gen_summary"):
    ui_theme.section_header("End-of-Day Summary")

    summary = get_session_summary()
    if summary["total"] > 0:
        eod1, eod2, eod3, eod4, eod5 = st.columns(5)
        eod1.metric("Total Signals", summary["total"])
        eod2.metric("BUY / SELL / SHORT",
                     f"{summary['buy_count']} / {summary['sell_count']} / {summary['short_count']}")
        eod3.metric("T1 Hits", summary["t1_hits"])
        eod4.metric("T2 Hits", summary["t2_hits"])
        eod5.metric("Stopped Out", summary["stopped_out"])

        # Signal breakdown by type
        if summary["signals_by_type"]:
            st.markdown("**Signal Breakdown by Type**")
            type_df = pd.DataFrame([
                {"Type": k.replace("_", " ").title(), "Count": v}
                for k, v in summary["signals_by_type"].items()
            ]).sort_values("Count", ascending=False)
            st.dataframe(type_df, use_container_width=True, hide_index=True)
    else:
        ui_theme.empty_state("No alerts recorded for today's session.")

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
