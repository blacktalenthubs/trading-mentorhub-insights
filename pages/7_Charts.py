"""Interactive Charts — Full-width candlestick charts with configurable overlays."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

from db import init_db, add_chart_level, delete_chart_level, get_chart_levels
from alert_config import ALERT_WATCHLIST
from alerting.alert_store import get_active_entries, get_alerts_today
from analytics.intraday_data import fetch_intraday, fetch_prior_day, compute_vwap
from analytics.market_hours import is_market_hours
import ui_theme

init_db()

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Charts | TradeSignal", page_icon="⚡", layout="wide")
ui_theme.inject_custom_css()

with st.sidebar:
    ui_theme.sidebar_branding()

# ── Timeframe definitions ────────────────────────────────────────────────────
# label → (yf period, yf interval, is_intraday)

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


# ── Cached data fetching ─────────────────────────────────────────────────────

@st.cache_data(ttl=180, show_spinner="Loading chart data...")
def _fetch_bars(symbol: str, period: str, interval: str | None) -> pd.DataFrame:
    """Fetch OHLCV bars for the given symbol, period, and interval."""
    if interval and interval != "weekly":
        return fetch_intraday(symbol, period=period, interval=interval)
    try:
        hist = yf.Ticker(symbol).history(period=period)
        if hist.empty:
            return pd.DataFrame()
        hist.index = hist.index.tz_localize(None)
        ohlcv = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        if interval == "weekly":
            ohlcv = ohlcv.resample("W-FRI").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum",
            }).dropna()
        return ohlcv
    except Exception:
        return pd.DataFrame()


# How many bars to show by default per timeframe (the rest is scrollable)
_DEFAULT_VISIBLE_BARS = {
    "1m": 120, "5m": 80, "15m": 80, "30m": 60,
    "1h": 60, "Daily": 90, "Weekly": 52,
}


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


# ── Chart builder ─────────────────────────────────────────────────────────────

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
    # Bars sit edge-to-edge like TradingView.
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

    return fig


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Charts")

    # Symbol
    all_symbols = list(ALERT_WATCHLIST)
    custom_sym = st.text_input("Custom symbol", placeholder="e.g. AMZN", key="chart_custom_sym")
    if custom_sym:
        sym_clean = custom_sym.strip().upper()
        if sym_clean and sym_clean not in all_symbols:
            all_symbols.insert(0, sym_clean)
    symbol = st.selectbox("Symbol", all_symbols, key="chart_symbol")

    st.divider()

    # Overlays — grouped multiselects
    st.markdown("**EMA**")
    ema_periods = st.multiselect(
        "EMA periods", [5, 9, 20, 50, 100, 200],
        default=[9, 20, 50],
        key="ema_periods", label_visibility="collapsed",
    )

    st.markdown("**SMA**")
    sma_periods = st.multiselect(
        "SMA periods", [20, 50, 100, 200],
        default=[],
        key="sma_periods", label_visibility="collapsed",
    )

    show_vwap = st.checkbox("VWAP", value=True, key="ov_vwap")

    st.divider()

    # Key Levels
    st.markdown("**Key Levels**")
    lc1, lc2, lc3 = st.columns([2, 2, 1])
    with lc1:
        new_price = st.number_input("Price", min_value=0.0, value=0.0,
                                    step=0.50, format="%.2f",
                                    key="new_level_price", label_visibility="collapsed")
    with lc2:
        new_label = st.text_input("Label", placeholder="Label",
                                  key="new_level_label", label_visibility="collapsed")
    with lc3:
        add_clicked = st.button("+", key="add_level_btn", use_container_width=True)

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
        if x_col.button("x", key=f"del_lvl_{lvl['id']}", type="secondary"):
            delete_chart_level(lvl["id"])
            st.rerun()


# ── Timeframe dropdown (above chart) ─────────────────────────────────────────

tf_col, spacer = st.columns([1, 5])
with tf_col:
    tf_label = st.selectbox(
        "Timeframe", list(TIMEFRAMES.keys()),
        index=1,  # default "5m"
        key="chart_tf", label_visibility="collapsed",
    )

period, interval, is_intraday = TIMEFRAMES[tf_label]

# ── Auto-refresh ──────────────────────────────────────────────────────────────

_market_open = is_market_hours()
if _market_open and is_intraday:
    st_autorefresh(interval=180_000, key="chart_refresh")

# ── Main chart area ──────────────────────────────────────────────────────────

bars = _fetch_bars(symbol, period, interval)
if bars.empty:
    st.warning(f"No data available for {symbol} ({tf_label}).")
    st.stop()

prior = fetch_prior_day(symbol) if is_intraday else None
active_entries = get_active_entries(symbol)

fig = _build_chart(
    symbol, bars, ema_periods, sma_periods,
    show_vwap and is_intraday, prior, active_entries, levels, is_intraday, tf_label,
)

st.plotly_chart(
    fig, use_container_width=True,
    config={
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToAdd": ["drawline", "eraseshape"],
        "displaylogo": False,
    },
)

# ── Alert context ─────────────────────────────────────────────────────────────

alerts_today = get_alerts_today()
symbol_alerts = [a for a in alerts_today if a.get("symbol") == symbol]

if symbol_alerts:
    st.subheader(f"Today's Alerts — {symbol}")
    alert_df = pd.DataFrame(symbol_alerts)[
        ["created_at", "alert_type", "direction", "price", "entry", "stop",
         "target_1", "confidence", "message"]
    ]
    alert_df.columns = ["Time", "Type", "Dir", "Price", "Entry", "Stop",
                        "T1", "Confidence", "Message"]
    st.dataframe(
        alert_df.style.format({
            "Price": "${:,.2f}", "Entry": "${:,.2f}",
            "Stop": "${:,.2f}", "T1": "${:,.2f}",
        }),
        use_container_width=True,
        hide_index=True,
    )
