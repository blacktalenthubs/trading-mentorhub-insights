"""Signal Scanner — Actionable trade plans for your watchlist."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

from db import get_watchlist, add_to_watchlist, remove_from_watchlist, set_watchlist
from config import DEFAULT_POSITION_SIZE
from analytics.market_data import classify_day, fetch_ohlc
from analytics.signal_engine import (
    scan_watchlist, SignalResult, ACTION_LABELS, action_label, action_color, action_help,
)
from analytics.intraday_data import (
    fetch_intraday, fetch_prior_day, get_spy_context,
    fetch_premarket_bars, compute_premarket_brief,
    fetch_hourly_bars, detect_hourly_support,
)
from analytics.intraday_rules import evaluate_rules
from analytics.market_hours import is_market_hours, is_premarket
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

user = ui_theme.setup_page("scanner")

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
def _cached_active_entries(symbol: str, session_date: str) -> list[dict]:
    """Active alert entries for a symbol today (1-min cache)."""
    return get_active_entries(symbol, session_date)


def _get_alert_narrative(symbol: str, session_date: str) -> str:
    """Fetch the most recent AI narrative for a symbol from today's alerts."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT narrative FROM alerts WHERE symbol=? AND session_date=? AND narrative != '' ORDER BY created_at DESC LIMIT 1",
            (symbol, session_date),
        ).fetchone()
        return row["narrative"] if row else ""


# ── Status styling ──────────────────────────────────────────────────────────

_STATUS_COLORS = {v["label"]: v["color"] for v in ACTION_LABELS.values()}


def _color_status(val):
    color = _STATUS_COLORS.get(val, "")
    return f"color: {color}; font-weight: bold" if color else ""


def _color_pattern(val):
    if val == "INSIDE":
        return "background-color: #3498db33; font-weight: bold"
    if val == "OUTSIDE":
        return "background-color: #e74c3c33; font-weight: bold"
    return ""


def _color_score(val):
    if "A+" in str(val):
        return "color: #2ecc71; font-weight: bold"
    if "A " in str(val) or str(val).startswith("A ("):
        return "color: #2ecc71; font-weight: bold"
    if "B" in str(val):
        return "color: #f39c12; font-weight: bold"
    if "C" in str(val):
        return "color: #e74c3c; font-weight: bold"
    return ""


def _color_plan(val):
    if val == "LIVE":
        return "color: #2ecc71; font-weight: bold"
    return "color: #888"


def _draw_mini_chart(r: SignalResult):
    """30-day candlestick chart with levels."""
    hist = _cached_fetch(r.symbol)
    if hist.empty:
        st.caption("Chart data unavailable.")
        return

    hist = hist.copy()
    hist["MA20"] = hist["Close"].rolling(window=20).mean()
    hist["MA50"] = hist["Close"].rolling(window=50).mean()
    chart = hist.tail(30).copy()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=chart.index.strftime("%Y-%m-%d"),
        open=chart["Open"], high=chart["High"],
        low=chart["Low"], close=chart["Close"],
        name=r.symbol,
        increasing_line_color="#2ecc71",
        decreasing_line_color="#e74c3c",
    ))

    for col, label, color in [("MA20", "20 MA", "#f39c12"), ("MA50", "50 MA", "#9b59b6")]:
        ma = chart[col].dropna()
        if not ma.empty:
            fig.add_trace(go.Scatter(
                x=ma.index.strftime("%Y-%m-%d"), y=ma.values,
                mode="lines", name=label, line=dict(color=color, width=1.5),
            ))

    # Trade plan levels — bold labels with colored badges
    fig.add_hline(y=r.entry, line_dash="dash", line_color="#3498db", line_width=2,
                  annotation_text=f"  ENTRY ${r.entry:,.2f}  ",
                  annotation_font=dict(size=12, color="white", family="Arial Black"),
                  annotation_bgcolor="#3498db", annotation_borderpad=3,
                  annotation_position="top left")
    fig.add_hline(y=r.stop, line_dash="dash", line_color="#e74c3c", line_width=2,
                  annotation_text=f"  STOP ${r.stop:,.2f}  ",
                  annotation_font=dict(size=12, color="white", family="Arial Black"),
                  annotation_bgcolor="#e74c3c", annotation_borderpad=3,
                  annotation_position="bottom left")
    fig.add_hline(y=r.target_1, line_dash="dash", line_color="#2ecc71", line_width=2,
                  annotation_text=f"  TARGET ${r.target_1:,.2f}  ",
                  annotation_font=dict(size=12, color="white", family="Arial Black"),
                  annotation_bgcolor="#2ecc71", annotation_borderpad=3,
                  annotation_position="top left")
    # Support level
    fig.add_hline(y=r.nearest_support, line_dash="dot", line_color="#f39c12", line_width=1,
                  annotation_text=f"  SUPPORT ${r.nearest_support:,.2f}  ",
                  annotation_font=dict(size=11, color="white"),
                  annotation_bgcolor="#f39c12", annotation_borderpad=3,
                  annotation_position="bottom left")

    fig.update_layout(
        height=350, xaxis_rangeslider_visible=False,
        yaxis_title="Price ($)",
        margin=dict(l=40, r=20, t=30, b=30),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True)


def _draw_intraday_chart(symbol: str, bars: pd.DataFrame, prior: dict | None, r: SignalResult):
    """5-minute intraday candlestick chart with key levels."""
    if bars.empty:
        return

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=bars.index.strftime("%H:%M"),
        open=bars["Open"], high=bars["High"],
        low=bars["Low"], close=bars["Close"],
        name=symbol,
        increasing_line_color="#2ecc71",
        decreasing_line_color="#e74c3c",
    ))

    # Add key levels
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

    fig.add_hline(y=r.entry, line_dash="dash", line_color="#3498db", line_width=1.5,
                  annotation_text=f"  Entry ${r.entry:,.2f}  ",
                  annotation_font=dict(size=10, color="white"),
                  annotation_bgcolor="#3498db", annotation_borderpad=2,
                  annotation_position="top left")
    fig.add_hline(y=r.stop, line_dash="dash", line_color="#e74c3c", line_width=1.5,
                  annotation_text=f"  Stop ${r.stop:,.2f}  ",
                  annotation_font=dict(size=10, color="white"),
                  annotation_bgcolor="#e74c3c", annotation_borderpad=2,
                  annotation_position="bottom left")
    fig.add_hline(y=r.target_1, line_dash="dash", line_color="#2ecc71", line_width=1.5,
                  annotation_text=f"  T1 ${r.target_1:,.2f}  ",
                  annotation_font=dict(size=10, color="white"),
                  annotation_bgcolor="#2ecc71", annotation_borderpad=2,
                  annotation_position="top left")

    fig.update_layout(
        height=300, xaxis_rangeslider_visible=False,
        yaxis_title="Price ($)", title=f"{symbol} — Intraday 5m",
        margin=dict(l=40, r=20, t=40, b=30),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Page layout ─────────────────────────────────────────────────────────────

ui_theme.page_header("Signal Scanner", "Trade plans for your watchlist — entry, stop, target, re-entry at a glance")

# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Watchlist")

    # Initialize watchlist in session state from DB
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = get_watchlist(user["id"] if user else None)

    _uid = user["id"] if user else None

    # Add symbol one at a time
    add_col, btn_col = st.columns([3, 1])
    with add_col:
        new_sym = st.text_input("Add symbol", key="add_sym_input", label_visibility="collapsed",
                                placeholder="Add symbol...")
    with btn_col:
        add_clicked = st.button("Add", key="add_sym_btn", use_container_width=True)

    if add_clicked and new_sym:
        sym_clean = new_sym.strip().upper()
        if sym_clean and sym_clean not in st.session_state["watchlist"]:
            add_to_watchlist(sym_clean, _uid)
            st.session_state["watchlist"].append(sym_clean)
            st.rerun()

    # Display current watchlist as compact grid with remove buttons
    if st.session_state["watchlist"]:
        remove_sym = None
        _wl = st.session_state["watchlist"]
        # 3-column grid for compactness
        _grid_cols = st.columns(3)
        for i, sym in enumerate(_wl):
            col = _grid_cols[i % 3]
            if col.button(f"{sym}  x", key=f"rm_{sym}_{i}", use_container_width=True):
                remove_sym = sym
        if remove_sym is not None:
            remove_from_watchlist(remove_sym, _uid)
            st.session_state["watchlist"].remove(remove_sym)
            st.rerun()
    else:
        st.caption("No symbols. Add one above.")

    # Bulk edit in collapsible expander
    with st.expander("Bulk Edit"):
        bulk_text = st.text_area(
            "Symbols (comma-separated)",
            value=", ".join(st.session_state["watchlist"]),
            height=80,
            key="bulk_edit_area",
            label_visibility="collapsed",
        )
        if st.button("Apply", key="bulk_apply", use_container_width=True):
            parsed = [s.strip().upper() for s in bulk_text.split(",") if s.strip()]
            set_watchlist(parsed, _uid)
            st.session_state["watchlist"] = parsed
            st.rerun()

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
        entries = _cached_active_entries(r.symbol, _session)
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

at_support = sum(1 for r in results if r.support_status == "AT SUPPORT" and r.score >= 65)
watching = sum(
    1 for r in results
    if r.support_status == "PULLBACK WATCH"
    or (r.support_status == "AT SUPPORT" and r.score < 65)
)
a_plus_count = sum(1 for r in results if r.score >= 90)
a_count = sum(1 for r in results if 75 <= r.score < 90)

col1, col2, col3 = st.columns(3)
col1.metric("BUY ZONE", at_support, help=action_help("AT SUPPORT"))
col2.metric("WAIT FOR DIP", watching, help=action_help("PULLBACK WATCH"))
col3.metric("A+ / A Signals", f"{a_plus_count} / {a_count}",
            help="A+ (90+): full size | A (75+): normal size")

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

# ── Trade Plan Table ────────────────────────────────────────────────────────

ui_theme.section_header("Trade Plans")

price_label = "Price (Live)" if _market_open else "Price"

table_rows = []
for r in results:
    shares = int(position_size / r.entry) if r.entry > 0 else 0
    total_risk = shares * r.risk_per_share

    # Projected S/R from available levels
    price = r.last_close
    _levels = []
    if r.prior_low > 0:
        _levels.append(r.prior_low)
    if r.prior_high > 0:
        _levels.append(r.prior_high)
    if r.ma20 is not None and r.ma20 > 0:
        _levels.append(r.ma20)
    if r.ma50 is not None and r.ma50 > 0:
        _levels.append(r.ma50)
    _below = [l for l in _levels if l <= price]
    _above = [l for l in _levels if l > price]
    proj_support = max(_below) if _below else None
    proj_resist = min(_above) if _above else None

    # Fallback: hourly swing lows when no daily support below price
    if proj_support is None:
        try:
            _h_bars = fetch_hourly_bars(r.symbol)
            _h_supports = detect_hourly_support(_h_bars)
            _h_below = [l for l in _h_supports if l <= price]
            if _h_below:
                proj_support = max(_h_below)
        except Exception:
            pass

    table_rows.append({
        "Symbol": r.symbol,
        "Plan": "LIVE" if r.symbol in _alert_entries else "DAILY",
        "Score": f"{r.score_label} ({r.score})",
        price_label: r.last_close,
        "Status": action_label(r.support_status, r.score),
        "Pattern": r.pattern.upper(),
        "Proj Support": proj_support,
        "Proj Resist": proj_resist,
        "Entry": r.entry,
        "Stop": r.stop,
        "Re-entry Stop": r.reentry_stop,
        "Target": r.target_1,
        "R:R": f"{r.rr_ratio:.1f}:1",
        "Risk/Sh": r.risk_per_share,
        "Shares": shares,
        "$ Risk": total_risk,
    })

table_df = pd.DataFrame(table_rows)

st.dataframe(
    table_df.style
    .format({
        price_label: "${:,.2f}",
        "Proj Support": lambda v: f"${v:,.2f}" if pd.notna(v) else "—",
        "Proj Resist": lambda v: f"${v:,.2f}" if pd.notna(v) else "—",
        "Entry": "${:,.2f}", "Stop": "${:,.2f}",
        "Re-entry Stop": "${:,.2f}", "Target": "${:,.2f}",
        "Risk/Sh": "${:,.2f}", "$ Risk": "${:,.0f}",
    })
    .applymap(_color_plan, subset=["Plan"])
    .applymap(_color_status, subset=["Status"])
    .applymap(_color_pattern, subset=["Pattern"])
    .applymap(_color_score, subset=["Score"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ── Detail per Symbol ───────────────────────────────────────────────────────

ui_theme.section_header("Detail")

for r in results:
    _label = action_label(r.support_status, r.score)
    _acolor = action_color(r.support_status, r.score)

    _opts_label = " | OPTIONS PLAY" if r.symbol in OPTIONS_ELIGIBLE_SYMBOLS and r.score >= OPTIONS_MIN_SCORE else ""

    with st.expander(
        f"{r.symbol}  |  {_label}  |  Score: {r.score_label} ({r.score}){_opts_label}  |  "
        f"Entry ${r.entry:,.2f}  Stop ${r.stop:,.2f}  Target ${r.target_1:,.2f}"
    ):
        # ── Support status + bias ─────────────────────────────────────
        st.markdown(
            f"### <span style='color:{_acolor}'>{_label}</span> — "
            f"{r.pattern.upper()} Day, {r.direction.title()}",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{r.bias}**")

        # ── LIVE plan banner ──────────────────────────────────────
        if r.symbol in _alert_entries:
            _ae = _alert_entries[r.symbol]
            _ae_type = _ae.get("alert_type", "alert").replace("_", " ").title()
            st.markdown(
                f"<div style='padding:8px 12px;border:2px solid #2ecc71;"
                f"border-radius:6px;background:#2ecc7115;margin-bottom:12px'>"
                f"<strong style='color:#2ecc71'>LIVE PLAN</strong> &mdash; "
                f"from <em>{_ae_type}</em> alert. "
                f"Entry/Stop/Targets from intraday signal.</div>",
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

        # ── Trade plan ────────────────────────────────────────────────
        st.markdown("**Trade Plan**")
        tc1, tc2, tc3, tc4, tc5 = st.columns(5)
        tc1.metric("Entry", f"${r.entry:,.2f}")
        tc2.metric("Stop", f"${r.stop:,.2f}",
                    delta=f"-${r.risk_per_share:,.2f}/sh", delta_color="off")
        tc3.metric("Target 1", f"${r.target_1:,.2f}")
        tc4.metric("Target 2", f"${r.target_2:,.2f}")
        tc5.metric("R:R", f"{r.rr_ratio:.1f}:1",
                    delta="GOOD" if r.rr_ratio >= 1.5 else "WEAK",
                    delta_color="normal" if r.rr_ratio >= 1.5 else "inverse")

        # ── AI Trade Thesis ──────────────────────────────────────────
        _narrative = _get_alert_narrative(r.symbol, _session)
        if _narrative:
            st.markdown(
                f"<div style='padding:10px 14px;border-left:4px solid #3498db;"
                f"background:#3498db10;border-radius:4px;margin:8px 0;font-size:0.95rem'>"
                f"<strong>AI Thesis:</strong> {_narrative}</div>",
                unsafe_allow_html=True,
            )

        # ── Re-entry protocol ─────────────────────────────────────────
        st.markdown("**Re-entry Protocol**")
        st.markdown(f"""
| | Attempt 1 | Attempt 2 |
|---|---|---|
| **Entry** | ${r.entry:,.2f} | ${r.entry:,.2f} (same level) |
| **Stop** | ${r.stop:,.2f} | ${r.reentry_stop:,.2f} ($1.50 wider) |
| **Risk/Share** | ${r.risk_per_share:,.2f} | ${r.risk_per_share + 1.50:,.2f} |
| **Rule** | First test of support | Only if price reclaims after stop |
""")
        st.caption("Max 2 attempts. If stopped twice, the level is dead — walk away.")

        # ── Position sizing ───────────────────────────────────────────
        if r.entry > 0 and r.risk_per_share > 0:
            st.markdown("**Position Size**")
            shares = position_size / r.entry
            total_risk = shares * r.risk_per_share
            total_reward_1 = shares * (r.target_1 - r.entry)
            risk_pct = total_risk / position_size * 100

            pc1, pc2, pc3, pc4 = st.columns(4)
            pc1.metric("Shares", f"{shares:,.0f}")
            pc2.metric("$ Risk", f"-${total_risk:,.0f}",
                        delta=f"{risk_pct:.1f}% of position", delta_color="off")
            pc3.metric("$ Reward (T1)", f"+${total_reward_1:,.0f}")
            pc4.metric("Day Range", f"${r.day_range:,.2f}")

            if r.pattern == "outside":
                st.warning(
                    f"Outside day — wide stop. Consider half position "
                    f"({shares/2:,.0f} shares, ${total_risk/2:,.0f} risk)."
                )
            elif risk_pct > 2.0:
                st.warning(f"Risk is {risk_pct:.1f}%. Consider reducing size.")

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
                        sig_color = "#2ecc71" if sig.direction == "BUY" else "#e74c3c"
                        st.markdown(
                            f"<div style='padding:8px 12px;border-left:4px solid {sig_color};"
                            f"background:{sig_color}15;margin-bottom:8px;border-radius:4px'>"
                            f"<strong style='color:{sig_color}'>{sig.direction}</strong> "
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
