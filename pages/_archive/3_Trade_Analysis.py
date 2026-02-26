"""Trade Analysis - Filterable trade table by symbol, category, holding period."""

import streamlit as st
import pandas as pd
import plotly.express as px

from db import init_db, get_user_trades
from auth import auto_login

init_db()
user = auto_login()
st.title("Trade Analysis")

df = get_user_trades(user["id"])
if df.empty:
    st.info("No trade data. Go to Import page to upload PDFs.")
    st.stop()

# --- Filters ---
with st.sidebar:
    st.subheader("Filters")

    # Month filter
    all_months = sorted(df["trade_date"].dt.to_period("M").astype(str).unique().tolist())
    month_options = ["All Months"] + all_months
    selected_month = st.selectbox("Month", month_options)

    # Source filter
    source_options = ["All Sources"] + sorted(df["source"].unique().tolist())
    selected_source = st.selectbox("Source", source_options)

    asset_types = st.multiselect("Asset Type", df["asset_type"].unique().tolist(),
                                  default=df["asset_type"].unique().tolist())
    categories = st.multiselect("Category", df["category"].unique().tolist(),
                                 default=df["category"].unique().tolist())

mask = df["asset_type"].isin(asset_types) & df["category"].isin(categories)
if selected_month != "All Months":
    mask &= df["trade_date"].dt.to_period("M").astype(str) == selected_month
if selected_source != "All Sources":
    mask &= df["source"] == selected_source
filtered = df[mask]

# --- P&L by Symbol ---
st.subheader("P&L by Symbol")
by_symbol = filtered.groupby("symbol").agg(
    total_pnl=("realized_pnl", "sum"),
    num_trades=("realized_pnl", "count"),
    avg_pnl=("realized_pnl", "mean"),
    win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
).reset_index().sort_values("total_pnl", ascending=False)

fig = px.bar(by_symbol, x="symbol", y="total_pnl", text_auto="$.2s",
             color="total_pnl", color_continuous_scale=["#e74c3c", "#95a5a6", "#2ecc71"],
             color_continuous_midpoint=0)
fig.update_layout(height=400, xaxis_title="", yaxis_title="P&L ($)")
st.plotly_chart(fig, use_container_width=True)

# --- Full Trade Table ---
st.subheader("All Trades")
display = filtered[[
    "trade_date", "symbol", "asset_type", "category", "quantity",
    "cost_basis", "proceeds", "realized_pnl", "wash_sale_disallowed",
    "holding_days", "holding_period_type", "source",
]].copy()
display["trade_date"] = display["trade_date"].dt.strftime("%Y-%m-%d")
display = display.sort_values("trade_date", ascending=False)

st.dataframe(
    display.style.format({
        "cost_basis": "${:,.2f}", "proceeds": "${:,.2f}",
        "realized_pnl": "${:,.2f}", "wash_sale_disallowed": "${:,.2f}",
        "quantity": "{:,.1f}",
    }),
    use_container_width=True, height=500,
)
