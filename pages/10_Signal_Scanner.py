"""Signal Scanner — Actionable trade plans for your watchlist."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

from db import init_db
from config import (
    DEFAULT_POSITION_SIZE,
    DEFAULT_WATCHLIST,
    QUICK_PICKS,
)
from analytics.market_data import classify_day, fetch_ohlc
from analytics.signal_engine import (
    scan_watchlist, SignalResult, ACTION_LABELS, action_label, action_color, action_help,
)
from analytics.intraday_data import fetch_intraday, fetch_prior_day
from analytics.intraday_rules import evaluate_rules
from analytics.market_hours import is_market_hours

init_db()

# ── Auto-refresh during market hours ──────────────────────────────────────
_market_open = is_market_hours()
if _market_open:
    st_autorefresh(interval=180_000, key="scanner_refresh")  # 3 min

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


@st.cache_data(ttl=180, show_spinner=False)
def _cached_intraday(symbol: str) -> pd.DataFrame:
    return fetch_intraday(symbol)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_prior_day(symbol: str) -> dict | None:
    return fetch_prior_day(symbol)


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

st.title("Signal Scanner")
st.caption("Trade plans for your watchlist — entry, stop, target, re-entry at a glance")

# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Watchlist")

    # Initialize watchlist in session state
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = list(DEFAULT_WATCHLIST)

    # Quick Picks — replace entire watchlist
    st.markdown("**Quick Picks**")
    for label, syms in QUICK_PICKS.items():
        if st.button(label, key=f"qp_{label}", use_container_width=True):
            st.session_state["watchlist"] = list(syms)
            st.rerun()

    st.divider()

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
            st.session_state["watchlist"].append(sym_clean)
            st.rerun()

    # Display current watchlist with remove buttons
    if st.session_state["watchlist"]:
        remove_idx = None
        for i, sym in enumerate(st.session_state["watchlist"]):
            sym_col, x_col = st.columns([4, 1])
            sym_col.markdown(f"**{sym}**")
            if x_col.button("X", key=f"rm_{sym}_{i}", type="secondary"):
                remove_idx = i
        if remove_idx is not None:
            st.session_state["watchlist"].pop(remove_idx)
            st.rerun()
    else:
        st.caption("No symbols. Add one above or use Quick Picks.")

    # Bulk edit in collapsible expander
    with st.expander("Bulk Edit"):
        bulk_text = st.text_area(
            "Symbols (comma-separated)",
            value=", ".join(st.session_state["watchlist"]),
            height=80,
            key="bulk_edit_area",
        )
        if st.button("Apply", key="bulk_apply", use_container_width=True):
            parsed = [s.strip().upper() for s in bulk_text.split(",") if s.strip()]
            st.session_state["watchlist"] = parsed
            st.rerun()

    st.divider()
    position_size = st.number_input(
        "Position Size ($)", value=DEFAULT_POSITION_SIZE, step=5000,
    )

    # Map action labels back to internal statuses for filtering
    _label_to_status = {v["label"]: k for k, v in ACTION_LABELS.items()}
    _all_labels = list(_label_to_status.keys())

    status_filter_labels = st.multiselect(
        "Filter by Status",
        _all_labels,
        default=_all_labels[:3],  # BUY ZONE, BREAKOUT SETUP, WAIT FOR DIP
    )
    status_filter = [_label_to_status[lbl] for lbl in status_filter_labels]

# ── Parse & scan ────────────────────────────────────────────────────────────

symbols = list(st.session_state["watchlist"])
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
col1.metric("BUY ZONE", at_support, help=action_help("AT SUPPORT"))
col2.metric("BREAKOUT SETUP", breakout, help=action_help("BREAKOUT"))
col3.metric("WAIT FOR DIP", watching, help=action_help("PULLBACK WATCH"))
col4.metric("NO TRADE", broken, help=action_help("BROKEN"))

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
        "Status": action_label(r.support_status),
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
    _label = action_label(r.support_status)
    _acolor = action_color(r.support_status)

    with st.expander(
        f"{r.symbol}  |  {_label}  |  "
        f"Entry ${r.entry:,.2f}  Stop ${r.stop:,.2f}  Target ${r.target_1:,.2f}"
    ):
        # ── Support status + bias ─────────────────────────────────────
        st.markdown(
            f"### <span style='color:{_acolor}'>{_label}</span> — "
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

                signals = evaluate_rules(r.symbol, intra_bars, prior, active_entries)
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

        # ── Position tracking ────────────────────────────────────────
        st.divider()
        st.markdown("**Track Position**")

        if "active_positions" not in st.session_state:
            st.session_state["active_positions"] = {}

        pos_key = r.symbol
        is_tracking = pos_key in st.session_state["active_positions"]

        tracking = st.checkbox(
            "I'm in this trade", value=is_tracking, key=f"track_{r.symbol}",
        )

        if tracking and not is_tracking:
            # Start tracking with pre-filled values from trade plan
            default_shares = int(position_size / r.entry) if r.entry > 0 else 0
            st.session_state["active_positions"][pos_key] = {
                "entry": r.entry,
                "shares": default_shares,
            }
            st.rerun()

        if not tracking and is_tracking:
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
                del st.session_state["active_positions"][pos_key]
                st.rerun()
