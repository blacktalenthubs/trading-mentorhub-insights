"""Real Trades — Track real trades tied to alerts with P&L dashboard."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db import init_db
from analytics.intraday_data import fetch_intraday
from alerting.real_trade_store import (
    close_real_trade,
    get_closed_trades,
    get_open_trades,
    get_real_trade_stats,
    stop_real_trade,
    update_trade_notes,
)
import ui_theme

init_db()

st.set_page_config(page_title="Real Trades | TradeSignal", page_icon="⚡", layout="wide")
ui_theme.inject_custom_css()

with st.sidebar:
    ui_theme.sidebar_branding()

ui_theme.page_header("Real Trades", "Track real trades tied to alerts — $50k cap ($100k SPY)")

# =====================================================================
# 1. Performance Summary
# =====================================================================
ui_theme.section_header("Performance Summary")

stats = get_real_trade_stats()
if stats["total_trades"] > 0:
    col1, col2, col3 = st.columns(3)
    pnl_color = "normal" if stats["total_pnl"] >= 0 else "inverse"
    col1.metric("Total P&L", f"${stats['total_pnl']:,.2f}",
                delta=f"${stats['total_pnl']:+,.2f}", delta_color=pnl_color)
    col2.metric("Win Rate", f"{stats['win_rate']:.1f}%")
    col3.metric("Total Trades", f"{stats['total_trades']}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Expectancy/Trade", f"${stats['expectancy']:,.2f}")
    col5.metric("Avg Winner", f"${stats['avg_win']:,.2f}")
    col6.metric("Avg Loser", f"${stats['avg_loss']:,.2f}")
else:
    ui_theme.empty_state("No closed real trades yet. Use 'Took It' on the home page to start tracking.")

st.divider()

# =====================================================================
# 2. Open Positions
# =====================================================================
ui_theme.section_header("Open Positions")

positions = get_open_trades()
if positions:
    for pos in positions:
        sym = pos["symbol"]
        shares = pos["shares"]
        entry = pos["entry_price"]
        stop = pos["stop_price"]
        t1 = pos["target_price"]
        direction = pos["direction"]

        # Fetch live price
        intra = fetch_intraday(sym)
        current = intra["Close"].iloc[-1] if not intra.empty else entry

        if direction == "SHORT":
            unrealized = (entry - current) * shares
        else:
            unrealized = (current - entry) * shares
        pnl_pct = (unrealized / (entry * shares) * 100) if entry * shares > 0 else 0

        pnl_color = "#2ecc71" if unrealized >= 0 else "#e74c3c"
        st.markdown(
            f"**{sym}** — {direction} {shares} shares @ ${entry:,.2f} | "
            f"Now: ${current:,.2f} | "
            f"<span style='color:{pnl_color}'>${unrealized:+,.2f} ({pnl_pct:+.2f}%)</span>",
            unsafe_allow_html=True,
        )

        with st.expander(f"Manage {sym} (ID: {pos['id']})"):
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Entry", f"${entry:,.2f}")
            mc2.metric("Current", f"${current:,.2f}")
            if stop:
                mc3.metric("Stop", f"${stop:,.2f}")
            if t1:
                mc4.metric("Target", f"${t1:,.2f}")

            # Close at custom price
            close_col, stop_col = st.columns(2)
            with close_col:
                exit_price = st.number_input(
                    "Exit Price", value=current, step=0.01,
                    key=f"exit_{pos['id']}",
                )
                close_notes = st.text_input("Notes", key=f"notes_close_{pos['id']}")
                if st.button("Close Trade", key=f"close_{pos['id']}"):
                    pnl = close_real_trade(pos["id"], exit_price, close_notes)
                    st.toast(f"Closed {sym} — P&L: ${pnl:+,.2f}")
                    st.rerun()

            with stop_col:
                stop_exit = st.number_input(
                    "Stop Exit Price", value=stop or current, step=0.01,
                    key=f"stop_exit_{pos['id']}",
                )
                stop_notes = st.text_input("Notes", key=f"notes_stop_{pos['id']}")
                if st.button("Stopped Out", key=f"stopped_{pos['id']}"):
                    pnl = stop_real_trade(pos["id"], stop_exit, stop_notes)
                    st.toast(f"Stopped {sym} — P&L: ${pnl:+,.2f}")
                    st.rerun()

            # Edit notes on open trade
            cur_notes = pos.get("notes", "") or ""
            new_notes = st.text_area("Journal", value=cur_notes, key=f"journal_{pos['id']}")
            if new_notes != cur_notes:
                if st.button("Save Notes", key=f"save_notes_{pos['id']}"):
                    update_trade_notes(pos["id"], new_notes)
                    st.toast("Notes saved")
                    st.rerun()
else:
    ui_theme.empty_state("No open positions.")

st.divider()

# =====================================================================
# 3. Closed Trades
# =====================================================================
ui_theme.section_header("Closed Trades")

history = get_closed_trades(limit=200)
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
        title="Equity Curve",
    )
    st.plotly_chart(fig, use_container_width=True)

    # P&L distribution + Win/Loss pie
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
        "symbol", "direction", "shares", "entry_price", "exit_price",
        "pnl", "status", "alert_type", "session_date", "notes",
    ]].copy()
    df_display = df_display.rename(columns={
        "symbol": "Symbol", "direction": "Direction", "shares": "Shares",
        "entry_price": "Entry", "exit_price": "Exit",
        "pnl": "P&L", "status": "Status",
        "alert_type": "Signal", "session_date": "Date", "notes": "Notes",
    })
    st.dataframe(
        df_display.set_index("Symbol").style.format({
            "Entry": "${:,.2f}", "Exit": "${:,.2f}", "P&L": "${:,.2f}",
        }),
        use_container_width=True,
    )
else:
    ui_theme.empty_state("No closed trades yet.")
