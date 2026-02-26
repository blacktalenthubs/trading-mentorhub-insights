"""Pre-Market Planner - Inside/outside day analysis, key levels, risk calculator."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from config import STOP_LOSS_PCT
from db import init_db, get_user_trades
from auth import auto_login
from analytics.market_data import (
    fetch_ohlc as _fetch_ohlc,
    classify_day,
    get_levels,
)

init_db()
user = auto_login()
st.title("Pre-Market Planner")
st.caption("Identify the day type, know your levels, size your risk — before the bell")


@st.cache_data(ttl=300)
def fetch_ohlc(symbol: str, period: str = "3mo") -> pd.DataFrame:
    """Cached wrapper around analytics.market_data.fetch_ohlc."""
    return _fetch_ohlc(symbol, period)


# === SYMBOL SELECTOR ===
with st.sidebar:
    st.subheader("Setup")
    symbol = st.text_input("Symbol", value="SPY").upper().strip()
    position_size = st.number_input("Position Size ($)", value=150000.0, step=5000.0,
                                     help="How much capital you'll deploy on this trade")

hist = fetch_ohlc(symbol)
if hist.empty:
    st.warning(f"Could not fetch data for {symbol}. Check the symbol and try again.")
    st.stop()

# === RECENT CANDLE PATTERN CLASSIFICATION ===
st.subheader(f"{symbol} — Recent Day Classification")

# Classify last 20 days
recent = hist.tail(21).copy()  # need 21 to classify 20 (need prior day for each)
pattern_data = []
for i in range(1, len(recent)):
    row = recent.iloc[i]
    prev = recent.iloc[i - 1]
    pattern, direction = classify_day(row, prev)
    date_str = recent.index[i].strftime("%Y-%m-%d")
    day_range = row["High"] - row["Low"]
    close_pct = ((row["Close"] - row["Low"]) / day_range * 100) if day_range > 0 else 50
    pattern_data.append({
        "Date": date_str,
        "Open": row["Open"],
        "High": row["High"],
        "Low": row["Low"],
        "Close": row["Close"],
        "Range": day_range,
        "Pattern": pattern.upper(),
        "Direction": direction,
        "Close %": close_pct,
    })

pattern_df = pd.DataFrame(pattern_data)
# Most recent first
pattern_df = pattern_df.iloc[::-1].reset_index(drop=True)

# Color coding for patterns
def style_pattern(val):
    if val == "INSIDE":
        return "background-color: #3498db33; font-weight: bold"
    elif val == "OUTSIDE":
        return "background-color: #e74c3c33; font-weight: bold"
    return ""

st.dataframe(
    pattern_df.style.format({
        "Open": "${:,.2f}", "High": "${:,.2f}", "Low": "${:,.2f}",
        "Close": "${:,.2f}", "Range": "${:,.2f}", "Close %": "{:.0f}%",
    }).applymap(style_pattern, subset=["Pattern"]),
    use_container_width=True,
)

st.markdown("""
| Pattern | What it means | How to trade it |
|---------|--------------|-----------------|
| **INSIDE** | Today's range fits *inside* yesterday's range. Compression = breakout coming. | Wait for breakout, tight stop below inside low. Best R:R setup. |
| **OUTSIDE** | Today's range *engulfs* yesterday's range. Both high and low broke. | Tricky — wide range = wide stop. Half size. Wait for pullback to midpoint. |
| **NORMAL** | Only one side broke (high OR low, not both). Regular directional day. | Trade prior day H/L as support/resistance. Buy near prior low, stop below. |
""")

# Count patterns
inside_count = (pattern_df["Pattern"] == "INSIDE").sum()
outside_count = (pattern_df["Pattern"] == "OUTSIDE").sum()
normal_count = (pattern_df["Pattern"] == "NORMAL").sum()

col1, col2, col3 = st.columns(3)
col1.metric("Inside Days (last 20)", inside_count)
col2.metric("Outside Days (last 20)", outside_count)
col3.metric("Normal Days", normal_count)

st.divider()

# === TODAY'S SETUP ===
st.header("Today's Setup")

last_idx = len(hist) - 1
levels = get_levels(hist, last_idx)

# Pattern banner
pattern_colors = {"inside": "#3498db", "outside": "#e74c3c", "normal": "#95a5a6"}
pattern_label = levels["pattern"].upper()
st.markdown(
    f"### <span style='color:{pattern_colors[levels['pattern']]}'>"
    f"{pattern_label} DAY</span> — {levels['direction'].title()}",
    unsafe_allow_html=True,
)
st.markdown(f"**{levels['bias']}**")
st.caption(levels["notes"])

if "alt_notes" in levels:
    st.caption(levels["alt_notes"])

st.divider()

# === KEY LEVELS TABLE ===
st.subheader("Key Levels")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Prior High", f"${levels['prior_high']:,.2f}")
col2.metric("Prior Low", f"${levels['prior_low']:,.2f}")
col3.metric("Prior Close", f"${levels['prior_close']:,.2f}")
col4.metric("Prior Range", f"${levels['prior_range']:,.2f}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Entry (Long)", f"${levels['entry_long']:,.2f}",
            help="Recommended entry price based on pattern")
col2.metric("Stop Loss", f"${levels['stop_long']:,.2f}",
            delta=f"-${levels['risk_per_share']:,.2f}/share", delta_color="off")
col3.metric("Target 1", f"${levels['target_1']:,.2f}")
col4.metric("Target 2", f"${levels['target_2']:,.2f}")

# R:R ratio
risk = levels["risk_per_share"]
reward_1 = levels["target_1"] - levels["entry_long"]
reward_2 = levels["target_2"] - levels["entry_long"]
rr_1 = reward_1 / risk if risk > 0 else 0
rr_2 = reward_2 / risk if risk > 0 else 0

col1, col2, col3 = st.columns(3)
col1.metric("Risk/Share", f"${risk:,.2f}")
col2.metric("R:R to Target 1", f"{rr_1:.1f}:1",
            delta="GOOD" if rr_1 >= 1.5 else "POOR" if rr_1 < 1.0 else "OK",
            delta_color="normal" if rr_1 >= 1.5 else "inverse" if rr_1 < 1.0 else "off")
col3.metric("R:R to Target 2", f"{rr_2:.1f}:1")

st.divider()

# === RISK CALCULATOR WITH THESE LEVELS ===
st.subheader("Risk at These Levels")
st.caption(f"Position size: ${position_size:,.0f}")

if levels["entry_long"] > 0:
    shares = position_size / levels["entry_long"]
    total_risk = shares * risk
    total_reward_1 = shares * reward_1
    total_reward_2 = shares * reward_2

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Shares", f"{shares:,.0f}")
    col2.metric("$ Risk if Stopped", f"-${total_risk:,.0f}")
    col3.metric("$ Reward (T1)", f"+${total_reward_1:,.0f}")
    col4.metric("$ Reward (T2)", f"+${total_reward_2:,.0f}")

    # Risk as % of position
    risk_pct = (total_risk / position_size * 100) if position_size > 0 else 0

    if levels["pattern"] == "outside":
        st.warning(
            f"Outside day stop is **${total_risk:,.0f}** ({risk_pct:.1f}% of position). "
            f"This is wide. Consider **half position** (${position_size/2:,.0f}) to keep "
            f"risk at ${total_risk/2:,.0f}, or use the tighter alt stop if available."
        )
    elif risk_pct > 2.0:
        st.warning(
            f"Risk is {risk_pct:.1f}% of position (${total_risk:,.0f}). "
            f"Consider reducing position to ${position_size * 1.5 / risk_pct:,.0f} "
            f"to keep risk under 1.5%."
        )
    else:
        st.success(
            f"Risk is {risk_pct:.1f}% of position (${total_risk:,.0f}). "
            f"{'Tight stop — good R:R setup.' if levels['pattern'] == 'inside' else 'Manageable risk.'}"
        )

    # If outside day, show half-size option
    if levels["pattern"] == "outside":
        st.markdown("**Half-Size Option (recommended for outside days):**")
        half_shares = shares / 2
        half_risk = half_shares * risk
        half_r1 = half_shares * reward_1
        col1, col2, col3 = st.columns(3)
        col1.metric("Half Shares", f"{half_shares:,.0f}")
        col2.metric("Half Risk", f"-${half_risk:,.0f}")
        col3.metric("Half Reward (T1)", f"+${half_r1:,.0f}")

st.divider()

# === CANDLESTICK CHART WITH LEVELS + MOVING AVERAGES ===
st.subheader("Chart with Key Levels & Moving Averages")

# Use enough history to show 50 MA context (show last 60 trading days on chart)
chart_days = min(60, len(hist))
chart_data = hist.tail(chart_days).copy()

# Calculate MAs on full history, then slice for chart
hist["MA20"] = hist["Close"].rolling(window=20).mean()
hist["MA50"] = hist["Close"].rolling(window=50).mean()
chart_data = hist.tail(chart_days).copy()

fig = go.Figure()

# Candlesticks
fig.add_trace(go.Candlestick(
    x=chart_data.index.strftime("%Y-%m-%d"),
    open=chart_data["Open"],
    high=chart_data["High"],
    low=chart_data["Low"],
    close=chart_data["Close"],
    name=symbol,
    increasing_line_color="#2ecc71",
    decreasing_line_color="#e74c3c",
))

# 20-day MA
ma20 = chart_data["MA20"].dropna()
if not ma20.empty:
    fig.add_trace(go.Scatter(
        x=ma20.index.strftime("%Y-%m-%d"),
        y=ma20.values,
        mode="lines", name="20 MA",
        line=dict(color="#f39c12", width=1.5),
    ))

# 50-day MA
ma50 = chart_data["MA50"].dropna()
if not ma50.empty:
    fig.add_trace(go.Scatter(
        x=ma50.index.strftime("%Y-%m-%d"),
        y=ma50.values,
        mode="lines", name="50 MA",
        line=dict(color="#9b59b6", width=1.5),
    ))

# Key levels as horizontal lines — bold labels with colored badges
fig.add_hline(y=levels["entry_long"], line_dash="dash", line_color="#3498db", line_width=2,
              annotation_text=f"  ENTRY ${levels['entry_long']:,.2f}  ",
              annotation_font=dict(size=13, color="white", family="Arial Black"),
              annotation_bgcolor="#3498db", annotation_borderpad=4,
              annotation_position="top left")
fig.add_hline(y=levels["stop_long"], line_dash="dash", line_color="#e74c3c", line_width=2,
              annotation_text=f"  STOP ${levels['stop_long']:,.2f}  ",
              annotation_font=dict(size=13, color="white", family="Arial Black"),
              annotation_bgcolor="#e74c3c", annotation_borderpad=4,
              annotation_position="bottom left")
fig.add_hline(y=levels["target_1"], line_dash="dash", line_color="#2ecc71", line_width=2,
              annotation_text=f"  T1 ${levels['target_1']:,.2f}  ",
              annotation_font=dict(size=13, color="white", family="Arial Black"),
              annotation_bgcolor="#2ecc71", annotation_borderpad=4,
              annotation_position="top left")
fig.add_hline(y=levels["target_2"], line_dash="dot", line_color="#27ae60", line_width=1,
              annotation_text=f"  T2 ${levels['target_2']:,.2f}  ",
              annotation_font=dict(size=12, color="white"),
              annotation_bgcolor="#27ae60", annotation_borderpad=3,
              annotation_position="top left")

# Mark inside/outside days with annotations
for i in range(1, len(chart_data)):
    row = chart_data.iloc[i]
    prev = chart_data.iloc[i - 1]
    pat, _ = classify_day(row, prev)
    date_str = chart_data.index[i].strftime("%Y-%m-%d")
    if pat == "inside":
        fig.add_annotation(
            x=date_str, y=row["High"], yshift=18,
            text="  ID  ", showarrow=False,
            font=dict(color="white", size=12, family="Arial Black"),
            bgcolor="#3498db", bordercolor="#3498db", borderwidth=1, borderpad=3,
        )
    elif pat == "outside":
        fig.add_annotation(
            x=date_str, y=row["High"], yshift=18,
            text="  OD  ", showarrow=False,
            font=dict(color="white", size=12, family="Arial Black"),
            bgcolor="#e74c3c", bordercolor="#e74c3c", borderwidth=1, borderpad=3,
        )

fig.update_layout(
    height=600, xaxis_rangeslider_visible=False,
    yaxis_title=f"{symbol} Price ($)",
    title=f"{symbol} — {chart_days} Days with 20 MA / 50 MA & Key Levels",
    legend=dict(orientation="h", y=1.05),
)
st.plotly_chart(fig, use_container_width=True)

# MA context info
last_close = chart_data["Close"].iloc[-1]
last_ma20 = chart_data["MA20"].iloc[-1] if pd.notna(chart_data["MA20"].iloc[-1]) else None
last_ma50 = chart_data["MA50"].iloc[-1] if pd.notna(chart_data["MA50"].iloc[-1]) else None

col1, col2, col3 = st.columns(3)
col1.metric("Last Close", f"${last_close:,.2f}")
if last_ma20 is not None:
    above_20 = "Above" if last_close > last_ma20 else "Below"
    col2.metric(f"20 MA ({above_20})", f"${last_ma20:,.2f}",
                delta=f"${last_close - last_ma20:,.2f}", delta_color="normal" if last_close > last_ma20 else "inverse")
if last_ma50 is not None:
    above_50 = "Above" if last_close > last_ma50 else "Below"
    col3.metric(f"50 MA ({above_50})", f"${last_ma50:,.2f}",
                delta=f"${last_close - last_ma50:,.2f}", delta_color="normal" if last_close > last_ma50 else "inverse")

# MA-based context
if last_ma20 is not None and last_ma50 is not None:
    if last_close > last_ma20 > last_ma50:
        st.success("Price above both MAs, 20 MA above 50 MA — **bullish structure**. "
                   "Look for pullbacks to 20 MA as buy zones.")
    elif last_close > last_ma50 and last_close < last_ma20:
        st.warning("Price below 20 MA but above 50 MA — **pullback in uptrend**. "
                   "50 MA is key support. If it holds, good long entry.")
    elif last_close < last_ma50:
        st.error("Price below both MAs — **bearish structure**. "
                 "Be defensive. 20 MA and 50 MA are now resistance overhead.")

st.divider()

# === INSIDE VS OUTSIDE DAY PLAYBOOK ===
st.header("Pattern Playbook")

tab_inside, tab_outside, tab_normal = st.tabs(["Inside Day", "Outside Day", "Normal Day"])

with tab_inside:
    st.markdown("""
### Inside Day Trading Rules

An **inside day** means today's high/low fits entirely within yesterday's range.
This signals **compression** → a breakout is coming.

**Why it's good for day trading:**
- The range is tight → your stop is tight → great risk/reward
- You know EXACTLY where to put your stop (below the inside day low)
- Breakout direction often follows the prior trend

**Entry Rules:**
1. **Wait for breakout** — don't enter during the inside day, enter the NEXT day
2. **Long entry**: Price breaks above inside day high
3. **Stop**: Below inside day low (this is your edge — tight stop)
4. **Target 1**: 1× the inside day range above entry (1R)
5. **Target 2**: Parent candle range above entry

**Position Sizing:**
- Inside day = tight stop = you can take FULL position
- Risk per share = inside high − inside low
- If risk/share is small, your total $ risk stays controlled even with full size

**What to watch for:**
- Multiple inside days in a row → even tighter range → bigger breakout
- Volume dropping on inside day → breakout will have more energy
- Inside day after a trend → continuation breakout more likely
""")

with tab_outside:
    st.markdown("""
### Outside Day Trading Rules

An **outside day** means today's high AND low both exceed yesterday's range.
This signals **expansion** and often a reversal or strong move.

**Why it's tricky:**
- The range is WIDE → your stop is wide → more $ at risk
- Both sides got tested → direction is unclear until the close
- Can trap both bulls and bears

**The Close Tells You Everything:**
- **Closed in upper 25%** → Bullish. Next day likely continues up.
- **Closed in lower 25%** → Bearish. Avoid longs.
- **Closed in middle** → Chop. Consider sitting out.

**Entry Rules (Bullish Outside Day):**
1. **DON'T chase** — the big move already happened
2. **Wait for pullback** to outside day midpoint
3. **Long entry**: Bounce off midpoint with confirmation
4. **Stop**: Below outside day midpoint (tighter) or below outside day low (safer but wider)
5. **Target**: Retest of outside day high, then extension

**Position Sizing:**
- Outside day = wide stop = **HALF position**
- This is the key rule: reduce size when stops are wide
- You can always add if the trade works

**When to avoid:**
- Outside day closes bearish → no longs
- Outside day on no volume → likely just noise
- Two outside days in a row → market is choppy, sit out
""")

with tab_normal:
    st.markdown("""
### Normal Day Trading Rules

Most days are normal — the range doesn't fit inside or engulf the prior day.

**Support/Resistance Approach:**
1. **Prior day low = support** → look for long entries near this level
2. **Prior day high = resistance** → take profits or reduce near this level
3. **Stop**: Below prior day low (with small buffer)

**For your style (support/resistance, key levels):**
- Prior day low is your first buy zone
- Set stop right below it — if prior day low breaks, it's no longer support
- Target is prior day high
- Risk is small (entry near low, stop just below)

**Position Sizing:**
- Normal days = normal risk = full position
- Stop is entry − prior day low (should be small if you buy near the low)
""")

st.divider()

# === BACKTEST: YOUR TRADES ON INSIDE/OUTSIDE DAYS ===
st.header("Your Historical Performance by Day Type")
st.caption("How did your actual trades perform on inside vs outside vs normal days?")

if not user:
    st.info("Log in to see your personal trade history matched against day patterns.")
    st.stop()

trades_df = get_user_trades(user["id"])
if not trades_df.empty:
    # Get historical data for traded symbols to classify their trade days
    trade_symbols = trades_df["symbol"].unique()
    # Focus on the most traded symbols
    top_symbols = trades_df["symbol"].value_counts().head(10).index.tolist()

    all_classified = []
    for sym in top_symbols:
        sym_trades = trades_df[trades_df["symbol"] == sym].copy()
        try:
            sym_hist = fetch_ohlc(sym, period="1y")
            if sym_hist.empty:
                continue
        except Exception:
            continue

        for _, trade in sym_trades.iterrows():
            trade_date = trade["trade_date"]
            # Find this date in historical data
            # Handle timezone-naive comparison
            hist_dates = sym_hist.index
            matches = hist_dates[hist_dates.date == trade_date.date()] if hasattr(trade_date, 'date') else []
            if len(matches) == 0:
                continue

            idx = sym_hist.index.get_loc(matches[0])
            if idx < 1:
                continue

            row = sym_hist.iloc[idx]
            prev = sym_hist.iloc[idx - 1]
            pattern, direction = classify_day(row, prev)

            all_classified.append({
                "date": trade_date,
                "symbol": sym,
                "realized_pnl": trade["realized_pnl"],
                "pattern": pattern,
                "direction": direction,
            })

    if all_classified:
        class_df = pd.DataFrame(all_classified)

        by_pattern = class_df.groupby("pattern").agg(
            total_pnl=("realized_pnl", "sum"),
            num_trades=("realized_pnl", "count"),
            win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
            avg_pnl=("realized_pnl", "mean"),
        ).reset_index()

        col1, col2 = st.columns(2)
        with col1:
            colors = {"inside": "#3498db", "outside": "#e74c3c", "normal": "#95a5a6"}
            fig = go.Figure(go.Bar(
                x=by_pattern["pattern"], y=by_pattern["total_pnl"],
                marker_color=[colors.get(p, "#95a5a6") for p in by_pattern["pattern"]],
                text=[f"${v:,.0f}" for v in by_pattern["total_pnl"]],
                textposition="outside",
            ))
            fig.update_layout(height=300, title="P&L by Day Pattern", yaxis_title="P&L ($)")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(
                by_pattern.rename(columns={
                    "pattern": "Pattern", "total_pnl": "Total P&L",
                    "num_trades": "Trades", "win_rate": "Win Rate %",
                    "avg_pnl": "Avg P&L",
                }).set_index("Pattern").style.format({
                    "Total P&L": "${:,.2f}", "Avg P&L": "${:,.2f}",
                    "Win Rate %": "{:.1f}%",
                }),
                use_container_width=True,
            )

        # Breakdown by pattern + direction
        by_pat_dir = class_df.groupby(["pattern", "direction"]).agg(
            total_pnl=("realized_pnl", "sum"),
            num_trades=("realized_pnl", "count"),
            win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
        ).reset_index()

        st.markdown("**Breakdown by Pattern + Direction:**")
        st.dataframe(
            by_pat_dir.rename(columns={
                "pattern": "Pattern", "direction": "Direction",
                "total_pnl": "Total P&L", "num_trades": "Trades",
                "win_rate": "Win Rate %",
            }).style.format({
                "Total P&L": "${:,.2f}", "Win Rate %": "{:.1f}%",
            }),
            use_container_width=True,
        )

        classified_count = len(class_df)
        total_count = len(trades_df)
        st.caption(f"Classified {classified_count} of {total_count} trades "
                   f"(top 10 symbols by frequency). Others couldn't be matched to price data.")
    else:
        st.info("Could not classify historical trades. Price data may not be available for the trade dates.")
