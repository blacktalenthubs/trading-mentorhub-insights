"""Analysis — Consolidated Charts + Win Rates + Fundamentals + AI Coach."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

from db import (
    add_chart_level,
    delete_chart_level,
    get_chart_levels,
    get_watchlist,
)
from alerting.alert_store import get_active_entries, get_alerts_today
from analytics.intraday_data import fetch_intraday, fetch_prior_day, compute_vwap
from analytics.market_hours import is_market_hours

import ui_theme
from ui_theme import (
    CHART_HEIGHTS,
    COLORS,
    PLOTLY_CONFIG,
    FREE_TIER_LIMITS,
    add_level_line,
    build_candlestick_fig,
    colored_metric,
    empty_state,
    page_header,
    section_header,
    get_current_tier,
    render_inline_upgrade,
    render_usage_counter,
    check_usage_limit,
)

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

user = ui_theme.setup_page("analysis", tier_required="pro", tier_preview="free")
_is_free = ui_theme.get_current_tier() == "free"
_tier = ui_theme.get_current_tier()

page_header(
    "Analysis",
    "Charts, win rates, fundamentals, and AI coach — all in one place",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "anly_coach_messages" not in st.session_state:
    st.session_state["anly_coach_messages"] = []
if "anly_coach_context" not in st.session_state:
    st.session_state["anly_coach_context"] = None

# ---------------------------------------------------------------------------
# Shared symbol selector (above tabs) — AI Coach pattern
# ---------------------------------------------------------------------------

_uid = user["id"] if user else None
watchlist = get_watchlist(_uid)
sym_options = watchlist if watchlist else ["SPY"]

# Deep link support (from Telegram alert links)
_qp_symbol = st.query_params.get("symbol", "").strip().upper()
_qp_alert = st.query_params.get("alert", "").strip()

sel_col, custom_col = st.columns([2, 1])
with sel_col:
    _default_idx = 0
    if _qp_symbol and _qp_symbol in sym_options:
        _default_idx = sym_options.index(_qp_symbol)
    selected_sym = st.selectbox(
        "Symbol", sym_options, index=_default_idx, key="anly_symbol_select",
    )
with custom_col:
    custom_sym = st.text_input(
        "Custom symbol", key="anly_custom_sym",
        placeholder="e.g. NVDA",
        value=_qp_symbol if (_qp_symbol and _qp_symbol not in sym_options) else "",
    )
symbol = custom_sym.strip().upper() if custom_sym.strip() else selected_sym

# If deep-linked from a Telegram alert, pre-seed the chat with context
if _qp_alert and not st.session_state["anly_coach_messages"]:
    _alert_label = _qp_alert.replace("_", " ").title()
    st.session_state["anly_deeplink_prompt"] = (
        f"Analyze this {_alert_label} signal for {symbol} — should I take it? "
        f"What's the conviction level and key invalidation price?"
    )

# ---------------------------------------------------------------------------
# Sidebar — context snapshot + controls
# ---------------------------------------------------------------------------

_ai_limit = FREE_TIER_LIMITS["ai_queries_per_day"]

with st.sidebar:
    # Usage counter for free users
    if _is_free and user:
        _, _current_usage = check_usage_limit(user["id"], "ai_query", _ai_limit)
        render_usage_counter(_current_usage, _ai_limit, "AI queries")
        st.divider()

    # Clear chat
    if st.button("Clear conversation", key="anly_clear_chat"):
        st.session_state["anly_coach_messages"] = []
        st.session_state["anly_coach_context"] = None
        st.rerun()

    st.divider()
    st.subheader("Context Snapshot")

    try:
        from analytics.trade_coach import assemble_context

        if st.session_state["anly_coach_context"] is None:
            with st.spinner("Loading market data..."):
                st.session_state["anly_coach_context"] = assemble_context()
        ctx = st.session_state["anly_coach_context"]

        # Open trades
        open_trades = ctx.get("open_trades") or []
        st.metric("Open Trades", len(open_trades))

        # P&L
        stats = ctx.get("trade_stats")
        if stats and stats.get("total_trades", 0) > 0:
            st.metric("Total P&L", f"${stats['total_pnl']:,.2f}")
            st.metric("Win Rate", f"{stats['win_rate']}%")
        else:
            st.metric("Total P&L", "\u2014")
            st.metric("Win Rate", "\u2014")

        # SPY regime
        spy = ctx.get("spy_context")
        if spy:
            st.metric("SPY Regime", spy.get("regime", "\u2014"))
        else:
            st.metric("SPY Regime", "\u2014")

    except Exception:
        st.caption("Could not load context")

    # Position Advisor button (Pro+)
    if not _is_free:
        st.divider()
        if st.button("Check My Positions", use_container_width=True, key="anly_pos_check"):
            st.session_state["anly_run_position_check"] = True

# ---------------------------------------------------------------------------
# Position check result (if triggered from sidebar)
# ---------------------------------------------------------------------------

if st.session_state.pop("anly_run_position_check", False):
    with st.expander("Position Check", expanded=True):
        try:
            from analytics.position_advisor import check_positions_stream
            st.write_stream(check_positions_stream())
        except Exception as e:
            st.error(f"Position check failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Chart helper — full _build_chart from Charts page
# ═══════════════════════════════════════════════════════════════════════════════

# Timeframe definitions: label -> (yf period, yf interval, is_intraday)
TIMEFRAMES = {
    "1m":     ("5d",  "1m",     True),
    "5m":     ("5d",  "5m",     True),
    "15m":    ("1mo", "15m",    True),
    "30m":    ("1mo", "30m",    True),
    "1h":     ("3mo", "1h",     True),
    "Daily":  ("1y",  None,     False),
    "Weekly": ("2y",  "weekly", False),
}

# MA/EMA color palettes
_EMA_COLORS = {5: "#1abc9c", 9: "#2ecc71", 20: "#f39c12", 50: "#e67e22", 100: "#e74c3c", 200: "#9b59b6"}
_SMA_COLORS = {20: "#f39c12", 50: "#9b59b6", 100: "#e74c3c", 200: "#2c3e50"}

# How many bars to show by default per timeframe
_DEFAULT_VISIBLE_BARS = {
    "1m": 120, "5m": 80, "15m": 80, "30m": 60,
    "1h": 60, "Daily": 90, "Weekly": 52,
}


@st.cache_data(ttl=180, show_spinner="Loading chart data...")
def _fetch_bars(symbol: str, period: str, interval: str | None) -> pd.DataFrame:
    """Fetch OHLCV bars for the given symbol, period, and interval."""
    if interval and interval != "weekly":
        return fetch_intraday(symbol, period=period, interval=interval)
    try:
        hist = yf.Ticker(symbol).history(period=period)
        if hist.empty:
            return pd.DataFrame()
        from analytics.intraday_data import _normalize_index_to_et
        hist = _normalize_index_to_et(hist)
        ohlcv = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        if interval == "weekly":
            ohlcv = ohlcv.resample("W-FRI").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum",
            }).dropna()
        return ohlcv
    except Exception:
        return pd.DataFrame()


def _make_tick_labels(bars: pd.DataFrame, is_intraday: bool) -> list[str]:
    """Build human-readable tick labels from bar timestamps."""
    labels = []
    prev_date = None
    for ts in bars.index:
        d = ts.strftime("%b %d")
        if is_intraday:
            if d != prev_date:
                labels.append(ts.strftime("%b %d %H:%M"))
            else:
                labels.append(ts.strftime("%H:%M"))
            prev_date = d
        else:
            labels.append(ts.strftime("%b %d"))
    return labels


def _build_chart(
    symbol: str,
    bars: pd.DataFrame,
    ema_periods: list[int],
    sma_periods: list[int],
    show_vwap: bool,
    prior: dict | None,
    active_entries: list[dict],
    custom_levels: list[dict],
    is_intraday: bool,
    tf_label: str,
) -> go.Figure:
    """Build candlestick + volume chart with all overlays."""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.8, 0.2], vertical_spacing=0.03,
    )

    # Sequential integer x-axis eliminates overnight/weekend gaps.
    n = len(bars)
    x = list(range(n))
    tick_labels = _make_tick_labels(bars, is_intraday)

    # Show ~20 tick labels evenly spaced
    tick_step = max(1, n // 20)
    tick_vals = list(range(0, n, tick_step))
    tick_text = [tick_labels[i] for i in tick_vals]

    # Helper: map a Series (computed on bars.index) to sequential x positions
    def _map_x(series: pd.Series) -> list[int]:
        idx_to_pos = {ts: i for i, ts in enumerate(bars.index)}
        return [idx_to_pos[ts] for ts in series.index if ts in idx_to_pos]

    def _map_y(series: pd.Series) -> list[float]:
        idx_set = set(bars.index)
        return [v for ts, v in zip(series.index, series.values) if ts in idx_set]

    # Row 1: Candlestick
    fig.add_trace(go.Candlestick(
        x=x,
        open=bars["Open"].values, high=bars["High"].values,
        low=bars["Low"].values, close=bars["Close"].values,
        name=symbol,
        increasing_line_color="#2ecc71",
        decreasing_line_color="#e74c3c",
    ), row=1, col=1)

    # Row 1: EMA lines
    for period in ema_periods:
        if len(bars) < period:
            continue
        values = bars["Close"].ewm(span=period, adjust=False).mean().dropna()
        if values.empty:
            continue
        fig.add_trace(go.Scatter(
            x=_map_x(values), y=_map_y(values),
            mode="lines", name=f"EMA {period}",
            line=dict(color=_EMA_COLORS.get(period, "#888"), width=1.5),
        ), row=1, col=1)

    # Row 1: SMA lines
    for period in sma_periods:
        if len(bars) < period:
            continue
        values = bars["Close"].rolling(window=period).mean().dropna()
        if values.empty:
            continue
        fig.add_trace(go.Scatter(
            x=_map_x(values), y=_map_y(values),
            mode="lines", name=f"SMA {period}",
            line=dict(color=_SMA_COLORS.get(period, "#888"), width=1.5),
        ), row=1, col=1)

    # Row 1: VWAP (intraday only)
    if show_vwap and is_intraday:
        vwap = compute_vwap(bars)
        if not vwap.empty:
            vwap_clean = vwap.dropna()
            fig.add_trace(go.Scatter(
                x=_map_x(vwap_clean), y=_map_y(vwap_clean),
                mode="lines", name="VWAP",
                line=dict(color="#3498db", width=1.5, dash="dash"),
            ), row=1, col=1)

    # Row 1: Prior day high/low
    if prior and is_intraday:
        fig.add_hline(
            y=prior["high"], line_dash="dot", line_color="#888", line_width=1,
            annotation_text=f"  Prior High ${prior['high']:,.2f}  ",
            annotation_font=dict(size=10, color="white"),
            annotation_bgcolor="#888", annotation_borderpad=2,
            annotation_position="top left", row=1, col=1,
        )
        fig.add_hline(
            y=prior["low"], line_dash="dot", line_color="#888", line_width=1,
            annotation_text=f"  Prior Low ${prior['low']:,.2f}  ",
            annotation_font=dict(size=10, color="white"),
            annotation_bgcolor="#888", annotation_borderpad=2,
            annotation_position="bottom left", row=1, col=1,
        )

    # Row 1: Active entry levels
    for ae in active_entries:
        if ae.get("entry_price"):
            fig.add_hline(
                y=ae["entry_price"], line_dash="dash", line_color="#3498db", line_width=1.5,
                annotation_text=f"  Entry ${ae['entry_price']:,.2f}  ",
                annotation_font=dict(size=10, color="white", family="Arial Black"),
                annotation_bgcolor="#3498db", annotation_borderpad=2,
                annotation_position="top left", row=1, col=1,
            )
        if ae.get("stop_price"):
            fig.add_hline(
                y=ae["stop_price"], line_dash="dash", line_color="#e74c3c", line_width=1.5,
                annotation_text=f"  Stop ${ae['stop_price']:,.2f}  ",
                annotation_font=dict(size=10, color="white", family="Arial Black"),
                annotation_bgcolor="#e74c3c", annotation_borderpad=2,
                annotation_position="bottom left", row=1, col=1,
            )
        if ae.get("target_1"):
            fig.add_hline(
                y=ae["target_1"], line_dash="dash", line_color="#2ecc71", line_width=1.5,
                annotation_text=f"  T1 ${ae['target_1']:,.2f}  ",
                annotation_font=dict(size=10, color="white", family="Arial Black"),
                annotation_bgcolor="#2ecc71", annotation_borderpad=2,
                annotation_position="top left", row=1, col=1,
            )
        if ae.get("target_2"):
            fig.add_hline(
                y=ae["target_2"], line_dash="dash", line_color="#27ae60", line_width=1,
                annotation_text=f"  T2 ${ae['target_2']:,.2f}  ",
                annotation_font=dict(size=10, color="white"),
                annotation_bgcolor="#27ae60", annotation_borderpad=2,
                annotation_position="top left", row=1, col=1,
            )

    # Row 1: Custom horizontal levels
    for lvl in custom_levels:
        lvl_label = lvl.get("label", "")
        lvl_text = f"  {lvl_label} ${lvl['price']:,.2f}  " if lvl_label else f"  ${lvl['price']:,.2f}  "
        fig.add_hline(
            y=lvl["price"], line_dash="dash", line_color=lvl["color"], line_width=1.5,
            annotation_text=lvl_text,
            annotation_font=dict(size=10, color="white"),
            annotation_bgcolor=lvl["color"], annotation_borderpad=2,
            annotation_position="top left", row=1, col=1,
        )

    # Row 2: Volume bars
    vol_colors = [
        "#2ecc71" if c >= o else "#e74c3c"
        for c, o in zip(bars["Close"], bars["Open"])
    ]
    fig.add_trace(go.Bar(
        x=x, y=bars["Volume"].values,
        marker_color=vol_colors, name="Volume",
        showlegend=False,
    ), row=2, col=1)

    # Default visible range — show most recent N bars
    visible_n = _DEFAULT_VISIBLE_BARS.get(tf_label, 80)
    x_start = max(0, n - visible_n)
    x_end = n - 1

    # Y-axis range from visible window
    vis = bars.iloc[x_start:x_end + 1]
    y_min = vis["Low"].min()
    y_max = vis["High"].max()
    y_pad = (y_max - y_min) * 0.05
    y_range = [y_min - y_pad, y_max + y_pad]

    fig.update_layout(
        height=700,
        yaxis_title="Price ($)",
        yaxis2_title="Volume",
        margin=dict(l=50, r=20, t=10, b=30),
        legend=dict(orientation="h", y=1.02),
        dragmode="pan",
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1a1a2e",
            bordercolor="#1e3a5f",
            font=dict(color="#c9d1d9", size=11),
        ),
        xaxis=dict(
            range=[x_start - 0.5, x_end + 0.5],
            tickvals=tick_vals,
            ticktext=tick_text,
            rangeslider=dict(visible=True, thickness=0.04),
        ),
        yaxis=dict(range=y_range, fixedrange=False),
        xaxis2=dict(
            tickvals=tick_vals,
            ticktext=tick_text,
        ),
        yaxis2=dict(fixedrange=False),
    )

    _spike_kw = dict(
        showspikes=True, spikemode="across", spikethickness=1,
        spikecolor="#888", spikedash="dot", spikesnap="cursor",
    )
    fig.update_xaxes(**_spike_kw)
    fig.update_yaxes(**_spike_kw)

    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# Tabs
# ═══════════════════════════════════════════════════════════════════════════════

tab_chart, tab_daily, tab_weekly, tab_mtf, tab_winrates, tab_fundamentals, tab_coach = st.tabs([
    "Chart", "Daily View", "Weekly View", "MTF Synthesis", "Win Rates", "Fundamentals", "AI Coach",
])


# ── Tab 1: Chart ────────────────────────────────────────────────────────────

with tab_chart:

    # --- Chart sidebar controls (rendered inline for tab context) ---
    with st.sidebar:
        st.divider()
        st.subheader("Chart Overlays")

        # Overlays — grouped multiselects
        st.markdown("**EMA**")
        ema_periods = st.multiselect(
            "EMA periods", [5, 9, 20, 50, 100, 200],
            default=[9, 20, 50],
            key="anly_ema_periods", label_visibility="collapsed",
        )

        st.markdown("**SMA**")
        sma_periods = st.multiselect(
            "SMA periods", [20, 50, 100, 200],
            default=[],
            key="anly_sma_periods", label_visibility="collapsed",
        )

        show_vwap = st.checkbox("VWAP", value=True, key="anly_ov_vwap")

        # Key Levels — only for pro+ users
        if not _is_free:
            st.divider()
            st.markdown("**Key Levels**")
            lc1, lc2, lc3 = st.columns([2, 2, 1])
            with lc1:
                new_price = st.number_input(
                    "Price", min_value=0.0, value=0.0,
                    step=0.50, format="%.2f",
                    key="anly_new_level_price", label_visibility="collapsed",
                )
            with lc2:
                new_label = st.text_input(
                    "Label", placeholder="Label",
                    key="anly_new_level_label", label_visibility="collapsed",
                )
            with lc3:
                add_clicked = st.button("+", key="anly_add_level_btn", use_container_width=True)

            if add_clicked and new_price > 0:
                add_chart_level(symbol, new_price, new_label, "#3498db")
                st.rerun()

            levels = get_chart_levels(symbol)
            for lvl in levels:
                lvl_col, x_col = st.columns([4, 1])
                lvl_text = f"${lvl['price']:,.2f}"
                if lvl.get("label"):
                    lvl_text += f" — {lvl['label']}"
                lvl_col.markdown(lvl_text)
                if x_col.button("x", key=f"anly_del_lvl_{lvl['id']}", type="secondary"):
                    delete_chart_level(lvl["id"])
                    st.rerun()
        else:
            levels = get_chart_levels(symbol)

    # --- Timeframe selector (above chart) ---
    tf_label = st.segmented_control(
        "Timeframe",
        options=list(TIMEFRAMES.keys()),
        default="5m",
        key="anly_chart_tf",
        label_visibility="collapsed",
    )
    if tf_label is None:
        tf_label = "5m"

    period, interval, is_intraday = TIMEFRAMES[tf_label]

    # Auto-refresh during market hours for intraday
    _market_open = is_market_hours()
    if _market_open and is_intraday:
        st_autorefresh(interval=180_000, key="anly_chart_refresh")

    # --- Main chart area ---
    bars = _fetch_bars(symbol, period, interval)
    if bars.empty:
        st.warning(f"No data available for {symbol} ({tf_label}).")
        st.stop()

    prior = fetch_prior_day(symbol) if is_intraday else None
    active_entries = get_active_entries(symbol, user_id=_uid)

    # Price / change header
    _last_close = bars["Close"].iloc[-1]
    _prev_close = bars["Close"].iloc[-2] if len(bars) > 1 else _last_close
    _change = _last_close - _prev_close
    _change_pct = (_change / _prev_close * 100) if _prev_close else 0
    _hi = bars["High"].max()
    _lo = bars["Low"].min()
    _vol = bars["Volume"].iloc[-1] if "Volume" in bars.columns else 0

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric(
        symbol, f"${_last_close:,.2f}",
        delta=f"{_change:+.2f} ({_change_pct:+.1f}%)",
        delta_color="normal",
    )
    mc2.metric("High", f"${_hi:,.2f}")
    mc3.metric("Low", f"${_lo:,.2f}")
    mc4.metric("Volume", f"{_vol:,.0f}")

    fig = _build_chart(
        symbol, bars, ema_periods, sma_periods,
        show_vwap and is_intraday, prior, active_entries, levels, is_intraday, tf_label,
    )

    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    # Alert context — today's alerts for this symbol
    alerts_today = get_alerts_today(user_id=_uid)
    symbol_alerts = [a for a in alerts_today if a.get("symbol") == symbol]

    if symbol_alerts:
        st.subheader(f"Today's Alerts — {symbol}")
        alert_df = pd.DataFrame(symbol_alerts)[
            ["created_at", "alert_type", "direction", "price", "entry", "stop",
             "target_1", "confidence", "message"]
        ]
        alert_df.columns = ["Time", "Type", "Dir", "Price", "Entry", "Stop",
                            "T1", "Confidence", "Message"]
        alert_df["Dir"] = alert_df["Dir"].map(
            lambda d: ui_theme.display_direction(d)[0]
        )
        st.dataframe(
            alert_df.style.format({
                "Price": "${:,.2f}", "Entry": "${:,.2f}",
                "Stop": "${:,.2f}", "T1": "${:,.2f}",
            }, na_rep="—"),
            use_container_width=True,
            hide_index=True,
        )


# ── Tab 2: Daily View ──────────────────────────────────────────────────────

with tab_daily:
    section_header(f"Daily Chart — {symbol}")

    try:
        from analytics.intel_hub import get_daily_bars, analyze_daily_setup

        with st.spinner("Loading daily data..."):
            daily_df, daily_mas = get_daily_bars(symbol)

        if daily_df.empty:
            empty_state(f"No daily data available for {symbol}")
        else:
            # Metrics row
            _d_last = daily_df.iloc[-1]
            _d_close = float(_d_last["Close"])
            _d_open = float(_d_last["Open"])
            _d_change = _d_close - _d_open
            _d_change_pct = (_d_change / _d_open * 100) if _d_open > 0 else 0

            dm1, dm2, dm3 = st.columns(3)
            with dm1:
                st.metric(f"{symbol} Last Close", f"${_d_close:.2f}")
            with dm2:
                st.metric("Day Change", f"{_d_change:+.2f} ({_d_change_pct:+.1f}%)")
            with dm3:
                _d_vol = int(_d_last["Volume"]) if pd.notna(_d_last["Volume"]) else 0
                st.metric("Volume", f"{_d_vol:,}")

            # Daily setup detection
            d_setup = analyze_daily_setup(daily_df, daily_mas)

            # Daily candlestick chart — last 6 months
            _six_mo = daily_df.iloc[-126:] if len(daily_df) > 126 else daily_df
            n_d = len(_six_mo)
            x_d = list(range(n_d))
            tick_step_d = max(1, n_d // 12)
            tick_vals_d = list(range(0, n_d, tick_step_d))
            tick_text_d = [
                _six_mo.index[i].strftime("%b %d") for i in tick_vals_d
            ]

            fig_d = build_candlestick_fig(
                _six_mo, x_d, symbol, height=CHART_HEIGHTS["hero"],
            )
            fig_d.update_xaxes(
                tickvals=tick_vals_d, ticktext=tick_text_d,
                row=1, col=1,
            )

            # SMA/EMA overlays
            _ma_colors = {
                "sma20": "#1abc9c", "sma50": "#f39c12",
                "sma100": "#3498db", "sma200": "#e74c3c",
                "ema20": "#2ecc71", "ema50": "#e67e22",
            }
            _ma_labels = {
                "sma20": "SMA20", "sma50": "SMA50",
                "sma100": "SMA100", "sma200": "SMA200",
                "ema20": "EMA20", "ema50": "EMA50",
            }
            _ma_dashes = {
                "ema20": "dot", "ema50": "dot",
            }
            for ma_key in ("sma20", "sma50", "sma100", "sma200", "ema20", "ema50"):
                period = int(ma_key[3:])
                if len(daily_df) >= period:
                    if ma_key.startswith("sma"):
                        ma_full = daily_df["Close"].rolling(period).mean()
                    else:
                        ma_full = daily_df["Close"].ewm(span=period, adjust=False).mean()
                    ma_slice = ma_full.iloc[-n_d:]
                    fig_d.add_trace(go.Scatter(
                        x=x_d, y=ma_slice.values,
                        mode="lines", name=_ma_labels[ma_key],
                        line=dict(
                            color=_ma_colors[ma_key], width=1.5,
                            dash=_ma_dashes.get(ma_key),
                        ),
                    ), row=1, col=1)

            # Setup level overlays
            if d_setup["setup_type"] != "NO_SETUP":
                if d_setup["entry"]:
                    add_level_line(fig_d, d_setup["entry"], "Entry", COLORS["blue"], width=1)
                if d_setup["stop"]:
                    add_level_line(fig_d, d_setup["stop"], "Stop", COLORS["red"], width=1)
                if d_setup["target_1"]:
                    add_level_line(fig_d, d_setup["target_1"], "T1", COLORS["green"], width=1)
                if d_setup["target_2"]:
                    add_level_line(fig_d, d_setup["target_2"], "T2", COLORS["green"], dash="dot", width=1)

            st.plotly_chart(fig_d, use_container_width=True, config=PLOTLY_CONFIG)

            # MA values row
            if daily_mas:
                _ma_cols = st.columns(len(daily_mas))
                for col, (key, val) in zip(_ma_cols, daily_mas.items()):
                    with col:
                        color = _ma_colors.get(key, COLORS["blue"])
                        colored_metric(key.upper(), f"${val:.2f}", color)

            # --- Daily Setup Card ---
            section_header("Daily Setup")

            if d_setup["setup_type"] == "NO_SETUP":
                empty_state("No daily setup detected")
            else:
                _d_setup_colors = {
                    "BREAKOUT": COLORS["green"],
                    "PULLBACK_TO_MA": COLORS["orange"],
                    "MA_COMPRESSION": COLORS["purple"],
                    "TREND_CONTINUATION": COLORS["blue"],
                    "BREAKDOWN": COLORS["red"],
                }
                _ds_color = _d_setup_colors.get(d_setup["setup_type"], COLORS["blue"])

                ds1, ds2 = st.columns([1, 2])
                with ds1:
                    colored_metric("Setup", d_setup["setup_type"].replace("_", " "), _ds_color)
                with ds2:
                    _ds_score_color = COLORS["green"] if d_setup["score"] >= 70 else COLORS["orange"] if d_setup["score"] >= 55 else COLORS["red"]
                    colored_metric("Score", f"{d_setup['score_label']} ({d_setup['score']})", _ds_score_color)

                st.caption(d_setup["edge"])

                # KPI row
                dk1, dk2, dk3, dk4, dk5 = st.columns(5)
                with dk1:
                    colored_metric("Consol Days", str(d_setup["consolidation_days"]) if d_setup["consolidation_days"] else "\u2014", COLORS["blue"])
                with dk2:
                    _dr_str = f"{d_setup['range_pct'] * 100:.1f}%" if d_setup["range_pct"] else "\u2014"
                    colored_metric("Range", _dr_str, COLORS["blue"])
                with dk3:
                    _ma_seq_color = COLORS["green"] if d_setup["ma_sequence"] == "bull" else COLORS["red"] if d_setup["ma_sequence"] == "bear" else COLORS["orange"]
                    colored_metric("MA Sequence", d_setup["ma_sequence"].upper(), _ma_seq_color)
                with dk4:
                    _drr_str = f"{d_setup['risk_reward']:.1f}:1" if d_setup["risk_reward"] else "\u2014"
                    _drr_color = COLORS["green"] if d_setup["risk_reward"] >= 2.0 else COLORS["orange"]
                    colored_metric("R:R", _drr_str, _drr_color)
                with dk5:
                    _dp, _dd = d_setup["daily_candle"]
                    colored_metric("Candle", f"{_dp} / {_dd}", COLORS["purple"])

                # Levels row
                dl1, dl2, dl3, dl4 = st.columns(4)
                with dl1:
                    val = f"${d_setup['entry']:.2f}" if d_setup["entry"] else "\u2014"
                    colored_metric("Entry", val, COLORS["blue"])
                with dl2:
                    val = f"${d_setup['stop']:.2f}" if d_setup["stop"] else "\u2014"
                    colored_metric("Stop", val, COLORS["red"])
                with dl3:
                    val = f"${d_setup['target_1']:.2f}" if d_setup["target_1"] else "\u2014"
                    colored_metric("Target 1", val, COLORS["green"])
                with dl4:
                    val = f"${d_setup['target_2']:.2f}" if d_setup["target_2"] else "\u2014"
                    colored_metric("Target 2", val, COLORS["green"])

            # AI Daily Trend button
            section_header("AI Analysis")
            _can_ai_d, _cnt_d = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
            if not _can_ai_d:
                render_inline_upgrade("Unlimited AI analysis — no daily limits", "elite")
            elif st.button("AI Daily Trend", key="anly_ai_daily"):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                try:
                    from analytics.intel_hub import ask_ai_insight

                    ctx_lines = [f"Daily chart for {symbol}:"]
                    for i in range(-3, 0):
                        if abs(i) <= len(daily_df):
                            bar = daily_df.iloc[i]
                            dt_label = daily_df.index[i].strftime("%Y-%m-%d")
                            ctx_lines.append(
                                f"{dt_label}: O=${float(bar['Open']):.2f} "
                                f"H=${float(bar['High']):.2f} "
                                f"L=${float(bar['Low']):.2f} "
                                f"C=${float(bar['Close']):.2f}"
                            )
                    for key, val in daily_mas.items():
                        ctx_lines.append(f"{key.upper()}: ${val:.2f}")
                    if d_setup["setup_type"] != "NO_SETUP":
                        ctx_lines.append(f"Daily setup: {d_setup['setup_type']}")
                        ctx_lines.append(f"Setup edge: {d_setup['edge']}")
                        ctx_lines.append(f"Score: {d_setup['score_label']} ({d_setup['score']})")
                        ctx_lines.append(f"MA sequence: {d_setup['ma_sequence']}")
                        if d_setup["entry"]:
                            ctx_lines.append(f"Entry: {d_setup['entry']:.2f}")
                        if d_setup["stop"]:
                            ctx_lines.append(f"Stop: {d_setup['stop']:.2f}")
                        if d_setup["target_1"]:
                            ctx_lines.append(f"T1: {d_setup['target_1']:.2f}")

                    st.write_stream(ask_ai_insight(
                        f"Analyze {symbol}'s daily chart structure. "
                        "Assess trend direction, MA positioning, key daily levels, "
                        "consolidation patterns, and what to watch tomorrow.",
                        "\n".join(ctx_lines),
                    ))
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"AI analysis error: {e}")

            # Pattern Classification button
            _can_ai_pat, _ = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
            if not _can_ai_pat:
                pass
            elif st.button("Classify Chart Pattern", key="anly_ai_pattern"):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                try:
                    from analytics.intel_hub import classify_daily_pattern
                    st.write_stream(classify_daily_pattern(symbol, daily_df, daily_mas))
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Pattern classification error: {e}")

    except Exception as e:
        st.error(f"Failed to load daily data: {e}")


# ── Tab 3: Weekly View ─────────────────────────────────────────────────────

with tab_weekly:
    section_header(f"Weekly Chart \u2014 {symbol}")

    try:
        from analytics.intel_hub import get_weekly_bars, analyze_weekly_setup

        with st.spinner("Loading weekly data..."):
            weekly_df, wmas = get_weekly_bars(symbol)

        if weekly_df.empty:
            empty_state(f"No weekly data available for {symbol}")
        else:
            last_bar = weekly_df.iloc[-1]
            week_close = float(last_bar["Close"])
            week_open = float(last_bar["Open"])
            week_change = week_close - week_open
            week_change_pct = (week_change / week_open * 100) if week_open > 0 else 0

            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric(f"{symbol} Weekly Close", f"${week_close:.2f}")
            with m2:
                st.metric("Week Change", f"{week_change:+.2f} ({week_change_pct:+.1f}%)")
            with m3:
                vol = int(last_bar["Volume"]) if pd.notna(last_bar["Volume"]) else 0
                st.metric("Week Volume", f"{vol:,}")

            setup = analyze_weekly_setup(weekly_df, wmas)

            # Weekly candlestick chart with WMA overlays
            n = len(weekly_df)
            x = list(range(n))
            tick_step = max(1, n // 15)
            tick_vals = list(range(0, n, tick_step))
            tick_text = [
                weekly_df.index[i].strftime("%b %Y") for i in tick_vals
            ]

            fig_w = build_candlestick_fig(
                weekly_df, x, symbol, height=CHART_HEIGHTS["hero"],
            )
            fig_w.update_xaxes(
                tickvals=tick_vals, ticktext=tick_text,
                row=1, col=1,
            )

            _wma_colors = {10: "#1abc9c", 20: "#f39c12", 50: "#9b59b6"}
            for period in (10, 20, 50):
                if len(weekly_df) >= period:
                    ma_series = weekly_df["Close"].rolling(period).mean()
                    fig_w.add_trace(go.Scatter(
                        x=x, y=ma_series.values,
                        mode="lines", name=f"WMA{period}",
                        line=dict(color=_wma_colors[period], width=1.5),
                    ), row=1, col=1)

            # Setup level overlays
            if setup["setup_type"] != "NO_SETUP":
                if setup["entry"]:
                    add_level_line(fig_w, setup["entry"], "Entry", COLORS["blue"], width=1)
                if setup["stop"]:
                    add_level_line(fig_w, setup["stop"], "Stop", COLORS["red"], width=1)
                if setup["target_1"]:
                    add_level_line(fig_w, setup["target_1"], "T1", COLORS["green"], width=1)
                if setup["target_2"]:
                    add_level_line(fig_w, setup["target_2"], "T2", COLORS["green"], dash="dot", width=1)

                if setup["base_high"] and setup["base_low"]:
                    fig_w.add_hrect(
                        y0=setup["base_low"], y1=setup["base_high"],
                        fillcolor="rgba(52, 152, 219, 0.12)",
                        line=dict(color="rgba(52, 152, 219, 0.3)", width=1),
                        annotation_text="Base Range",
                        annotation_font=dict(size=9, color="#3498db"),
                        annotation_position="top left",
                        row=1, col=1,
                    )

            st.plotly_chart(fig_w, use_container_width=True, config=PLOTLY_CONFIG)

            # WMA values
            if wmas:
                wma_cols = st.columns(len(wmas))
                for col, (key, val) in zip(wma_cols, wmas.items()):
                    with col:
                        label = key.upper()
                        color = _wma_colors.get(int(key[3:]), COLORS["blue"])
                        colored_metric(label, f"${val:.2f}", color)

            # --- Setup Card ---
            section_header("Weekly Setup")

            if setup["setup_type"] == "NO_SETUP":
                empty_state("No weekly setup detected")
            else:
                _setup_colors = {
                    "BREAKOUT": COLORS["green"],
                    "BASE_FORMING": COLORS["blue"],
                    "PULLBACK": COLORS["orange"],
                }
                setup_color = _setup_colors.get(setup["setup_type"], COLORS["blue"])

                s1, s2 = st.columns([1, 2])
                with s1:
                    colored_metric("Setup", setup["setup_type"].replace("_", " "), setup_color)
                with s2:
                    score_color = COLORS["green"] if setup["score"] >= 70 else COLORS["orange"] if setup["score"] >= 55 else COLORS["red"]
                    colored_metric("Score", f"{setup['score_label']} ({setup['score']})", score_color)

                st.caption(setup["edge"])

                k1, k2, k3, k4, k5 = st.columns(5)
                with k1:
                    colored_metric("Base Weeks", str(setup["base_weeks"]) if setup["base_weeks"] else "\u2014", COLORS["blue"])
                with k2:
                    range_str = f"{setup['base_range_pct'] * 100:.1f}%" if setup["base_range_pct"] else "\u2014"
                    colored_metric("Range", range_str, COLORS["blue"])
                with k3:
                    vol_str = "Yes" if setup["volume_contracting"] else "No"
                    vol_color = COLORS["green"] if setup["volume_contracting"] else COLORS["red"]
                    colored_metric("Vol Contracting", vol_str, vol_color)
                with k4:
                    rr_str = f"{setup['risk_reward']:.1f}:1" if setup["risk_reward"] else "\u2014"
                    rr_color = COLORS["green"] if setup["risk_reward"] >= 2.0 else COLORS["orange"]
                    colored_metric("R:R", rr_str, rr_color)
                with k5:
                    pattern, direction = setup["weekly_candle"]
                    colored_metric("Candle", f"{pattern} / {direction}", COLORS["purple"])

                l1, l2, l3, l4 = st.columns(4)
                with l1:
                    val = f"${setup['entry']:.2f}" if setup["entry"] else "\u2014"
                    colored_metric("Entry", val, COLORS["blue"])
                with l2:
                    val = f"${setup['stop']:.2f}" if setup["stop"] else "\u2014"
                    colored_metric("Stop", val, COLORS["red"])
                with l3:
                    val = f"${setup['target_1']:.2f}" if setup["target_1"] else "\u2014"
                    colored_metric("Target 1", val, COLORS["green"])
                with l4:
                    val = f"${setup['target_2']:.2f}" if setup["target_2"] else "\u2014"
                    colored_metric("Target 2", val, COLORS["green"])

            # AI Weekly Trend button
            section_header("AI Analysis")
            _can_ai_3, _cnt_3 = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
            if not _can_ai_3:
                render_inline_upgrade("Unlimited AI analysis — no daily limits", "elite")
            elif st.button("AI Weekly Trend", key="anly_ai_weekly"):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                try:
                    from analytics.intel_hub import ask_ai_insight

                    context_parts = [f"Weekly chart for {symbol}:"]
                    context_parts.append(
                        f"Last week: O=${week_open:.2f} H=${float(last_bar['High']):.2f} "
                        f"L=${float(last_bar['Low']):.2f} C=${week_close:.2f}"
                    )
                    if len(weekly_df) >= 2:
                        prev = weekly_df.iloc[-2]
                        context_parts.append(
                            f"Prior week: O=${float(prev['Open']):.2f} "
                            f"H=${float(prev['High']):.2f} "
                            f"L=${float(prev['Low']):.2f} "
                            f"C=${float(prev['Close']):.2f}"
                        )
                    for key, val in wmas.items():
                        context_parts.append(f"{key.upper()}: ${val:.2f}")
                    if setup["setup_type"] != "NO_SETUP":
                        context_parts.append(f"Weekly setup: {setup['setup_type']}")
                        context_parts.append(f"Setup edge: {setup['edge']}")
                        context_parts.append(f"Score: {setup['score_label']} ({setup['score']})")
                        if setup["entry"]:
                            context_parts.append(f"Entry: {setup['entry']:.2f}")
                        if setup["stop"]:
                            context_parts.append(f"Stop: {setup['stop']:.2f}")
                        if setup["target_1"]:
                            context_parts.append(f"T1: {setup['target_1']:.2f}")

                    st.write_stream(ask_ai_insight(
                        f"Analyze {symbol}'s weekly chart structure. "
                        "Assess trend direction, MA positioning, key weekly "
                        "levels, and what to watch next week.",
                        "\n".join(context_parts),
                    ))
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"AI analysis error: {e}")

    except Exception as e:
        st.error(f"Failed to load weekly data: {e}")


# ── Tab 4: MTF Synthesis ───────────────────────────────────────────────────

with tab_mtf:
    section_header(f"Multi-Timeframe Synthesis \u2014 {symbol}")

    try:
        from analytics.intel_hub import get_daily_bars, get_weekly_bars
        from analytics.intel_hub import analyze_daily_setup, analyze_weekly_setup
        from analytics.intel_hub import build_mtf_context

        with st.spinner("Loading daily + weekly data..."):
            _mtf_daily, _mtf_dmas = get_daily_bars(symbol)
            _mtf_weekly, _mtf_wmas = get_weekly_bars(symbol)

        if _mtf_daily.empty and _mtf_weekly.empty:
            empty_state(f"No data available for {symbol}")
        else:
            _mtf_d_setup = analyze_daily_setup(_mtf_daily, _mtf_dmas) if not _mtf_daily.empty else {"setup_type": "NO_SETUP", "score": 0, "score_label": "C", "edge": "No data", "ma_sequence": "mixed", "daily_candle": ("normal", "neutral")}
            _mtf_w_setup = analyze_weekly_setup(_mtf_weekly, _mtf_wmas) if not _mtf_weekly.empty else {"setup_type": "NO_SETUP", "score": 0, "score_label": "C", "edge": "No data", "weekly_candle": ("normal", "neutral")}

            # Side-by-side setup comparison
            col_d, col_w = st.columns(2)
            with col_d:
                section_header("Daily Setup")
                _ds_type = _mtf_d_setup["setup_type"]
                _ds_color = COLORS["green"] if _ds_type in ("BREAKOUT", "PULLBACK_TO_MA", "TREND_CONTINUATION") else COLORS["red"] if _ds_type == "BREAKDOWN" else COLORS["blue"]
                colored_metric("Setup", _ds_type.replace("_", " "), _ds_color)
                _ds_sc = COLORS["green"] if _mtf_d_setup["score"] >= 70 else COLORS["orange"] if _mtf_d_setup["score"] >= 55 else COLORS["red"]
                colored_metric("Score", f"{_mtf_d_setup['score_label']} ({_mtf_d_setup['score']})", _ds_sc)
                st.caption(_mtf_d_setup["edge"])
                colored_metric("MA Sequence", _mtf_d_setup.get("ma_sequence", "mixed").upper(), COLORS["blue"])

            with col_w:
                section_header("Weekly Setup")
                _ws_type = _mtf_w_setup["setup_type"]
                _ws_color = COLORS["green"] if _ws_type in ("BREAKOUT", "PULLBACK") else COLORS["orange"] if _ws_type == "BASE_FORMING" else COLORS["blue"]
                colored_metric("Setup", _ws_type.replace("_", " "), _ws_color)
                _ws_sc = COLORS["green"] if _mtf_w_setup["score"] >= 70 else COLORS["orange"] if _mtf_w_setup["score"] >= 55 else COLORS["red"]
                colored_metric("Score", f"{_mtf_w_setup['score_label']} ({_mtf_w_setup['score']})", _ws_sc)
                st.caption(_mtf_w_setup["edge"])
                wc_p, wc_d = _mtf_w_setup.get("weekly_candle", ("normal", "neutral"))
                colored_metric("Weekly Candle", f"{wc_p} / {wc_d}", COLORS["purple"])

            # Alignment badge
            st.divider()
            _w_bull = _mtf_w_setup["setup_type"] in ("BREAKOUT", "PULLBACK", "BASE_FORMING")
            _d_bull = _mtf_d_setup["setup_type"] in ("BREAKOUT", "PULLBACK_TO_MA", "TREND_CONTINUATION", "MA_COMPRESSION")
            _w_bear = _mtf_w_setup["setup_type"] == "NO_SETUP" and wc_d == "bearish"
            _d_bear = _mtf_d_setup["setup_type"] == "BREAKDOWN" or _mtf_d_setup.get("ma_sequence") == "bear"

            if _w_bull and _d_bull:
                colored_metric("Alignment", "ALIGNED BULLISH", COLORS["green"])
                st.caption("Both weekly and daily timeframes constructive \u2014 higher conviction long setups")
            elif _w_bear and _d_bear:
                colored_metric("Alignment", "ALIGNED BEARISH", COLORS["red"])
                st.caption("Both timeframes weak \u2014 avoid longs, consider shorts or cash")
            elif _w_bull and _d_bear:
                colored_metric("Alignment", "CONFLICT", COLORS["orange"])
                st.caption("Weekly bullish but daily breaking down \u2014 potential trap or pullback in progress")
            elif _w_bear and _d_bull:
                colored_metric("Alignment", "CONFLICT", COLORS["orange"])
                st.caption("Daily bounce but weekly structure weak \u2014 counter-trend risk, tighten stops")
            else:
                colored_metric("Alignment", "MIXED", COLORS["blue"])
                st.caption("No clear alignment between timeframes \u2014 wait for resolution or reduce size")

            # AI MTF Synthesis button
            section_header("AI Analysis")
            _can_ai_mtf, _ = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
            if not _can_ai_mtf:
                render_inline_upgrade("Unlimited AI analysis \u2014 no daily limits", "elite")
            elif st.button("AI MTF Synthesis", key="anly_ai_mtf"):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                try:
                    from analytics.intel_hub import ask_ai_insight

                    mtf_ctx = build_mtf_context(
                        symbol,
                        _mtf_daily, _mtf_dmas, _mtf_d_setup,
                        _mtf_weekly, _mtf_wmas, _mtf_w_setup,
                    )
                    st.write_stream(ask_ai_insight(
                        f"Synthesize {symbol}'s multi-timeframe picture. "
                        "Are the daily and weekly timeframes aligned or conflicting? "
                        "What is the highest-probability trade setup given both views? "
                        "Identify key levels where the timeframes converge. "
                        "What should the trader watch for confirmation or invalidation?",
                        mtf_ctx,
                    ))
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"AI analysis error: {e}")

    except Exception as e:
        st.error(f"Failed to load MTF data: {e}")


# ── Tab 5: Win Rates ────────────────────────────────────────────────────────

with tab_winrates:
    if _is_free:
        render_inline_upgrade("Win rate analytics with AI insights", "pro")
    else:
        section_header("Alert Win Rates", "Historical signal accuracy")

        _wr_col1, _wr_col2 = st.columns(2)
        with _wr_col1:
            lookback = st.selectbox(
                "Lookback period", [30, 60, 90, 180],
                index=2, key="anly_win_rate_lookback",
                format_func=lambda d: f"{d} days",
            )
        with _wr_col2:
            _metric_mode = st.radio(
                "View", ["All Alerts", "My Trades"],
                horizontal=True, key="anly_win_rate_mode",
                help="'My Trades' shows only alerts you acknowledged via Telegram.",
            )

        try:
            from analytics.intel_hub import get_alert_win_rates, get_acked_trade_win_rates

            with st.spinner("Analyzing alerts..."):
                if _metric_mode == "My Trades" and _uid is not None:
                    rates = get_acked_trade_win_rates(user_id=_uid, days=lookback)
                else:
                    rates = get_alert_win_rates(days=lookback, user_id=_uid)

            overall = rates.get("overall", {})
            if overall.get("total", 0) == 0:
                empty_state("No entry signals found in this period")
            else:
                # KPI row
                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    colored_metric("Total Signals", str(overall["total"]), COLORS["blue"])
                with k2:
                    wr = overall["win_rate"]
                    wr_color = COLORS["green"] if wr >= 50 else COLORS["red"]
                    colored_metric("Win Rate", f"{wr}%", wr_color)
                with k3:
                    colored_metric("Wins", str(overall["wins"]), COLORS["green"])
                with k4:
                    colored_metric("Losses", str(overall["losses"]), COLORS["red"])

                # Win rate by symbol
                by_sym = rates.get("by_symbol", {})
                if by_sym:
                    section_header("By Symbol")
                    sym_rows = [
                        {"Symbol": sym, "Win Rate": f"{d['win_rate']}%",
                         "Wins": d["wins"], "Losses": d["losses"],
                         "Total": d["total"]}
                        for sym, d in sorted(by_sym.items(),
                                             key=lambda x: x[1]["win_rate"],
                                             reverse=True)
                    ]
                    st.dataframe(
                        pd.DataFrame(sym_rows),
                        use_container_width=True, hide_index=True,
                    )

                # Win rate by setup type
                by_type = rates.get("by_alert_type", {})
                if by_type:
                    section_header("By Setup Type")
                    type_rows = [
                        {"Setup": at.replace("_", " ").title(),
                         "Win Rate": f"{d['win_rate']}%",
                         "Wins": d["wins"], "Losses": d["losses"],
                         "Total": d["total"]}
                        for at, d in sorted(by_type.items(),
                                            key=lambda x: x[1]["win_rate"],
                                            reverse=True)
                    ]
                    st.dataframe(
                        pd.DataFrame(type_rows),
                        use_container_width=True, hide_index=True,
                    )

                # Win rate by hour
                by_hour = rates.get("by_hour", {})
                if by_hour:
                    section_header("By Hour of Day")

                    hours = list(by_hour.keys())
                    wr_vals = [by_hour[h]["win_rate"] for h in hours]
                    bar_colors = [
                        COLORS["green"] if w >= 50 else COLORS["red"]
                        for w in wr_vals
                    ]
                    fig_hr = go.Figure(go.Bar(
                        x=[f"{h}:00" for h in hours],
                        y=wr_vals,
                        marker_color=bar_colors,
                        text=[f"{w}%" for w in wr_vals],
                        textposition="outside",
                    ))
                    fig_hr.update_layout(
                        height=300,
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#c9d1d9", size=11),
                        margin=dict(l=40, r=20, t=30, b=30),
                        yaxis_title="Win Rate %",
                        xaxis_title="Hour (ET)",
                        yaxis=dict(gridcolor="#1e3a5f"),
                    )
                    st.plotly_chart(fig_hr, use_container_width=True,
                                    config={"displayModeBar": False})

                # AI Analysis button
                section_header("AI Analysis")
                _can_ai_1, _cnt_1 = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
                if not _can_ai_1:
                    render_inline_upgrade("Unlimited AI analysis — no daily limits", "elite")
                elif st.button("Get AI Analysis", key="anly_ai_win_rate"):
                    if _is_free and user:
                        from db import increment_daily_usage
                        increment_daily_usage(user["id"], "ai_query")
                    try:
                        from analytics.intel_hub import ask_ai_insight

                        context_lines = [f"Alert win rates ({lookback} days):"]
                        context_lines.append(
                            f"Overall: {overall['win_rate']}% "
                            f"({overall['wins']}W/{overall['losses']}L)"
                        )
                        for sym_name, d in sorted(
                            by_sym.items(), key=lambda x: x[1]["total"], reverse=True
                        )[:10]:
                            context_lines.append(
                                f"{sym_name}: {d['win_rate']}% ({d['wins']}W/{d['losses']}L)"
                            )
                        for at, d in by_type.items():
                            context_lines.append(
                                f"{at.replace('_', ' ')}: {d['win_rate']}%"
                            )

                        st.write_stream(ask_ai_insight(
                            "Analyze these alert win rates. Identify patterns: "
                            "which symbols and setups perform best/worst, "
                            "optimal trading hours, and actionable improvements.",
                            "\n".join(context_lines),
                        ))
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"AI analysis error: {e}")

        except Exception as e:
            st.error(f"Failed to load win rates: {e}")

        # ── Decision Quality ──────────────────────────────────────────────
        if _uid:
            section_header("Decision Quality", "Are you taking the right trades?")
            try:
                from analytics.intel_hub import get_decision_quality

                dq = get_decision_quality(_uid, days=lookback)
                took = dq.get("took", {})
                skipped = dq.get("skipped", {})

                if took.get("total", 0) == 0 and skipped.get("total", 0) == 0:
                    empty_state(
                        "No ACK data yet. Use the Took It / Skip buttons on "
                        "Telegram alerts to start tracking your decisions."
                    )
                else:
                    d1, d2, d3 = st.columns(3)
                    with d1:
                        if took.get("total", 0) > 0:
                            wr = took["win_rate"]
                            wr_color = COLORS["green"] if wr >= 50 else COLORS["red"]
                            colored_metric(
                                "Took It Win Rate",
                                f"{wr}% ({took['wins']}W/{took['losses']}L)",
                                wr_color,
                            )
                        else:
                            colored_metric("Took It", "No trades yet", COLORS["blue"])
                    with d2:
                        if skipped.get("total", 0) > 0:
                            wr = skipped["win_rate"]
                            wr_color = COLORS["green"] if wr >= 50 else COLORS["red"]
                            colored_metric(
                                "Skipped Win Rate",
                                f"{wr}% ({skipped['wins']}W/{skipped['losses']}L)",
                                wr_color,
                            )
                        else:
                            colored_metric("Skipped", "No skips yet", COLORS["blue"])
                    with d3:
                        edge = dq.get("decision_edge")
                        if edge is not None:
                            edge_color = COLORS["green"] if edge > 0 else COLORS["red"] if edge < 0 else COLORS["blue"]
                            sign = "+" if edge > 0 else ""
                            colored_metric("Decision Edge", f"{sign}{edge}%", edge_color)
                            if edge > 0:
                                st.caption("You're filtering well — took trades outperform skipped ones.")
                            elif edge < 0:
                                st.caption("Skipped trades did better — consider being less selective.")
                        else:
                            colored_metric("Decision Edge", "Need both took + skipped data", COLORS["blue"])

            except Exception as e:
                st.caption(f"Decision quality unavailable: {e}")

        # ── Trading Journal ───────────────────────────────────────────────
        if _uid:
            section_header("Trading Journal", "Your recent trade decisions")
            try:
                from analytics.intel_hub import get_trading_journal

                _journal_days = st.selectbox(
                    "Journal period", [7, 14, 30, 60, 90],
                    index=2, key="anly_journal_lookback",
                    format_func=lambda d: f"Last {d} days",
                )
                journal = get_trading_journal(_uid, days=_journal_days)

                if not journal:
                    empty_state(
                        "No trade decisions yet. ACK alerts via Telegram to populate your journal."
                    )
                else:
                    # Summary row
                    took_count = sum(1 for j in journal if j["user_action"] == "took")
                    skip_count = sum(1 for j in journal if j["user_action"] == "skipped")
                    wins = sum(1 for j in journal if j["user_action"] == "took" and j["outcome"] == "win")
                    losses = sum(1 for j in journal if j["user_action"] == "took" and j["outcome"] == "loss")
                    total_pnl = sum(j.get("pnl") or 0 for j in journal if j.get("pnl") is not None)

                    j1, j2, j3, j4 = st.columns(4)
                    with j1:
                        colored_metric("Trades Taken", str(took_count), COLORS["green"])
                    with j2:
                        colored_metric("Skipped", str(skip_count), COLORS["orange"])
                    with j3:
                        wr = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0.0
                        wr_color = COLORS["green"] if wr >= 50 else COLORS["red"]
                        colored_metric("Win Rate", f"{wr}%", wr_color)
                    with j4:
                        pnl_color = COLORS["green"] if total_pnl >= 0 else COLORS["red"]
                        colored_metric("Total P&L", f"${total_pnl:+,.2f}", pnl_color)

                    # Journal table
                    rows = []
                    for j in journal:
                        action_badge = "TOOK" if j["user_action"] == "took" else "SKIP"
                        outcome_map = {"win": "W", "loss": "L", "open": "-"}
                        pnl_str = f"${j['pnl']:+.2f}" if j.get("pnl") is not None else ""
                        rows.append({
                            "Date": j.get("session_date", ""),
                            "Symbol": j["symbol"],
                            "Setup": j["alert_type"].replace("_", " ").title(),
                            "Score": j.get("score_label") or "",
                            "Action": action_badge,
                            "Entry": f"${j['entry']:.2f}" if j.get("entry") else "",
                            "Stop": f"${j['stop']:.2f}" if j.get("stop") else "",
                            "Outcome": outcome_map.get(j.get("outcome", ""), "-"),
                            "P&L": pnl_str,
                        })

                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                    )

                    # AI Journal Analysis button
                    _can_ai_j, _ = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
                    if not _can_ai_j:
                        render_inline_upgrade("Unlimited AI analysis", "elite")
                    elif st.button("AI Journal Analysis", key="anly_ai_journal"):
                        if _is_free and user:
                            from db import increment_daily_usage
                            increment_daily_usage(user["id"], "ai_query")
                        try:
                            from analytics.intel_hub import ask_ai_insight

                            context_lines = [f"Trading journal ({_journal_days} days):"]
                            context_lines.append(f"Took: {took_count}, Skipped: {skip_count}")
                            context_lines.append(f"Win rate: {wr}%, Total P&L: ${total_pnl:+.2f}")
                            for j in journal[:20]:
                                action = j["user_action"].upper()
                                outcome = j.get("outcome", "open")
                                pnl = f" P&L=${j['pnl']:+.2f}" if j.get("pnl") is not None else ""
                                context_lines.append(
                                    f"{j['session_date']} {j['symbol']} "
                                    f"{j['alert_type'].replace('_', ' ')}: "
                                    f"{action} -> {outcome}{pnl}"
                                )

                            st.write_stream(ask_ai_insight(
                                "Analyze my trading journal. Identify: "
                                "1) Am I skipping the right signals? "
                                "2) Which setups am I best at? "
                                "3) Patterns in my wins vs losses. "
                                "4) Specific actionable improvements.",
                                "\n".join(context_lines),
                            ))
                        except ValueError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"AI analysis error: {e}")

            except Exception as e:
                st.caption(f"Journal unavailable: {e}")


# ── Tab 3: Fundamentals ─────────────────────────────────────────────────────

with tab_fundamentals:
    if _is_free:
        render_inline_upgrade("Company fundamentals with AI analysis", "pro")
    else:
        section_header(f"Fundamentals \u2014 {symbol}")

        try:
            from analytics.intel_hub import get_fundamentals

            with st.spinner("Loading fundamentals..."):
                fnd = get_fundamentals(symbol)

            if fnd is None:
                empty_state(f"No fundamental data available for {symbol}")
            else:
                if fnd.get("name"):
                    st.caption(fnd["name"])

                # Row 1: PE, Market Cap, 52W High, 52W Low
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    pe_val = f"{fnd['pe']:.1f}" if fnd.get("pe") else "N/A"
                    colored_metric("P/E Ratio", pe_val, COLORS["blue"])
                with c2:
                    colored_metric("Market Cap", fnd.get("market_cap_fmt", "N/A"),
                                   COLORS["blue"])
                with c3:
                    h52 = f"${fnd['high_52w']:.2f}" if fnd.get("high_52w") else "N/A"
                    colored_metric("52W High", h52, COLORS["green"])
                with c4:
                    l52 = f"${fnd['low_52w']:.2f}" if fnd.get("low_52w") else "N/A"
                    colored_metric("52W Low", l52, COLORS["red"])

                # Row 2: Sector, Beta, Div Yield, Earnings Date
                c5, c6, c7, c8 = st.columns(4)
                with c5:
                    colored_metric("Sector", fnd.get("sector") or "N/A",
                                   COLORS["purple"])
                with c6:
                    beta_val = f"{fnd['beta']:.2f}" if fnd.get("beta") else "N/A"
                    colored_metric("Beta", beta_val, COLORS["orange"])
                with c7:
                    div_val = (f"{fnd['dividend_yield']:.2%}"
                               if fnd.get("dividend_yield") else "N/A")
                    colored_metric("Div Yield", div_val, COLORS["blue"])
                with c8:
                    earn_date = fnd.get("earnings_date") or "N/A"
                    colored_metric("Earnings Date", earn_date, COLORS["orange"])

                # Earnings proximity warning
                if fnd.get("earnings_date"):
                    try:
                        from datetime import date, datetime
                        ed = datetime.strptime(fnd["earnings_date"][:10], "%Y-%m-%d").date()
                        days_until = (ed - date.today()).days
                        if 0 <= days_until <= 5:
                            st.warning(
                                f"Earnings in {days_until} day{'s' if days_until != 1 else ''} "
                                f"({fnd['earnings_date']}). Consider position sizing."
                            )
                    except (ValueError, TypeError):
                        pass

                # AI Fundamental Analysis
                section_header("AI Analysis")
                _can_ai_2, _cnt_2 = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
                if not _can_ai_2:
                    render_inline_upgrade("Unlimited AI analysis — no daily limits", "elite")
                elif st.button("AI Fundamental Analysis", key="anly_ai_fundamentals"):
                    if _is_free and user:
                        from db import increment_daily_usage
                        increment_daily_usage(user["id"], "ai_query")
                    try:
                        from analytics.intel_hub import ask_ai_insight

                        context_parts = [f"Fundamentals for {symbol}:"]
                        for k, v in fnd.items():
                            if v is not None and k != "market_cap":
                                context_parts.append(f"  {k}: {v}")

                        st.write_stream(ask_ai_insight(
                            f"Analyze {symbol}'s fundamentals for a day trader. "
                            "How do these metrics affect the trade thesis? "
                            "Flag any risks (earnings, high beta, valuation).",
                            "\n".join(context_parts),
                        ))
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"AI analysis error: {e}")

        except Exception as e:
            st.error(f"Failed to load fundamentals: {e}")


# ── Tab 4: AI Coach ─────────────────────────────────────────────────────────

with tab_coach:
    if _tier not in ("elite", "admin") and not _is_free:
        # Pro users see upgrade prompt for elite
        render_inline_upgrade("AI Trade Coach with multi-turn conversations", "elite")
    elif _is_free:
        # Free users get 3 queries/day
        _can_free_coach, _free_cnt = check_usage_limit(user["id"], "ai_query", _ai_limit) if user else (False, 0)
        if not _can_free_coach and not user:
            render_inline_upgrade("AI Trade Coach — sign up to try free", "elite")
        else:
            # Free users can use coach with daily limit — fall through to render
            pass

    # Render coach for elite users AND free users (with limit)
    _show_coach = (_tier in ("elite", "admin")) or (_is_free and user is not None)

    if _show_coach:
        section_header("AI Trade Coach")

        # Quick prompts (enhanced with symbol)
        _QUICK_PROMPTS = [
            f"Analyze {symbol} setup",
            "SPY outlook",
            "Review my positions",
            "Best setups today",
        ]

        def _send_prompt(text: str):
            """Append a user message and trigger rerun to process it."""
            st.session_state["anly_coach_messages"].append(
                {"role": "user", "content": text}
            )

        if not st.session_state["anly_coach_messages"]:
            with st.chat_message("assistant"):
                st.write(
                    f"Hey! I'm your AI trade coach. I'm currently focused on "
                    f"**{symbol}** with full context: fundamentals, S/R levels, "
                    f"weekly trend, and historical win rates. Ask me anything!"
                )
            # Auto-send deeplink prompt from Telegram alert link
            _dl_prompt = st.session_state.pop("anly_deeplink_prompt", None)
            if _dl_prompt:
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                _send_prompt(_dl_prompt)
                st.rerun()

        _can_qp, _ = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)
        cols = st.columns(len(_QUICK_PROMPTS))
        for col, label in zip(cols, _QUICK_PROMPTS):
            with col:
                if st.button(label, use_container_width=True, key=f"anly_qp_{label}",
                             disabled=(not _can_qp)):
                    if _is_free and user:
                        from db import increment_daily_usage
                        increment_daily_usage(user["id"], "ai_query")
                    _send_prompt(label)
                    st.rerun()

        # Render conversation history
        for msg in st.session_state["anly_coach_messages"]:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # Process pending user message
        _needs_response = (
            st.session_state["anly_coach_messages"]
            and st.session_state["anly_coach_messages"][-1]["role"] == "user"
        )

        # Chat input — gate for free users
        _can_chat, _cnt_chat = check_usage_limit(user["id"], "ai_query", _ai_limit) if _is_free and user else (True, 0)

        if not _can_chat:
            render_inline_upgrade("Unlimited AI Coach conversations — no daily limits", "elite")
        else:
            if prompt := st.chat_input("Ask your trade coach...", key="anly_coach_input"):
                if _is_free and user:
                    from db import increment_daily_usage
                    increment_daily_usage(user["id"], "ai_query")
                with st.chat_message("user"):
                    st.write(prompt)
                st.session_state["anly_coach_messages"].append(
                    {"role": "user", "content": prompt}
                )
                _needs_response = True

        # Generate assistant response
        if _needs_response:
            with st.chat_message("assistant"):
                try:
                    from analytics.trade_coach import (
                        assemble_context,
                        ask_coach,
                        format_system_prompt,
                    )

                    ctx = assemble_context(hub_symbol=symbol)
                    system_prompt = format_system_prompt(ctx)

                    # Pro/Elite get Sonnet; free tier gets Haiku (default)
                    _coach_model = None
                    if not _is_free:
                        from alert_config import CLAUDE_MODEL_SONNET
                        _coach_model = CLAUDE_MODEL_SONNET

                    response = st.write_stream(
                        ask_coach(system_prompt, st.session_state["anly_coach_messages"],
                                  max_tokens=1024, model=_coach_model)
                    )
                    st.session_state["anly_coach_messages"].append(
                        {"role": "assistant", "content": response}
                    )

                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Coach error: {e}")
