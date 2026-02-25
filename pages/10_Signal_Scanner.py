"""Signal Scanner — Actionable trade plans for your watchlist."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from auth import require_auth
from db import init_db
from config import (
    DEFAULT_POSITION_SIZE,
    DEFAULT_WATCHLIST,
    QUICK_PICKS,
)
from analytics.market_data import classify_day, fetch_ohlc
from analytics.signal_engine import scan_watchlist, SignalResult

init_db()
user = require_auth()

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
        }
        for r in results
    ]


@st.cache_data(ttl=300)
def _cached_fetch(symbol: str) -> pd.DataFrame:
    return fetch_ohlc(symbol, "3mo")


# ── Status styling ──────────────────────────────────────────────────────────

_STATUS_COLORS = {
    "AT SUPPORT": "#2ecc71",
    "BREAKOUT": "#3498db",
    "PULLBACK WATCH": "#f39c12",
    "BROKEN": "#e74c3c",
}


def _color_status(val):
    color = _STATUS_COLORS.get(val, "")
    return f"color: {color}; font-weight: bold" if color else ""


def _color_pattern(val):
    if val == "INSIDE":
        return "background-color: #3498db33; font-weight: bold"
    if val == "OUTSIDE":
        return "background-color: #e74c3c33; font-weight: bold"
    return ""


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


# ── Page layout ─────────────────────────────────────────────────────────────

st.title("Signal Scanner")
st.caption("Trade plans for your watchlist — entry, stop, target, re-entry at a glance")

# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Watchlist")

    st.markdown("**Quick Picks**")
    for label, syms in QUICK_PICKS.items():
        if st.button(label, key=f"qp_{label}", use_container_width=True):
            st.session_state["scanner_symbols"] = ", ".join(syms)

    default_text = st.session_state.get("scanner_symbols", ", ".join(DEFAULT_WATCHLIST))
    symbols_input = st.text_area(
        "Symbols (comma-separated)", value=default_text, height=100,
    )
    st.session_state["scanner_symbols"] = symbols_input

    st.divider()
    position_size = st.number_input(
        "Position Size ($)", value=DEFAULT_POSITION_SIZE, step=5000,
    )

    status_filter = st.multiselect(
        "Filter by Status",
        ["AT SUPPORT", "BREAKOUT", "PULLBACK WATCH", "BROKEN"],
        default=["AT SUPPORT", "BREAKOUT", "PULLBACK WATCH"],
    )

# ── Parse & scan ────────────────────────────────────────────────────────────

symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
if not symbols:
    st.info("Enter at least one symbol in the sidebar.")
    st.stop()

raw_results = _cached_scan(tuple(symbols))
results: list[SignalResult] = [SignalResult(**d) for d in raw_results]

# Apply status filter
if status_filter:
    results = [r for r in results if r.support_status in status_filter]

if not results:
    st.warning("No symbols match. Check your symbols or adjust the status filter.")
    st.stop()

# ── KPI Row ─────────────────────────────────────────────────────────────────

at_support = sum(1 for r in results if r.support_status == "AT SUPPORT")
breakout = sum(1 for r in results if r.support_status == "BREAKOUT")
watching = sum(1 for r in results if r.support_status == "PULLBACK WATCH")
broken = sum(1 for r in results if r.support_status == "BROKEN")

col1, col2, col3, col4 = st.columns(4)
col1.metric("AT SUPPORT", at_support, help="Near support — ready for entry")
col2.metric("BREAKOUT", breakout, help="Inside day — watch for breakout")
col3.metric("PULLBACK WATCH", watching, help="Above support — wait for pullback")
col4.metric("BROKEN", broken, help="Support broken — no long setup")

st.divider()

# ── Trade Plan Table ────────────────────────────────────────────────────────

st.subheader("Trade Plans")

table_rows = []
for r in results:
    shares = int(position_size / r.entry) if r.entry > 0 else 0
    total_risk = shares * r.risk_per_share
    table_rows.append({
        "Symbol": r.symbol,
        "Price": r.last_close,
        "Status": r.support_status,
        "Pattern": r.pattern.upper(),
        "Support": r.nearest_support,
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
        "Price": "${:,.2f}", "Support": "${:,.2f}",
        "Entry": "${:,.2f}", "Stop": "${:,.2f}",
        "Re-entry Stop": "${:,.2f}", "Target": "${:,.2f}",
        "Risk/Sh": "${:,.2f}", "$ Risk": "${:,.0f}",
    })
    .applymap(_color_status, subset=["Status"])
    .applymap(_color_pattern, subset=["Pattern"]),
    use_container_width=True,
    hide_index=True,
)

st.divider()

# ── Detail per Symbol ───────────────────────────────────────────────────────

st.subheader("Detail")

for r in results:
    status_icon = {
        "AT SUPPORT": "**AT SUPPORT**",
        "BREAKOUT": "**BREAKOUT WATCH**",
        "PULLBACK WATCH": "PULLBACK WATCH",
        "BROKEN": "BROKEN",
    }.get(r.support_status, r.support_status)

    with st.expander(
        f"{r.symbol}  |  {r.support_status}  |  "
        f"Entry ${r.entry:,.2f}  Stop ${r.stop:,.2f}  Target ${r.target_1:,.2f}"
    ):
        # ── Support status + bias ─────────────────────────────────────
        color = _STATUS_COLORS.get(r.support_status, "#95a5a6")
        st.markdown(
            f"### <span style='color:{color}'>{r.support_status}</span> — "
            f"{r.pattern.upper()} Day, {r.direction.title()}",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{r.bias}**")

        # ── Key levels ────────────────────────────────────────────────
        st.markdown("**Key Levels**")
        lc1, lc2, lc3, lc4 = st.columns(4)
        lc1.metric("Prior High", f"${r.prior_high:,.2f}")
        lc2.metric("Prior Low", f"${r.prior_low:,.2f}")
        lc3.metric("Nearest Support", f"${r.nearest_support:,.2f}",
                    delta=f"{r.support_label}", delta_color="off")
        lc4.metric("Distance", f"${r.distance_to_support:,.2f}",
                    delta=f"{r.distance_pct:+.2f}%", delta_color="off")

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
