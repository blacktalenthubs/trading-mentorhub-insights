"""Pre-Market Planner - Inside/outside day analysis, key levels, risk calculator."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from config import STOP_LOSS_PCT
from db import init_db, get_focus_account_trades

init_db()
st.title("Pre-Market Planner")
st.caption("Identify the day type, know your levels, size your risk — before the bell")


@st.cache_data(ttl=300)
def fetch_ohlc(symbol: str, period: str = "3mo") -> pd.DataFrame:
    """Fetch OHLC data via yfinance. Cached for 5 minutes."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            return pd.DataFrame()
        hist.index = hist.index.tz_localize(None)
        return hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception as e:
        st.error(f"Failed to fetch data for {symbol}: {e}")
        return pd.DataFrame()


def classify_day(row, prev_row):
    """Classify a candle relative to previous day."""
    if prev_row is None:
        return "normal", "—"

    prev_h, prev_l = prev_row["High"], prev_row["Low"]
    curr_h, curr_l = row["High"], row["Low"]
    prev_range = prev_h - prev_l
    curr_range = curr_h - curr_l

    # Inside day: current range fits within previous range
    is_inside = curr_h <= prev_h and curr_l >= prev_l

    # Outside day: current range engulfs previous range
    is_outside = curr_h > prev_h and curr_l < prev_l

    # Close position within the day's range
    day_range = curr_h - curr_l
    if day_range > 0:
        close_position = (row["Close"] - curr_l) / day_range
    else:
        close_position = 0.5

    if close_position >= 0.6:
        direction = "bullish"
    elif close_position <= 0.4:
        direction = "bearish"
    else:
        direction = "neutral"

    if is_inside:
        return "inside", direction
    elif is_outside:
        return "outside", direction
    else:
        return "normal", direction


def get_levels(hist, idx):
    """Calculate key trading levels for the next session based on candle pattern."""
    row = hist.iloc[idx]
    prev_row = hist.iloc[idx - 1] if idx > 0 else None
    two_back = hist.iloc[idx - 2] if idx > 1 else None

    pattern, direction = classify_day(row, prev_row)

    levels = {
        "pattern": pattern,
        "direction": direction,
        "prior_high": row["High"],
        "prior_low": row["Low"],
        "prior_close": row["Close"],
        "prior_open": row["Open"],
        "prior_range": row["High"] - row["Low"],
        "prior_mid": (row["High"] + row["Low"]) / 2,
    }

    if prev_row is not None:
        levels["parent_high"] = prev_row["High"]
        levels["parent_low"] = prev_row["Low"]
        levels["parent_range"] = prev_row["High"] - prev_row["Low"]
        levels["parent_mid"] = (prev_row["High"] + prev_row["Low"]) / 2

    if pattern == "inside":
        # Inside day: tight range, breakout setup
        # Parent candle = the day before the inside day
        parent_h = prev_row["High"] if prev_row is not None else row["High"]
        parent_l = prev_row["Low"] if prev_row is not None else row["Low"]
        inside_h = row["High"]
        inside_l = row["Low"]

        levels["entry_long"] = inside_h  # breakout above inside day high
        levels["stop_long"] = inside_l   # stop below inside day low
        levels["target_1"] = inside_h + (inside_h - inside_l)  # 1R target
        levels["target_2"] = inside_h + (parent_h - parent_l)  # parent range extension
        levels["risk_per_share"] = inside_h - inside_l
        levels["notes"] = (
            f"Inside day — range ${row['High'] - row['Low']:,.2f} inside "
            f"parent range ${parent_h - parent_l:,.2f}. "
            f"Tight stop at inside low. Wait for breakout above ${inside_h:,.2f}. "
            f"Good R:R setup for day trade."
        )
        if direction == "bullish":
            levels["bias"] = "Bullish — inside day closed strong, breakout up more likely"
        elif direction == "bearish":
            levels["bias"] = "Bearish lean — inside day closed weak, be cautious on long breakout"
        else:
            levels["bias"] = "Neutral — wait for the breakout direction"

    elif pattern == "outside":
        # Outside day: wide range, tricky
        levels["entry_long"] = levels["prior_mid"]  # pullback to midpoint
        levels["stop_long"] = row["Low"]  # below outside day low (wide!)
        levels["target_1"] = row["High"]  # retest of outside day high
        levels["target_2"] = row["High"] + (row["High"] - levels["prior_mid"])  # extension
        levels["risk_per_share"] = levels["prior_mid"] - row["Low"]
        levels["notes"] = (
            f"Outside day — range ${row['High'] - row['Low']:,.2f} engulfs prior day. "
            f"Wide range means wide stops. Consider half-size position. "
            f"Wait for pullback to midpoint ${levels['prior_mid']:,.2f} before entry."
        )
        if direction == "bullish":
            levels["bias"] = (
                "Closed bullish (upper range) — continuation likely. "
                "Buy pullback to midpoint, stop below midpoint."
            )
            # Tighter stop option for bullish outside day
            levels["alt_stop"] = levels["prior_mid"] - (row["High"] - levels["prior_mid"]) * 0.5
            levels["alt_notes"] = (
                f"Tighter stop option: ${levels['alt_stop']:,.2f} "
                f"(below midpoint by half the upper range). Reduces risk but may get stopped on normal pullback."
            )
        elif direction == "bearish":
            levels["bias"] = (
                "Closed bearish (lower range) — reversal/continuation down likely. "
                "AVOID longs or wait for very strong support. Consider sitting out."
            )
        else:
            levels["bias"] = (
                "Closed neutral — no clear direction. Chop likely. "
                "Trade smaller or wait for next day's setup."
            )

    else:
        # Normal day
        levels["entry_long"] = row["Low"]  # buy near prior day low (support)
        levels["stop_long"] = row["Low"] - (row["High"] - row["Low"]) * 0.25  # stop below low
        levels["target_1"] = row["High"]  # prior day high
        levels["target_2"] = row["High"] + (row["High"] - row["Low"]) * 0.5  # extension
        levels["risk_per_share"] = row["Low"] - levels["stop_long"]
        levels["notes"] = (
            f"Normal day — range ${row['High'] - row['Low']:,.2f}. "
            f"Trade prior day H/L as support/resistance."
        )
        if direction == "bullish":
            levels["bias"] = "Closed bullish — look for pullback to prior day low for long entry"
        elif direction == "bearish":
            levels["bias"] = "Closed bearish — prior day low may break, be defensive"
        else:
            levels["bias"] = "Neutral close — trade the range, buy low sell high"

    return levels


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

# === CANDLESTICK CHART WITH LEVELS ===
st.subheader("Chart with Key Levels")

chart_data = hist.tail(15).copy()
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

# Key levels as horizontal lines
last_date = chart_data.index[-1].strftime("%Y-%m-%d")
fig.add_hline(y=levels["entry_long"], line_dash="dash", line_color="#3498db",
              annotation_text=f"Entry ${levels['entry_long']:,.2f}")
fig.add_hline(y=levels["stop_long"], line_dash="dash", line_color="#e74c3c",
              annotation_text=f"Stop ${levels['stop_long']:,.2f}")
fig.add_hline(y=levels["target_1"], line_dash="dash", line_color="#2ecc71",
              annotation_text=f"T1 ${levels['target_1']:,.2f}")
fig.add_hline(y=levels["target_2"], line_dash="dot", line_color="#27ae60",
              annotation_text=f"T2 ${levels['target_2']:,.2f}")

# Mark inside/outside days with annotations
for i in range(1, len(chart_data)):
    row = chart_data.iloc[i]
    prev = chart_data.iloc[i - 1]
    pattern, _ = classify_day(row, prev)
    date_str = chart_data.index[i].strftime("%Y-%m-%d")
    if pattern == "inside":
        fig.add_annotation(
            x=date_str, y=row["High"], yshift=15,
            text="ID", showarrow=False,
            font=dict(color="#3498db", size=11, family="Arial Black"),
            bgcolor="rgba(52, 152, 219, 0.2)", bordercolor="#3498db",
        )
    elif pattern == "outside":
        fig.add_annotation(
            x=date_str, y=row["High"], yshift=15,
            text="OD", showarrow=False,
            font=dict(color="#e74c3c", size=11, family="Arial Black"),
            bgcolor="rgba(231, 76, 60, 0.2)", bordercolor="#e74c3c",
        )

fig.update_layout(
    height=500, xaxis_rangeslider_visible=False,
    yaxis_title=f"{symbol} Price ($)",
    title=f"{symbol} — Last 15 Days with Levels",
)
st.plotly_chart(fig, use_container_width=True)

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

trades_df = get_focus_account_trades()
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
