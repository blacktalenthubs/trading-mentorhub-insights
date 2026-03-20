"""TradeCoPilot — Alert Command Center (v2 Redesign).

Terminal-trader aesthetic with dense data layout, color-coded alerts,
position tracker with P&L bars, and exit coach feed.
"""

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
    update_alert_notification,
    user_has_used_ack,
    was_alert_fired,
)
from alerting.notifier import notify, notify_user
from alerting.paper_trader import (
    close_position as paper_close_position,
    is_enabled as paper_trading_enabled,
    place_bracket_order,
)
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
    REAL_TRADE_POSITION_SIZE, REAL_TRADE_SPY_SHARES,
    SCORE_VERSION,
    TELEGRAM_TIER1_MIN_SCORE,
)
import ui_theme
from config import is_crypto_alert_symbol
from analytics.intraday_data import fetch_intraday_crypto

# ── Page Setup ──────────────────────────────────────────────────────────────
user = ui_theme.setup_page("home", tier_required="free")
from db import get_user_tier
_user_tier = get_user_tier(user["id"])

# ── Terminal Trader CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

/* Override Streamlit defaults */
.stApp { background-color: #04060b; }
section[data-testid="stSidebar"] { background-color: #080c14; }
.stMarkdown, .stCaption, p, span { color: #e2e8f0; }

/* Custom components */
.tc-topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 0; margin-bottom: 16px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.tc-brand {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700; font-size: 22px; letter-spacing: -0.5px;
    display: flex; align-items: center; gap: 10px;
}
.tc-bolt {
    display: inline-flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; background: linear-gradient(135deg, #10b981, #059669);
    border-radius: 8px; font-size: 16px;
}
.tc-status {
    font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #8b9cc0;
    display: flex; align-items: center; gap: 12px;
}
.tc-live-dot {
    width: 7px; height: 7px; border-radius: 50%; background: #10b981;
    box-shadow: 0 0 8px rgba(16,185,129,0.4);
    animation: pulse 2s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; } 50% { opacity: 0.4; }
}
.tc-regime {
    padding: 3px 10px; border-radius: 4px;
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
    font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase;
}
.tc-regime.down { background: rgba(239,68,68,0.12); color: #ef4444; border: 1px solid rgba(239,68,68,0.2); }
.tc-regime.up { background: rgba(16,185,129,0.12); color: #10b981; border: 1px solid rgba(16,185,129,0.2); }
.tc-regime.choppy { background: rgba(245,158,11,0.12); color: #f59e0b; border: 1px solid rgba(245,158,11,0.2); }

/* KPI Strip */
.tc-kpi-strip { display: flex; gap: 1px; margin-bottom: 16px; }
.tc-kpi {
    flex: 1; padding: 12px 16px; background: #0d1220;
    border: 1px solid rgba(255,255,255,0.04); border-radius: 6px;
}
.tc-kpi-label {
    font-family: 'JetBrains Mono', monospace; font-size: 9px;
    text-transform: uppercase; letter-spacing: 1.2px; color: #4a5578;
}
.tc-kpi-value {
    font-family: 'JetBrains Mono', monospace; font-size: 20px;
    font-weight: 600; letter-spacing: -0.5px; margin-top: 2px;
}
.tc-kpi-sub {
    font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #4a5578;
}
.green { color: #10b981; }
.red { color: #ef4444; }
.amber { color: #f59e0b; }

/* Watchlist Heatmap */
.tc-wl-grid { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.tc-wl-item {
    flex: 1; min-width: 100px; padding: 10px; border-radius: 6px;
    text-align: center; border: 1px solid rgba(255,255,255,0.04);
    transition: all 0.15s; cursor: pointer;
}
.tc-wl-item:hover { border-color: rgba(255,255,255,0.15); }
.tc-wl-item.signal { border-color: rgba(245,158,11,0.4); }
.tc-wl-sym {
    font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 13px;
}
.tc-wl-price {
    font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #e2e8f0;
}
.tc-wl-change {
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    padding: 1px 5px; border-radius: 3px; display: inline-block; margin-top: 2px;
}
.tc-wl-change.up { background: rgba(16,185,129,0.12); color: #10b981; }
.tc-wl-change.down { background: rgba(239,68,68,0.12); color: #ef4444; }

/* Alert Cards */
.tc-alert {
    padding: 14px 18px; margin-bottom: 8px; border-radius: 6px;
    border-left: 3px solid transparent; background: #0d1220;
    border: 1px solid rgba(255,255,255,0.04);
}
.tc-alert.buy { border-left-color: #10b981; }
.tc-alert.sell { border-left-color: #ef4444; }
.tc-alert.notice { border-left-color: #3b82f6; }
.tc-alert.short { border-left-color: #a78bfa; }
.tc-alert-top {
    display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap;
}
.tc-dir {
    padding: 2px 8px; border-radius: 3px;
    font-family: 'JetBrains Mono', monospace; font-size: 9px;
    font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase;
}
.tc-dir.buy { background: rgba(16,185,129,0.12); color: #10b981; }
.tc-dir.sell { background: rgba(239,68,68,0.12); color: #ef4444; }
.tc-dir.notice { background: rgba(59,130,246,0.12); color: #3b82f6; }
.tc-symbol {
    font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 15px;
}
.tc-alert-type {
    font-family: 'IBM Plex Sans', sans-serif; font-size: 12px; color: #8b9cc0;
}
.tc-score {
    padding: 2px 8px; border-radius: 3px;
    font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600;
    margin-left: auto;
}
.tc-score.aplus { background: rgba(16,185,129,0.15); color: #10b981; }
.tc-score.a { background: rgba(16,185,129,0.10); color: #10b981; }
.tc-score.b { background: rgba(245,158,11,0.12); color: #f59e0b; }
.tc-score.c { background: rgba(255,255,255,0.05); color: #4a5578; }
.tc-time {
    font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #4a5578;
}
.tc-levels {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
    padding: 10px 12px; background: #080c14; border-radius: 5px;
    border: 1px solid rgba(255,255,255,0.04); margin: 8px 0;
}
.tc-lv-label {
    font-family: 'JetBrains Mono', monospace; font-size: 8px;
    text-transform: uppercase; letter-spacing: 1px; color: #4a5578;
}
.tc-lv-val {
    font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 500;
}
.tc-lv-val.entry { color: #3b82f6; }
.tc-lv-val.stop { color: #ef4444; }
.tc-lv-val.t1 { color: #10b981; }
.tc-lv-val.t2 { color: #f59e0b; }
.tc-msg {
    font-size: 12px; color: #8b9cc0; line-height: 1.5; margin-top: 6px;
}
.tc-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.tc-tag {
    padding: 2px 7px; border-radius: 3px;
    font-family: 'JetBrains Mono', monospace; font-size: 9px;
    background: rgba(255,255,255,0.04); color: #4a5578;
    border: 1px solid rgba(255,255,255,0.04);
}
.tc-tag.caution { background: rgba(245,158,11,0.10); color: #f59e0b; border-color: rgba(245,158,11,0.2); }
.tc-tag.confluence { background: rgba(16,185,129,0.10); color: #10b981; border-color: rgba(16,185,129,0.2); }
.tc-tag.wick { background: rgba(239,68,68,0.10); color: #ef4444; border-color: rgba(239,68,68,0.2); }
.tc-tag.new { background: rgba(245,158,11,0.15); color: #f59e0b; border-color: rgba(245,158,11,0.3); }

/* Section headers */
.tc-section {
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
    text-transform: uppercase; letter-spacing: 1.5px; color: #4a5578;
    padding: 12px 0 8px; margin-top: 16px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}

/* Position card */
.tc-position {
    padding: 12px 16px; background: #0d1220; border-radius: 6px;
    border: 1px solid rgba(255,255,255,0.04); margin-bottom: 8px;
}
.tc-pos-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;
}
.tc-pos-sym { font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 14px; }
.tc-pos-pnl { font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 600; }
.tc-pos-bar {
    height: 4px; border-radius: 2px; background: rgba(255,255,255,0.04);
    margin: 6px 0; overflow: hidden;
}
.tc-pos-bar-fill { height: 100%; border-radius: 2px; transition: width 0.5s; }
.tc-pos-bar-fill.profit { background: linear-gradient(90deg, #10b981, #34d399); }
.tc-pos-bar-fill.loss { background: linear-gradient(90deg, #ef4444, #f87171); }
.tc-pos-levels {
    display: flex; justify-content: space-between;
    font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #4a5578;
}
</style>
""", unsafe_allow_html=True)

# ── Auto-refresh ────────────────────────────────────────────────────────────
_market_open = is_market_hours()
if _market_open:
    st_autorefresh(interval=180_000, key="alert_refresh")

# ── Shared State ────────────────────────────────────────────────────────────
watchlist = st.session_state.get("watchlist", get_watchlist(user["id"]))

# ── Cached Helpers ──────────────────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def _cached_intraday(symbol: str) -> pd.DataFrame:
    if is_crypto_alert_symbol(symbol):
        return fetch_intraday_crypto(symbol)
    return fetch_intraday(symbol)

@st.cache_data(ttl=300, show_spinner=False)
def _cached_prior_day(symbol: str) -> dict | None:
    return fetch_prior_day(symbol, is_crypto=is_crypto_alert_symbol(symbol))

@st.cache_data(ttl=300, show_spinner=False)
def _cached_daily_scores(syms: tuple[str, ...]) -> dict[str, int]:
    results = scan_watchlist(list(syms))
    return {r.symbol: r.score for r in results}


# ── SPY Context ─────────────────────────────────────────────────────────────
_spy_ctx = get_spy_context()
_spy_close = _spy_ctx.get("close", 0) if _spy_ctx else 0
_spy_regime = _spy_ctx.get("regime", "CHOPPY") if _spy_ctx else "CHOPPY"
_spy_rsi = _spy_ctx.get("rsi14", 0) if _spy_ctx else 0
_spy_trend = _spy_ctx.get("trend", "neutral") if _spy_ctx else "neutral"

# ── Top Bar ─────────────────────────────────────────────────────────────────
_regime_class = "down" if "DOWN" in _spy_regime else ("up" if _spy_trend == "bullish" else "choppy")
_phase = get_session_phase() if _market_open else "closed"
_now_str = datetime.now().strftime("%H:%M:%S ET")

st.markdown(f"""
<div class="tc-topbar">
    <div class="tc-brand">
        <span class="tc-bolt">&#9889;</span> TradeCoPilot
    </div>
    <div class="tc-status">
        {"<span class='tc-live-dot'></span> LIVE" if _market_open else "MARKET CLOSED"}
        &nbsp;|&nbsp; {_phase}
        &nbsp;|&nbsp; {_now_str}
    </div>
    <div style="display:flex;align-items:center;gap:12px;">
        <span class="tc-regime {_regime_class}">{_spy_regime}</span>
        <span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#8b9cc0;">
            SPY ${_spy_close:,.2f}
        </span>
    </div>
</div>
""", unsafe_allow_html=True)


# ── KPI Strip ───────────────────────────────────────────────────────────────
_db_alerts_for_kpi = get_alerts_today(user_id=user["id"])
_buy_count = sum(1 for a in _db_alerts_for_kpi if a.get("direction") == "BUY")
_sell_count = sum(1 for a in _db_alerts_for_kpi if a.get("direction") == "SELL")
_t1_hits = sum(1 for a in _db_alerts_for_kpi if a.get("alert_type") == "target_1_hit")
_stopped = sum(1 for a in _db_alerts_for_kpi if a.get("alert_type") in ("stop_loss_hit", "auto_stop_out"))
_decided = _t1_hits + _stopped
_win_rate = f"{_t1_hits / _decided * 100:.0f}%" if _decided > 0 else "N/A"
_wr_class = "green" if _decided > 0 and _t1_hits / _decided >= 0.5 else ("red" if _decided > 0 else "")
_rsi_class = "red" if _spy_rsi < 40 else ("green" if _spy_rsi > 60 else "amber")

st.markdown(f"""
<div class="tc-kpi-strip">
    <div class="tc-kpi">
        <div class="tc-kpi-label">Alerts Today</div>
        <div class="tc-kpi-value">{len(_db_alerts_for_kpi)}</div>
        <div class="tc-kpi-sub">{_buy_count} BUY / {_sell_count} SELL</div>
    </div>
    <div class="tc-kpi">
        <div class="tc-kpi-label">Win Rate</div>
        <div class="tc-kpi-value {_wr_class}">{_win_rate}</div>
        <div class="tc-kpi-sub">{_t1_hits}W / {_stopped}L</div>
    </div>
    <div class="tc-kpi">
        <div class="tc-kpi-label">SPY RSI</div>
        <div class="tc-kpi-value {_rsi_class}">{_spy_rsi:.1f}</div>
        <div class="tc-kpi-sub">{"Oversold" if _spy_rsi < 35 else ("Overbought" if _spy_rsi > 70 else "Neutral")}</div>
    </div>
    <div class="tc-kpi">
        <div class="tc-kpi-label">Session</div>
        <div class="tc-kpi-value">{_phase.replace("_", " ").title()}</div>
        <div class="tc-kpi-sub">{len(watchlist)} symbols</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── Watchlist Heatmap ───────────────────────────────────────────────────────
_symbol_intraday: dict[str, pd.DataFrame] = {}
_wl_html_parts = []

for sym in watchlist:
    intra = _cached_intraday(sym)
    _symbol_intraday[sym] = intra
    if not intra.empty:
        cur = intra["Close"].iloc[-1]
        sym_open = intra["Open"].iloc[0]
        chg = (cur - sym_open) / sym_open * 100 if sym_open > 0 else 0
    else:
        cur = 0
        chg = 0

    chg_class = "up" if chg >= 0 else "down"
    bg = "rgba(16,185,129,0.06)" if chg >= 0 else "rgba(239,68,68,0.06)"

    _wl_html_parts.append(
        f"<div class='tc-wl-item' style='background:{bg}'>"
        f"<div class='tc-wl-sym'>{sym}</div>"
        f"<div class='tc-wl-price'>${cur:,.2f}</div>"
        f"<span class='tc-wl-change {chg_class}'>{chg:+.2f}%</span>"
        f"</div>"
    )

st.markdown(
    f"<div class='tc-wl-grid'>{''.join(_wl_html_parts)}</div>",
    unsafe_allow_html=True,
)


# ── Chart for Selected Symbol ──────────────────────────────────────────────
_chart_sym = st.selectbox(
    "Chart", watchlist, index=0,
    label_visibility="collapsed",
    key="chart_symbol",
)

_chart_bars = _symbol_intraday.get(_chart_sym, pd.DataFrame())
if not _chart_bars.empty:
    _chart_prior = _cached_prior_day(_chart_sym)
    x_int = list(range(len(_chart_bars)))
    time_labels = _chart_bars.index.strftime("%H:%M")
    step = max(1, len(_chart_bars) // 12)
    tick_vals = x_int[::step]
    tick_text = [time_labels[i] for i in tick_vals]

    fig = ui_theme.build_candlestick_fig(
        _chart_bars, x_int, _chart_sym,
        height=320, tick_vals=tick_vals, tick_text=tick_text,
    )

    # VWAP
    _vwap_s = compute_vwap(_chart_bars)
    if not _vwap_s.empty:
        fig.add_trace(go.Scatter(
            x=list(range(len(_vwap_s))), y=_vwap_s.values,
            mode="lines", name="VWAP",
            line=dict(color="#f59e0b", width=1.5, dash="dot"),
        ))

    # Prior day levels
    if _chart_prior:
        ui_theme.add_level_line(fig, _chart_prior["high"], "PDH", "#ef4444", position="top right", dash="dot", width=1)
        ui_theme.add_level_line(fig, _chart_prior["low"], "PDL", "#10b981", position="bottom right", dash="dot", width=1)

        # Key EMAs
        for ema_key, ema_label, ema_color in [
            ("ema20", "EMA20", "#8b9cc0"),
            ("ema50", "EMA50", "#a78bfa"),
            ("ema200", "EMA200", "#3b82f6"),
        ]:
            ema_val = _chart_prior.get(ema_key)
            if ema_val:
                ui_theme.add_level_line(fig, ema_val, ema_label, ema_color, dash="dash", width=1)

    st.plotly_chart(fig, use_container_width=True, config=ui_theme.PLOTLY_CONFIG_MINIMAL)


# ── Live Alert Scanning ─────────────────────────────────────────────────────
st.markdown("<div class='tc-section'>Live Alerts</div>", unsafe_allow_html=True)

if not _market_open:
    st.caption("Market closed — alerts resume at 9:30 AM ET.")
else:
    if "alert_history" not in st.session_state:
        st.session_state["alert_history"] = []
    if "auto_stop_entries" not in st.session_state:
        st.session_state["auto_stop_entries"] = {}

    _current_session = today_session()
    if st.session_state.get("_auto_stop_session") != _current_session:
        st.session_state["auto_stop_entries"] = {}
        st.session_state["_auto_stop_session"] = _current_session

    # Dedup from DB
    _dedup_uid = None if _user_tier == "admin" else user["id"]
    db_alerts = get_alerts_today(user_id=_dedup_uid)
    fired_today: set[tuple[str, str]] = {
        (a["symbol"], a["alert_type"]) for a in db_alerts
    }
    cooled_symbols: set[str] = get_active_cooldowns(user_id=_dedup_uid)

    # Allow re-fire after stop-out cooldown expiry
    _stop_types = {"stop_loss_hit", "auto_stop_out"}
    stopped_symbols = {a["symbol"] for a in db_alerts if a["alert_type"] in _stop_types}
    _sell_types = _stop_types | {
        "target_1_hit", "target_2_hit", "support_breakdown",
        "resistance_prior_high", "resistance_prior_low",
        "hourly_resistance_approach", "ma_resistance",
        "weekly_high_resistance", "ema_resistance",
        "opening_range_breakdown",
    }
    for sym in stopped_symbols:
        if sym not in cooled_symbols:
            fired_today = {(s, at) for s, at in fired_today if s != sym or at in _sell_types}

    all_signals: list[AlertSignal] = []

    with st.spinner(f"Scanning {len(watchlist)} symbols..."):
        for symbol in watchlist:
            intra = _symbol_intraday.get(symbol, pd.DataFrame())
            prior = _cached_prior_day(symbol)
            if intra.empty:
                continue
            plan = get_daily_plan(symbol, today_session())
            auto_stop = st.session_state.get("auto_stop_entries", {})
            signals = evaluate_rules(
                symbol, intra, prior, [],
                spy_context=_spy_ctx,
                auto_stop_entries=auto_stop.get(symbol),
                is_cooled_down=symbol in cooled_symbols,
                fired_today=fired_today,
                daily_plan=plan,
                is_crypto=is_crypto_alert_symbol(symbol),
            )
            all_signals.extend(signals)

    # Daily score cross-reference
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
            sig.score_label = "A+" if sig.score >= 90 else ("A" if sig.score >= 75 else ("B" if sig.score >= 50 else "C"))

    # Dedup + record new signals
    existing_keys = {
        (a["symbol"], a["alert_type"], a["direction"]) for a in db_alerts
    } | {
        (a["symbol"], a["alert_type"], a["direction"])
        for a in st.session_state.get("alert_history", [])
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
            if _ack_active and sig.direction == "SELL":
                if not has_acked_entry(sig.symbol, user["id"], session):
                    continue
            if was_alert_fired(sig.symbol, sig.alert_type.value, session, user_id=_dedup_uid):
                continue

            new_signals.append(sig)
            alert_id = record_alert(sig, session, False, False, user_id=user["id"])
            if alert_id is None:
                continue

            prefs = get_notification_prefs(user["id"])
            if prefs:
                email_sent, tg_sent = notify_user(sig, prefs, alert_id=alert_id)
            else:
                email_sent, tg_sent = notify(sig, alert_id=alert_id)
            update_alert_notification(alert_id, email_sent, tg_sent)

            if sig.direction == "BUY" and sig.alert_type not in _non_entry_types:
                if not _ack_active:
                    create_active_entry(sig, session, user_id=user["id"])
                if paper_trading_enabled():
                    place_bracket_order(sig, alert_id=alert_id)

            if sig.alert_type in (AlertType.STOP_LOSS_HIT, AlertType.AUTO_STOP_OUT):
                if paper_trading_enabled():
                    paper_close_position(sig.symbol, exit_price=sig.price, reason=sig.alert_type.value)
            if sig.alert_type in (AlertType.TARGET_1_HIT, AlertType.TARGET_2_HIT):
                if paper_trading_enabled():
                    paper_close_position(sig.symbol, exit_price=sig.price, reason=sig.alert_type.value)

            st.session_state["alert_history"].append({
                "symbol": sig.symbol, "alert_type": sig.alert_type.value,
                "direction": sig.direction, "price": sig.price,
                "entry": sig.entry, "stop": sig.stop,
                "target_1": sig.target_1, "target_2": sig.target_2,
                "message": sig.message, "time": datetime.now().strftime("%H:%M:%S"),
            })

            if sig.direction == "BUY" and sig.entry and sig.stop:
                st.session_state.setdefault("auto_stop_entries", {})[sig.symbol] = {
                    "entry_price": sig.entry, "stop_price": sig.stop,
                    "alert_type": sig.alert_type.value,
                }
            if sig.alert_type.value in ("auto_stop_out", "stop_loss_hit"):
                st.session_state.get("auto_stop_entries", {}).pop(sig.symbol, None)

    if new_signals:
        st.toast(f"{len(new_signals)} new signal(s) detected")

    # Sort by score
    all_signals.sort(key=lambda s: s.score, reverse=True)

    # ── Render Alert Cards ──────────────────────────────────────────────────
    if all_signals:
        for sig in all_signals:
            _dir_label, color = ui_theme.display_direction(sig.direction)
            is_new = sig in new_signals
            dir_class = sig.direction.lower()

            # Score badge
            if sig.score >= 90:
                score_html = "<span class='tc-score aplus'>A+ ({0})</span>".format(sig.score)
            elif sig.score >= 75:
                score_html = "<span class='tc-score a'>A ({0})</span>".format(sig.score)
            elif sig.score >= 50:
                score_html = "<span class='tc-score b'>B ({0})</span>".format(sig.score)
            else:
                score_html = "<span class='tc-score c'>C ({0})</span>".format(sig.score)

            # Tags
            tags_html = ""
            if is_new:
                tags_html += "<span class='tc-tag new'>NEW</span>"
            if "CAUTION" in sig.message:
                tags_html += "<span class='tc-tag caution'>CAUTION</span>"
            if "confirming" in sig.message:
                tags_html += "<span class='tc-tag confluence'>CONFLUENCE</span>"
            if "wick touch" in sig.message:
                tags_html += "<span class='tc-tag wick'>WICK ONLY</span>"
            if "HA bearish" in sig.message:
                tags_html += "<span class='tc-tag wick'>HA BEARISH</span>"

            # Levels grid
            levels_html = ""
            if sig.entry:
                _stop_s = f"${sig.stop:,.2f}" if sig.stop else "—"
                _t1_s = f"${sig.target_1:,.2f}" if sig.target_1 else "—"
                _t2_s = f"${sig.target_2:,.2f}" if sig.target_2 else "—"
                levels_html = (
                    '<div class="tc-levels">'
                    f'<div><div class="tc-lv-label">Entry</div><div class="tc-lv-val entry">${sig.entry:,.2f}</div></div>'
                    f'<div><div class="tc-lv-label">Stop</div><div class="tc-lv-val stop">{_stop_s}</div></div>'
                    f'<div><div class="tc-lv-label">T1</div><div class="tc-lv-val t1">{_t1_s}</div></div>'
                    f'<div><div class="tc-lv-label">T2</div><div class="tc-lv-val t2">{_t2_s}</div></div>'
                    '</div>'
                )

            _msg_clean = sig.message.split(" | ")[0] if " | " in sig.message else sig.message
            _alert_type_label = sig.alert_type.value.replace("_", " ").title()

            st.markdown(
                f'<div class="tc-alert {dir_class}">'
                f'<div class="tc-alert-top">'
                f'<span class="tc-dir {dir_class}">{sig.direction}</span>'
                f'<span class="tc-symbol">{sig.symbol}</span>'
                f'<span class="tc-alert-type">{_alert_type_label}</span>'
                f'{score_html}'
                f'<span class="tc-time">${sig.price:,.2f}</span>'
                f'</div>'
                f'{levels_html}'
                f'<div class="tc-msg">{_msg_clean}</div>'
                f'<div class="tc-tags">{tags_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ACK buttons + chart (Streamlit native)
            if sig.entry and sig.direction in ("BUY", "SHORT"):
                col1, col2, col3 = st.columns([1, 1, 6])
                if _ack_active and is_new:
                    from alerting.alert_store import get_alert_id as _get_alert_id
                    from alerting.real_trade_store import open_real_trade
                    _sig_alert_id = _get_alert_id(sig.symbol, sig.alert_type.value, session, user_id=user["id"])
                    if _sig_alert_id:
                        if col1.button("Took It", key=f"ack_{sig.symbol}_{sig.alert_type.value}", type="primary"):
                            ack_alert(_sig_alert_id, "took")
                            create_active_entry_from_alert(_sig_alert_id, user_id=user["id"])
                            if not has_open_trade(sig.symbol):
                                open_real_trade(
                                    symbol=sig.symbol, direction=sig.direction,
                                    entry_price=sig.entry or sig.price,
                                    stop_price=sig.stop, target_price=sig.target_1,
                                    target_2_price=sig.target_2,
                                    alert_type=sig.alert_type.value,
                                    alert_id=_sig_alert_id, session_date=session,
                                )
                            st.toast(f"Trade opened: {sig.symbol}")
                            st.rerun()
                        if col2.button("Skip", key=f"skip_{sig.symbol}_{sig.alert_type.value}"):
                            ack_alert(_sig_alert_id, "skipped")
                            st.toast(f"Skipped {sig.symbol}")
                            st.rerun()

    else:
        st.caption("No signals firing right now. Scanning every 3 minutes.")

    st.caption(f"Last scan: {datetime.now().strftime('%H:%M:%S')} ET | {len(watchlist)} symbols")


# ── Live P&L Tracker ────────────────────────────────────────────────────────
auto_stop = st.session_state.get("auto_stop_entries", {})
if auto_stop:
    st.markdown("<div class='tc-section'>Open Positions</div>", unsafe_allow_html=True)

    for sym, entry_info in auto_stop.items():
        intra = _symbol_intraday.get(sym, pd.DataFrame())
        if intra.empty:
            continue
        current = float(intra["Close"].iloc[-1])
        ep = entry_info["entry_price"]
        sp = entry_info["stop_price"]
        pnl = current - ep
        pnl_pct = (pnl / ep * 100) if ep > 0 else 0
        risk = ep - sp if sp else 1
        r_mult = pnl / risk if risk > 0 else 0

        pnl_class = "green" if pnl >= 0 else "red"
        bar_class = "profit" if pnl >= 0 else "loss"
        bar_width = min(abs(r_mult) / 3 * 100, 100)

        # Look up targets
        t1, t2 = 0.0, 0.0
        for a in st.session_state.get("alert_history", []):
            if a["symbol"] == sym and a["direction"] == "BUY" and a.get("target_1"):
                t1 = a["target_1"]
                t2 = a.get("target_2", 0)
                break

        st.markdown(f"""
        <div class="tc-position">
            <div class="tc-pos-header">
                <span class="tc-pos-sym">{sym}</span>
                <span class="tc-pos-pnl {pnl_class}">{pnl_pct:+.2f}% ({r_mult:+.1f}R)</span>
            </div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#8b9cc0;">
                Entry ${ep:,.2f} &rarr; Current ${current:,.2f}
            </div>
            <div class="tc-pos-bar">
                <div class="tc-pos-bar-fill {bar_class}" style="width:{bar_width:.0f}%"></div>
            </div>
            <div class="tc-pos-levels">
                <span style="color:#ef4444">Stop <span style="color:#8b9cc0">${sp:,.2f}</span></span>
                {"<span style='color:#10b981'>T1 <span style='color:#8b9cc0'>${0:,.2f}</span></span>".format(t1) if t1 else ""}
                {"<span style='color:#f59e0b'>T2 <span style='color:#8b9cc0'>${0:,.2f}</span></span>".format(t2) if t2 else ""}
            </div>
        </div>
        """, unsafe_allow_html=True)


# ── Alert History ───────────────────────────────────────────────────────────
st.markdown("<div class='tc-section'>Alert History</div>", unsafe_allow_html=True)

_db_history = get_alerts_today(user_id=user["id"])
if _db_history:
    _hist_cols = ["symbol", "alert_type", "direction", "price", "entry",
                  "stop", "target_1", "target_2", "confidence", "created_at"]
    hist_df = pd.DataFrame(_db_history)
    _hist_cols = [c for c in _hist_cols if c in hist_df.columns]
    hist_df = hist_df[_hist_cols]
    if "created_at" in hist_df.columns:
        hist_df["created_at"] = pd.to_datetime(hist_df["created_at"]).dt.strftime("%H:%M:%S")
        hist_df = hist_df.rename(columns={"created_at": "time"})
    st.dataframe(
        hist_df, use_container_width=True, hide_index=True,
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
    st.caption("No alerts fired this session.")


# ── EOD Summary ─────────────────────────────────────────────────────────────
_session_phase = get_session_phase()
if _session_phase in ("closed", "last_30", "power_hour") or st.button("Generate Summary", key="gen_summary"):
    st.markdown("<div class='tc-section'>End-of-Day Summary</div>", unsafe_allow_html=True)

    summary = get_session_summary(user_id=user["id"])
    if summary["total"] > 0:
        eod1, eod2, eod3 = st.columns(3)
        eod1.metric("Total", summary["total"])
        eod2.metric("T1 Hits", summary["t1_hits"])
        eod3.metric("Stopped", summary["stopped_out"])

        if summary["signals_by_type"]:
            type_df = pd.DataFrame([
                {"Type": k.replace("_", " ").title(), "Count": v}
                for k, v in summary["signals_by_type"].items()
            ]).sort_values("Count", ascending=False)
            st.dataframe(type_df, use_container_width=True, hide_index=True)
