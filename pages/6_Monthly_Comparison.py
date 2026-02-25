"""Monthly Comparison - Month-over-month trends, strategy evolution."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db import init_db, get_focus_account_trades

init_db()
st.title("Monthly Comparison")
st.caption("Are you improving month over month?")

df = get_focus_account_trades()
if df.empty:
    st.info("No trade data. Go to Import page to upload PDFs.")
    st.stop()

df["month"] = df["trade_date"].dt.to_period("M").astype(str)

# === Monthly Summary Table ===
monthly = df.groupby("month").agg(
    total_pnl=("realized_pnl", "sum"),
    num_trades=("realized_pnl", "count"),
    win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
    avg_pnl=("realized_pnl", "mean"),
    avg_win=("realized_pnl", lambda x: x[x > 0].mean() if (x > 0).any() else 0),
    avg_loss=("realized_pnl", lambda x: x[x < 0].mean() if (x < 0).any() else 0),
    total_proceeds=("proceeds", "sum"),
    total_wash=("wash_sale_disallowed", "sum"),
).reset_index()

# Add holding time
has_days = df[df["holding_days"].notna()]
if not has_days.empty:
    hold = has_days.groupby(has_days["trade_date"].dt.to_period("M").astype(str)).agg(
        avg_hold=("holding_days", "mean"),
    ).reset_index().rename(columns={"trade_date": "month"})
    monthly = monthly.merge(hold, on="month", how="left")

# Add day trade % and swing %
period_mix = df.groupby(["month", "holding_period_type"]).size().unstack(fill_value=0)
if "day_trade" in period_mix.columns:
    period_mix["day_trade_pct"] = period_mix.get("day_trade", 0) / period_mix.sum(axis=1) * 100
else:
    period_mix["day_trade_pct"] = 0
if "swing" in period_mix.columns:
    period_mix["swing_pct"] = period_mix.get("swing", 0) / period_mix.sum(axis=1) * 100
else:
    period_mix["swing_pct"] = 0
period_mix = period_mix[["day_trade_pct", "swing_pct"]].reset_index()
period_mix.columns.name = None
monthly = monthly.merge(period_mix, on="month", how="left")

monthly["risk_reward"] = abs(monthly["avg_win"] / monthly["avg_loss"].where(monthly["avg_loss"] != 0, 1))

st.subheader("Monthly Summary")
disp = monthly.copy()
disp_cols = {
    "month": "Month", "total_pnl": "P&L", "num_trades": "Trades",
    "win_rate": "Win Rate", "avg_pnl": "Avg P&L",
    "risk_reward": "R:R", "day_trade_pct": "Day Trade %",
    "swing_pct": "Swing %", "total_wash": "Wash Sales",
}
if "avg_hold" in disp.columns:
    disp_cols["avg_hold"] = "Avg Hold Days"

fmt = {
    "P&L": "${:,.2f}", "Avg P&L": "${:,.2f}", "Win Rate": "{:.1f}%",
    "R:R": "{:.2f}", "Day Trade %": "{:.0f}%", "Swing %": "{:.0f}%",
    "Wash Sales": "${:,.0f}", "Trades": "{:.0f}",
}
if "Avg Hold Days" in disp_cols.values():
    fmt["Avg Hold Days"] = "{:.1f}"

st.dataframe(
    disp[list(disp_cols.keys())].rename(columns=disp_cols).set_index("Month").style.format(fmt),
    use_container_width=True,
)

st.divider()

# === P&L Trend with Cumulative ===
st.subheader("P&L Trend")
fig = go.Figure()
fig.add_trace(go.Bar(
    x=monthly["month"], y=monthly["total_pnl"],
    name="Monthly P&L",
    marker_color=["#2ecc71" if v >= 0 else "#e74c3c" for v in monthly["total_pnl"]],
    text=[f"${v:,.0f}" for v in monthly["total_pnl"]],
    textposition="outside",
))
fig.add_trace(go.Scatter(
    x=monthly["month"], y=monthly["total_pnl"].cumsum(),
    name="Cumulative", mode="lines+markers",
    yaxis="y2", line=dict(color="#3498db", width=3),
))
fig.update_layout(
    height=400,
    yaxis=dict(title="Monthly P&L ($)"),
    yaxis2=dict(title="Cumulative P&L ($)", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig, use_container_width=True)

# === Win Rate Trend ===
st.subheader("Win Rate & R:R Trend")
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=monthly["month"], y=monthly["win_rate"],
    mode="lines+markers", name="Win Rate %",
    line=dict(color="#2ecc71", width=2),
))
fig.add_trace(go.Scatter(
    x=monthly["month"], y=monthly["risk_reward"],
    mode="lines+markers", name="Risk/Reward",
    yaxis="y2", line=dict(color="#e67e22", width=2),
))
fig.add_hline(y=50, line_dash="dash", line_color="gray")
fig.update_layout(
    height=350,
    yaxis=dict(title="Win Rate %"),
    yaxis2=dict(title="Risk/Reward Ratio", overlaying="y", side="right"),
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig, use_container_width=True)

# === Strategy Evolution: Day Trade % over time ===
st.subheader("Strategy Evolution")
st.caption("Tracking shift from day trading to swing trading over time")

fig = go.Figure()
fig.add_trace(go.Bar(
    x=monthly["month"], y=monthly["day_trade_pct"],
    name="Day Trade %", marker_color="#e74c3c",
))
fig.add_trace(go.Bar(
    x=monthly["month"], y=monthly["swing_pct"],
    name="Swing %", marker_color="#2ecc71",
))
fig.update_layout(
    height=350, barmode="stack",
    yaxis_title="% of Trades",
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig, use_container_width=True)

# === Category Mix Over Time ===
st.subheader("Category Mix Over Time")
cat_monthly = df.groupby(["month", "category"]).agg(
    pnl=("realized_pnl", "sum"),
    trades=("realized_pnl", "count"),
).reset_index()

fig = px.bar(cat_monthly, x="month", y="trades", color="category", barmode="stack",
             color_discrete_map={
                 "mega_cap": "#2ecc71", "speculative": "#e74c3c",
                 "index_etf": "#3498db", "other": "#95a5a6",
             })
fig.update_layout(height=350, xaxis_title="", yaxis_title="# Trades")
st.plotly_chart(fig, use_container_width=True)

# === Speculation vs Index/Mega-cap P&L by month ===
st.subheader("Speculation vs Index/Mega-Cap P&L")
df["bucket"] = df["category"].map(
    lambda c: "Index/Mega-Cap" if c in ("mega_cap", "index_etf")
    else "Speculative" if c == "speculative"
    else "Other"
)
bucket_monthly = df.groupby(["month", "bucket"]).agg(
    pnl=("realized_pnl", "sum"),
).reset_index()

fig = px.bar(bucket_monthly, x="month", y="pnl", color="bucket",
             barmode="group",
             color_discrete_map={
                 "Index/Mega-Cap": "#2ecc71", "Speculative": "#e74c3c", "Other": "#95a5a6",
             })
fig.update_layout(height=350, xaxis_title="", yaxis_title="P&L ($)")
st.plotly_chart(fig, use_container_width=True)

# === Trade Count Trend ===
st.subheader("Trade Frequency")
fig = px.bar(monthly, x="month", y="num_trades", text_auto=True,
             color_discrete_sequence=["#9b59b6"])
fig.update_layout(height=300, xaxis_title="", yaxis_title="# Trades")
st.plotly_chart(fig, use_container_width=True)
