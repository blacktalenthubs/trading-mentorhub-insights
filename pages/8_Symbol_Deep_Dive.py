"""Symbol Deep-Dive - All trades for a single ticker with full analysis."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from db import init_db, get_focus_account_trades, get_annotations

init_db()
st.title("Symbol Deep-Dive")
st.caption("Select a symbol to see all your trades and whether you should keep trading it")

df = get_focus_account_trades()
if df.empty:
    st.info("No trade data. Go to Import page to upload PDFs.")
    st.stop()

# --- Symbol selector ---
symbol_stats = df.groupby("symbol").agg(
    total_pnl=("realized_pnl", "sum"),
    num_trades=("realized_pnl", "count"),
).reset_index().sort_values("num_trades", ascending=False)

symbol_labels = [
    f"{row['symbol']} ({row['num_trades']} trades, ${row['total_pnl']:,.0f})"
    for _, row in symbol_stats.iterrows()
]
symbol_map = dict(zip(symbol_labels, symbol_stats["symbol"]))

selected_label = st.selectbox("Symbol", symbol_labels)
symbol = symbol_map[selected_label]

sym_df = df[df["symbol"] == symbol].copy().sort_values("trade_date")

if sym_df.empty:
    st.warning("No trades for this symbol.")
    st.stop()

# === KPIs ===
total_pnl = sym_df["realized_pnl"].sum()
num_trades = len(sym_df)
winners = sym_df[sym_df["realized_pnl"] > 0]
losers = sym_df[sym_df["realized_pnl"] < 0]
win_rate = len(winners) / num_trades * 100 if num_trades > 0 else 0
avg_win = winners["realized_pnl"].mean() if len(winners) > 0 else 0
avg_loss = losers["realized_pnl"].mean() if len(losers) > 0 else 0
risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
total_volume = sym_df["proceeds"].sum()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total P&L", f"${total_pnl:,.2f}")
col2.metric("Trades", f"{num_trades}")
col3.metric("Win Rate", f"{win_rate:.1f}%")
col4.metric("R:R Ratio", f"{risk_reward:.2f}")
col5.metric("Volume", f"${total_volume:,.0f}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Avg Win", f"${avg_win:,.2f}")
col2.metric("Avg Loss", f"${avg_loss:,.2f}")
avg_hold = sym_df["holding_days"].mean() if sym_df["holding_days"].notna().any() else 0
col3.metric("Avg Hold Days", f"{avg_hold:.1f}")
col4.metric("Category", sym_df["category"].iloc[0])

# Verdict
expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)
if total_pnl > 0 and win_rate >= 40:
    verdict = "KEEP TRADING - Profitable with decent win rate"
    verdict_color = "#2ecc71"
elif total_pnl > 0:
    verdict = "CAUTION - Profitable but low win rate, relies on big wins"
    verdict_color = "#f39c12"
elif num_trades >= 5 and win_rate < 30:
    verdict = "STOP - Multiple trades, low win rate, net loser"
    verdict_color = "#e74c3c"
elif total_pnl < -500:
    verdict = "STOP - Significant losses"
    verdict_color = "#e74c3c"
else:
    verdict = "REVIEW - Small sample or marginal results"
    verdict_color = "#95a5a6"

st.markdown(f"### Verdict: <span style='color:{verdict_color}'>{verdict}</span>",
            unsafe_allow_html=True)
st.caption(f"Expectancy per trade: ${expectancy:,.2f}")

st.divider()

# === Cumulative P&L Timeline ===
st.subheader("P&L Timeline")

sym_df["cumulative_pnl"] = sym_df["realized_pnl"].cumsum()
sym_df["trade_num"] = range(1, len(sym_df) + 1)

fig = go.Figure()
# P&L bars per trade
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
# Cumulative line
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

# === Entry/Exit Price Chart ===
st.subheader("Entry & Exit Prices")

sym_df["entry_price"] = sym_df["cost_basis"] / sym_df["quantity"].where(sym_df["quantity"] != 0, 1)
sym_df["exit_price"] = sym_df["proceeds"] / sym_df["quantity"].where(sym_df["quantity"] != 0, 1)

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=sym_df["trade_date"].dt.strftime("%Y-%m-%d"),
    y=sym_df["entry_price"],
    mode="markers+lines", name="Entry",
    marker=dict(color="#3498db", size=8, symbol="triangle-up"),
    line=dict(color="#3498db", width=1, dash="dot"),
))
fig.add_trace(go.Scatter(
    x=sym_df["trade_date"].dt.strftime("%Y-%m-%d"),
    y=sym_df["exit_price"],
    mode="markers+lines", name="Exit",
    marker=dict(color="#e67e22", size=8, symbol="triangle-down"),
    line=dict(color="#e67e22", width=1, dash="dot"),
))
# Color the area between entry and exit
for _, row in sym_df.iterrows():
    color = "rgba(46, 204, 113, 0.3)" if row["realized_pnl"] > 0 else "rgba(231, 76, 60, 0.3)"
    date_str = row["trade_date"].strftime("%Y-%m-%d")
    fig.add_shape(
        type="line", x0=date_str, x1=date_str,
        y0=row["entry_price"], y1=row["exit_price"],
        line=dict(color=color.replace("0.3", "0.8"), width=3),
    )

fig.update_layout(height=350, yaxis_title=f"{symbol} Price ($)")
st.plotly_chart(fig, use_container_width=True)

st.divider()

# === Holding Period Breakdown ===
st.subheader("By Holding Period")
has_period = sym_df[sym_df["holding_period_type"].notna() & (sym_df["holding_period_type"] != "unknown")]
if not has_period.empty:
    by_period = has_period.groupby("holding_period_type").agg(
        total_pnl=("realized_pnl", "sum"),
        num_trades=("realized_pnl", "count"),
        win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
    ).reset_index()

    st.dataframe(by_period.rename(columns={
        "holding_period_type": "Period", "total_pnl": "Total P&L",
        "num_trades": "Trades", "win_rate": "Win Rate %",
    }).set_index("Period").style.format({
        "Total P&L": "${:,.2f}", "Win Rate %": "{:.1f}%",
    }), use_container_width=True)

st.divider()

# === Full Trade Table ===
st.subheader("All Trades")

# Merge annotations
annotations = get_annotations()
display = sym_df[[
    "trade_date", "quantity", "cost_basis", "proceeds",
    "realized_pnl", "holding_days", "holding_period_type", "source",
]].copy()
display["entry_price"] = display["cost_basis"] / display["quantity"].where(display["quantity"] != 0, 1)
display["exit_price"] = display["proceeds"] / display["quantity"].where(display["quantity"] != 0, 1)
display["pnl_pct"] = (display["realized_pnl"] / display["cost_basis"] * 100).where(display["cost_basis"] != 0, 0)

if not annotations.empty:
    sym_ann = annotations[annotations["symbol"] == symbol]
    if not sym_ann.empty:
        display["trade_date_str"] = display["trade_date"].dt.strftime("%Y-%m-%d")
        display = display.merge(
            sym_ann[["trade_date", "quantity", "strategy_tag", "notes"]].rename(
                columns={"trade_date": "trade_date_str"}
            ),
            on=["trade_date_str", "quantity"],
            how="left",
        )
        display.drop(columns=["trade_date_str"], errors="ignore", inplace=True)

if "strategy_tag" not in display.columns:
    display["strategy_tag"] = None

display["trade_date"] = display["trade_date"].dt.strftime("%Y-%m-%d")

st.dataframe(
    display[["trade_date", "quantity", "entry_price", "exit_price", "realized_pnl",
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
