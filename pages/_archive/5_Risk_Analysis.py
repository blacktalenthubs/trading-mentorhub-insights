"""Risk Analysis - Wash sales, concentration, biggest wins/losses."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db import init_db, get_user_trades
from auth import auto_login
from analytics.wash_sale import detect_wash_sales, get_wash_sale_timeline

init_db()
user = auto_login()
st.title("Risk Analysis")

df = get_user_trades(user["id"])
if df.empty:
    st.info("No trade data. Go to Import page to upload PDFs.")
    st.stop()

# === Wash Sales ===
st.subheader("Wash Sale Exposure")

wash_df = df.rename(columns={})  # already has trade_date
wash_summary = detect_wash_sales(df)
wash_timeline = get_wash_sale_timeline(df)

total_wash = df["wash_sale_disallowed"].sum()
num_wash = (df["wash_sale_disallowed"] > 0).sum()

col1, col2, col3 = st.columns(3)
col1.metric("Total Wash Sale Disallowed", f"${total_wash:,.2f}")
col2.metric("Trades with Wash Sales", f"{num_wash}")
col3.metric("% of Trades Affected", f"{num_wash/len(df)*100:.1f}%")

col1, col2 = st.columns(2)
with col1:
    if not wash_summary.empty:
        st.markdown("**Wash Sales by Symbol**")
        fig = px.bar(wash_summary.head(15), x="symbol", y="total_wash_disallowed",
                     text_auto="$.2s", color_discrete_sequence=["#e74c3c"])
        fig.update_layout(height=400, xaxis_title="", yaxis_title="Wash Sale ($)")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    if not wash_timeline.empty:
        st.markdown("**Wash Sales Over Time**")
        fig = px.bar(wash_timeline, x="month", y="wash_amount",
                     text_auto="$.2s", color_discrete_sequence=["#c0392b"])
        fig.update_layout(height=400, xaxis_title="", yaxis_title="Wash Sale ($)")
        st.plotly_chart(fig, use_container_width=True)

if not wash_summary.empty:
    st.dataframe(wash_summary.rename(columns={
        "symbol": "Symbol", "total_wash_disallowed": "Total Disallowed",
        "num_wash_trades": "# Wash Trades",
        "first_wash_date": "First Date", "last_wash_date": "Last Date",
    }).style.format({"Total Disallowed": "${:,.2f}"}), use_container_width=True)

st.divider()

# === Position Concentration ===
st.subheader("Trading Volume Concentration")

by_symbol = df.groupby("symbol").agg(
    total_proceeds=("proceeds", "sum"),
    num_trades=("realized_pnl", "count"),
).reset_index().sort_values("total_proceeds", ascending=False)

fig = px.pie(by_symbol.head(10), values="total_proceeds", names="symbol",
             title="Top 10 by Trading Volume")
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# === Biggest Wins & Losses ===
st.subheader("Biggest Trades")
col1, col2 = st.columns(2)

with col1:
    st.markdown("**Top 10 Winners**")
    top_wins = df.nlargest(10, "realized_pnl")[
        ["trade_date", "symbol", "quantity", "cost_basis", "proceeds", "realized_pnl", "holding_days"]
    ].copy()
    top_wins["entry"] = top_wins["cost_basis"] / top_wins["quantity"].where(top_wins["quantity"] != 0, 1)
    top_wins["exit"] = top_wins["proceeds"] / top_wins["quantity"].where(top_wins["quantity"] != 0, 1)
    top_wins["trade_date"] = top_wins["trade_date"].dt.strftime("%Y-%m-%d")
    st.dataframe(top_wins[["trade_date", "symbol", "entry", "exit", "realized_pnl", "holding_days"]].rename(
        columns={"trade_date": "Date", "symbol": "Symbol", "entry": "Entry $",
                 "exit": "Exit $", "realized_pnl": "P&L $", "holding_days": "Days"}
    ).style.format({
        "Entry $": "${:,.2f}", "Exit $": "${:,.2f}", "P&L $": "${:,.2f}",
    }), use_container_width=True)

with col2:
    st.markdown("**Top 10 Losers**")
    top_losses = df.nsmallest(10, "realized_pnl")[
        ["trade_date", "symbol", "quantity", "cost_basis", "proceeds", "realized_pnl", "holding_days"]
    ].copy()
    top_losses["entry"] = top_losses["cost_basis"] / top_losses["quantity"].where(top_losses["quantity"] != 0, 1)
    top_losses["exit"] = top_losses["proceeds"] / top_losses["quantity"].where(top_losses["quantity"] != 0, 1)
    top_losses["trade_date"] = top_losses["trade_date"].dt.strftime("%Y-%m-%d")
    st.dataframe(top_losses[["trade_date", "symbol", "entry", "exit", "realized_pnl", "holding_days"]].rename(
        columns={"trade_date": "Date", "symbol": "Symbol", "entry": "Entry $",
                 "exit": "Exit $", "realized_pnl": "P&L $", "holding_days": "Days"}
    ).style.format({
        "Entry $": "${:,.2f}", "Exit $": "${:,.2f}", "P&L $": "${:,.2f}",
    }), use_container_width=True)

st.divider()

# === P&L Distribution ===
st.subheader("P&L Distribution")
fig = px.histogram(df, x="realized_pnl", nbins=50,
                   labels={"realized_pnl": "P&L per Trade ($)"},
                   color_discrete_sequence=["#3498db"])
fig.add_vline(x=0, line_dash="dash", line_color="red")
fig.update_layout(height=350)
st.plotly_chart(fig, use_container_width=True)
