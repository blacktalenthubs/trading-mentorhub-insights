"""Swing Trades — Burns-style EOD scanner with RSI zones & MA setups."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from alerting.alert_store import today_session
from alerting.real_trade_store import (
    calculate_shares,
    close_real_trade,
    get_open_trades,
    has_open_trade,
    open_real_trade,
    stop_real_trade,
    update_trade_notes,
)
from alerting.swing_scanner import (
    get_active_swing_trades,
    get_swing_categories,
    get_swing_trades_history,
)
from analytics.intraday_data import fetch_intraday, get_spy_context
from analytics.swing_rules import check_spy_regime
from db import get_db
import ui_theme

user = ui_theme.setup_page("swing_trades")

ui_theme.page_header(
    "Swing Trades",
    "Burns-style daily setups — EMA crossovers, 200MA reclaims, RSI zones",
)

session = today_session()

# ── Regime Banner ────────────────────────────────────────────────────────

spy_ctx = get_spy_context()
regime_ok = check_spy_regime(spy_ctx)

spy_close = spy_ctx.get("close", 0)
spy_ema20 = spy_ctx.get("spy_ema20", 0)
spy_rsi = spy_ctx.get("spy_rsi14")
spy_dist_pct = ((spy_close - spy_ema20) / spy_ema20 * 100) if spy_ema20 else 0

if regime_ok:
    st.markdown(
        f"<div style='background:rgba(63,185,80,0.12);border:1px solid #3fb950;"
        f"border-radius:8px;padding:1rem 1.2rem;margin-bottom:1rem'>"
        f"<span style='color:#3fb950;font-weight:700;font-size:1.1rem'>"
        f"SPY TRENDING</span>"
        f"<span style='color:#8b949e;font-size:0.85rem;margin-left:1rem'>"
        f"Swing trading active — SPY above 20 EMA</span>"
        f"<br><span style='color:#b1bac4;font-size:0.85rem'>"
        f"Close: ${spy_close:,.2f} · EMA20: ${spy_ema20:,.2f} · "
        f"Distance: {spy_dist_pct:+.2f}%"
        f"{f' · RSI: {spy_rsi:.1f}' if spy_rsi else ''}"
        f"</span></div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<div style='background:rgba(248,81,73,0.12);border:1px solid #f85149;"
        f"border-radius:8px;padding:1rem 1.2rem;margin-bottom:1rem'>"
        f"<span style='color:#f85149;font-weight:700;font-size:1.1rem'>"
        f"SPY NOT TRENDING</span>"
        f"<span style='color:#8b949e;font-size:0.85rem;margin-left:1rem'>"
        f"Swing scanner paused — SPY below 20 EMA</span>"
        f"<br><span style='color:#b1bac4;font-size:0.85rem'>"
        f"Close: ${spy_close:,.2f} · EMA20: ${spy_ema20:,.2f} · "
        f"Distance: {spy_dist_pct:+.2f}%"
        f"{f' · RSI: {spy_rsi:.1f}' if spy_rsi else ''}"
        f"</span></div>",
        unsafe_allow_html=True,
    )

# ── Manual Scan Button ──────────────────────────────────────────────────

col_scan, col_spacer = st.columns([1, 3])
with col_scan:
    if st.button("Run EOD Scan Now"):
        with st.spinner("Running swing scan..."):
            from alerting.swing_scanner import swing_scan_eod

            count = swing_scan_eod()
        st.success(f"Scan complete — {count} signals fired")
        st.rerun()

# ── Active Swing Trades (real_trades) ──────────────────────────────────

ui_theme.section_header("Active Swing Trades")

swing_positions = get_open_trades(trade_type="swing")

if not swing_positions:
    ui_theme.empty_state("No active swing trades. Use 'Took It' on a signal below to start tracking.")
else:
    for pos in swing_positions:
        sym = pos["symbol"]
        shares = pos["shares"]
        entry = pos["entry_price"]
        stop = pos["stop_price"]
        direction = pos["direction"]

        intra = fetch_intraday(sym)
        current = intra["Close"].iloc[-1] if not intra.empty else entry

        if direction == "SHORT":
            unrealized = (entry - current) * shares
        else:
            unrealized = (current - entry) * shares
        pnl_pct = (unrealized / (entry * shares) * 100) if entry * shares > 0 else 0

        entry_date = pos.get("session_date", "")
        days_held = 0
        if entry_date:
            try:
                days_held = (pd.Timestamp.now() - pd.Timestamp(entry_date)).days
            except Exception:
                pass

        pnl_color = "#2ecc71" if unrealized >= 0 else "#e74c3c"
        stop_label = (pos.get("stop_type") or "").replace("_", " ").title()
        rsi_label = pos.get("entry_rsi") or ""

        st.markdown(
            f"**{sym}** — {direction} {shares} shares @ ${entry:,.2f} | "
            f"Now: ${current:,.2f} | "
            f"<span style='color:{pnl_color}'>${unrealized:+,.2f} ({pnl_pct:+.2f}%)</span>"
            f" | Days: {days_held}"
            f"{f' | Stop: {stop_label}' if stop_label else ''}"
            f"{f' | RSI: {rsi_label}' if rsi_label else ''}",
            unsafe_allow_html=True,
        )

        with st.expander(f"Manage {sym} (ID: {pos['id']})"):
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Entry", f"${entry:,.2f}")
            mc2.metric("Current", f"${current:,.2f}")
            if stop:
                mc3.metric("Stop", f"${stop:,.2f}")

            close_col, stop_col = st.columns(2)
            with close_col:
                exit_price = st.number_input(
                    "Exit Price", value=current, step=0.01,
                    key=f"sw_exit_{pos['id']}",
                )
                close_notes = st.text_input("Notes", key=f"sw_notes_close_{pos['id']}")
                if st.button("Close Trade", key=f"sw_close_{pos['id']}"):
                    pnl = close_real_trade(pos["id"], exit_price, close_notes)
                    st.toast(f"Closed {sym} — P&L: ${pnl:+,.2f}")
                    st.rerun()

            with stop_col:
                stop_exit = st.number_input(
                    "Stop Exit Price", value=stop or current, step=0.01,
                    key=f"sw_stop_exit_{pos['id']}",
                )
                stop_notes = st.text_input("Notes", key=f"sw_notes_stop_{pos['id']}")
                if st.button("Stopped Out", key=f"sw_stopped_{pos['id']}"):
                    pnl = stop_real_trade(pos["id"], stop_exit, stop_notes)
                    st.toast(f"Stopped {sym} — P&L: ${pnl:+,.2f}")
                    st.rerun()

            cur_notes = pos.get("notes", "") or ""
            new_notes = st.text_area("Journal", value=cur_notes, key=f"sw_journal_{pos['id']}")
            if new_notes != cur_notes:
                if st.button("Save Notes", key=f"sw_save_notes_{pos['id']}"):
                    update_trade_notes(pos["id"], new_notes)
                    st.toast("Notes saved")
                    st.rerun()

# ── Today's Swing Signals ───────────────────────────────────────────────

ui_theme.section_header("Today's Swing Signals")

# Setup alert_type → stop_type mapping for "Took It"
_STOP_MAP = {
    "swing_ema_crossover_5_20": "ema_cross_under_5_20",
    "swing_200ma_reclaim": "close_below_200ma",
    "swing_pullback_20ema": "close_below_20ema",
}

# Setup alert types that are tradeable BUY setups
_SETUP_TYPES = set(_STOP_MAP.keys())

with get_db() as conn:
    today_signals = conn.execute(
        """SELECT * FROM alerts
           WHERE session_date = ? AND alert_type LIKE 'swing_%'
           ORDER BY created_at DESC""",
        (session,),
    ).fetchall()

if not today_signals:
    ui_theme.empty_state("No swing signals today. Signals fire after market close (4 PM ET).")
else:
    DIR_COLORS = {
        "BUY": "#3fb950", "SELL": "#f85149",
        "SHORT": "#bc8cff", "NOTICE": "#d29922",
    }

    for alert in today_signals:
        alert = dict(alert)
        direction = alert.get("direction", "")
        dir_color = DIR_COLORS.get(direction, "#8b949e")
        symbol = alert.get("symbol", "")
        raw_alert_type = alert.get("alert_type", "")
        alert_type_label = raw_alert_type.replace("swing_", "").replace("_", " ").title()
        message = alert.get("message", "")
        price = alert.get("price", 0)
        alert_id = alert.get("id")
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

        st.markdown(
            f"<div style='background:#161b22;border:1px solid #30363d;border-left:3px solid {dir_color};"
            f"border-radius:6px;padding:0.9rem 1.1rem;margin-bottom:0.6rem'>"
            f"<span style='font-weight:700;font-size:1.05rem'>{symbol}</span> "
            f"<span style='background:{dir_bg};color:{dir_color};padding:2px 8px;border-radius:10px;"
            f"font-size:0.75rem;font-weight:600'>{direction}</span> "
            f"<span style='color:#8b949e;font-size:0.8rem'>{alert_type_label}</span>"
            f"<span style='float:right'>"
            f"<span style='color:#58a6ff;font-size:0.8rem'>{time_str}</span>"
            f"</span>"
            f"<br><span style='font-size:0.82rem;color:#8b949e'>Price: ${price:,.2f}</span>"
            f"<br><span style='font-size:0.85rem;color:#b1bac4;line-height:1.5'>{message}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # "Took It" button — only for BUY setup signals, not management/RSI alerts
        is_setup = direction == "BUY" and raw_alert_type in _SETUP_TYPES
        if is_setup:
            if has_open_trade(symbol):
                st.markdown(
                    "<span style='color:#58a6ff;font-size:0.8rem;font-weight:600'>"
                    "Already tracking</span>",
                    unsafe_allow_html=True,
                )
            else:
                default_shares = calculate_shares(symbol, price) if price > 0 else 100
                shares_input = st.number_input(
                    f"Shares for {symbol}",
                    min_value=1,
                    value=default_shares,
                    step=1,
                    key=f"sw_shares_{alert_id}",
                )
                if st.button("Took It", key=f"sw_took_{alert_id}"):
                    # Extract RSI from the alert message if present
                    entry_rsi = None
                    msg = alert.get("message", "")
                    if "RSI" in msg:
                        import re
                        m = re.search(r"RSI\s*[=:]?\s*([\d.]+)", msg)
                        if m:
                            entry_rsi = float(m.group(1))

                    open_real_trade(
                        symbol=symbol,
                        direction="BUY",
                        entry_price=price,
                        stop_price=None,
                        target_price=None,
                        target_2_price=None,
                        alert_type=raw_alert_type,
                        alert_id=alert_id,
                        session_date=session,
                        shares=shares_input,
                        trade_type="swing",
                        stop_type=_STOP_MAP.get(raw_alert_type),
                        target_type="rsi_70",
                        entry_rsi=entry_rsi,
                    )
                    st.toast(f"Tracking {symbol} — {shares_input} shares @ ${price:,.2f}")
                    st.rerun()

# ── RSI Heatmap ─────────────────────────────────────────────────────────

ui_theme.section_header("RSI Heatmap")

categories = get_swing_categories(session)

if not categories:
    ui_theme.empty_state("No RSI data yet. Run an EOD scan to populate.")
else:
    # Build grid of symbols with RSI color coding
    cols_per_row = 6
    items = [(c["symbol"], c.get("rsi")) for c in categories if c.get("rsi") is not None]
    items.sort(key=lambda x: x[1] if x[1] is not None else 50)

    for i in range(0, len(items), cols_per_row):
        chunk = items[i : i + cols_per_row]
        cols = st.columns(cols_per_row)
        for j, (sym, rsi) in enumerate(chunk):
            with cols[j]:
                if rsi is not None:
                    if rsi < 30:
                        bg = "rgba(63,185,80,0.3)"
                        fg = "#3fb950"
                    elif rsi < 35:
                        bg = "rgba(63,185,80,0.15)"
                        fg = "#3fb950"
                    elif rsi > 70:
                        bg = "rgba(248,81,73,0.3)"
                        fg = "#f85149"
                    elif rsi > 65:
                        bg = "rgba(248,81,73,0.15)"
                        fg = "#f85149"
                    else:
                        bg = "rgba(139,148,158,0.1)"
                        fg = "#8b949e"
                else:
                    bg = "rgba(139,148,158,0.1)"
                    fg = "#8b949e"
                    rsi = 0

                st.markdown(
                    f"<div style='background:{bg};border-radius:6px;padding:0.5rem;"
                    f"text-align:center;margin-bottom:0.4rem'>"
                    f"<span style='font-weight:700;font-size:0.9rem;color:{fg}'>{sym}</span>"
                    f"<br><span style='font-size:0.8rem;color:{fg}'>{rsi:.1f}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

# ── Watchlist Categories ────────────────────────────────────────────────

ui_theme.section_header("Watchlist Categories")

if not categories:
    ui_theme.empty_state("Run an EOD scan to categorise your watchlist.")
else:
    buckets: dict[str, list[dict]] = {
        "buy_zone": [],
        "strongest": [],
        "building_base": [],
        "overbought": [],
        "weak": [],
    }
    for c in categories:
        bucket = c.get("category", "weak")
        if bucket in buckets:
            buckets[bucket].append(c)

    BUCKET_LABELS = {
        "buy_zone": ("Buy Zone", "#3fb950"),
        "strongest": ("Strongest", "#58a6ff"),
        "building_base": ("Building Base", "#d29922"),
        "overbought": ("Overbought", "#f85149"),
        "weak": ("Weak", "#8b949e"),
    }

    tabs = st.tabs([
        f"{label} ({len(buckets[key])})"
        for key, (label, _) in BUCKET_LABELS.items()
    ])

    for tab, (key, (label, color)) in zip(tabs, BUCKET_LABELS.items()):
        with tab:
            if not buckets[key]:
                st.caption(f"No symbols in {label} category.")
            else:
                rows = []
                for c in buckets[key]:
                    rows.append({
                        "Symbol": c["symbol"],
                        "RSI": f"{c.get('rsi', 0):.1f}" if c.get("rsi") else "—",
                        "Category": label,
                    })
                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True,
                )

# ── History ─────────────────────────────────────────────────────────────

with st.expander("Closed Swing Trades"):
    history = get_swing_trades_history(limit=50)
    if not history:
        st.caption("No closed swing trades yet.")
    else:
        rows = []
        for t in history:
            entry = t["entry_price"]
            exit_price = t.get("current_price") or entry
            pnl = t.get("pnl_pct", 0) or 0
            rows.append({
                "Symbol": t["symbol"],
                "Setup": t["alert_type"].replace("swing_", "").replace("_", " ").title(),
                "Entry": f"${entry:,.2f}",
                "Exit": f"${exit_price:,.2f}",
                "P&L%": f"{pnl:+.2f}%",
                "Status": t["status"].replace("_", " ").title(),
                "Entry Date": t.get("entry_date", ""),
                "Closed Date": t.get("closed_date", ""),
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )
