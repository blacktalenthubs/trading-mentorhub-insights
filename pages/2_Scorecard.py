"""Monthly Scorecard — is my system working?"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db import init_db, get_user_trades, get_user_options, get_annotations
from auth import auto_login
import ui_theme

st.set_page_config(page_title="Scorecard | TradeSignal", page_icon="⚡", layout="wide")
init_db()
user = auto_login()
ui_theme.inject_custom_css()

ui_theme.page_header("Monthly Scorecard", "Am I making money? What's working? Am I disciplined?")

df = get_user_trades(user["id"])
if df.empty:
    ui_theme.empty_state("No trade data. Go to Import page to upload PDFs.")
    st.stop()

# =====================================================================
# 1. Top KPIs
# =====================================================================
total_pnl = df["realized_pnl"].sum()
total_trades = len(df)
winners = df[df["realized_pnl"] > 0]
losers = df[df["realized_pnl"] < 0]
win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
avg_win = winners["realized_pnl"].mean() if len(winners) > 0 else 0
avg_loss = losers["realized_pnl"].mean() if len(losers) > 0 else 0
risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total P&L", f"${total_pnl:,.2f}")
col2.metric("Win Rate", f"{win_rate:.1f}%")
col3.metric("Total Trades", f"{total_trades}")
col4.metric("Expectancy/Trade", f"${expectancy:,.2f}")

col5, col6, col7 = st.columns(3)
col5.metric("Avg Winner", f"${avg_win:,.2f}")
col6.metric("Avg Loser", f"${avg_loss:,.2f}")
col7.metric("Risk/Reward", f"{risk_reward:.2f}")

# Options P&L callout
opts = get_user_options(user["id"])
if not opts.empty:
    opt_pnl = opts["realized_pnl"].sum()
    st.info(f"Options P&L: **${opt_pnl:,.2f}** across {len(opts)} trades (excluded from analysis).")

st.divider()

# =====================================================================
# Precompute monthly aggregates (shared by several sections)
# =====================================================================
df["month"] = df["trade_date"].dt.to_period("M").astype(str)

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

# Holding period mix
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

# =====================================================================
# 2. P&L Trend — monthly bars (green/red) + cumulative line
# =====================================================================
ui_theme.section_header("P&L Trend")
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

# =====================================================================
# 3. Win Rate & R:R Trend — dual-axis line chart
# =====================================================================
ui_theme.section_header("Win Rate & R:R Trend")
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

# =====================================================================
# 4. Strategy Performance — P&L by strategy tag + table
# =====================================================================
annotations = get_annotations(user["id"])
if not annotations.empty:
    df_tagged = df.copy()
    df_tagged["trade_date_str"] = df_tagged["trade_date"].dt.strftime("%Y-%m-%d")
    df_tagged = df_tagged.merge(
        annotations[["source", "symbol", "trade_date", "quantity", "strategy_tag"]].rename(
            columns={"trade_date": "trade_date_str", "source": "ann_source"}
        ),
        left_on=["source", "symbol", "trade_date_str", "quantity"],
        right_on=["ann_source", "symbol", "trade_date_str", "quantity"],
        how="left",
    )
    df_tagged.drop(columns=["ann_source", "trade_date_str"], errors="ignore", inplace=True)
else:
    df_tagged = df.copy()
    df_tagged["strategy_tag"] = None

tagged = df_tagged[df_tagged["strategy_tag"].notna()]
if not tagged.empty:
    ui_theme.section_header("Strategy Performance")
    by_tag = tagged.groupby("strategy_tag").agg(
        total_pnl=("realized_pnl", "sum"),
        num_trades=("realized_pnl", "count"),
        win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
        avg_pnl=("realized_pnl", "mean"),
    ).reset_index().sort_values("total_pnl", ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in by_tag["total_pnl"]]
        fig = go.Figure(go.Bar(
            x=by_tag["strategy_tag"], y=by_tag["total_pnl"],
            marker_color=colors,
            text=[f"${v:,.0f}" for v in by_tag["total_pnl"]],
            textposition="outside",
        ))
        fig.update_layout(height=300, xaxis_title="", yaxis_title="P&L ($)", title="P&L by Strategy")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.dataframe(by_tag.rename(columns={
            "strategy_tag": "Strategy", "total_pnl": "Total P&L",
            "num_trades": "Trades", "win_rate": "Win Rate %", "avg_pnl": "Avg P&L",
        }).set_index("Strategy").style.format({
            "Total P&L": "${:,.2f}", "Avg P&L": "${:,.2f}", "Win Rate %": "{:.1f}%",
        }), use_container_width=True)

    st.caption(f"{len(tagged)} of {len(df)} trades tagged. Tag more in the History page.")
    st.divider()

# =====================================================================
# 5. Best & Worst Symbols — top 10 winners/losers bar charts
# =====================================================================
ui_theme.section_header("Best & Worst Symbols")

by_symbol = df.groupby("symbol").agg(
    total_pnl=("realized_pnl", "sum"),
    num_trades=("realized_pnl", "count"),
    win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
    avg_pnl=("realized_pnl", "mean"),
    total_proceeds=("proceeds", "sum"),
).reset_index().sort_values("total_pnl", ascending=False)

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Best Symbols**")
    top = by_symbol.head(10)
    fig = px.bar(top, x="symbol", y="total_pnl", text_auto="$.2s",
                 color_discrete_sequence=["#2ecc71"])
    fig.update_layout(height=350, xaxis_title="", yaxis_title="P&L ($)")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown("**Worst Symbols**")
    bottom = by_symbol.tail(10).sort_values("total_pnl")
    fig = px.bar(bottom, x="symbol", y="total_pnl", text_auto="$.2s",
                 color_discrete_sequence=["#e74c3c"])
    fig.update_layout(height=350, xaxis_title="", yaxis_title="P&L ($)")
    st.plotly_chart(fig, use_container_width=True)

st.dataframe(
    by_symbol.rename(columns={
        "symbol": "Symbol", "total_pnl": "Total P&L", "num_trades": "Trades",
        "win_rate": "Win Rate %", "avg_pnl": "Avg P&L", "total_proceeds": "Volume",
    }).set_index("Symbol").style.format({
        "Total P&L": "${:,.2f}", "Avg P&L": "${:,.2f}",
        "Win Rate %": "{:.1f}%", "Volume": "${:,.0f}",
    }),
    use_container_width=True,
)

st.divider()

# =====================================================================
# 6. Day Trade vs Swing Trend — stacked bar by month
# =====================================================================
ui_theme.section_header("Day Trade vs Swing Trend")
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

st.divider()

# =====================================================================
# 7. Equity Curve & Drawdown
# =====================================================================
ui_theme.section_header("Equity Curve & Drawdown")
df_sorted = df.sort_values("trade_date")
df_sorted["cumulative_pnl"] = df_sorted["realized_pnl"].cumsum()
df_sorted["trade_num"] = range(1, len(df_sorted) + 1)

# Calculate drawdown from peak
df_sorted["peak"] = df_sorted["cumulative_pnl"].cummax()
df_sorted["drawdown"] = df_sorted["cumulative_pnl"] - df_sorted["peak"]

fig2 = go.Figure()
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
fig2.add_trace(go.Scatter(
    x=df_sorted["trade_num"], y=df_sorted["peak"],
    mode="lines", name="Peak",
    line=dict(color="#95a5a6", width=1, dash="dot"),
))
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
after_dd = df_sorted[df_sorted["trade_num"] >= max_dd_trade]
recovered = after_dd[after_dd["cumulative_pnl"] >= df_sorted.loc[max_dd_idx, "peak"]]
if not recovered.empty:
    recovery_trades = recovered.iloc[0]["trade_num"] - max_dd_trade
    col3.metric("Recovery (trades)", f"{int(recovery_trades)}")
else:
    col3.metric("Recovery", "Not yet")

st.divider()

# =====================================================================
# 8. Monthly Summary Table
# =====================================================================
ui_theme.section_header("Monthly Summary")

# Add avg holding days if available
has_days = df[df["holding_days"].notna()]
if not has_days.empty:
    hold = has_days.groupby(has_days["trade_date"].dt.to_period("M").astype(str)).agg(
        avg_hold=("holding_days", "mean"),
    ).reset_index().rename(columns={"trade_date": "month"})
    monthly = monthly.merge(hold, on="month", how="left")

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
