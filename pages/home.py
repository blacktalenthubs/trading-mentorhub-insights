"""TradeCoPilot — Dashboard."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime

from streamlit_autorefresh import st_autorefresh

from db import get_watchlist
from analytics.intraday_data import (
    fetch_intraday, fetch_prior_day, get_spy_context, compute_vwap,
)
from analytics.intraday_rules import evaluate_rules, AlertSignal
from analytics.market_hours import is_market_hours, get_session_phase
from alerting.alert_store import (
    ack_alert,
    create_active_entry,
    create_active_entry_from_alert,
    get_active_cooldowns, get_alerts_today, get_session_dates,
    get_session_summary,
    has_acked_entry,
    record_alert,
    today_session,
    user_has_used_ack,
    was_alert_fired,
)
from alerting.notifier import notify_user
from db import get_notification_prefs
from alerting.real_trade_store import (
    calculate_shares, has_open_trade,
)
from alerting.options_trade_store import (
    has_open_options_trade, open_options_trade,
)
from analytics.intraday_rules import AlertType
from analytics.signal_engine import scan_watchlist
from db import get_daily_plan
from alert_config import (
    DAILY_SCORE_VERY_WEAK_PENALTY,
    DAILY_SCORE_VERY_WEAK_THRESHOLD,
    DAILY_SCORE_WEAK_PENALTY,
    DAILY_SCORE_WEAK_THRESHOLD,
    OPTIONS_ELIGIBLE_SYMBOLS,
    OPTIONS_MIN_SCORE,
    POLL_INTERVAL_MINUTES,
    REAL_TRADE_POSITION_SIZE, REAL_TRADE_SPY_POSITION_SIZE,
    SCORE_VERSION,
    TELEGRAM_TIER1_MIN_SCORE,
)
import ui_theme

user = ui_theme.setup_page("home", tier_required="free")

# Authenticated user — show dashboard
from db import get_user_tier
_user_tier = get_user_tier(user["id"])

ui_theme.page_header("TradeCoPilot", "AI-Powered Trade Intelligence")
ui_theme.welcome_banner()

# ── Auto-refresh during market hours ──────────────────────────────────────
_market_open = is_market_hours()
if _market_open:
    st_autorefresh(interval=180_000, key="alert_refresh")  # 3 min

# ── Shared watchlist (from Scanner or default) ────────────────────────────
watchlist = st.session_state.get("watchlist", get_watchlist(user["id"]))

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
    active_cd_symbols = get_active_cooldowns(user_id=user["id"])
    cd_text = ", ".join(sorted(active_cd_symbols)) if active_cd_symbols else "None"

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Signals", f"{buy_hist}E / {sell_hist}X / {short_hist}S")
    sc2.metric("Win Rate", win_rate, delta=f"{t1_wins}W / {stopped}L", delta_color="off")
    sc3.metric("Cooldowns", len(active_cd_symbols) if active_cd_symbols else 0,
               delta=cd_text if active_cd_symbols else None, delta_color="off")
    sc4.metric("Refresh", f"{POLL_INTERVAL_MINUTES * 60}s")

# ---------------------------------------------------------------------------
# Cached helpers
# ---------------------------------------------------------------------------


@st.cache_data(ttl=180, show_spinner=False)
def _cached_intraday(symbol: str) -> pd.DataFrame:
    return fetch_intraday(symbol)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_prior_day(symbol: str) -> dict | None:
    return fetch_prior_day(symbol)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_daily_scores(syms: tuple[str, ...]) -> dict[str, int]:
    """Fetch Scanner scores for watchlist (cached 5 min, keyed on symbol tuple)."""
    results = scan_watchlist(list(syms))
    return {r.symbol: r.score for r in results}


# ---------------------------------------------------------------------------
# F6: Signal chart overlay helper
# ---------------------------------------------------------------------------


def _draw_signal_chart(symbol: str, sig: AlertSignal):
    """5-min candlestick + volume chart with signal overlays, VWAP, and dark theme."""
    bars = _cached_intraday(symbol)
    if bars.empty:
        return

    prior = _cached_prior_day(symbol)
    chart = bars.copy()

    # Gap-free integer x-axis with time labels
    x_int = list(range(len(chart)))
    time_labels = chart.index.strftime("%H:%M")
    step = max(1, len(chart) // 10)
    tick_vals = x_int[::step]
    tick_text = [time_labels[i] for i in tick_vals]

    fig = ui_theme.build_candlestick_fig(
        chart, x_int, symbol,
        height=380, tick_vals=tick_vals, tick_text=tick_text,
    )

    # VWAP line
    vwap = compute_vwap(bars)
    if not vwap.empty:
        vwap_x = list(range(len(vwap)))
        fig.add_trace(go.Scatter(
            x=vwap_x, y=vwap.values,
            mode="lines", name="VWAP",
            line=dict(color="#9b59b6", width=1.5, dash="dash"),
        ))

    # Prior day high/low
    if prior:
        ui_theme.add_level_line(fig, prior["high"], "Prior High", "#e74c3c",
                                position="top right", dash="dot", width=1)
        ui_theme.add_level_line(fig, prior["low"], "Prior Low", "#2ecc71",
                                position="bottom right", dash="dot", width=1)

    # Signal levels (non-prescriptive labels)
    if sig.entry:
        ui_theme.add_level_line(fig, sig.entry, "Watch", "#3498db", position="top left")
    if sig.stop:
        ui_theme.add_level_line(fig, sig.stop, "Risk", "#e74c3c", position="bottom left")
    if sig.target_1:
        ui_theme.add_level_line(fig, sig.target_1, "T1", "#2ecc71", position="top right")
    if sig.target_2:
        ui_theme.add_level_line(fig, sig.target_2, "T2", "#27ae60", position="top right", width=1)

    # Signal marker
    if sig.entry:
        fig.add_trace(go.Scatter(
            x=[x_int[-1]], y=[sig.entry],
            mode="markers", name="Signal",
            marker=dict(symbol="triangle-up", size=14, color="#f39c12"),
        ))

    st.plotly_chart(fig, use_container_width=True, config=ui_theme.PLOTLY_CONFIG_MINIMAL)


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

    # Clear stale auto-stop entries from previous sessions
    _current_session = today_session()
    if st.session_state.get("_auto_stop_session") != _current_session:
        st.session_state["auto_stop_entries"] = {}
        st.session_state["_auto_stop_session"] = _current_session

    # Build fired_today from DB (authoritative, persistent across restarts)
    db_alerts = get_alerts_today(user_id=user["id"])
    fired_today: set[tuple[str, str]] = {
        (a["symbol"], a["alert_type"]) for a in db_alerts
    }

    # Build active cooldown set from DB
    cooled_symbols: set[str] = get_active_cooldowns(user_id=user["id"])

    # After a stop-out + cooldown expiry, allow BUY signals to re-fire.
    _stop_types = {"stop_loss_hit", "auto_stop_out"}
    stopped_symbols = {
        a["symbol"] for a in db_alerts if a["alert_type"] in _stop_types
    }
    _sell_types = _stop_types | {
        "target_1_hit", "target_2_hit", "support_breakdown",
        "resistance_prior_high", "resistance_prior_low",
        "hourly_resistance_approach", "ma_resistance",
        "weekly_high_resistance", "ema_resistance",
        "opening_range_breakdown",
    }
    for sym in stopped_symbols:
        if sym not in cooled_symbols:
            fired_today = {
                (s, at) for s, at in fired_today
                if s != sym or at in _sell_types
            }

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
            plan = get_daily_plan(symbol, today_session())
            signals = evaluate_rules(
                symbol, intra, prior, active_entries,
                spy_context=_spy_ctx,
                auto_stop_entries=auto_stop.get(symbol),
                is_cooled_down=symbol in cooled_symbols,
                fired_today=fired_today,
                daily_plan=plan,
            )
            all_signals.extend(signals)

    # ── Daily score cross-reference: penalise weak BUY setups ───────────
    daily_scores = _cached_daily_scores(tuple(watchlist))
    for sig in all_signals:
        if sig.direction != "BUY":
            continue
        ds = daily_scores.get(sig.symbol)
        if ds is None:
            continue
        penalty = 0
        if ds < DAILY_SCORE_VERY_WEAK_THRESHOLD:
            penalty = DAILY_SCORE_VERY_WEAK_PENALTY
        elif ds < DAILY_SCORE_WEAK_THRESHOLD:
            penalty = DAILY_SCORE_WEAK_PENALTY
        if penalty:
            sig.score = max(0, sig.score - penalty)
            sig.message += f" | daily {ds} (-{penalty})"
            # Recompute label after penalty
            if sig.score >= 90:
                sig.score_label = "A+"
            elif sig.score >= 75:
                sig.score_label = "A"
            elif sig.score >= 50:
                sig.score_label = "B"
            else:
                sig.score_label = "C"

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

    _non_entry_types = {
        AlertType.GAP_FILL, AlertType.SUPPORT_BREAKDOWN,
        AlertType.RESISTANCE_PRIOR_HIGH, AlertType.PDH_REJECTION,
        AlertType.HOURLY_RESISTANCE_APPROACH,
        AlertType.MA_RESISTANCE, AlertType.RESISTANCE_PRIOR_LOW,
        AlertType.OPENING_RANGE_BREAKDOWN,
    }
    session = today_session()
    _ack_active = user_has_used_ack(user["id"])

    new_signals = []
    for sig in all_signals:
        key = (sig.symbol, sig.alert_type.value, sig.direction)
        if key not in existing_keys:
            # Gate: suppress ALL exit/sell signals for un-ACK'd symbols
            if _ack_active and sig.direction != "BUY":
                if not has_acked_entry(sig.symbol, user["id"], session):
                    continue

            # Final DB dedup check (another tab may have recorded it)
            if was_alert_fired(sig.symbol, sig.alert_type.value, session, user_id=user["id"]):
                continue

            new_signals.append(sig)

            # Record to DB so alerts persist and dedup works across refreshes
            alert_id = record_alert(sig, session, False, False, user_id=user["id"])

            if alert_id is None:
                continue  # duplicate — already recorded by another tab or worker

            # Per-user notification (matches worker.py pattern)
            prefs = get_notification_prefs(user["id"])
            if prefs:
                notify_user(sig, prefs, alert_id=alert_id)

            # Track active entries for actionable BUY signals
            if sig.direction == "BUY" and sig.alert_type not in _non_entry_types:
                if not _ack_active:
                    create_active_entry(sig, session, user_id=user["id"])  # legacy fallback
                # else: created on ACK callback

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

            # Clean up on stop-out (cooldown is handled via DB)
            if sig.alert_type.value in ("auto_stop_out", "stop_loss_hit"):
                st.session_state.get("auto_stop_entries", {}).pop(sig.symbol, None)

    if new_signals:
        st.toast(f"{len(new_signals)} new signal(s) detected")

    # ── F8: Sort signals by score descending ──────────────────────────────
    all_signals.sort(key=lambda s: s.score, reverse=True)

    # Display all current signals as colored cards
    if all_signals:
        for sig in all_signals:
            _dir_label, color = ui_theme.display_direction(sig.direction)
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
            _opts_eligible = (
                sig.symbol in OPTIONS_ELIGIBLE_SYMBOLS
                and sig.score >= OPTIONS_MIN_SCORE
                and sig.confidence == "high"
            )
            opts_badge = (
                " <span style='background:#9b59b6;color:white;padding:2px 6px;"
                "border-radius:3px;font-size:0.75em;font-weight:bold'>OPTIONS PLAY</span>"
                if _opts_eligible else ""
            )

            opacity = "0.6" if sig.score < 50 else "1.0"
            padding = "14px 18px" if sig.score >= 90 else "10px 14px"
            font_size = "1.2em" if sig.score >= 90 else "1.1em"

            st.markdown(
                f"<div style='padding:{padding};border-left:4px solid {color};"
                f"background:{color}10;margin-bottom:8px;border-radius:4px;opacity:{opacity}'>"
                f"{score_badge} "
                f"<strong style='color:{color};font-size:{font_size}'>{_dir_label}</strong>"
                f"{new_badge}{opts_badge} "
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
                    dc1.metric("Watch Near", f"${sig.entry:,.2f}")
                    if sig.stop:
                        dc2.metric("Risk Below", f"${sig.stop:,.2f}")
                    if sig.target_1:
                        dc3.metric("T1", f"${sig.target_1:,.2f}")
                    if sig.target_2:
                        dc4.metric("T2", f"${sig.target_2:,.2f}")

                    # Quick trade info
                    if sig.direction in ("BUY", "SHORT") and sig.entry and sig.stop:
                        if has_open_trade(sig.symbol):
                            st.info("Tracking this trade (see Real Trades)")
                        else:
                            shares = calculate_shares(sig.symbol, sig.entry)
                            cap = REAL_TRADE_SPY_POSITION_SIZE if sig.symbol == "SPY" else REAL_TRADE_POSITION_SIZE
                            st.caption(
                                f"{shares} shares x ${sig.entry:,.2f} = "
                                f"${shares * sig.entry:,.0f} (${cap / 1000:.0f}k cap) — "
                                f"track on **Scanner**"
                            )

                    # ACK buttons (desktop fallback for Telegram)
                    if _ack_active and sig.direction in ("BUY", "SHORT") and is_new:
                        from alerting.alert_store import get_alert_id as _get_alert_id
                        from alerting.real_trade_store import open_real_trade
                        _sig_alert_id = _get_alert_id(sig.symbol, sig.alert_type.value, session, user_id=user["id"])
                        if _sig_alert_id:
                            _bc1, _bc2, _ = st.columns([1, 1, 3])
                            if _bc1.button("Took It", key=f"ack_{sig.symbol}_{sig.alert_type.value}", type="primary"):
                                ack_alert(_sig_alert_id, "took")
                                create_active_entry_from_alert(_sig_alert_id, user_id=user["id"])
                                if not has_open_trade(sig.symbol):
                                    open_real_trade(
                                        symbol=sig.symbol,
                                        direction=sig.direction,
                                        entry_price=sig.entry or sig.price,
                                        stop_price=sig.stop,
                                        target_price=sig.target_1,
                                        target_2_price=sig.target_2,
                                        alert_type=sig.alert_type.value,
                                        alert_id=_sig_alert_id,
                                        session_date=session,
                                    )
                                st.toast(f"Trade opened: {sig.symbol}")
                                st.rerun()
                            if _bc2.button("Skip", key=f"skip_{sig.symbol}_{sig.alert_type.value}"):
                                ack_alert(_sig_alert_id, "skipped")
                                st.toast(f"Skipped {sig.symbol}")
                                st.rerun()

                    # Options play form
                    if _opts_eligible and sig.direction == "BUY":
                        st.markdown("---")
                        if has_open_options_trade(sig.symbol):
                            st.info("Options trade already tracking (see Real Trades)")
                        else:
                            st.markdown(
                                "<span style='color:#9b59b6;font-weight:bold'>"
                                "Track Options Play</span>",
                                unsafe_allow_html=True,
                            )
                            oc1, oc2 = st.columns(2)
                            opt_type = oc1.radio(
                                "Type", ["CALL", "PUT"],
                                key=f"home_opt_type_{sig.symbol}",
                                horizontal=True,
                            )
                            opt_strike = oc2.number_input(
                                "Strike", value=round(sig.entry, 0),
                                step=1.0, format="%.2f",
                                key=f"home_opt_strike_{sig.symbol}",
                            )
                            oc3, oc4 = st.columns(2)
                            opt_expiry = oc3.date_input(
                                "Expiration",
                                key=f"home_opt_expiry_{sig.symbol}",
                            )
                            opt_contracts = oc4.number_input(
                                "Contracts", min_value=1, value=1, step=1,
                                key=f"home_opt_contracts_{sig.symbol}",
                            )
                            opt_premium = st.number_input(
                                "Premium per contract",
                                min_value=0.01, value=1.00, step=0.05,
                                format="%.2f",
                                key=f"home_opt_premium_{sig.symbol}",
                            )
                            opt_cost = opt_contracts * opt_premium * 100
                            st.caption(
                                f"{opt_contracts} x ${opt_premium:.2f} x 100 = "
                                f"${opt_cost:,.0f} total cost"
                            )
                            if st.button(
                                "Track Options",
                                key=f"home_opt_track_{sig.symbol}",
                                type="primary",
                            ):
                                open_options_trade(
                                    symbol=sig.symbol,
                                    option_type=opt_type,
                                    strike=opt_strike,
                                    expiration=opt_expiry.isoformat(),
                                    contracts=opt_contracts,
                                    premium_per_contract=opt_premium,
                                    alert_type=sig.alert_type.value,
                                    alert_id=None,
                                    session_date=today_session(),
                                )
                                st.toast(
                                    f"Tracking {sig.symbol} {opt_type} "
                                    f"${opt_strike:.0f} — ${opt_cost:,.0f}"
                                )
                                st.rerun()

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
        kpi2.metric("Potential Entries", buy_count)
        kpi3.metric("Exit Zones", sell_count)
        kpi4.metric("Potential Shorts", short_count)
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


# ---------------------------------------------------------------------------
# Alert History (session)
# ---------------------------------------------------------------------------

ui_theme.section_header("Alert History (This Session)")

# Load from database — persists across page refreshes and app restarts
_db_history = get_alerts_today(user_id=user["id"])

if _db_history:
    _hist_cols = ["symbol", "alert_type", "direction", "price", "entry",
                  "stop", "target_1", "target_2", "confidence", "message", "created_at"]
    hist_df = pd.DataFrame(_db_history)
    # Keep only columns that exist in the data
    _hist_cols = [c for c in _hist_cols if c in hist_df.columns]
    hist_df = hist_df[_hist_cols]
    # Format the timestamp for readability
    if "created_at" in hist_df.columns:
        hist_df["created_at"] = pd.to_datetime(hist_df["created_at"]).dt.strftime("%H:%M:%S")
        hist_df = hist_df.rename(columns={"created_at": "time"})
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
    st.caption(f"{len(_db_history)} alerts fired today")
else:
    ui_theme.empty_state("No alerts fired this session.")

# ---------------------------------------------------------------------------
# F10: End-of-Day Summary
# ---------------------------------------------------------------------------

_session_phase = get_session_phase()
_show_eod = _session_phase in ("closed", "last_30", "power_hour")

if _show_eod or st.button("Generate Summary Now", key="gen_summary"):
    ui_theme.section_header("End-of-Day Summary")

    summary = get_session_summary(user_id=user["id"])
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
# Daily Alert Report (date-browsable)
# ---------------------------------------------------------------------------

ui_theme.section_header("Daily Alert Report")

_available_dates = get_session_dates(user_id=user["id"])
_today_str = date.today().isoformat()

if _available_dates:
    # Build date objects for the picker; ensure today is always an option
    _date_objs = sorted(
        {date.fromisoformat(d) for d in _available_dates} | {date.today()},
        reverse=True,
    )
    _selected_date = st.date_input(
        "Session date",
        value=date.today(),
        min_value=_date_objs[-1],
        max_value=_date_objs[0],
        key="report_date",
    )
    _sel_str = _selected_date.isoformat()

    # KPI row
    _rpt_summary = get_session_summary(_sel_str, user_id=user["id"])

    rk1, rk2, rk3, rk4, rk5 = st.columns(5)
    rk1.metric("Total Signals", _rpt_summary["total"])
    rk2.metric(
        "BUY / SELL / SHORT",
        f"{_rpt_summary['buy_count']} / {_rpt_summary['sell_count']} / {_rpt_summary['short_count']}",
    )
    rk3.metric("T1 Hits", _rpt_summary["t1_hits"])
    rk4.metric("T2 Hits", _rpt_summary["t2_hits"])
    rk5.metric("Stopped Out", _rpt_summary["stopped_out"])

    # Full alert table
    _rpt_alerts = get_alerts_today(_sel_str, user_id=user["id"])
    if _rpt_alerts:
        _rpt_df = pd.DataFrame(_rpt_alerts)

        # Build score_label from score column
        def _score_to_label(s: int) -> str:
            if s >= 90:
                return "A+"
            if s >= 75:
                return "A"
            if s >= 50:
                return "B"
            return "C" if s > 0 else ""

        _rpt_df["score_label"] = _rpt_df["score"].apply(_score_to_label)

        _rpt_cols = [
            "symbol", "score", "score_label", "alert_type", "direction",
            "price", "entry", "stop", "target_1", "target_2",
            "confidence", "message", "created_at",
        ]
        _rpt_cols = [c for c in _rpt_cols if c in _rpt_df.columns]
        _rpt_df = _rpt_df[_rpt_cols]

        if "created_at" in _rpt_df.columns:
            _rpt_df["created_at"] = pd.to_datetime(
                _rpt_df["created_at"]
            ).dt.strftime("%H:%M:%S")
            _rpt_df = _rpt_df.rename(columns={"created_at": "time"})

        st.dataframe(
            _rpt_df,
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
        st.caption(f"{len(_rpt_alerts)} alerts on {_sel_str}")

        # Signal breakdown by type
        if _rpt_summary["signals_by_type"]:
            st.markdown("**Signal Breakdown by Type**")
            _rpt_type_df = pd.DataFrame([
                {"Type": k.replace("_", " ").title(), "Count": v}
                for k, v in _rpt_summary["signals_by_type"].items()
            ]).sort_values("Count", ascending=False)
            st.dataframe(_rpt_type_df, use_container_width=True, hide_index=True)
    else:
        ui_theme.empty_state(f"No alerts recorded for {_sel_str}.")
else:
    ui_theme.empty_state("No alert history yet — alerts will appear here after your first session.")

# ---------------------------------------------------------------------------
# Test Notifications (debug only — use Settings page for production)
# ---------------------------------------------------------------------------

import os as _os
if _os.environ.get("TRADESIGNAL_DEBUG", "").lower() == "true":
    with st.expander("Test Notifications"):
        st.caption("Send a test alert to verify your notification settings.")

        if st.button("Send Test Alert"):
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
                message="Test alert from TradeCoPilot — ignore this message",
            )

            with st.spinner("Sending test notifications..."):
                email_ok, sms_ok = notify(test_signal)

            if email_ok:
                st.success("Test email sent!")
            if sms_ok:
                st.success("Test Telegram sent!")
            if not email_ok and not sms_ok:
                st.warning("Nothing sent — check .env config.")
