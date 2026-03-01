"""Paper Trading — Alpaca paper trade performance dashboard."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db import init_db
from alerting.paper_trader import (
    get_account_info,
    get_open_positions,
    get_paper_trade_stats,
    get_paper_trades_history,
    is_enabled,
    sync_open_trades,
)
import ui_theme

init_db()

st.set_page_config(page_title="Paper Trading | TradeSignal", page_icon="⚡", layout="wide")
ui_theme.inject_custom_css()

with st.sidebar:
    ui_theme.sidebar_branding()

ui_theme.page_header("Paper Trading", "Alpaca paper trade execution and P&L tracking")

if not is_enabled():
    st.warning(
        "Paper trading is not configured. Set the following in your `.env` file:\n\n"
        "```\n"
        "ALPACA_API_KEY=your-key\n"
        "ALPACA_SECRET_KEY=your-secret\n"
        "PAPER_TRADE_ENABLED=true\n"
        "PAPER_TRADE_POSITION_SIZE=50000\n"
        "```"
    )
    st.stop()

# Sync local DB with Alpaca before displaying
sync_open_trades()

# =====================================================================
# 1. Account Overview
# =====================================================================
ui_theme.section_header("Account Overview")

account = get_account_info()
if account:
    today_pnl = account["equity"] - account["last_equity"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Portfolio Value", f"${account['equity']:,.2f}")
    col2.metric("Cash", f"${account['cash']:,.2f}")
    col3.metric("Buying Power", f"${account['buying_power']:,.2f}")
    col4.metric("Today's P&L", f"${today_pnl:,.2f}",
                delta=f"{today_pnl:+,.2f}")
else:
    st.error("Could not fetch Alpaca account info. Check your API keys.")

st.divider()

# =====================================================================
# 2. Performance Summary
# =====================================================================
ui_theme.section_header("Performance Summary")

stats = get_paper_trade_stats()
if stats["total_trades"] > 0:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total P&L", f"${stats['total_pnl']:,.2f}")
    col2.metric("Win Rate", f"{stats['win_rate']:.1f}%")
    col3.metric("Total Trades", f"{stats['total_trades']}")
    col4.metric("Expectancy/Trade", f"${stats['expectancy']:,.2f}")

    col5, col6, col7 = st.columns(3)
    col5.metric("Avg Winner", f"${stats['avg_win']:,.2f}")
    col6.metric("Avg Loser", f"${stats['avg_loss']:,.2f}")
    col7.metric("Risk/Reward", f"{stats['risk_reward']:.2f}")
else:
    ui_theme.empty_state("No closed paper trades yet. Trades will appear once signals fire and positions close.")

st.divider()

# =====================================================================
# 3. Open Positions
# =====================================================================
ui_theme.section_header("Open Positions")

positions = get_open_positions()
if positions:
    df_pos = pd.DataFrame(positions)
    df_pos = df_pos.rename(columns={
        "symbol": "Symbol",
        "qty": "Shares",
        "avg_entry_price": "Avg Entry",
        "current_price": "Current Price",
        "market_value": "Market Value",
        "unrealized_pl": "Unrealized P&L",
        "unrealized_plpc": "P&L %",
    })
    st.dataframe(
        df_pos.set_index("Symbol").style.format({
            "Avg Entry": "${:,.2f}",
            "Current Price": "${:,.2f}",
            "Market Value": "${:,.2f}",
            "Unrealized P&L": "${:,.2f}",
            "P&L %": "{:+.2f}%",
        }),
        use_container_width=True,
    )
else:
    ui_theme.empty_state("No open positions.")

st.divider()

# =====================================================================
# 4. Closed Trades
# =====================================================================
ui_theme.section_header("Closed Trades")

history = get_paper_trades_history(limit=200)
if history:
    df = pd.DataFrame(history)

    # Equity curve
    df_sorted = df.sort_values("closed_at")
    df_sorted["cumulative_pnl"] = df_sorted["pnl"].cumsum()
    df_sorted["trade_num"] = range(1, len(df_sorted) + 1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_sorted["trade_num"], y=df_sorted["cumulative_pnl"],
        mode="lines+markers", name="Cumulative P&L",
        line=dict(color="#3498db", width=2),
        hovertemplate=(
            "Trade #%{x}<br>"
            "%{customdata[0]}<br>"
            "P&L: $%{customdata[1]:,.2f}<br>"
            "Cumulative: $%{y:,.2f}<extra></extra>"
        ),
        customdata=list(zip(df_sorted["symbol"], df_sorted["pnl"])),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(
        height=400,
        xaxis_title="Trade #",
        yaxis_title="Cumulative P&L ($)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Win/Loss distribution
    col1, col2 = st.columns(2)
    with col1:
        fig_dist = px.histogram(
            df_sorted, x="pnl", nbins=20,
            title="P&L Distribution",
            color_discrete_sequence=["#3498db"],
        )
        fig_dist.add_vline(x=0, line_dash="dash", line_color="red")
        fig_dist.update_layout(height=300, xaxis_title="P&L ($)", yaxis_title="Count")
        st.plotly_chart(fig_dist, use_container_width=True)

    with col2:
        win_count = len(df_sorted[df_sorted["pnl"] > 0])
        loss_count = len(df_sorted[df_sorted["pnl"] <= 0])
        fig_pie = px.pie(
            names=["Winners", "Losers"],
            values=[win_count, loss_count],
            color_discrete_sequence=["#2ecc71", "#e74c3c"],
            title="Win/Loss Ratio",
        )
        fig_pie.update_layout(height=300)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Trade history table
    st.markdown("**Trade History**")
    df_display = df_sorted[[
        "symbol", "shares", "entry_price", "exit_price",
        "stop_price", "target_price", "pnl", "status",
        "alert_type", "session_date",
    ]].copy()
    df_display = df_display.rename(columns={
        "symbol": "Symbol", "shares": "Shares",
        "entry_price": "Entry", "exit_price": "Exit",
        "stop_price": "Stop", "target_price": "Target",
        "pnl": "P&L", "status": "Status",
        "alert_type": "Signal", "session_date": "Date",
    })
    st.dataframe(
        df_display.set_index("Symbol").style.format({
            "Entry": "${:,.2f}", "Exit": "${:,.2f}",
            "Stop": "${:,.2f}", "Target": "${:,.2f}",
            "P&L": "${:,.2f}",
        }),
        use_container_width=True,
    )
else:
    ui_theme.empty_state("No closed trades yet.")
