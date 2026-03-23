"""Signal Scanner — Actionable trade plans for your watchlist."""

from __future__ import annotations

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
from alerting.alert_store import get_active_entries, today_session
from db import get_db
from alerting.real_trade_store import (
    open_real_trade, close_real_trade, has_open_trade, get_open_trades,
)
from alerting.options_trade_store import (
    has_open_options_trade, open_options_trade,
)
from alert_config import OPTIONS_ELIGIBLE_SYMBOLS, OPTIONS_MIN_SCORE
import ui_theme

user = ui_theme.setup_page("scanner", tier_required="free")

# ── Sync active positions from DB (survive page refresh) ──────────────────
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

# ── Auto-refresh during market hours / pre-market ─────────────────────────
_market_open = is_market_hours()
_premarket = is_premarket()
if _market_open:
    st_autorefresh(interval=180_000, key="scanner_refresh")  # 3 min
elif _premarket:
    st_autorefresh(interval=120_000, key="scanner_pm_refresh")  # 2 min

# ── Cached helpers ──────────────────────────────────────────────────────────


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

    # Key levels — alternate left/right to reduce overlap
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


# ── Page layout ─────────────────────────────────────────────────────────────

ui_theme.page_header("Signal Scanner", "Trade plans for your watchlist — entry, stop, target, re-entry at a glance")

# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    ui_theme.render_sidebar_watchlist(user)

    st.divider()
    position_size = st.number_input(
        "Position Size ($)", value=DEFAULT_POSITION_SIZE, step=5000,
    )

# ── Parse & scan ────────────────────────────────────────────────────────────

symbols = list(st.session_state["watchlist"])
if not symbols:
    ui_theme.empty_state("Enter at least one symbol in the sidebar.")
    st.stop()

raw_results = _cached_scan(tuple(symbols))
results: list[SignalResult] = [SignalResult(**d) for d in raw_results]

# ── Alert-driven plan overlay (market hours only) ────────────────────────
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

# ── KPI Row ─────────────────────────────────────────────────────────────────

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

# ── Pre-Market Brief (4:00-9:29 AM ET only) ──────────────────────────────

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

# ── Trade Plans (expandable cards) ─────────────────────────────────────────

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

        # ── Key levels ─────────────────────────────────────────────
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

        # ── Context ────────────────────────────────────────────────
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

        # AI Thesis (primary context) — falls back to pattern label when unavailable
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

        # ── Key levels ────────────────────────────────────────────────
        st.markdown("**Key Levels**")
        lc1, lc2, lc3, lc4 = st.columns(4)
        lc1.metric("Prior High", f"${r.prior_high:,.2f}")
        lc2.metric("Prior Low", f"${r.prior_low:,.2f}")
        lc3.metric("Nearest Support", f"${r.nearest_support:,.2f}",
                    delta=f"{r.support_label}", delta_color="off")
        lc4.metric("Distance", f"${r.distance_to_support:,.2f}",
                    delta=f"{r.distance_pct:+.2f}%", delta_color="off")

        # ── Live status metrics (LIVE plan, market hours) ────────────
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

                # Progress bar: stop → T2 range
                _total_range = r.target_2 - r.stop
                if _total_range > 0:
                    _progress = (_live_price - r.stop) / _total_range
                    _progress = max(0.0, min(1.0, _progress))
                    st.progress(_progress, text=f"Stop → T2: {_progress:.0%}")

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

        # ── MA context ────────────────────────────────────────────────
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

        # ── Mini chart ────────────────────────────────────────────────
        _draw_mini_chart(r)

        # ── Intraday section ──────────────────────────────────────────
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
                    pos = positions[r.symbol]
                    active_entries.append({
                        "entry_price": pos["entry"],
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
            st.caption("Market closed — intraday data available during market hours (9:30-16:00 ET)")

        # ── Position tracking (persisted to real_trades DB) ─────────
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
                        f"${_opt_strike:.0f} — ${_opt_cost:,.0f}"
                    )
                    st.rerun()

        if not tracking and is_tracking:
            # Close trade in DB
            pos = st.session_state["active_positions"][pos_key]
            trade_id = pos.get("trade_id")
            if trade_id:
                exit_price = r.last_close
                if _market_open and not intra_bars.empty:
                    exit_price = intra_bars["Close"].iloc[-1]
                close_real_trade(trade_id, exit_price)
            del st.session_state["active_positions"][pos_key]
            st.rerun()

        if tracking and is_tracking:
            pos = st.session_state["active_positions"][pos_key]

            pe1, pe2 = st.columns(2)
            new_entry = pe1.number_input(
                "Entry Price", value=pos["entry"], step=0.01,
                key=f"pos_entry_{r.symbol}", format="%.2f",
            )
            new_shares = pe2.number_input(
                "Shares", value=pos["shares"], step=1,
                key=f"pos_shares_{r.symbol}",
            )

            # Update if changed
            if new_entry != pos["entry"] or new_shares != pos["shares"]:
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
                st.progress(progress, text=f"Stop → T2: {progress:.0%}")

            if st.button("Close Position", key=f"close_pos_{r.symbol}", type="secondary"):
                trade_id = pos.get("trade_id")
                if trade_id:
                    close_real_trade(trade_id, live_price)
                del st.session_state["active_positions"][pos_key]
                st.rerun()
