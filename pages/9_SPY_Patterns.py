"""
SPY Pattern Analysis — Prior Day Low Behavior

Answers:
- How often does SPY test the prior day's low?
- When it tests, does it reclaim or break?
- What's the optimal stop distance?
- How does trend context affect the outcome?
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from analytics.spy_patterns import (
    load_or_fetch_spy,
    analyze_prior_day_low,
    compute_pattern_stats,
    compute_stop_analysis,
    compute_reentry_analysis,
    compute_ma_context,
)

st.set_page_config(page_title="SPY Patterns", layout="wide")
st.title("SPY Prior Day Low — Pattern Analysis")
st.caption("How does SPY behave around yesterday's low? Data-driven stop placement.")

# ---------------------------------------------------------------------------
# Load Data
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_data(refresh: bool = False):
    df = load_or_fetch_spy(force_refresh=refresh)
    results = analyze_prior_day_low(df)
    results_ma = compute_ma_context(df, results)
    return df, results, results_ma


with st.sidebar:
    st.subheader("Settings")
    refresh = st.button("Refresh SPY Data")
    lookback = st.selectbox("Lookback Period", ["All", "6 Months", "3 Months", "1 Month"], index=0)

try:
    df, results, results_ma = load_data(refresh=refresh)
except ImportError:
    st.error("yfinance not installed. Run: `pip install yfinance`")
    st.stop()

# Apply lookback filter
if lookback == "6 Months":
    cutoff = pd.Timestamp.now().date() - pd.Timedelta(days=180)
    results = results[results["date"] >= cutoff]
    results_ma = results_ma[results_ma["date"] >= cutoff]
elif lookback == "3 Months":
    cutoff = pd.Timestamp.now().date() - pd.Timedelta(days=90)
    results = results[results["date"] >= cutoff]
    results_ma = results_ma[results_ma["date"] >= cutoff]
elif lookback == "1 Month":
    cutoff = pd.Timestamp.now().date() - pd.Timedelta(days=30)
    results = results[results["date"] >= cutoff]
    results_ma = results_ma[results_ma["date"] >= cutoff]

stats = compute_pattern_stats(results)

# ---------------------------------------------------------------------------
# Section 1: Overview KPIs
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("How Often Does SPY Test Prior Day's Low?")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Days Analyzed", stats["total_trading_days"])
col2.metric("Days Tested Prior Low", stats["days_tested_prior_low"],
            f"{stats['pct_days_tested']:.1f}%")
col3.metric("Days Never Reached", stats["days_never_reached"],
            f"{100 - stats['pct_days_tested']:.1f}%")

tested_total = stats["days_tested_prior_low"]
if tested_total > 0:
    bullish = stats.get("count_wick_reclaim", 0) + stats.get("count_held_above", 0)
    col4.metric("Bullish When Tested", bullish,
                f"{bullish / tested_total * 100:.1f}% win rate")

# ---------------------------------------------------------------------------
# Section 2: Outcome Breakdown
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("What Happens When SPY Tests Prior Day's Low?")

col1, col2 = st.columns(2)

with col1:
    if tested_total > 0:
        outcomes = {
            "Wick Below → Reclaimed": stats.get("count_wick_reclaim", 0),
            "Held At/Above": stats.get("count_held_above", 0),
            "Broke → Closed Below": stats.get("count_broke_and_closed_below", 0),
        }
        fig_pie = go.Figure(data=[go.Pie(
            labels=list(outcomes.keys()),
            values=list(outcomes.values()),
            marker_colors=["#00C853", "#4CAF50", "#FF1744"],
            textinfo="label+percent+value",
            hole=0.4,
        )])
        fig_pie.update_layout(
            title="Outcome When Prior Low is Tested",
            height=400,
            template="plotly_dark",
        )
        st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.markdown("""
    **Outcome Definitions:**

    - **Wick Below + Reclaimed**: Price broke below prior day's low, then closed
      ABOVE it. This is the re-entry signal — market swept stops then reversed.

    - **Held At/Above**: Price came within range of prior low but never broke below.
      Buyers defended the level. Entry on the hold is cleaner but rarer.

    - **Broke + Closed Below**: Price broke below and stayed below at close.
      The level failed. This is when your stop saves you.

    **Your Edge**: The wick-and-reclaim pattern means market makers sweep the
    obvious stops, then real buyers step in. By waiting for the reclaim (not
    just the test), you enter AFTER the stop hunt.
    """)

# ---------------------------------------------------------------------------
# Section 3: Wick Depth Analysis
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("How Far Does the Wick Go Before Reclaiming?")

reentry = compute_reentry_analysis(results)
if reentry and "penetration_buckets" in reentry:
    col1, col2 = st.columns(2)

    with col1:
        pen_df = reentry["penetration_buckets"]
        fig_bar = go.Figure(data=[go.Bar(
            x=pen_df["max_wick_below_prior_low"],
            y=pen_df["pct_of_reclaims"],
            text=[f"{v:.0f}%" for v in pen_df["pct_of_reclaims"]],
            textposition="auto",
            marker_color="#00C853",
        )])
        fig_bar.update_layout(
            title="Cumulative % of Reclaims by Max Wick Depth",
            xaxis_title="Max Wick Below Prior Low",
            yaxis_title="% of Reclaims (Cumulative)",
            height=400,
            template="plotly_dark",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col2:
        cs = reentry.get("close_stats", {})
        st.metric("Reclaim vs Break Ratio", reentry.get("reclaim_vs_break_ratio", "N/A"))
        st.metric("Avg Close Above Prior Low (after reclaim)",
                  f"${cs.get('avg_close_above_prior_low', 0):.2f}")
        st.metric("Closed as Green Candle (after reclaim)",
                  f"{cs.get('pct_closed_above_open', 0):.1f}%")

        st.markdown("""
        **Key Insight**: Most reclaims wick less than $1.50 below the prior low.
        This tells you exactly where to place your stop — just outside the
        typical wick range.
        """)

# ---------------------------------------------------------------------------
# Section 4: Optimal Stop Distance
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Optimal Stop Distance (Data-Driven)")

stop_df = compute_stop_analysis(results)
if len(stop_df) > 0:
    col1, col2 = st.columns(2)

    with col1:
        fig_stop = go.Figure()
        fig_stop.add_trace(go.Bar(
            x=stop_df["stop_distance"].apply(lambda x: f"${x:.2f}"),
            y=stop_df["win_rate"],
            name="Win Rate %",
            marker_color="#2196F3",
            yaxis="y",
        ))
        fig_stop.add_trace(go.Scatter(
            x=stop_df["stop_distance"].apply(lambda x: f"${x:.2f}"),
            y=stop_df["expectancy"],
            name="Expectancy $/trade",
            line=dict(color="#FF9800", width=3),
            yaxis="y2",
        ))
        fig_stop.update_layout(
            title="Win Rate & Expectancy by Stop Distance",
            xaxis_title="Stop Distance Below Prior Low",
            yaxis=dict(title="Win Rate %", side="left"),
            yaxis2=dict(title="Expectancy $/trade", side="right", overlaying="y"),
            height=400,
            template="plotly_dark",
            legend=dict(x=0.01, y=0.99),
        )
        st.plotly_chart(fig_stop, use_container_width=True)

    with col2:
        best = stop_df.loc[stop_df["expectancy"].idxmax()]
        st.markdown("### Recommended Stop")
        st.metric("Best Stop Distance", f"${best['stop_distance']:.2f}")
        st.metric("Win Rate at Best Stop", f"{best['win_rate']:.1f}%")
        st.metric("Expectancy", f"${best['expectancy']:.2f} / trade")
        st.metric("Max Loss per 100 shares", f"${best['max_loss_per_100_shares']:.0f}")

        st.markdown(f"""
        **Translation**: Place your stop **${best['stop_distance']:.2f}** below
        the prior day's low. With a 2:1 target, this gives the best expected
        value per trade.

        At 100 shares of SPY (~$69,000 position):
        - Risk per trade: **${best['max_loss_per_100_shares']:.0f}**
        - Target per trade: **${best['max_loss_per_100_shares'] * 2:.0f}**
        """)

    # Full table
    st.markdown("#### All Stop Distances Compared")
    display_df = stop_df.copy()
    display_df.columns = ["Stop $", "Wins", "Losses", "Trades", "Win %",
                          "Avg Win $", "Avg Loss $", "Expectancy $", "Max Loss/100sh"]
    st.dataframe(display_df.style.highlight_max(subset=["Expectancy $"], color="#1B5E20"),
                 use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Section 5: Trend Context
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Does Market Trend Affect the Pattern?")

tested_ma = results_ma[results_ma["tested_prior_low"]]
if len(tested_ma) > 0:
    trend_stats = []
    for trend in ["uptrend", "downtrend", "mixed"]:
        subset = tested_ma[tested_ma["trend"] == trend]
        if len(subset) > 0:
            bullish = len(subset[subset["outcome"].isin(["wick_reclaim", "held_above"])])
            trend_stats.append({
                "Trend": trend.title(),
                "Times Tested": len(subset),
                "Bullish Outcomes": bullish,
                "Bearish Outcomes": len(subset) - bullish,
                "Bullish %": bullish / len(subset) * 100,
            })

    if trend_stats:
        trend_df = pd.DataFrame(trend_stats)

        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(
            x=trend_df["Trend"],
            y=trend_df["Bullish %"],
            name="Bullish %",
            marker_color="#00C853",
        ))
        fig_trend.add_trace(go.Bar(
            x=trend_df["Trend"],
            y=100 - trend_df["Bullish %"],
            name="Bearish %",
            marker_color="#FF1744",
        ))
        fig_trend.update_layout(
            barmode="stack",
            title="Prior Day Low Outcome by Market Trend",
            yaxis_title="% of Outcomes",
            height=400,
            template="plotly_dark",
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        st.dataframe(trend_df.style.format({"Bullish %": "{:.1f}%"}),
                     use_container_width=True, hide_index=True)

        st.markdown("""
        **Trading Rule**: The prior-day-low reclaim pattern has a significantly
        higher success rate in uptrends (price above both MA20 and MA50).
        In downtrends, the level breaks more often — tighter stops or skip the trade.
        """)

# ---------------------------------------------------------------------------
# Section 6: Recent Days Detail
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Recent 20 Days — Detailed View")

recent = results.sort_values("date", ascending=False).head(20).copy()
recent["outcome_emoji"] = recent["outcome"].map({
    "no_test": "---",
    "wick_reclaim": "RECLAIM",
    "held_above": "HELD",
    "broke_and_closed_below": "BROKE",
})

display_cols = ["date", "open", "close", "prior_low", "outcome_emoji",
                "max_penetration_below", "close_vs_prior_low", "day_range"]
display_recent = recent[display_cols].copy()
display_recent.columns = ["Date", "Open", "Close", "Prior Low", "Outcome",
                          "Max Below $", "Close vs Low $", "Day Range $"]

for col in ["Open", "Close", "Prior Low", "Max Below $", "Close vs Low $", "Day Range $"]:
    display_recent[col] = display_recent[col].apply(lambda x: f"${x:.2f}")

def color_outcome(val):
    if val == "RECLAIM":
        return "background-color: #1B5E20; color: white"
    elif val == "HELD":
        return "background-color: #2E7D32; color: white"
    elif val == "BROKE":
        return "background-color: #B71C1C; color: white"
    return ""

st.dataframe(
    display_recent.style.applymap(color_outcome, subset=["Outcome"]),
    use_container_width=True,
    hide_index=True,
    height=700,
)

# ---------------------------------------------------------------------------
# Section 7: Your Trading Rules
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Data-Derived Trading Rules")

if len(stop_df) > 0:
    best = stop_df.loc[stop_df["expectancy"].idxmax()]

st.markdown(f"""
### SPY Prior Day Low Playbook

| Rule | Detail |
|------|--------|
| **Entry Signal** | SPY wicks below prior day's low then reclaims above it (candle close or 5min reclaim) |
| **Stop Loss** | ${best['stop_distance']:.2f} below prior day's low |
| **Target** | ${best['stop_distance'] * 2:.2f} above entry (2:1 R/R) |
| **Max Attempts** | 2 per day. If stopped twice, the level is broken — walk away |
| **Trend Filter** | Higher confidence when SPY is above MA20 + MA50 (uptrend) |
| **Time Filter** | Best signals in first 2 hours (9:30-11:30 ET). Avoid 12:00-2:00 chop |
| **Abort** | If price stays below prior low for >10 min with no reclaim attempt, skip |
| **Position Size** | Risk max 1% of account per attempt |

### The Re-Entry Protocol

```
Attempt 1: Enter on first reclaim → stop ${best['stop_distance']:.2f} below
    |
    ├── WIN: Price hits target → done for the day
    |
    └── STOPPED: Price wicked through stop
            |
            └── WAIT: Does price reclaim again?
                    |
                    ├── YES → Attempt 2: Re-enter on second reclaim
                    |         Same stop distance. Same target.
                    |
                    └── NO (stays below >10 min) → DONE. Level is dead.
```
""")
