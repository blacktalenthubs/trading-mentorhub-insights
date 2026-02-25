"""Overview - P&L summary, win rate, monthly chart, cumulative P&L."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db import init_db, get_user_trades, get_user_options
from auth import require_auth

init_db()
user = require_auth()
st.title("Overview")

df = get_user_trades(user["id"])
if df.empty:
    st.info("No trade data. Go to Import page to upload PDFs.")
    st.stop()

# --- KPIs ---
total_pnl = df["realized_pnl"].sum()
total_trades = len(df)
winners = df[df["realized_pnl"] > 0]
losers = df[df["realized_pnl"] < 0]
win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
avg_win = winners["realized_pnl"].mean() if len(winners) > 0 else 0
avg_loss = losers["realized_pnl"].mean() if len(losers) > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total P&L (Stocks/ETFs)", f"${total_pnl:,.2f}")
col2.metric("Win Rate", f"{win_rate:.1f}%")
col3.metric("Total Trades", f"{total_trades}")
col4.metric("Wash Sale Disallowed", f"${df['wash_sale_disallowed'].sum():,.2f}")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Avg Winner", f"${avg_win:,.2f}")
col6.metric("Avg Loser", f"${avg_loss:,.2f}")
risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
col7.metric("Risk/Reward", f"{risk_reward:.2f}")
expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)
col8.metric("Expectancy/Trade", f"${expectancy:,.2f}")

# --- Options P&L callout ---
opts = get_user_options(user["id"])
if not opts.empty:
    opt_pnl = opts["realized_pnl"].sum()
    st.info(f"For reference: Options P&L in this account was **${opt_pnl:,.2f}** "
            f"across {len(opts)} trades (excluded from analysis above).")

st.divider()

# --- Monthly P&L Bar Chart ---
st.subheader("Monthly P&L")
df["month"] = df["trade_date"].dt.to_period("M").astype(str)
monthly = df.groupby("month").agg(
    pnl=("realized_pnl", "sum"),
    trades=("realized_pnl", "count"),
    wins=("realized_pnl", lambda x: (x > 0).sum()),
).reset_index()
monthly["win_rate"] = monthly["wins"] / monthly["trades"] * 100

colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in monthly["pnl"]]
fig = go.Figure(go.Bar(
    x=monthly["month"], y=monthly["pnl"],
    marker_color=colors,
    text=[f"${v:,.0f}" for v in monthly["pnl"]],
    textposition="outside",
    hovertemplate="Month: %{x}<br>P&L: $%{y:,.2f}<br><extra></extra>",
))
fig.update_layout(xaxis_title="Month", yaxis_title="P&L ($)", height=400, showlegend=False)
st.plotly_chart(fig, use_container_width=True)

# --- Equity Curve with Drawdown ---
st.subheader("Equity Curve & Drawdown")
df_sorted = df.sort_values("trade_date")
df_sorted["cumulative_pnl"] = df_sorted["realized_pnl"].cumsum()
df_sorted["trade_num"] = range(1, len(df_sorted) + 1)

# Calculate drawdown from peak
df_sorted["peak"] = df_sorted["cumulative_pnl"].cummax()
df_sorted["drawdown"] = df_sorted["cumulative_pnl"] - df_sorted["peak"]

fig2 = go.Figure()
# Equity line
fig2.add_trace(go.Scatter(
    x=df_sorted["trade_num"], y=df_sorted["cumulative_pnl"],
    mode="lines", name="Equity",
    line=dict(color="#3498db", width=2),
    hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>P&L: $%{customdata[2]:,.2f}<br>Equity: $%{y:,.2f}<extra></extra>",
    customdata=list(zip(
        df_sorted["trade_date"].dt.strftime("%Y-%m-%d"),
        df_sorted["symbol"],
        df_sorted["realized_pnl"],
    )),
))
# Peak line
fig2.add_trace(go.Scatter(
    x=df_sorted["trade_num"], y=df_sorted["peak"],
    mode="lines", name="Peak",
    line=dict(color="#95a5a6", width=1, dash="dot"),
))
# Drawdown fill
fig2.add_trace(go.Scatter(
    x=df_sorted["trade_num"], y=df_sorted["drawdown"],
    mode="lines", name="Drawdown",
    fill="tozeroy", fillcolor="rgba(231, 76, 60, 0.2)",
    line=dict(color="#e74c3c", width=1),
    yaxis="y2",
))
fig2.add_hline(y=0, line_dash="dash", line_color="gray")

max_dd = df_sorted["drawdown"].min()
max_dd_idx = df_sorted["drawdown"].idxmin()
max_dd_trade = df_sorted.loc[max_dd_idx, "trade_num"]

fig2.update_layout(
    height=450,
    xaxis_title="Trade #",
    yaxis=dict(title="Cumulative P&L ($)"),
    yaxis2=dict(title="Drawdown ($)", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig2, use_container_width=True)

col1, col2, col3 = st.columns(3)
col1.metric("Max Drawdown", f"${max_dd:,.2f}")
col2.metric("Max Drawdown Trade #", f"{max_dd_trade}")
# Recovery: from max drawdown back to peak
after_dd = df_sorted[df_sorted["trade_num"] >= max_dd_trade]
recovered = after_dd[after_dd["cumulative_pnl"] >= df_sorted.loc[max_dd_idx, "peak"]]
if not recovered.empty:
    recovery_trades = recovered.iloc[0]["trade_num"] - max_dd_trade
    col3.metric("Recovery (trades)", f"{int(recovery_trades)}")
else:
    col3.metric("Recovery", "Not yet")

# --- Holding Period Breakdown ---
st.subheader("P&L by Holding Period")
has_period = df[df["holding_period_type"].notna() & (df["holding_period_type"] != "unknown")]
if not has_period.empty:
    by_period = has_period.groupby("holding_period_type").agg(
        total_pnl=("realized_pnl", "sum"),
        num_trades=("realized_pnl", "count"),
        win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl=("realized_pnl", "mean"),
    ).reset_index()

    order = ["day_trade", "swing", "position"]
    by_period["holding_period_type"] = pd.Categorical(
        by_period["holding_period_type"], categories=order, ordered=True
    )
    by_period = by_period.sort_values("holding_period_type").dropna(subset=["holding_period_type"])

    col1, col2 = st.columns(2)
    with col1:
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in by_period["total_pnl"]]
        fig = go.Figure(go.Bar(
            x=by_period["holding_period_type"], y=by_period["total_pnl"],
            marker_color=colors,
            text=[f"${v:,.0f}" for v in by_period["total_pnl"]],
            textposition="outside",
        ))
        fig.update_layout(height=300, xaxis_title="", yaxis_title="P&L ($)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.dataframe(by_period.rename(columns={
            "holding_period_type": "Period",
            "total_pnl": "Total P&L",
            "num_trades": "Trades",
            "avg_pnl": "Avg P&L",
            "win_rate": "Win Rate %",
        }).set_index("Period").style.format({
            "Total P&L": "${:,.2f}",
            "Avg P&L": "${:,.2f}",
            "Win Rate %": "{:.1f}%",
        }), use_container_width=True)
