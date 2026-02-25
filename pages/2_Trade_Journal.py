"""Trade Journal - Entry/exit/P&L, stop loss analysis, calendar heatmap, streaks."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

from config import STOP_LOSS_PCT, LOSS_ACCEPTABLE_PCT, LOSS_CAUTION_PCT
from db import (
    init_db, get_focus_account_trades, get_annotations,
    upsert_annotation, STRATEGY_TAGS,
)

init_db()
st.title("Trade Journal")
st.caption("Every trade: entry, exit, P&L, stop loss recommendations")

df = get_focus_account_trades()
if df.empty:
    st.info("No trade data. Go to Import page to upload PDFs.")
    st.stop()

# --- Filters ---
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

# --- Compute stop loss fields for all filtered trades ---
filtered["entry_price"] = filtered["cost_basis"] / filtered["quantity"].where(filtered["quantity"] != 0, 1)
filtered["exit_price"] = filtered["proceeds"] / filtered["quantity"].where(filtered["quantity"] != 0, 1)
filtered["pnl_pct"] = (filtered["realized_pnl"] / filtered["cost_basis"] * 100).where(filtered["cost_basis"] != 0, 0)

# Recommended stop % based on holding period
filtered["rec_stop_pct"] = filtered["holding_period_type"].map(STOP_LOSS_PCT).fillna(2.5)
# Recommended stop price
filtered["rec_stop_price"] = filtered["entry_price"] * (1 - filtered["rec_stop_pct"] / 100)
# Max loss if stop was hit
filtered["max_loss_at_stop"] = -filtered["cost_basis"] * filtered["rec_stop_pct"] / 100
# Excess loss = how much more you lost beyond the stop (only for losers)
filtered["excess_loss"] = 0.0
loser_mask = filtered["realized_pnl"] < filtered["max_loss_at_stop"]
filtered.loc[loser_mask, "excess_loss"] = filtered.loc[loser_mask, "realized_pnl"] - filtered.loc[loser_mask, "max_loss_at_stop"]
# What P&L would have been with the stop
filtered["pnl_with_stop"] = filtered["realized_pnl"].copy()
filtered.loc[loser_mask, "pnl_with_stop"] = filtered.loc[loser_mask, "max_loss_at_stop"]

# Loss severity
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

# --- Quick Stats ---
winners = filtered[filtered["realized_pnl"] > 0]
losers = filtered[filtered["realized_pnl"] < 0]
avg_win = winners["realized_pnl"].mean() if len(winners) > 0 else 0
avg_loss = losers["realized_pnl"].mean() if len(losers) > 0 else 0
win_rate = len(winners) / len(filtered) * 100

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Trades", len(filtered))
col2.metric("P&L", f"${filtered['realized_pnl'].sum():,.2f}")
col3.metric("Win Rate", f"{win_rate:.1f}%")
col4.metric("Avg Win", f"${avg_win:,.2f}")
col5.metric("Avg Loss", f"${avg_loss:,.2f}")

st.divider()

# === DAILY P&L CALENDAR HEATMAP ===
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

st.divider()

# === TRADE LOG TABLE (with stop loss columns) ===
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
annotations = get_annotations()
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


def color_excess(val):
    try:
        if float(val.replace("$", "").replace(",", "")) < -10:
            return "color: #e74c3c; font-weight: bold"
    except (ValueError, AttributeError):
        pass
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

# ============================================================
# === STOP LOSS LAB ===
# ============================================================
st.header("Stop Loss Lab")
st.caption("Analyzing the cost of not using stops and what disciplined stops would do for your P&L")

all_losers = filtered[filtered["realized_pnl"] < 0].copy()
blown_stops = filtered[filtered["excess_loss"] < 0].copy()

# --- Key metrics ---
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

# --- Loss Severity Breakdown ---
st.subheader("Loss Severity Breakdown")
st.caption("SMALL LOSS = disciplined exit (<2%). CAUTION = held too long (2-5%). "
           "DANGER = no stop, big damage (>5%).")

grade_counts = filtered["loss_grade"].value_counts()
grade_pnl = filtered.groupby("loss_grade")["realized_pnl"].sum()

col1, col2 = st.columns(2)
with col1:
    grade_df = pd.DataFrame({
        "Grade": grade_counts.index,
        "Count": grade_counts.values,
    })
    grade_colors = {"WIN": "#2ecc71", "SMALL LOSS": "#f39c12", "CAUTION": "#e67e22", "DANGER": "#e74c3c"}
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

# --- What-If Scenarios ---
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

# --- Worst Offenders (biggest excess losses) ---
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

    # Bar chart of excess losses
    fig = go.Figure(go.Bar(
        x=worst["trade_date"].astype(str) + " " + worst["symbol"],
        y=worst["excess_loss"],
        marker_color="#e74c3c",
        text=[f"${v:,.0f}" for v in worst["excess_loss"]],
        textposition="outside",
    ))
    fig.update_layout(height=350, xaxis_title="", yaxis_title="Excess Loss ($)",
                      title="Money Left on Table (No Stop)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.success("All losing trades were within stop limits!")

st.divider()

# --- Per-Symbol Stop Analysis ---
st.subheader("Stop Discipline by Symbol")
st.caption("Which symbols burn you worst when you don't stop out?")

sym_stop = filtered[filtered["realized_pnl"] < 0].groupby("symbol").agg(
    num_losses=("realized_pnl", "count"),
    total_loss=("realized_pnl", "sum"),
    total_excess=("excess_loss", "sum"),
    avg_loss_pct=("pnl_pct", "mean"),
    worst_loss=("realized_pnl", "min"),
    num_danger=("loss_grade", lambda x: (x == "DANGER").sum()),
).reset_index().sort_values("total_excess")

if not sym_stop.empty:
    col1, col2 = st.columns(2)
    with col1:
        top_offenders = sym_stop.head(10)
        fig = go.Figure(go.Bar(
            x=top_offenders["symbol"],
            y=top_offenders["total_excess"],
            marker_color="#e74c3c",
            text=[f"${v:,.0f}" for v in top_offenders["total_excess"]],
            textposition="outside",
        ))
        fig.update_layout(height=350, xaxis_title="", yaxis_title="Excess Loss ($)",
                          title="Symbols with Most Excess Loss")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.dataframe(
            sym_stop.rename(columns={
                "symbol": "Symbol", "num_losses": "# Losses",
                "total_loss": "Total Loss", "total_excess": "Excess Loss",
                "avg_loss_pct": "Avg Loss %", "worst_loss": "Worst Trade",
                "num_danger": "DANGER Trades",
            }).set_index("Symbol").style.format({
                "Total Loss": "${:,.2f}", "Excess Loss": "${:,.2f}",
                "Avg Loss %": "{:.1f}%", "Worst Trade": "${:,.2f}",
            }),
            use_container_width=True,
        )

st.divider()

# === MARCH TRADING PLAN ===
st.header("Next Month Trading Plan")
st.caption("Recommendations based on your trading data to improve stop discipline")

# Calculate data-driven recommendations
avg_trade_size = filtered["cost_basis"].mean()
avg_winning_trade = avg_win
median_trade_size = filtered["cost_basis"].median()

st.markdown("### Recommended Stop Levels")

rec_data = []
for period, stop_pct in STOP_LOSS_PCT.items():
    if period == "unknown":
        continue
    period_trades = filtered[filtered["holding_period_type"] == period]
    if period_trades.empty:
        continue
    avg_entry = period_trades["entry_price"].mean()
    avg_qty = period_trades["quantity"].mean()
    avg_size = period_trades["cost_basis"].mean()
    stop_price_ex = avg_entry * (1 - stop_pct / 100)
    max_loss = avg_size * stop_pct / 100
    rec_data.append({
        "Trade Type": period.replace("_", " ").title(),
        "Stop %": f"{stop_pct}%",
        "Avg Entry": avg_entry,
        "Stop Price Example": stop_price_ex,
        "Max $ Loss": max_loss,
        "Avg Position Size": avg_size,
        "Avg Shares": avg_qty,
    })

if rec_data:
    rec_df = pd.DataFrame(rec_data)
    st.dataframe(
        rec_df.style.format({
            "Avg Entry": "${:,.2f}",
            "Stop Price Example": "${:,.2f}",
            "Max $ Loss": "${:,.2f}",
            "Avg Position Size": "${:,.0f}",
            "Avg Shares": "{:,.0f}",
        }),
        use_container_width=True,
    )

# === PRE-TRADE RISK CALCULATOR ===
st.markdown("### Pre-Trade Risk Calculator")
st.caption("Enter your position and see exactly how much you're risking at each stop level. "
           "Know your risk BEFORE you enter.")

calc_col1, calc_col2 = st.columns(2)
with calc_col1:
    position_amount = st.number_input(
        "Position Amount ($)", value=63000.0, step=1000.0,
        help="Total $ you're putting into this trade (e.g., $150K for SPY, $63K for META)",
    )
with calc_col2:
    entry_price_input = st.number_input(
        "Entry Price ($)", value=635.0, step=1.0,
        help="Your buy price per share",
    )

if entry_price_input > 0 and position_amount > 0:
    shares = position_amount / entry_price_input

    # Show risk at every stop level
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

    # Quick summary metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Shares", f"{shares:,.0f}")
    col2.metric("Position", f"${position_amount:,.0f}")
    # Highlight the 1% and 2% risk
    risk_1pct = position_amount * 0.01
    risk_2pct = position_amount * 0.02
    col3.metric("Entry", f"${entry_price_input:,.2f}")

    # Risk table
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

    # Quick-reference for common setups
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

    # Context: how does this compare to your actual data?
    st.markdown("---")
    st.markdown("**Reality check from your data:**")
    avg_actual_loss = abs(avg_loss) if avg_loss != 0 else 0
    st.markdown(
        f"- Your average losing trade loses **${avg_actual_loss:,.2f}**\n"
        f"- At 1% stop on ${position_amount:,.0f}, you'd risk **${position_amount * 0.01:,.2f}** "
        f"{'(within your avg loss)' if position_amount * 0.01 <= avg_actual_loss else '(more than your avg loss — tighten stop or reduce size)'}\n"
        f"- At 2% stop on ${position_amount:,.0f}, you'd risk **${position_amount * 0.02:,.2f}** "
        f"{'— that is a big hit, keep stops tight on large positions' if position_amount * 0.02 > 500 else ''}"
    )

st.divider()

# === DAILY RISK BUDGET ===
st.markdown("### Daily Risk Budget")
st.caption("If you take multiple trades per day, know your total exposure")

budget_col1, budget_col2 = st.columns(2)
with budget_col1:
    daily_max_loss = st.number_input("Max daily loss ($)", value=500.0, step=100.0,
                                      help="Stop trading for the day if you hit this")
with budget_col2:
    trades_per_day = st.number_input("Planned trades today", value=3, step=1, min_value=1)

if daily_max_loss > 0 and trades_per_day > 0:
    risk_per_trade = daily_max_loss / trades_per_day
    st.markdown(f"""
| | |
|---|---|
| **Daily max loss** | ${daily_max_loss:,.0f} |
| **Trades planned** | {trades_per_day} |
| **Risk budget per trade** | **${risk_per_trade:,.0f}** |
| **If you lose trade 1** | Budget left: ${daily_max_loss - risk_per_trade:,.0f} for {trades_per_day - 1} more |
| **If you lose 2 in a row** | {'STOP for the day' if trades_per_day <= 3 else f'Budget left: ${daily_max_loss - 2*risk_per_trade:,.0f}'} |
""")

st.divider()

# Rules summary
st.markdown("### Rules for March")
danger_count = (filtered["loss_grade"] == "DANGER").sum()
caution_count = (filtered["loss_grade"] == "CAUTION").sum()
total_danger_loss = filtered[filtered["loss_grade"] == "DANGER"]["realized_pnl"].sum()

# Find best performing period
period_pnl = filtered.groupby("holding_period_type")["realized_pnl"].sum()
best_period = period_pnl.idxmax() if not period_pnl.empty else "swing"

st.markdown(f"""
**Based on your data:**

1. **Always set a stop.** You had **{danger_count} DANGER trades** that cost you **${total_danger_loss:,.2f}**.
   With stops, your P&L would be **${pnl_with_stops:,.2f}** instead of ${actual_total_pnl:,.2f}.

2. **Use {STOP_LOSS_PCT.get(best_period, 2.5)}% stops for {best_period.replace('_', ' ')} trades** — your most profitable style
   ({best_period.replace('_', ' ')} P&L: ${period_pnl.get(best_period, 0):,.2f}).

3. **Before every trade, use the calculator above.** Enter your position size,
   see the risk at each stop %. If the risk is too high, either tighten the stop or reduce shares.

4. **{caution_count} trades were in CAUTION zone** (2-5% loss). Review if these could have
   been stopped earlier at support levels.

5. **Set a daily loss limit.** After 2 consecutive losses, walk away. Revenge trading
   compounds drawdowns.

6. **Pre-set stops at order entry.** Don't decide in the moment — set the stop when you buy.
""")

st.divider()

# === TAG TRADES ===
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
    selected_trade_label = st.selectbox("Select trade to tag", trade_labels)
    idx = trade_labels.index(selected_trade_label)
    sel = tag_trades.iloc[idx]

    col1, col2 = st.columns(2)
    with col1:
        tag = st.selectbox("Strategy Tag", ["(none)"] + STRATEGY_TAGS)
    with col2:
        note = st.text_input("Note (optional)")

    if st.button("Save Tag"):
        upsert_annotation(
            source=sel["source"],
            symbol=sel["symbol"],
            trade_date=sel["trade_date"].strftime("%Y-%m-%d"),
            quantity=sel["quantity"],
            strategy_tag=tag if tag != "(none)" else None,
            notes=note if note else None,
        )
        st.success(f"Tagged {sel['symbol']} {sel['trade_date'].strftime('%Y-%m-%d')}")
        st.rerun()

st.divider()

# === WIN/LOSS STREAKS ===
st.subheader("Win/Loss Streaks")

results = filtered.sort_values("trade_date")["realized_pnl"].values
streaks = []
current_streak = 0
current_type = None

for pnl in results:
    if pnl > 0:
        if current_type == "W":
            current_streak += 1
        else:
            if current_streak != 0:
                streaks.append((current_type, current_streak))
            current_streak = 1
            current_type = "W"
    elif pnl < 0:
        if current_type == "L":
            current_streak += 1
        else:
            if current_streak != 0:
                streaks.append((current_type, current_streak))
            current_streak = 1
            current_type = "L"
if current_streak != 0:
    streaks.append((current_type, current_streak))

if streaks:
    max_win_streak = max((s for t, s in streaks if t == "W"), default=0)
    max_loss_streak = max((s for t, s in streaks if t == "L"), default=0)
    avg_win_streak = np.mean([s for t, s in streaks if t == "W"]) if any(t == "W" for t, s in streaks) else 0
    avg_loss_streak = np.mean([s for t, s in streaks if t == "L"]) if any(t == "L" for t, s in streaks) else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Max Win Streak", max_win_streak)
    col2.metric("Max Loss Streak", max_loss_streak)
    col3.metric("Avg Win Streak", f"{avg_win_streak:.1f}")
    col4.metric("Avg Loss Streak", f"{avg_loss_streak:.1f}")

    streak_colors = []
    streak_vals = []
    for t, s in streaks:
        streak_vals.append(s if t == "W" else -s)
        streak_colors.append("#2ecc71" if t == "W" else "#e74c3c")

    fig = go.Figure(go.Bar(
        x=list(range(1, len(streak_vals) + 1)),
        y=streak_vals,
        marker_color=streak_colors,
    ))
    fig.update_layout(
        height=250, xaxis_title="Streak #", yaxis_title="Streak Length (+ win, - loss)",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# === RUNNING P&L ===
st.subheader("Running P&L (Trade by Trade)")

running = filtered.sort_values("trade_date").copy()
running["cumulative_pnl"] = running["realized_pnl"].cumsum()
running["cumulative_with_stops"] = running["pnl_with_stop"].cumsum()
running["trade_num"] = range(1, len(running) + 1)

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=running["trade_num"], y=running["cumulative_pnl"],
    mode="lines", line=dict(color="#e74c3c", width=2),
    name="Actual P&L",
))
fig.add_trace(go.Scatter(
    x=running["trade_num"], y=running["cumulative_with_stops"],
    mode="lines", line=dict(color="#2ecc71", width=2, dash="dash"),
    name="P&L with Stops",
))
fig.add_hline(y=0, line_dash="dash", line_color="gray")
fig.update_layout(height=350, xaxis_title="Trade #", yaxis_title="Cumulative P&L ($)",
                  legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

st.divider()

# === DAY OF WEEK ANALYSIS ===
st.subheader("Performance by Day of Week")

filtered_dow = filtered.copy()
filtered_dow["day_of_week"] = filtered_dow["trade_date"].dt.day_name()
dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

by_dow = filtered_dow.groupby("day_of_week").agg(
    total_pnl=("realized_pnl", "sum"),
    num_trades=("realized_pnl", "count"),
    win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
    avg_pnl=("realized_pnl", "mean"),
).reindex(dow_order).dropna().reset_index()

col1, col2 = st.columns(2)
with col1:
    colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in by_dow["total_pnl"]]
    fig = go.Figure(go.Bar(
        x=by_dow["day_of_week"], y=by_dow["total_pnl"],
        marker_color=colors,
        text=[f"${v:,.0f}" for v in by_dow["total_pnl"]],
        textposition="outside",
    ))
    fig.update_layout(height=300, xaxis_title="", yaxis_title="P&L ($)", title="P&L by Day")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.dataframe(by_dow.rename(columns={
        "day_of_week": "Day", "total_pnl": "Total P&L",
        "num_trades": "Trades", "win_rate": "Win Rate %", "avg_pnl": "Avg P&L",
    }).set_index("Day").style.format({
        "Total P&L": "${:,.2f}", "Avg P&L": "${:,.2f}", "Win Rate %": "{:.1f}%",
    }), use_container_width=True)

st.divider()

# === TRADE SIZE vs OUTCOME ===
st.subheader("Trade Size vs Outcome")
fig = px.scatter(filtered, x="proceeds", y="realized_pnl",
                 color="loss_grade",
                 hover_data=["symbol", "trade_date"],
                 labels={"proceeds": "Trade Size ($)", "realized_pnl": "P&L ($)",
                          "loss_grade": "Grade"},
                 color_discrete_map={
                     "WIN": "#2ecc71", "SMALL LOSS": "#f39c12",
                     "CAUTION": "#e67e22", "DANGER": "#e74c3c",
                 })
fig.add_hline(y=0, line_dash="dash", line_color="gray")
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)
