"""Scanner — Intraday signal scanner + Swing trade scanner with mode toggle."""

from __future__ import annotations

import re

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

from config import DEFAULT_POSITION_SIZE
from analytics.market_data import classify_day, fetch_ohlc
from analytics.signal_engine import (
    scan_watchlist, SignalResult, action_label, action_color, action_help,
)
from analytics.intraday_data import (
    fetch_intraday, fetch_prior_day, get_spy_context,
    fetch_premarket_bars, compute_premarket_brief,
    fetch_hourly_bars, detect_hourly_support,
)
from analytics.intraday_rules import evaluate_rules
from analytics.market_hours import is_market_hours, is_premarket, get_session_phase
from analytics.swing_rules import check_spy_regime
from alerting.alert_store import get_active_entries, today_session
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
from alerting.options_trade_store import (
    has_open_options_trade, open_options_trade,
)
from alert_config import OPTIONS_ELIGIBLE_SYMBOLS, OPTIONS_MIN_SCORE
from db import get_db, get_watchlist
import ui_theme

from ui_theme import get_current_tier, render_inline_upgrade

# ── Page setup ────────────────────────────────────────────────────────────────

user = ui_theme.setup_page("scanner", tier_required="free")

# ── Mode toggle ───────────────────────────────────────────────────────────────

scan_mode = st.radio("Mode", ["Intraday", "Swing"], horizontal=True, key="scan_mode")

# ═══════════════════════════════════════════════════════════════════════════════
# SWING MODE
# ═══════════════════════════════════════════════════════════════════════════════

if scan_mode == "Swing":
    _is_free = get_current_tier() == "free"
    _user_watchlist = set(get_watchlist(user["id"] if user else None))

    ui_theme.page_header(
        "Swing Trades",
        "Burns-style daily setups -- EMA crossovers, 200MA reclaims, RSI zones",
    )

    session = today_session()

    # ── Regime Banner ─────────────────────────────────────────────────────

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
            f"Swing trading active -- SPY above 20 EMA</span>"
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
            f"Swing scanner paused -- SPY below 20 EMA</span>"
            f"<br><span style='color:#b1bac4;font-size:0.85rem'>"
            f"Close: ${spy_close:,.2f} · EMA20: ${spy_ema20:,.2f} · "
            f"Distance: {spy_dist_pct:+.2f}%"
            f"{f' · RSI: {spy_rsi:.1f}' if spy_rsi else ''}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

    # ── Tier gating for Swing mode ────────────────────────────────────────
    if _is_free:
        render_inline_upgrade("Full swing trade scanner with EOD setups", "pro")
        st.stop()

    # ── Manual Scan Button ────────────────────────────────────────────────

    col_scan, col_spacer = st.columns([1, 3])
    with col_scan:
        if st.button("Run EOD Scan Now"):
            with st.spinner("Running swing scan..."):
                from alerting.swing_scanner import swing_scan_eod

                count = swing_scan_eod()
            st.success(f"Scan complete -- {count} signals fired")
            st.rerun()

    # ── Active Swing Trades (real_trades) ─────────────────────────────────

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
                f"**{sym}** -- {direction} {shares} shares @ ${entry:,.2f} | "
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
                        st.toast(f"Closed {sym} -- P&L: ${pnl:+,.2f}")
                        st.rerun()

                with stop_col:
                    stop_exit = st.number_input(
                        "Stop Exit Price", value=stop or current, step=0.01,
                        key=f"sw_stop_exit_{pos['id']}",
                    )
                    stop_notes = st.text_input("Notes", key=f"sw_notes_stop_{pos['id']}")
                    if st.button("Stopped Out", key=f"sw_stopped_{pos['id']}"):
                        pnl = stop_real_trade(pos["id"], stop_exit, stop_notes)
                        st.toast(f"Stopped {sym} -- P&L: ${pnl:+,.2f}")
                        st.rerun()

                cur_notes = pos.get("notes", "") or ""
                new_notes = st.text_area("Journal", value=cur_notes, key=f"sw_journal_{pos['id']}")
                if new_notes != cur_notes:
                    if st.button("Save Notes", key=f"sw_save_notes_{pos['id']}"):
                        update_trade_notes(pos["id"], new_notes)
                        st.toast("Notes saved")
                        st.rerun()

    # ── Today's Swing Signals ─────────────────────────────────────────────

    ui_theme.section_header("Today's Swing Signals")

    # Setup alert_type -> stop_type mapping for "Track This"
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
        today_signals = [s for s in today_signals if s["symbol"] in _user_watchlist]

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

            _score = alert.get("score", 0) or 0
            _confidence = alert.get("confidence", "")
            _sw_opts_eligible = (
                symbol in OPTIONS_ELIGIBLE_SYMBOLS
                and _score >= OPTIONS_MIN_SCORE
                and _confidence == "high"
            )
            _sw_opts_badge = (
                " <span style='background:#9b59b6;color:white;padding:2px 6px;"
                "border-radius:3px;font-size:0.75em;font-weight:bold'>OPTIONS PLAY</span>"
                if _sw_opts_eligible else ""
            )

            st.markdown(
                f"<div style='background:#161b22;border:1px solid #30363d;border-left:3px solid {dir_color};"
                f"border-radius:6px;padding:0.9rem 1.1rem;margin-bottom:0.6rem'>"
                f"<span style='font-weight:700;font-size:1.05rem'>{symbol}</span> "
                f"<span style='background:{dir_bg};color:{dir_color};padding:2px 8px;border-radius:10px;"
                f"font-size:0.75rem;font-weight:600'>{direction}</span> "
                f"<span style='color:#8b949e;font-size:0.8rem'>{alert_type_label}</span>"
                f"{_sw_opts_badge}"
                f"<span style='float:right'>"
                f"<span style='color:#58a6ff;font-size:0.8rem'>{time_str}</span>"
                f"</span>"
                f"<br><span style='font-size:0.82rem;color:#8b949e'>Price: ${price:,.2f}</span>"
                f"<br><span style='font-size:0.85rem;color:#b1bac4;line-height:1.5'>{message}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # "Track This" button -- only for BUY setup signals, not management/RSI alerts
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
                    if st.button("Track This", key=f"sw_took_{alert_id}"):
                        # Extract RSI from the alert message if present
                        entry_rsi = None
                        msg = alert.get("message", "")
                        if "RSI" in msg:
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
                        st.toast(f"Tracking {symbol} -- {shares_input} shares @ ${price:,.2f}")
                        st.rerun()

            # Options play form
            if _sw_opts_eligible and direction == "BUY":
                if has_open_options_trade(symbol):
                    st.info("Options trade already tracking (see Real Trades)")
                else:
                    st.markdown(
                        "<span style='color:#9b59b6;font-weight:bold'>"
                        "Track Options Play</span>",
                        unsafe_allow_html=True,
                    )
                    _swc1, _swc2 = st.columns(2)
                    _sw_opt_type = _swc1.radio(
                        "Type", ["CALL", "PUT"],
                        key=f"sw_opt_type_{alert_id}",
                        horizontal=True,
                    )
                    _sw_opt_strike = _swc2.number_input(
                        "Strike", value=round(price, 0),
                        step=1.0, format="%.2f",
                        key=f"sw_opt_strike_{alert_id}",
                    )
                    _swc3, _swc4 = st.columns(2)
                    _sw_opt_expiry = _swc3.date_input(
                        "Expiration",
                        key=f"sw_opt_expiry_{alert_id}",
                    )
                    _sw_opt_contracts = _swc4.number_input(
                        "Contracts", min_value=1, value=1, step=1,
                        key=f"sw_opt_contracts_{alert_id}",
                    )
                    _sw_opt_premium = st.number_input(
                        "Premium per contract",
                        min_value=0.01, value=1.00, step=0.05,
                        format="%.2f",
                        key=f"sw_opt_premium_{alert_id}",
                    )
                    _sw_opt_cost = _sw_opt_contracts * _sw_opt_premium * 100
                    st.caption(
                        f"{_sw_opt_contracts} x ${_sw_opt_premium:.2f} x 100 = "
                        f"${_sw_opt_cost:,.0f} total cost"
                    )
                    if st.button(
                        "Track Options",
                        key=f"sw_opt_track_{alert_id}",
                        type="primary",
                    ):
                        open_options_trade(
                            symbol=symbol,
                            option_type=_sw_opt_type,
                            strike=_sw_opt_strike,
                            expiration=_sw_opt_expiry.isoformat(),
                            contracts=_sw_opt_contracts,
                            premium_per_contract=_sw_opt_premium,
                            alert_type=raw_alert_type,
                            alert_id=alert_id,
                            session_date=session,
                        )
                        st.toast(
                            f"Tracking {symbol} {_sw_opt_type} "
                            f"${_sw_opt_strike:.0f} -- ${_sw_opt_cost:,.0f}"
                        )
                        st.rerun()

    # ── RSI Heatmap ───────────────────────────────────────────────────────

    ui_theme.section_header("RSI Heatmap")

    _all_categories = get_swing_categories(session)
    categories = [c for c in _all_categories if c["symbol"] in _user_watchlist]

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

    # ── Watchlist Categories ──────────────────────────────────────────────

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
                            "RSI": f"{c.get('rsi', 0):.1f}" if c.get("rsi") else "--",
                            "Category": label,
                        })
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )

    # ── History ───────────────────────────────────────────────────────────

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

# ═══════════════════════════════════════════════════════════════════════════════
# INTRADAY MODE
# ═══════════════════════════════════════════════════════════════════════════════

else:
    # ── Sync active positions from DB (survive page refresh) ──────────────
    if "active_positions" not in st.session_state:
        st.session_state["active_positions"] = {}
    if "_db_positions_loaded" not in st.session_state:
        open_trades = get_open_trades()
        for t in open_trades:
            st.session_state["active_positions"][t["symbol"]] = {
                "entry": t["entry_price"],
                "shares": t["shares"],
                "trade_id": t["id"],
            }
        st.session_state["_db_positions_loaded"] = True

    # ── Auto-refresh during market hours / pre-market ─────────────────────
    _market_open = is_market_hours()
    _premarket = is_premarket()
    if _market_open:
        st_autorefresh(interval=180_000, key="scanner_refresh")  # 3 min
    elif _premarket:
        st_autorefresh(interval=120_000, key="scanner_pm_refresh")  # 2 min

    # ── Cached helpers ────────────────────────────────────────────────────

    @st.cache_data(ttl=300, show_spinner="Scanning watchlist...")
    def _cached_scan(syms: tuple[str, ...]) -> list[dict]:
        """Scan and return serializable dicts (dataclass not cacheable)."""
        results = scan_watchlist(list(syms))
        return [
            {
                "symbol": r.symbol,
                "last_close": r.last_close,
                "prior_high": r.prior_high,
                "prior_low": r.prior_low,
                "nearest_support": r.nearest_support,
                "support_label": r.support_label,
                "support_status": r.support_status,
                "distance_to_support": r.distance_to_support,
                "distance_pct": r.distance_pct,
                "entry": r.entry,
                "stop": r.stop,
                "target_1": r.target_1,
                "target_2": r.target_2,
                "reentry_stop": r.reentry_stop,
                "risk_per_share": r.risk_per_share,
                "rr_ratio": r.rr_ratio,
                "pattern": r.pattern,
                "direction": r.direction,
                "bias": r.bias,
                "day_range": r.day_range,
                "ma20": r.ma20,
                "ma50": r.ma50,
                "avg_volume": r.avg_volume,
                "last_volume": r.last_volume,
                "volume_ratio": r.volume_ratio,
                "score": r.score,
                "score_label": r.score_label,
            }
            for r in results
        ]

    @st.cache_data(ttl=300)
    def _cached_fetch(symbol: str) -> pd.DataFrame:
        return fetch_ohlc(symbol, "3mo")

    @st.cache_data(ttl=180, show_spinner=False)
    def _cached_intraday(symbol: str) -> pd.DataFrame:
        return fetch_intraday(symbol)

    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_prior_day(symbol: str) -> dict | None:
        return fetch_prior_day(symbol)

    @st.cache_data(ttl=60, show_spinner=False)
    def _cached_active_entries(symbol: str, session_date: str, user_id: int | None = None) -> list[dict]:
        """Active alert entries for a symbol today (1-min cache)."""
        return get_active_entries(symbol, session_date, user_id=user_id)

    def _get_alert_narrative(symbol: str, session_date: str) -> str:
        """Fetch the most recent AI narrative for a symbol from today's alerts."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT narrative FROM alerts WHERE symbol=? AND session_date=? AND narrative != '' ORDER BY created_at DESC LIMIT 1",
                (symbol, session_date),
            ).fetchone()
            return row["narrative"] if row else ""

    # Shared chart helpers (from ui_theme)
    _add_level_line = ui_theme.add_level_line
    _volume_colors = ui_theme.volume_colors
    _build_candlestick_fig = ui_theme.build_candlestick_fig

    def _draw_mini_chart(r: SignalResult):
        """30-day candlestick + volume chart with levels."""
        hist = _cached_fetch(r.symbol)
        if hist.empty:
            st.caption("Chart data unavailable.")
            return

        hist = hist.copy()
        hist["MA20"] = hist["Close"].rolling(window=20).mean()
        hist["MA50"] = hist["Close"].rolling(window=50).mean()
        chart = hist.tail(30).copy()

        # Gap-free integer x-axis
        x_int = list(range(len(chart)))
        date_labels = chart.index.strftime("%b %d")
        step = max(1, len(chart) // 8)
        tick_vals = x_int[::step]
        tick_text = [date_labels[i] for i in tick_vals]

        fig = _build_candlestick_fig(
            chart, x_int, r.symbol,
            height=450, tick_vals=tick_vals, tick_text=tick_text,
        )

        # Moving averages
        for col, label, color in [("MA20", "20 MA", "#f39c12"), ("MA50", "50 MA", "#9b59b6")]:
            ma = chart[col].dropna()
            if not ma.empty:
                ma_x = [x_int[chart.index.get_loc(idx)] for idx in ma.index]
                fig.add_trace(go.Scatter(
                    x=ma_x, y=ma.values,
                    mode="lines", name=label,
                    line=dict(color=color, width=1.5),
                ))

        # Key levels -- alternate left/right to reduce overlap
        _add_level_line(fig, r.entry, "WATCH", "#3498db", position="top left")
        _add_level_line(fig, r.stop, "RISK", "#e74c3c", position="bottom right")
        _add_level_line(fig, r.target_1, "TARGET", "#2ecc71", position="top right")
        _add_level_line(fig, r.nearest_support, "SUPPORT", "#f39c12",
                        position="bottom left", dash="dot", width=1)

        st.plotly_chart(fig, use_container_width=True, config=ui_theme.PLOTLY_CONFIG)

    def _draw_intraday_chart(symbol: str, bars: pd.DataFrame, prior: dict | None, r: SignalResult):
        """5-minute intraday candlestick + volume chart with key levels."""
        if bars.empty:
            return

        chart = bars.copy()

        # Gap-free integer x-axis with time labels
        x_int = list(range(len(chart)))
        time_labels = chart.index.strftime("%H:%M")
        step = max(1, len(chart) // 10)
        tick_vals = x_int[::step]
        tick_text = [time_labels[i] for i in tick_vals]

        fig = _build_candlestick_fig(
            chart, x_int, symbol,
            height=380, tick_vals=tick_vals, tick_text=tick_text,
        )

        # Prior day levels
        if prior:
            _add_level_line(fig, prior["high"], "Prior High", "#e74c3c",
                            position="top right", dash="dot", width=1)
            _add_level_line(fig, prior["low"], "Prior Low", "#2ecc71",
                            position="bottom right", dash="dot", width=1)

        # Key levels
        _add_level_line(fig, r.entry, "Watch", "#3498db", position="top left")
        _add_level_line(fig, r.stop, "Risk", "#e74c3c", position="bottom left")
        _add_level_line(fig, r.target_1, "T1", "#2ecc71", position="top right")

        st.plotly_chart(fig, use_container_width=True, config=ui_theme.PLOTLY_CONFIG_MINIMAL)

    # ── Page layout ───────────────────────────────────────────────────────

    ui_theme.page_header("Signal Scanner", "Trade plans for your watchlist -- entry, stop, target, re-entry at a glance")

    # ── Sidebar ───────────────────────────────────────────────────────────

    with st.sidebar:
        ui_theme.render_sidebar_watchlist(user)

        st.divider()
        position_size = st.number_input(
            "Position Size ($)", value=DEFAULT_POSITION_SIZE, step=5000,
        )

    # ── Parse & scan ──────────────────────────────────────────────────────

    symbols = list(st.session_state["watchlist"])
    if not symbols:
        ui_theme.empty_state("Enter at least one symbol in the sidebar.")
        st.stop()

    raw_results = _cached_scan(tuple(symbols))
    results: list[SignalResult] = [SignalResult(**d) for d in raw_results]

    # ── Alert-driven plan overlay (market hours only) ─────────────────────
    _alert_entries: dict[str, dict] = {}
    _session = today_session()
    if _market_open:
        for r in results:
            entries = _cached_active_entries(r.symbol, _session, user_id=user["id"])
            if entries:
                ae = entries[-1]  # most recent active entry
                _alert_entries[r.symbol] = ae
                r.entry = ae["entry_price"]
                r.stop = ae["stop_price"]
                r.target_1 = ae["target_1"]
                r.target_2 = ae["target_2"]
                r.risk_per_share = r.entry - r.stop if r.entry > r.stop else r.risk_per_share
                r.rr_ratio = (r.target_1 - r.entry) / r.risk_per_share if r.risk_per_share > 0 else 0
                r.reentry_stop = r.stop - 1.50

    # ── Intraday price overlay (market hours only) ────────────────────────
    if _market_open:
        for r in results:
            _live = _cached_intraday(r.symbol)
            if not _live.empty:
                r.last_close = _live["Close"].iloc[-1]

    if not results:
        ui_theme.empty_state("No scan results returned.", icon="warning")
        st.stop()

    # ── KPI Row ───────────────────────────────────────────────────────────

    potential_entries = sum(1 for r in results if r.support_status == "AT SUPPORT" and r.score >= 65)
    avg_score = int(sum(r.score for r in results) / len(results)) if results else 0

    _phase = get_session_phase()
    _phase_labels = {
        "premarket": "Pre-Market",
        "market": "Market Open",
        "afterhours": "After Hours",
        "closed": "Closed",
    }
    _market_label = _phase_labels.get(_phase, _phase.replace("_", " ").title())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Scanned", len(results))
    col2.metric("Potential Entries", potential_entries, help=action_help("AT SUPPORT"))
    col3.metric("Avg Score", avg_score)
    col4.metric("Market", _market_label)

    st.divider()

    # ── Pre-Market Brief (4:00-9:29 AM ET only) ──────────────────────────

    if _premarket:
        ui_theme.section_header("Pre-Market Brief", "Watchlist insights before the bell")

        # Gather PM data for all symbols
        _pm_briefs: list[dict] = []
        for sym in symbols:
            pm_bars = fetch_premarket_bars(sym)
            if pm_bars.empty:
                continue
            prior = _cached_prior_day(sym)
            brief = compute_premarket_brief(sym, pm_bars, prior)
            if brief:
                _pm_briefs.append(brief)

        if _pm_briefs:
            # SPY Pre-Market Context card
            _spy_briefs = [b for b in _pm_briefs if b["symbol"] == "SPY"]
            if _spy_briefs:
                spy_pm = _spy_briefs[0]
                gap_dir = "UP" if spy_pm["gap_pct"] > 0 else "DOWN" if spy_pm["gap_pct"] < 0 else "FLAT"
                gap_color = "#2ecc71" if spy_pm["gap_pct"] > 0 else "#e74c3c" if spy_pm["gap_pct"] < 0 else "#888"
                sc1, sc2, sc3, sc4 = st.columns(4)
                sc1.metric("SPY PM Price", f"${spy_pm['pm_last']:,.2f}")
                sc2.metric("SPY Gap", f"{spy_pm['gap_pct']:+.2f}%")
                sc3.metric("SPY PM Range", f"{spy_pm['pm_range_pct']:.2f}%")
                sc4.metric("SPY Direction", gap_dir)

            # Sort by priority score descending
            _pm_briefs.sort(key=lambda b: b["priority_score"], reverse=True)

            # Watchlist Priority Table
            pm_rows = []
            for b in _pm_briefs:
                priority_color = {"HIGH": "#2ecc71", "MEDIUM": "#f39c12", "LOW": "#888"}.get(b["priority_label"], "#888")
                pm_rows.append({
                    "Symbol": b["symbol"],
                    "PM Price": b["pm_last"],
                    "Change%": b["pm_change_pct"],
                    "Gap%": b["gap_pct"],
                    "PM High": b["pm_high"],
                    "PM Low": b["pm_low"],
                    "Flags": ", ".join(b["flags"]) if b["flags"] else "-",
                    "Score": b["priority_score"],
                    "Priority": b["priority_label"],
                })

            pm_df = pd.DataFrame(pm_rows)

            def _color_priority(val):
                colors = {"HIGH": "#2ecc71", "MEDIUM": "#f39c12", "LOW": "#888"}
                color = colors.get(val, "")
                return f"color: {color}; font-weight: bold" if color else ""

            def _color_change(val):
                if isinstance(val, (int, float)):
                    if val > 0:
                        return "color: #2ecc71"
                    if val < 0:
                        return "color: #e74c3c"
                return ""

            st.dataframe(
                pm_df.style
                .format({
                    "PM Price": "${:,.2f}",
                    "PM High": "${:,.2f}",
                    "PM Low": "${:,.2f}",
                    "Change%": "{:+.2f}%",
                    "Gap%": "{:+.2f}%",
                })
                .applymap(_color_priority, subset=["Priority"])
                .applymap(_color_change, subset=["Change%", "Gap%"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No pre-market data available yet. Data appears after 4:00 AM ET.")

        st.divider()

    # ── Trade Plans (expandable cards) ────────────────────────────────────

    ui_theme.section_header("Trade Plans")

    for r in results:
        _label = action_label(r.support_status, r.score)
        _acolor = action_color(r.support_status, r.score)

        _live_tag = " | LIVE" if r.symbol in _alert_entries else ""
        _pattern_tag = f" | {r.pattern.upper()}" if r.pattern != "normal" else ""
        _opts_tag = " | OPTIONS" if r.symbol in OPTIONS_ELIGIBLE_SYMBOLS and r.score >= OPTIONS_MIN_SCORE else ""

        with st.expander(
            f"{r.symbol}  |  {_label}  |  {r.score_label} ({r.score})"
            f"  |  ${r.last_close:,.2f}{_live_tag}{_pattern_tag}{_opts_tag}"
        ):
            # ── Signal card summary ───────────────────────────────────
            ui_theme.render_signal_card(
                symbol=r.symbol,
                score_label=r.score_label,
                score=r.score,
                status_label=_label,
                status_color=_acolor,
                price=r.last_close,
                support_level=r.nearest_support,
                support_name=r.support_label,
                distance_pct=r.distance_pct,
                ma20=r.ma20,
                ma50=r.ma50,
                is_live=r.symbol in _alert_entries,
                pattern=r.pattern,
            )

            # ── Key levels ────────────────────────────────────────────
            st.markdown("**Key Levels**")
            tc1, tc2, tc3, tc4, tc5 = st.columns(5)
            tc1.metric("Watch Near", f"${r.entry:,.2f}")
            tc2.metric("Risk Below", f"${r.stop:,.2f}",
                        delta=f"-${r.risk_per_share:,.2f}/sh", delta_color="off")
            tc3.metric("Target 1", f"${r.target_1:,.2f}")
            tc4.metric("Target 2", f"${r.target_2:,.2f}")
            tc5.metric("R:R", f"{r.rr_ratio:.1f}:1",
                        delta="GOOD" if r.rr_ratio >= 1.5 else "WEAK",
                        delta_color="normal" if r.rr_ratio >= 1.5 else "inverse")

            # ── Context ───────────────────────────────────────────────
            st.markdown(
                f"<span style='color:{_acolor};font-weight:600'>{_label}</span>"
                f" &mdash; {r.pattern.upper()} Day, {r.direction.title()}",
                unsafe_allow_html=True,
            )

            # LIVE plan banner
            if r.symbol in _alert_entries:
                _ae = _alert_entries[r.symbol]
                _ae_type = _ae.get("alert_type", "alert").replace("_", " ").title()
                st.markdown(
                    f"<div style='padding:8px 12px;border:2px solid #2ecc71;"
                    f"border-radius:6px;background:#2ecc7115;margin-bottom:12px'>"
                    f"<strong style='color:#2ecc71'>LIVE</strong> &mdash; "
                    f"from <em>{_ae_type}</em> alert. "
                    f"Levels updated from intraday signal.</div>",
                    unsafe_allow_html=True,
                )

            # AI Thesis (primary context)
            _narrative = _get_alert_narrative(r.symbol, _session)
            if _narrative:
                st.markdown(
                    f"<div style='padding:10px 14px;border-left:4px solid #3498db;"
                    f"background:#3498db10;border-radius:4px;margin:8px 0;font-size:0.95rem'>"
                    f"<strong>AI Thesis:</strong> {_narrative}</div>",
                    unsafe_allow_html=True,
                )

            # ── Pre-market metrics (if premarket) ─────────────────────
            if _premarket:
                _sym_pm_bars = fetch_premarket_bars(r.symbol)
                _sym_prior = _cached_prior_day(r.symbol)
                _sym_pm = compute_premarket_brief(r.symbol, _sym_pm_bars, _sym_prior) if not _sym_pm_bars.empty else None
                if _sym_pm:
                    st.markdown("**Pre-Market**")
                    pm1, pm2, pm3, pm4 = st.columns(4)
                    pm1.metric("PM Price", f"${_sym_pm['pm_last']:,.2f}",
                                delta=f"{_sym_pm['pm_change_pct']:+.2f}%", delta_color="off")
                    pm2.metric("PM High", f"${_sym_pm['pm_high']:,.2f}")
                    pm3.metric("PM Low", f"${_sym_pm['pm_low']:,.2f}")
                    pm4.metric("Gap", f"{_sym_pm['gap_pct']:+.2f}%",
                                delta=_sym_pm["gap_type"].replace("_", " ").upper(), delta_color="off")
                    if _sym_pm["flags"]:
                        flag_badges = " ".join(
                            f"<span style='background:#1e3a5f;padding:2px 8px;border-radius:4px;"
                            f"font-size:0.8rem;margin-right:4px'>{f}</span>"
                            for f in _sym_pm["flags"]
                        )
                        st.markdown(flag_badges, unsafe_allow_html=True)

            # ── Key levels ────────────────────────────────────────────
            st.markdown("**Key Levels**")
            lc1, lc2, lc3, lc4 = st.columns(4)
            lc1.metric("Prior High", f"${r.prior_high:,.2f}")
            lc2.metric("Prior Low", f"${r.prior_low:,.2f}")
            lc3.metric("Nearest Support", f"${r.nearest_support:,.2f}",
                        delta=f"{r.support_label}", delta_color="off")
            lc4.metric("Distance", f"${r.distance_to_support:,.2f}",
                        delta=f"{r.distance_pct:+.2f}%", delta_color="off")

            # ── Live status metrics (LIVE plan, market hours) ─────────
            if r.symbol in _alert_entries and _market_open:
                _live_bars = _cached_intraday(r.symbol)
                if not _live_bars.empty:
                    _live_price = _live_bars["Close"].iloc[-1]
                    _live_high = _live_bars["High"].max()
                    _live_low = _live_bars["Low"].min()
                    _to_stop = _live_price - r.stop
                    _to_t1 = r.target_1 - _live_price
                    _to_t2 = r.target_2 - _live_price

                    st.markdown("**Live Status**")
                    ls1, ls2, ls3, ls4 = st.columns(4)
                    ls1.metric("Current", f"${_live_price:,.2f}")
                    ls2.metric("To Stop", f"${_to_stop:,.2f}",
                               delta="SAFE" if _to_stop > 0 else "STOPPED",
                               delta_color="normal" if _to_stop > 0 else "inverse")
                    ls3.metric("To T1", f"${_to_t1:,.2f}",
                               delta="HIT" if _to_t1 <= 0 else f"${_to_t1:,.2f} away",
                               delta_color="normal" if _to_t1 <= 0 else "off")
                    ls4.metric("To T2", f"${_to_t2:,.2f}",
                               delta="HIT" if _to_t2 <= 0 else f"${_to_t2:,.2f} away",
                               delta_color="normal" if _to_t2 <= 0 else "off")

                    # Progress bar: stop -> T2 range
                    _total_range = r.target_2 - r.stop
                    if _total_range > 0:
                        _progress = (_live_price - r.stop) / _total_range
                        _progress = max(0.0, min(1.0, _progress))
                        st.progress(_progress, text=f"Stop -> T2: {_progress:.0%}")

                    # Levels hit badges
                    _hits = []
                    if _live_high >= r.target_1:
                        _hits.append(("T1 HIT", "#2ecc71"))
                    if _live_high >= r.target_2:
                        _hits.append(("T2 HIT", "#27ae60"))
                    if _live_low <= r.stop:
                        _hits.append(("STOP HIT", "#e74c3c"))
                    if _hits:
                        _badges = " ".join(
                            f"<span style='background:{c};padding:2px 8px;border-radius:4px;"
                            f"font-size:0.8rem;color:white;margin-right:4px'>{lbl}</span>"
                            for lbl, c in _hits
                        )
                        st.markdown(_badges, unsafe_allow_html=True)

            # ── MA context ────────────────────────────────────────────
            ma_parts = [f"Close ${r.last_close:,.2f}"]
            if r.ma20 is not None:
                pos = "above" if r.last_close > r.ma20 else "below"
                ma_parts.append(f"20MA ${r.ma20:,.2f} ({pos})")
            if r.ma50 is not None:
                pos = "above" if r.last_close > r.ma50 else "below"
                ma_parts.append(f"50MA ${r.ma50:,.2f} ({pos})")
            if r.volume_ratio > 0:
                ma_parts.append(f"Vol {r.volume_ratio:.1f}x avg")
            st.caption(" | ".join(ma_parts))

            # ── Mini chart ────────────────────────────────────────────
            _draw_mini_chart(r)

            # ── Intraday section ──────────────────────────────────────
            st.divider()
            intra_bars = _cached_intraday(r.symbol)
            prior = _cached_prior_day(r.symbol)

            if _market_open:
                st.markdown("**Intraday (5m)**")

                if not intra_bars.empty:
                    # Current price and intraday stats
                    current_price = intra_bars["Close"].iloc[-1]
                    intra_high = intra_bars["High"].max()
                    intra_low = intra_bars["Low"].min()

                    ic1, ic2, ic3, ic4 = st.columns(4)
                    ic1.metric("Current", f"${current_price:,.2f}")
                    ic2.metric("Intraday High", f"${intra_high:,.2f}")
                    ic3.metric("Intraday Low", f"${intra_low:,.2f}")

                    # Which levels hit
                    levels_hit = []
                    if intra_high >= r.target_1:
                        levels_hit.append("T1")
                    if intra_high >= r.target_2:
                        levels_hit.append("T2")
                    if intra_low <= r.stop:
                        levels_hit.append("Stop")
                    ic4.metric("Levels Hit", ", ".join(levels_hit) if levels_hit else "None")

                    # Evaluate intraday rules
                    active_entries = []
                    positions = st.session_state.get("active_positions", {})
                    if r.symbol in positions:
                        pos_data = positions[r.symbol]
                        active_entries.append({
                            "entry_price": pos_data["entry"],
                            "stop_price": r.stop,
                            "target_1": r.target_1,
                            "target_2": r.target_2,
                        })

                    _spy_ctx = get_spy_context()
                    signals = evaluate_rules(r.symbol, intra_bars, prior, active_entries, spy_context=_spy_ctx)
                    if signals:
                        for sig in signals:
                            _dir_label, sig_color = ui_theme.display_direction(sig.direction)
                            st.markdown(
                                f"<div style='padding:8px 12px;border-left:4px solid {sig_color};"
                                f"background:{sig_color}15;margin-bottom:8px;border-radius:4px'>"
                                f"<strong style='color:{sig_color}'>{_dir_label}</strong> "
                                f"&mdash; {sig.message}</div>",
                                unsafe_allow_html=True,
                            )

                    _draw_intraday_chart(r.symbol, intra_bars, prior, r)
                else:
                    st.caption("No intraday data available yet.")
            else:
                st.caption("Market closed -- intraday data available during market hours (9:30-16:00 ET)")

            # ── Position tracking (persisted to real_trades DB) ───────
            st.divider()
            st.markdown("**Track Position**")

            pos_key = r.symbol
            is_tracking = pos_key in st.session_state["active_positions"]

            tracking = st.checkbox(
                "I'm in this trade", value=is_tracking, key=f"track_{r.symbol}",
            )

            if tracking and not is_tracking:
                from datetime import date as _date
                _shares_key = f"shares_{r.symbol}"
                default_shares = int(position_size / r.entry) if r.entry > 0 else 0
                if _shares_key not in st.session_state:
                    st.session_state[_shares_key] = default_shares
                shares_input = st.number_input(
                    "Shares",
                    min_value=1,
                    step=1,
                    key=_shares_key,
                    help=f"Default: {default_shares} (${position_size / 1000:.0f}k / ${r.entry:,.2f})",
                )
                exposure = shares_input * r.entry
                st.caption(f"{shares_input} x ${r.entry:,.2f} = ${exposure:,.0f}")

                if st.button("Confirm Trade", key=f"confirm_{r.symbol}", type="primary",
                             use_container_width=True):
                    if not has_open_trade(r.symbol):
                        trade_id = open_real_trade(
                            symbol=r.symbol,
                            direction="BUY",
                            entry_price=r.entry,
                            stop_price=r.stop,
                            target_price=r.target_1,
                            target_2_price=r.target_2,
                            alert_type="scanner_manual",
                            alert_id=None,
                            session_date=_date.today().isoformat(),
                            shares=shares_input,
                        )
                    else:
                        _existing = [
                            t for t in get_open_trades() if t["symbol"] == r.symbol
                        ]
                        trade_id = _existing[0]["id"] if _existing else None
                    st.session_state["active_positions"][pos_key] = {
                        "entry": r.entry,
                        "shares": shares_input,
                        "trade_id": trade_id,
                    }
                    st.rerun()

            # Options play form
            if r.symbol in OPTIONS_ELIGIBLE_SYMBOLS and r.score >= OPTIONS_MIN_SCORE:
                st.markdown("---")
                if has_open_options_trade(r.symbol):
                    st.info("Options trade already tracking (see Real Trades)")
                else:
                    st.markdown(
                        "<span style='color:#9b59b6;font-weight:bold'>"
                        "Track Options Play</span>",
                        unsafe_allow_html=True,
                    )
                    _oc1, _oc2 = st.columns(2)
                    _opt_type = _oc1.radio(
                        "Type", ["CALL", "PUT"],
                        key=f"scan_opt_type_{r.symbol}",
                        horizontal=True,
                    )
                    _opt_strike = _oc2.number_input(
                        "Strike", value=round(r.entry, 0),
                        step=1.0, format="%.2f",
                        key=f"scan_opt_strike_{r.symbol}",
                    )
                    _oc3, _oc4 = st.columns(2)
                    _opt_expiry = _oc3.date_input(
                        "Expiration",
                        key=f"scan_opt_expiry_{r.symbol}",
                    )
                    _opt_contracts = _oc4.number_input(
                        "Contracts", min_value=1, value=1, step=1,
                        key=f"scan_opt_contracts_{r.symbol}",
                    )
                    _opt_premium = st.number_input(
                        "Premium per contract",
                        min_value=0.01, value=1.00, step=0.05,
                        format="%.2f",
                        key=f"scan_opt_premium_{r.symbol}",
                    )
                    _opt_cost = _opt_contracts * _opt_premium * 100
                    st.caption(
                        f"{_opt_contracts} x ${_opt_premium:.2f} x 100 = "
                        f"${_opt_cost:,.0f} total cost"
                    )
                    if st.button(
                        "Track Options",
                        key=f"scan_opt_track_{r.symbol}",
                        type="primary",
                    ):
                        from datetime import date as _date

                        open_options_trade(
                            symbol=r.symbol,
                            option_type=_opt_type,
                            strike=_opt_strike,
                            expiration=_opt_expiry.isoformat(),
                            contracts=_opt_contracts,
                            premium_per_contract=_opt_premium,
                            alert_type="scanner_manual",
                            alert_id=None,
                            session_date=_date.today().isoformat(),
                        )
                        st.toast(
                            f"Tracking {r.symbol} {_opt_type} "
                            f"${_opt_strike:.0f} -- ${_opt_cost:,.0f}"
                        )
                        st.rerun()

            if not tracking and is_tracking:
                # Close trade in DB
                pos_info = st.session_state["active_positions"][pos_key]
                trade_id = pos_info.get("trade_id")
                if trade_id:
                    exit_price = r.last_close
                    if _market_open and not intra_bars.empty:
                        exit_price = intra_bars["Close"].iloc[-1]
                    close_real_trade(trade_id, exit_price)
                del st.session_state["active_positions"][pos_key]
                st.rerun()

            if tracking and is_tracking:
                pos_info = st.session_state["active_positions"][pos_key]

                pe1, pe2 = st.columns(2)
                new_entry = pe1.number_input(
                    "Entry Price", value=pos_info["entry"], step=0.01,
                    key=f"pos_entry_{r.symbol}", format="%.2f",
                )
                new_shares = pe2.number_input(
                    "Shares", value=pos_info["shares"], step=1,
                    key=f"pos_shares_{r.symbol}",
                )

                # Update if changed
                if new_entry != pos_info["entry"] or new_shares != pos_info["shares"]:
                    st.session_state["active_positions"][pos_key]["entry"] = new_entry
                    st.session_state["active_positions"][pos_key]["shares"] = new_shares

                # Live P&L calculation
                if _market_open and not intra_bars.empty:
                    live_price = intra_bars["Close"].iloc[-1]
                else:
                    live_price = r.last_close

                pnl_per_share = live_price - new_entry
                total_pnl = pnl_per_share * new_shares
                pnl_pct = (pnl_per_share / new_entry * 100) if new_entry > 0 else 0

                # Distance to stop and targets
                dist_stop = live_price - r.stop
                dist_t1 = r.target_1 - live_price
                dist_t2 = r.target_2 - live_price

                pnl_color = "#2ecc71" if total_pnl >= 0 else "#e74c3c"
                st.markdown(
                    f"#### <span style='color:{pnl_color}'>"
                    f"{'+'if total_pnl>=0 else ''}${total_pnl:,.0f} "
                    f"({pnl_pct:+.1f}%)</span>",
                    unsafe_allow_html=True,
                )

                pp1, pp2, pp3, pp4 = st.columns(4)
                pp1.metric("Live Price", f"${live_price:,.2f}")
                pp2.metric("To Stop", f"${dist_stop:,.2f}",
                            delta="SAFE" if dist_stop > 0 else "STOPPED",
                            delta_color="normal" if dist_stop > 0 else "inverse")
                pp3.metric("To T1", f"${dist_t1:,.2f}",
                            delta="HIT" if dist_t1 <= 0 else f"${dist_t1:,.2f} away",
                            delta_color="normal" if dist_t1 <= 0 else "off")
                pp4.metric("To T2", f"${dist_t2:,.2f}",
                            delta="HIT" if dist_t2 <= 0 else f"${dist_t2:,.2f} away",
                            delta_color="normal" if dist_t2 <= 0 else "off")

                # Progress bars: stop to T2 range
                total_range = r.target_2 - r.stop
                if total_range > 0:
                    progress = (live_price - r.stop) / total_range
                    progress = max(0.0, min(1.0, progress))
                    st.progress(progress, text=f"Stop -> T2: {progress:.0%}")

                if st.button("Close Position", key=f"close_pos_{r.symbol}", type="secondary"):
                    trade_id = pos_info.get("trade_id")
                    if trade_id:
                        close_real_trade(trade_id, live_price)
                    del st.session_state["active_positions"][pos_key]
                    st.rerun()
