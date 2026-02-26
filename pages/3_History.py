"""Trade History — journal + analysis in tabs."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from config import STOP_LOSS_PCT, LOSS_ACCEPTABLE_PCT, LOSS_CAUTION_PCT
from db import (
    init_db, get_user_trades, get_annotations,
    upsert_annotation, STRATEGY_TAGS,
)
from auth import auto_login

init_db()
user = auto_login()
st.title("Trade History")
st.caption("Journal, calendar, stop discipline, and symbol lookup")

df = get_user_trades(user["id"])
if df.empty:
    st.info("No trade data. Go to **Import** page to upload PDFs.")
    st.stop()

# =====================================================================
# Sidebar Filters (shared across tabs)
# =====================================================================
with st.sidebar:
    st.subheader("Filters")

    all_months = sorted(df["trade_date"].dt.to_period("M").astype(str).unique().tolist())
    month_options = ["All Months"] + all_months
    selected_month = st.selectbox("Month", month_options)

    source_options = ["All Sources"] + sorted(df["source"].unique().tolist())
    selected_source = st.selectbox("Source", source_options)

    symbols = sorted(df["symbol"].unique().tolist())
    selected_symbols = st.multiselect("Symbols", symbols, default=symbols)

    period_opts = ["All", "day_trade", "swing", "position"]
    selected_period = st.selectbox("Holding Period", period_opts)

mask = df["symbol"].isin(selected_symbols)
if selected_month != "All Months":
    mask &= df["trade_date"].dt.to_period("M").astype(str) == selected_month
if selected_source != "All Sources":
    mask &= df["source"] == selected_source
if selected_period != "All":
    mask &= df["holding_period_type"] == selected_period
filtered = df[mask].copy().sort_values("trade_date")

if filtered.empty:
    st.warning("No trades match the current filters.")
    st.stop()

# =====================================================================
# Stop loss field computation (shared by Trade Log & Stop Discipline)
# =====================================================================
filtered["entry_price"] = filtered["cost_basis"] / filtered["quantity"].where(filtered["quantity"] != 0, 1)
filtered["exit_price"] = filtered["proceeds"] / filtered["quantity"].where(filtered["quantity"] != 0, 1)
filtered["pnl_pct"] = (filtered["realized_pnl"] / filtered["cost_basis"] * 100).where(filtered["cost_basis"] != 0, 0)

filtered["rec_stop_pct"] = filtered["holding_period_type"].map(STOP_LOSS_PCT).fillna(2.5)
filtered["rec_stop_price"] = filtered["entry_price"] * (1 - filtered["rec_stop_pct"] / 100)
filtered["max_loss_at_stop"] = -filtered["cost_basis"] * filtered["rec_stop_pct"] / 100
filtered["excess_loss"] = 0.0
loser_mask = filtered["realized_pnl"] < filtered["max_loss_at_stop"]
filtered.loc[loser_mask, "excess_loss"] = filtered.loc[loser_mask, "realized_pnl"] - filtered.loc[loser_mask, "max_loss_at_stop"]
filtered["pnl_with_stop"] = filtered["realized_pnl"].copy()
filtered.loc[loser_mask, "pnl_with_stop"] = filtered.loc[loser_mask, "max_loss_at_stop"]


def classify_loss(row):
    if row["realized_pnl"] >= 0:
        return "WIN"
    loss_pct = abs(row["pnl_pct"])
    if loss_pct <= LOSS_ACCEPTABLE_PCT:
        return "SMALL LOSS"
    elif loss_pct <= LOSS_CAUTION_PCT:
        return "CAUTION"
    else:
        return "DANGER"


filtered["loss_grade"] = filtered.apply(classify_loss, axis=1)

# Shared quick stats
winners = filtered[filtered["realized_pnl"] > 0]
losers = filtered[filtered["realized_pnl"] < 0]
avg_win = winners["realized_pnl"].mean() if len(winners) > 0 else 0
avg_loss = losers["realized_pnl"].mean() if len(losers) > 0 else 0
win_rate = len(winners) / len(filtered) * 100

# =====================================================================
# Tabs
# =====================================================================
tab_log, tab_cal, tab_stop, tab_sym = st.tabs([
    "Trade Log", "Calendar", "Stop Discipline", "Symbol Lookup",
])

# =====================================================================
# Tab 1: Trade Log
# =====================================================================
with tab_log:
    # Quick stats
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Trades", len(filtered))
    col2.metric("P&L", f"${filtered['realized_pnl'].sum():,.2f}")
    col3.metric("Win Rate", f"{win_rate:.1f}%")
    col4.metric("Avg Win", f"${avg_win:,.2f}")
    col5.metric("Avg Loss", f"${avg_loss:,.2f}")

    st.divider()

    # P&L by Symbol bar chart
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

    # Trade table
    st.subheader("Trade Log")
    st.caption("Rec Stop = recommended stop based on holding period. "
               "Excess Loss = how much you lost beyond that stop.")

    log = filtered[[
        "trade_date", "symbol", "category", "quantity",
        "entry_price", "exit_price", "realized_pnl", "pnl_pct",
        "rec_stop_pct", "rec_stop_price", "max_loss_at_stop", "excess_loss",
        "loss_grade", "holding_days", "holding_period_type", "source",
    ]].copy()

    # Merge annotations
    annotations = get_annotations(user["id"])
    if not annotations.empty:
        log["trade_date_str"] = log["trade_date"].dt.strftime("%Y-%m-%d")
        log = log.merge(
            annotations[["source", "symbol", "trade_date", "quantity", "strategy_tag", "notes"]].rename(
                columns={"trade_date": "trade_date_str", "source": "ann_source"}
            ),
            left_on=["source", "symbol", "trade_date_str", "quantity"],
            right_on=["ann_source", "symbol", "trade_date_str", "quantity"],
            how="left",
        )
        log.drop(columns=["ann_source", "trade_date_str"], errors="ignore", inplace=True)
    else:
        log["strategy_tag"] = None
        log["notes"] = None

    log["trade_date"] = log["trade_date"].dt.strftime("%Y-%m-%d")

    display_cols = [
        "trade_date", "symbol", "quantity",
        "entry_price", "exit_price", "rec_stop_price",
        "realized_pnl", "max_loss_at_stop", "excess_loss",
        "pnl_pct", "loss_grade",
        "holding_days", "holding_period_type", "strategy_tag",
    ]
    display_names = {
        "trade_date": "Date", "symbol": "Symbol", "quantity": "Qty",
        "entry_price": "Entry $", "exit_price": "Exit $", "rec_stop_price": "Rec Stop $",
        "realized_pnl": "P&L $", "max_loss_at_stop": "Max Loss @Stop",
        "excess_loss": "Excess Loss",
        "pnl_pct": "P&L %", "loss_grade": "Grade",
        "holding_days": "Days", "holding_period_type": "Period",
        "strategy_tag": "Strategy",
    }

    def color_grade(val):
        if val == "WIN":
            return "color: #2ecc71; font-weight: bold"
        elif val == "SMALL LOSS":
            return "color: #f39c12"
        elif val == "CAUTION":
            return "color: #e67e22; font-weight: bold"
        elif val == "DANGER":
            return "color: #e74c3c; font-weight: bold"
        return ""

    st.dataframe(
        log[display_cols].rename(columns=display_names).style.format({
            "Qty": "{:,.0f}",
            "Entry $": "${:,.2f}",
            "Exit $": "${:,.2f}",
            "Rec Stop $": "${:,.2f}",
            "P&L $": "${:,.2f}",
            "Max Loss @Stop": "${:,.2f}",
            "Excess Loss": "${:,.2f}",
            "P&L %": "{:+.2f}%",
        }).applymap(color_grade, subset=["Grade"]),
        use_container_width=True,
        height=500,
    )

    st.divider()

    # Trade tagging UI
    st.subheader("Tag a Trade")
    st.caption("Add strategy tags and notes to individual trades for tracking what works")

    tag_trades = filtered[["trade_date", "symbol", "quantity", "realized_pnl", "source"]].copy()
    tag_trades["label"] = (
        tag_trades["trade_date"].dt.strftime("%Y-%m-%d") + " | " +
        tag_trades["symbol"] + " | " +
        tag_trades["quantity"].apply(lambda x: f"{x:.0f} shares") + " | $" +
        tag_trades["realized_pnl"].apply(lambda x: f"{x:,.2f}")
    )
    trade_labels = tag_trades["label"].tolist()

    if trade_labels:
        selected_trade_label = st.selectbox("Select trade to tag", trade_labels, key="tag_select")
        idx = trade_labels.index(selected_trade_label)
        sel = tag_trades.iloc[idx]

        col1, col2 = st.columns(2)
        with col1:
            tag = st.selectbox("Strategy Tag", ["(none)"] + STRATEGY_TAGS, key="tag_strat")
        with col2:
            note = st.text_input("Note (optional)", key="tag_note")

        if st.button("Save Tag", key="tag_save"):
            upsert_annotation(
                source=sel["source"],
                symbol=sel["symbol"],
                trade_date=sel["trade_date"].strftime("%Y-%m-%d"),
                quantity=sel["quantity"],
                user_id=user["id"],
                strategy_tag=tag if tag != "(none)" else None,
                notes=note if note else None,
            )
            st.success(f"Tagged {sel['symbol']} {sel['trade_date'].strftime('%Y-%m-%d')}")
            st.rerun()

# =====================================================================
# Tab 2: Calendar
# =====================================================================
with tab_cal:
    st.subheader("Daily P&L Calendar")

    daily_pnl = filtered.groupby(filtered["trade_date"].dt.date).agg(
        pnl=("realized_pnl", "sum"),
        trades=("realized_pnl", "count"),
    ).reset_index()
    daily_pnl.columns = ["date", "pnl", "trades"]
    daily_pnl["date"] = pd.to_datetime(daily_pnl["date"])
    daily_pnl["day_of_week"] = daily_pnl["date"].dt.dayofweek
    daily_pnl["month_str"] = daily_pnl["date"].dt.strftime("%Y-%m")

    months_in_data = sorted(daily_pnl["month_str"].unique())
    for month_str in months_in_data:
        month_data = daily_pnl[daily_pnl["month_str"] == month_str].copy()
        if month_data.empty:
            continue

        first_day = pd.Timestamp(month_str + "-01")
        last_day = first_day + pd.offsets.MonthEnd(0)
        all_days = pd.date_range(first_day, last_day, freq="D")
        weekdays = all_days[all_days.dayofweek < 5]

        grid_data = pd.DataFrame({"date": weekdays})
        grid_data["day_of_week"] = grid_data["date"].dt.dayofweek
        grid_data["week_num"] = (grid_data["date"].dt.day - 1 + grid_data["date"].iloc[0].dayofweek) // 7
        grid_data = grid_data.merge(month_data[["date", "pnl", "trades"]], on="date", how="left")

        pivot = grid_data.pivot(index="day_of_week", columns="week_num", values="pnl")
        trades_pivot = grid_data.pivot(index="day_of_week", columns="week_num", values="trades")
        dates_pivot = grid_data.pivot(index="day_of_week", columns="week_num", values="date")

        hover_text = []
        for dow in pivot.index:
            row_text = []
            for wk in pivot.columns:
                d = dates_pivot.loc[dow, wk] if pd.notna(dates_pivot.loc[dow, wk]) else None
                p = pivot.loc[dow, wk]
                t = trades_pivot.loc[dow, wk]
                if d is not None and pd.notna(p):
                    row_text.append(f"{d.strftime('%b %d')}: ${p:,.0f} ({int(t)} trades)")
                elif d is not None:
                    row_text.append(f"{d.strftime('%b %d')}: no trades")
                else:
                    row_text.append("")
            hover_text.append(row_text)

        max_abs = max(abs(month_data["pnl"].min()), abs(month_data["pnl"].max()), 1)

        fig = go.Figure(go.Heatmap(
            z=pivot.values,
            x=[f"Wk {c+1}" for c in pivot.columns],
            y=["Mon", "Tue", "Wed", "Thu", "Fri"],
            text=hover_text, hoverinfo="text",
            colorscale=[[0, "#e74c3c"], [0.5, "#f5f5f5"], [1, "#2ecc71"]],
            zmid=0, zmin=-max_abs, zmax=max_abs, showscale=False,
        ))
        for i, dow in enumerate(pivot.index):
            for j, wk in enumerate(pivot.columns):
                val = pivot.loc[dow, wk]
                if pd.notna(val):
                    fig.add_annotation(
                        x=f"Wk {wk+1}", y=["Mon", "Tue", "Wed", "Thu", "Fri"][i],
                        text=f"${val:,.0f}", showarrow=False,
                        font=dict(size=10, color="black"),
                    )

        fig.update_layout(
            title=f"{pd.Timestamp(month_str + '-01').strftime('%B %Y')}",
            height=200, margin=dict(l=50, r=20, t=40, b=20),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)

# =====================================================================
# Tab 3: Stop Discipline
# =====================================================================
with tab_stop:
    st.header("Stop Loss Lab")
    st.caption("Analyzing the cost of not using stops and what disciplined stops would do for your P&L")

    all_losers = filtered[filtered["realized_pnl"] < 0].copy()
    blown_stops = filtered[filtered["excess_loss"] < 0].copy()

    # Key metrics
    actual_total_pnl = filtered["realized_pnl"].sum()
    pnl_with_stops = filtered["pnl_with_stop"].sum()
    total_excess_loss = blown_stops["excess_loss"].sum()
    num_blown = len(blown_stops)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Actual P&L", f"${actual_total_pnl:,.2f}")
    col2.metric("P&L with Stops", f"${pnl_with_stops:,.2f}",
                delta=f"${pnl_with_stops - actual_total_pnl:,.2f}")
    col3.metric("Excess Loss (No Stops)", f"${total_excess_loss:,.2f}")
    col4.metric("Trades that Blew Stop", f"{num_blown} of {len(all_losers)} losers")

    st.divider()

    # Loss Severity Breakdown
    st.subheader("Loss Severity Breakdown")
    st.caption("SMALL LOSS = disciplined exit (<2%). CAUTION = held too long (2-5%). "
               "DANGER = no stop, big damage (>5%).")

    grade_counts = filtered["loss_grade"].value_counts()
    grade_pnl = filtered.groupby("loss_grade")["realized_pnl"].sum()

    col1, col2 = st.columns(2)
    grade_colors = {"WIN": "#2ecc71", "SMALL LOSS": "#f39c12", "CAUTION": "#e67e22", "DANGER": "#e74c3c"}
    with col1:
        grade_df = pd.DataFrame({
            "Grade": grade_counts.index,
            "Count": grade_counts.values,
        })
        fig = go.Figure(go.Bar(
            x=grade_df["Grade"], y=grade_df["Count"],
            marker_color=[grade_colors.get(g, "#95a5a6") for g in grade_df["Grade"]],
            text=grade_df["Count"], textposition="outside",
        ))
        fig.update_layout(height=300, xaxis_title="", yaxis_title="# Trades", title="Trade Count by Grade")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        grade_pnl_df = grade_pnl.reset_index()
        grade_pnl_df.columns = ["Grade", "P&L"]
        fig = go.Figure(go.Bar(
            x=grade_pnl_df["Grade"], y=grade_pnl_df["P&L"],
            marker_color=[grade_colors.get(g, "#95a5a6") for g in grade_pnl_df["Grade"]],
            text=[f"${v:,.0f}" for v in grade_pnl_df["P&L"]], textposition="outside",
        ))
        fig.update_layout(height=300, xaxis_title="", yaxis_title="P&L ($)", title="P&L Impact by Grade")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # What-If Scenarios
    st.subheader("What-If: P&L at Different Stop Levels")
    st.caption("If you had enforced a stop at each % level, what would your total P&L be?")

    scenarios = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    scenario_results = []

    for stop_pct in scenarios:
        max_loss_per_trade = -filtered["cost_basis"] * stop_pct / 100
        capped_pnl = filtered["realized_pnl"].copy()
        blow_mask = filtered["realized_pnl"] < max_loss_per_trade
        capped_pnl[blow_mask] = max_loss_per_trade[blow_mask]
        total = capped_pnl.sum()
        trades_saved = blow_mask.sum()
        money_saved = total - actual_total_pnl
        scenario_results.append({
            "Stop %": f"{stop_pct}%",
            "Total P&L": total,
            "vs Actual": money_saved,
            "Trades Saved": trades_saved,
        })

    scenario_df = pd.DataFrame(scenario_results)

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=scenario_df["Stop %"], y=scenario_df["Total P&L"],
            marker_color=["#2ecc71" if v >= 0 else "#e74c3c" for v in scenario_df["Total P&L"]],
            text=[f"${v:,.0f}" for v in scenario_df["Total P&L"]],
            textposition="outside", name="P&L with Stop",
        ))
        fig.add_hline(y=actual_total_pnl, line_dash="dash", line_color="#3498db",
                      annotation_text=f"Actual: ${actual_total_pnl:,.0f}")
        fig.update_layout(height=350, xaxis_title="Stop Loss %", yaxis_title="Total P&L ($)",
                          title="Total P&L at Each Stop Level")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.dataframe(
            scenario_df.style.format({
                "Total P&L": "${:,.2f}",
                "vs Actual": "${:+,.2f}",
                "Trades Saved": "{:.0f}",
            }),
            use_container_width=True,
        )

    st.divider()

    # Worst Offenders
    st.subheader("Worst Offenders - Biggest Excess Losses")
    st.caption("These trades blew past the recommended stop. This is where your money went.")

    if not blown_stops.empty:
        worst = blown_stops.nsmallest(15, "excess_loss")[[
            "trade_date", "symbol", "quantity", "entry_price", "exit_price",
            "rec_stop_price", "realized_pnl", "max_loss_at_stop", "excess_loss",
            "pnl_pct", "holding_period_type",
        ]].copy()
        worst["trade_date"] = worst["trade_date"].dt.strftime("%Y-%m-%d")

        st.dataframe(
            worst.rename(columns={
                "trade_date": "Date", "symbol": "Symbol", "quantity": "Qty",
                "entry_price": "Entry $", "exit_price": "Exit $",
                "rec_stop_price": "Stop Should Be", "realized_pnl": "Actual P&L",
                "max_loss_at_stop": "Max Loss @Stop", "excess_loss": "Excess Loss",
                "pnl_pct": "Loss %", "holding_period_type": "Period",
            }).style.format({
                "Qty": "{:,.0f}", "Entry $": "${:,.2f}", "Exit $": "${:,.2f}",
                "Stop Should Be": "${:,.2f}", "Actual P&L": "${:,.2f}",
                "Max Loss @Stop": "${:,.2f}", "Excess Loss": "${:,.2f}",
                "Loss %": "{:+.1f}%",
            }),
            use_container_width=True,
        )

        fig = go.Figure(go.Bar(
            x=worst["Date"].astype(str) + " " + worst["Symbol"],
            y=worst["Excess Loss"],
            marker_color="#e74c3c",
            text=[f"${v:,.0f}" for v in worst["Excess Loss"]],
            textposition="outside",
        ))
        fig.update_layout(height=350, xaxis_title="", yaxis_title="Excess Loss ($)",
                          title="Money Left on Table (No Stop)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("All losing trades were within stop limits!")

    st.divider()

    # Pre-Trade Risk Calculator
    st.subheader("Pre-Trade Risk Calculator")
    st.caption("Enter your position and see exactly how much you're risking at each stop level.")

    calc_col1, calc_col2 = st.columns(2)
    with calc_col1:
        position_amount = st.number_input(
            "Position Amount ($)", value=63000.0, step=1000.0,
            help="Total $ you're putting into this trade",
            key="risk_pos",
        )
    with calc_col2:
        entry_price_input = st.number_input(
            "Entry Price ($)", value=635.0, step=1.0,
            help="Your buy price per share",
            key="risk_entry",
        )

    if entry_price_input > 0 and position_amount > 0:
        shares = position_amount / entry_price_input

        stop_levels = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
        risk_rows = []
        for sp in stop_levels:
            stop_px = entry_price_input * (1 - sp / 100)
            loss_per_share = entry_price_input * sp / 100
            total_loss = shares * loss_per_share
            risk_rows.append({
                "Stop %": f"{sp}%",
                "Stop Price": stop_px,
                "Loss/Share": loss_per_share,
                "Total $ Risk": total_loss,
            })
        risk_df = pd.DataFrame(risk_rows)

        col1, col2, col3 = st.columns(3)
        col1.metric("Shares", f"{shares:,.0f}")
        col2.metric("Position", f"${position_amount:,.0f}")
        col3.metric("Entry", f"${entry_price_input:,.2f}")

        col1, col2 = st.columns([3, 2])
        with col1:
            st.dataframe(
                risk_df.style.format({
                    "Stop Price": "${:,.2f}",
                    "Loss/Share": "${:,.2f}",
                    "Total $ Risk": "${:,.2f}",
                }).applymap(
                    lambda v: "background-color: #2ecc7133" if isinstance(v, str) and v in ("0.5%", "1.0%")
                    else "background-color: #f39c1233" if isinstance(v, str) and v in ("2.0%", "2.5%")
                    else "background-color: #e74c3c33" if isinstance(v, str) and v in ("4.0%", "5.0%")
                    else "",
                    subset=["Stop %"],
                ),
                use_container_width=True,
            )

        with col2:
            fig = go.Figure(go.Bar(
                x=[r["Stop %"] for r in risk_rows],
                y=[r["Total $ Risk"] for r in risk_rows],
                marker_color=["#2ecc71", "#2ecc71", "#2ecc71", "#27ae60",
                              "#f39c12", "#e67e22", "#e67e22",
                              "#e74c3c", "#e74c3c", "#c0392b"],
                text=[f"${r['Total $ Risk']:,.0f}" for r in risk_rows],
                textposition="outside",
            ))
            fig.update_layout(height=350, xaxis_title="Stop %", yaxis_title="$ at Risk",
                              title="Risk by Stop Level", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Quick Risk Check:**")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("0.5% Stop", f"-${position_amount * 0.005:,.0f}",
                  delta=f"Stop @ ${entry_price_input * 0.995:,.2f}", delta_color="off")
        q2.metric("1% Stop", f"-${position_amount * 0.01:,.0f}",
                  delta=f"Stop @ ${entry_price_input * 0.99:,.2f}", delta_color="off")
        q3.metric("2% Stop", f"-${position_amount * 0.02:,.0f}",
                  delta=f"Stop @ ${entry_price_input * 0.98:,.2f}", delta_color="off")
        q4.metric("3% Stop", f"-${position_amount * 0.03:,.0f}",
                  delta=f"Stop @ ${entry_price_input * 0.97:,.2f}", delta_color="off")

# =====================================================================
# Tab 4: Symbol Lookup
# =====================================================================
with tab_sym:
    st.subheader("Symbol Deep-Dive")
    st.caption("Select a symbol to see all your trades and whether you should keep trading it")

    # Symbol selector
    symbol_stats = df.groupby("symbol").agg(
        total_pnl=("realized_pnl", "sum"),
        num_trades=("realized_pnl", "count"),
    ).reset_index().sort_values("num_trades", ascending=False)

    symbol_labels = [
        f"{row['symbol']} ({row['num_trades']} trades, ${row['total_pnl']:,.0f})"
        for _, row in symbol_stats.iterrows()
    ]
    symbol_map = dict(zip(symbol_labels, symbol_stats["symbol"]))

    selected_label = st.selectbox("Symbol", symbol_labels, key="sym_lookup")
    symbol = symbol_map[selected_label]

    sym_df = df[df["symbol"] == symbol].copy().sort_values("trade_date")

    if sym_df.empty:
        st.warning("No trades for this symbol.")
    else:
        # KPIs
        s_total_pnl = sym_df["realized_pnl"].sum()
        s_num_trades = len(sym_df)
        s_winners = sym_df[sym_df["realized_pnl"] > 0]
        s_losers = sym_df[sym_df["realized_pnl"] < 0]
        s_win_rate = len(s_winners) / s_num_trades * 100 if s_num_trades > 0 else 0
        s_avg_win = s_winners["realized_pnl"].mean() if len(s_winners) > 0 else 0
        s_avg_loss = s_losers["realized_pnl"].mean() if len(s_losers) > 0 else 0
        s_risk_reward = abs(s_avg_win / s_avg_loss) if s_avg_loss != 0 else 0
        s_total_volume = sym_df["proceeds"].sum()

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total P&L", f"${s_total_pnl:,.2f}")
        col2.metric("Trades", f"{s_num_trades}")
        col3.metric("Win Rate", f"{s_win_rate:.1f}%")
        col4.metric("R:R Ratio", f"{s_risk_reward:.2f}")
        col5.metric("Volume", f"${s_total_volume:,.0f}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Avg Win", f"${s_avg_win:,.2f}")
        col2.metric("Avg Loss", f"${s_avg_loss:,.2f}")
        s_avg_hold = sym_df["holding_days"].mean() if sym_df["holding_days"].notna().any() else 0
        col3.metric("Avg Hold Days", f"{s_avg_hold:.1f}")
        col4.metric("Category", sym_df["category"].iloc[0])

        # Verdict
        s_expectancy = (s_win_rate / 100 * s_avg_win) + ((1 - s_win_rate / 100) * s_avg_loss)
        if s_total_pnl > 0 and s_win_rate >= 40:
            verdict = "KEEP TRADING - Profitable with decent win rate"
            verdict_color = "#2ecc71"
        elif s_total_pnl > 0:
            verdict = "CAUTION - Profitable but low win rate, relies on big wins"
            verdict_color = "#f39c12"
        elif s_num_trades >= 5 and s_win_rate < 30:
            verdict = "STOP - Multiple trades, low win rate, net loser"
            verdict_color = "#e74c3c"
        elif s_total_pnl < -500:
            verdict = "STOP - Significant losses"
            verdict_color = "#e74c3c"
        else:
            verdict = "REVIEW - Small sample or marginal results"
            verdict_color = "#95a5a6"

        st.markdown(f"### Verdict: <span style='color:{verdict_color}'>{verdict}</span>",
                    unsafe_allow_html=True)
        st.caption(f"Expectancy per trade: ${s_expectancy:,.2f}")

        st.divider()

        # P&L Timeline
        st.subheader("P&L Timeline")
        sym_df["cumulative_pnl"] = sym_df["realized_pnl"].cumsum()

        fig = go.Figure()
        colors = ["#2ecc71" if v > 0 else "#e74c3c" for v in sym_df["realized_pnl"]]
        fig.add_trace(go.Bar(
            x=sym_df["trade_date"].dt.strftime("%Y-%m-%d"),
            y=sym_df["realized_pnl"],
            marker_color=colors,
            name="Trade P&L",
            text=[f"${v:,.0f}" for v in sym_df["realized_pnl"]],
            textposition="outside",
            hovertemplate="%{x}<br>P&L: $%{y:,.2f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=sym_df["trade_date"].dt.strftime("%Y-%m-%d"),
            y=sym_df["cumulative_pnl"],
            mode="lines+markers", name="Cumulative",
            yaxis="y2", line=dict(color="#3498db", width=2),
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(
            height=400,
            yaxis=dict(title="Trade P&L ($)"),
            yaxis2=dict(title="Cumulative P&L ($)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # Full Trade Table
        st.subheader("All Trades")

        sym_annotations = get_annotations(user["id"])
        s_display = sym_df[[
            "trade_date", "quantity", "cost_basis", "proceeds",
            "realized_pnl", "holding_days", "holding_period_type", "source",
        ]].copy()
        s_display["entry_price"] = s_display["cost_basis"] / s_display["quantity"].where(s_display["quantity"] != 0, 1)
        s_display["exit_price"] = s_display["proceeds"] / s_display["quantity"].where(s_display["quantity"] != 0, 1)
        s_display["pnl_pct"] = (s_display["realized_pnl"] / s_display["cost_basis"] * 100).where(s_display["cost_basis"] != 0, 0)

        if not sym_annotations.empty:
            sym_ann = sym_annotations[sym_annotations["symbol"] == symbol]
            if not sym_ann.empty:
                s_display["trade_date_str"] = s_display["trade_date"].dt.strftime("%Y-%m-%d")
                s_display = s_display.merge(
                    sym_ann[["trade_date", "quantity", "strategy_tag", "notes"]].rename(
                        columns={"trade_date": "trade_date_str"}
                    ),
                    on=["trade_date_str", "quantity"],
                    how="left",
                )
                s_display.drop(columns=["trade_date_str"], errors="ignore", inplace=True)

        if "strategy_tag" not in s_display.columns:
            s_display["strategy_tag"] = None

        s_display["trade_date"] = s_display["trade_date"].dt.strftime("%Y-%m-%d")

        st.dataframe(
            s_display[["trade_date", "quantity", "entry_price", "exit_price", "realized_pnl",
                        "pnl_pct", "holding_days", "holding_period_type", "strategy_tag", "source"]
            ].rename(columns={
                "trade_date": "Date", "quantity": "Qty", "entry_price": "Entry $",
                "exit_price": "Exit $", "realized_pnl": "P&L $", "pnl_pct": "P&L %",
                "holding_days": "Days", "holding_period_type": "Period",
                "strategy_tag": "Strategy", "source": "Source",
            }).style.format({
                "Qty": "{:,.0f}", "Entry $": "${:,.2f}", "Exit $": "${:,.2f}",
                "P&L $": "${:,.2f}", "P&L %": "{:+.2f}%",
            }),
            use_container_width=True,
        )
