"""Signal Scanner — Multi-symbol BUY/WAIT/AVOID recommendations."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from auth import require_auth
from db import init_db
from config import (
    DEFAULT_POSITION_SIZE,
    DEFAULT_WATCHLIST,
    QUICK_PICKS,
    SCORE_THRESHOLDS,
)
from analytics.market_data import classify_day, fetch_ohlc
from analytics.signal_engine import scan_watchlist, SignalResult

init_db()
user = require_auth()

# ── Cached helpers (must be defined before use) ──────────────────────────────


@st.cache_data(ttl=300, show_spinner="Scanning watchlist...")
def _cached_scan(syms: tuple[str, ...]) -> list[dict]:
    """Scan and return serializable dicts (dataclass not cacheable)."""
    results = scan_watchlist(list(syms))
    return [
        {
            "symbol": r.symbol,
            "score": r.score,
            "signal": r.signal,
            "signal_type": r.signal_type,
            "pattern": r.pattern,
            "direction": r.direction,
            "entry": r.entry,
            "stop": r.stop,
            "target_1": r.target_1,
            "target_2": r.target_2,
            "risk_per_share": r.risk_per_share,
            "rr_ratio": r.rr_ratio,
            "scores": r.scores,
            "last_close": r.last_close,
            "ma20": r.ma20,
            "ma50": r.ma50,
            "avg_volume": r.avg_volume,
            "last_volume": r.last_volume,
        }
        for r in results
    ]


@st.cache_data(ttl=300)
def _cached_fetch(symbol: str) -> pd.DataFrame:
    return fetch_ohlc(symbol, "3mo")


def _draw_mini_chart(r: SignalResult):
    """30-day candlestick chart with MAs and levels overlaid."""
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

    # MAs
    for col, label, color in [
        ("MA20", "20 MA", "#f39c12"),
        ("MA50", "50 MA", "#9b59b6"),
    ]:
        ma = chart[col].dropna()
        if not ma.empty:
            fig.add_trace(go.Scatter(
                x=ma.index.strftime("%Y-%m-%d"), y=ma.values,
                mode="lines", name=label,
                line=dict(color=color, width=1.5),
            ))

    # Levels
    fig.add_hline(y=r.entry, line_dash="dash", line_color="#3498db",
                  annotation_text=f"Entry ${r.entry:,.2f}")
    fig.add_hline(y=r.stop, line_dash="dash", line_color="#e74c3c",
                  annotation_text=f"Stop ${r.stop:,.2f}")
    fig.add_hline(y=r.target_1, line_dash="dash", line_color="#2ecc71",
                  annotation_text=f"T1 ${r.target_1:,.2f}")

    # ID/OD annotations
    for i in range(1, len(chart)):
        row = chart.iloc[i]
        prev = chart.iloc[i - 1]
        pat, _ = classify_day(row, prev)
        if pat in ("inside", "outside"):
            date_str = chart.index[i].strftime("%Y-%m-%d")
            tag = "ID" if pat == "inside" else "OD"
            clr = "#3498db" if pat == "inside" else "#e74c3c"
            fig.add_annotation(
                x=date_str, y=row["High"], yshift=12,
                text=tag, showarrow=False,
                font=dict(color=clr, size=10, family="Arial Black"),
                bgcolor=f"rgba({52 if pat == 'inside' else 231}, "
                        f"{152 if pat == 'inside' else 76}, "
                        f"{219 if pat == 'inside' else 60}, 0.2)",
                bordercolor=clr,
            )

    fig.update_layout(
        height=350,
        xaxis_rangeslider_visible=False,
        yaxis_title="Price ($)",
        margin=dict(l=40, r=20, t=30, b=30),
        legend=dict(orientation="h", y=1.08),
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)


_SIGNAL_COLORS = {"BUY": "#2ecc71", "WAIT": "#f39c12", "AVOID": "#e74c3c"}


def _color_signal(val):
    color = _SIGNAL_COLORS.get(val, "")
    return f"color: {color}; font-weight: bold" if color else ""


def _color_pattern(val):
    if val == "INSIDE":
        return "background-color: #3498db33; font-weight: bold"
    if val == "OUTSIDE":
        return "background-color: #e74c3c33; font-weight: bold"
    return ""


# ── Page layout ──────────────────────────────────────────────────────────────

st.title("Signal Scanner")
st.caption("Composite scoring across your watchlist — BUY / WAIT / AVOID at a glance")

# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Watchlist")

    # Quick-pick buttons
    st.markdown("**Quick Picks**")
    for label, syms in QUICK_PICKS.items():
        if st.button(label, key=f"qp_{label}", use_container_width=True):
            st.session_state["scanner_symbols"] = ", ".join(syms)

    default_text = st.session_state.get(
        "scanner_symbols", ", ".join(DEFAULT_WATCHLIST)
    )
    symbols_input = st.text_area(
        "Symbols (comma-separated)",
        value=default_text,
        height=100,
        help="Enter ticker symbols separated by commas",
    )
    # Persist for quick-pick updates
    st.session_state["scanner_symbols"] = symbols_input

    st.divider()
    position_size = st.number_input(
        "Position Size ($)",
        value=DEFAULT_POSITION_SIZE,
        step=5000,
        help="Capital per trade for risk calculations",
    )
    min_score = st.slider("Min Score Filter", 0, 100, 0, step=5)

# ── Parse symbols ────────────────────────────────────────────────────────────

symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
if not symbols:
    st.info("Enter at least one symbol in the sidebar to start scanning.")
    st.stop()

# ── Scan ─────────────────────────────────────────────────────────────────────

raw_results = _cached_scan(tuple(symbols))

# Reconstruct SignalResult objects
results: list[SignalResult] = [SignalResult(**d) for d in raw_results]

# Apply min-score filter
results = [r for r in results if r.score >= min_score]

if not results:
    st.warning("No symbols returned results. Check your symbols or lower the min score.")
    st.stop()

# ── KPI Row ──────────────────────────────────────────────────────────────────

buy_count = sum(1 for r in results if r.signal == "BUY")
wait_count = sum(1 for r in results if r.signal == "WAIT")
avoid_count = sum(1 for r in results if r.signal == "AVOID")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Scanned", len(results))
col2.metric("BUY", buy_count)
col3.metric("WAIT", wait_count)
col4.metric("AVOID", avoid_count)

# ── Market Context ───────────────────────────────────────────────────────────

bullish_count = sum(1 for r in results if r.direction == "bullish")
inside_count = sum(1 for r in results if r.pattern == "inside")
ctx_parts = [f"{bullish_count}/{len(results)} symbols bullish"]
if inside_count:
    ctx_parts.append(f"{inside_count} inside day{'s' if inside_count != 1 else ''} detected")
st.caption(" | ".join(ctx_parts))

st.divider()

# ── Ranked Signal Table ─────────────────────────────────────────────────────

table_rows = []
for r in results:
    table_rows.append({
        "Symbol": r.symbol,
        "Signal": r.signal,
        "Score": r.score,
        "Type": r.signal_type.replace("_", " ").title(),
        "Pattern": r.pattern.upper(),
        "Direction": r.direction.title(),
        "Entry": r.entry,
        "Stop": r.stop,
        "R:R": f"{r.rr_ratio:.1f}:1",
    })

table_df = pd.DataFrame(table_rows)

st.subheader("Signal Rankings")
st.dataframe(
    table_df.style
    .format({"Entry": "${:,.2f}", "Stop": "${:,.2f}", "Score": "{:d}"})
    .applymap(_color_signal, subset=["Signal"])
    .applymap(_color_pattern, subset=["Pattern"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ── Expandable Detail per Symbol ─────────────────────────────────────────────

st.subheader("Detail")

for r in results:
    with st.expander(
        f"{r.symbol}  —  {r.signal} ({r.score})  |  "
        f"{r.pattern.upper()} {r.direction.title()}  |  "
        f"{r.signal_type.replace('_', ' ').title()}"
    ):
        # ── Score breakdown ──────────────────────────────────────────────
        st.markdown("**Score Breakdown**")
        sc = r.scores
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Candle Pattern", f"{sc['candle_pattern']}/25")
        b2.metric("MA Position", f"{sc['ma_position']}/25")
        b3.metric("Support Prox.", f"{sc['support_proximity']}/25")
        b4.metric("Volume", f"{sc['volume']}/25")

        # ── Levels ───────────────────────────────────────────────────────
        st.markdown("**Levels**")
        lc1, lc2, lc3, lc4 = st.columns(4)
        lc1.metric("Entry", f"${r.entry:,.2f}")
        lc2.metric("Stop", f"${r.stop:,.2f}")
        lc3.metric("Target 1", f"${r.target_1:,.2f}")
        lc4.metric("Target 2", f"${r.target_2:,.2f}")

        reward_1 = r.target_1 - r.entry
        reward_2 = r.target_2 - r.entry
        rr2 = reward_2 / r.risk_per_share if r.risk_per_share > 0 else 0

        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("Risk/Share", f"${r.risk_per_share:,.2f}")
        rc2.metric("R:R (T1)", f"{r.rr_ratio:.1f}:1")
        rc3.metric("R:R (T2)", f"{rr2:.1f}:1")

        # ── Risk Calculator ──────────────────────────────────────────────
        if r.entry > 0 and r.risk_per_share > 0:
            st.markdown("**Risk Calculator**")
            shares = position_size / r.entry
            total_risk = shares * r.risk_per_share
            total_reward_1 = shares * reward_1
            total_reward_2 = shares * reward_2
            risk_pct = total_risk / position_size * 100

            pc1, pc2, pc3, pc4 = st.columns(4)
            pc1.metric("Shares", f"{shares:,.0f}")
            pc2.metric("$ Risk", f"-${total_risk:,.0f}")
            pc3.metric("$ Reward (T1)", f"+${total_reward_1:,.0f}")
            pc4.metric("$ Reward (T2)", f"+${total_reward_2:,.0f}")

            if r.pattern == "outside":
                st.warning(
                    f"Outside day — wide stop. Consider half position "
                    f"({shares/2:,.0f} shares, ${total_risk/2:,.0f} risk)."
                )
            elif risk_pct > 2.0:
                st.warning(f"Risk is {risk_pct:.1f}% of position. Consider reducing size.")
            else:
                st.success(f"Risk is {risk_pct:.1f}% of position — manageable.")

        # ── MA context ───────────────────────────────────────────────────
        ma_parts = [f"Close ${r.last_close:,.2f}"]
        if r.ma20 is not None:
            ma_parts.append(f"20MA ${r.ma20:,.2f}")
        if r.ma50 is not None:
            ma_parts.append(f"50MA ${r.ma50:,.2f}")
        st.caption(" | ".join(ma_parts))

        # ── Mini chart ───────────────────────────────────────────────────
        _draw_mini_chart(r)
