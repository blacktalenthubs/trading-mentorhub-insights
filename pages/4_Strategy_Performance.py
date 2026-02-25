"""Strategy Performance - What's working: by symbol, hold period, category, consistency."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from db import init_db, get_focus_account_trades, get_annotations

init_db()
st.title("Strategy Performance")
st.caption("Which trades make money? Where do you lose?")

df = get_focus_account_trades()
if df.empty:
    st.info("No trade data. Go to Import page to upload PDFs.")
    st.stop()

# Merge strategy tags
annotations = get_annotations()
if not annotations.empty:
    df["trade_date_str"] = df["trade_date"].dt.strftime("%Y-%m-%d")
    df = df.merge(
        annotations[["source", "symbol", "trade_date", "quantity", "strategy_tag"]].rename(
            columns={"trade_date": "trade_date_str", "source": "ann_source"}
        ),
        left_on=["source", "symbol", "trade_date_str", "quantity"],
        right_on=["ann_source", "symbol", "trade_date_str", "quantity"],
        how="left",
    )
    df.drop(columns=["ann_source", "trade_date_str"], errors="ignore", inplace=True)
else:
    df["strategy_tag"] = None

# === STRATEGY TAG PERFORMANCE ===
tagged = df[df["strategy_tag"].notna()]
if not tagged.empty:
    st.subheader("Performance by Strategy Tag")
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

    st.caption(f"{len(tagged)} of {len(df)} trades tagged. Tag more trades in the Trade Journal page.")
    st.divider()
else:
    st.info("No trades tagged yet. Go to **Trade Journal** to add strategy tags "
            "(support_bounce, ma_bounce, key_level, etc.) and see which strategies work best.")
    st.divider()

# === KEY INSIGHT: Day Trade vs Swing ===
st.subheader("Day Trade vs Swing vs Position")

has_period = df[df["holding_period_type"].notna() & (df["holding_period_type"] != "unknown")]

if not has_period.empty:
    by_period = has_period.groupby("holding_period_type").agg(
        total_pnl=("realized_pnl", "sum"),
        num_trades=("realized_pnl", "count"),
        win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
        avg_win=("realized_pnl", lambda x: x[x > 0].mean() if (x > 0).any() else 0),
        avg_loss=("realized_pnl", lambda x: x[x < 0].mean() if (x < 0).any() else 0),
        avg_pnl=("realized_pnl", "mean"),
        total_proceeds=("proceeds", "sum"),
    ).reset_index()
    by_period["risk_reward"] = abs(by_period["avg_win"] / by_period["avg_loss"].where(by_period["avg_loss"] != 0, 1))

    order = ["day_trade", "swing", "position"]
    by_period["holding_period_type"] = pd.Categorical(
        by_period["holding_period_type"], categories=order, ordered=True
    )
    by_period = by_period.sort_values("holding_period_type").dropna(subset=["holding_period_type"])

    col1, col2, col3 = st.columns(3)
    for i, row in by_period.iterrows():
        col = [col1, col2, col3][list(by_period.index).index(i) % 3]
        label = str(row["holding_period_type"]).replace("_", " ").title()
        with col:
            st.markdown(f"### {label}")
            pnl_color = "normal" if row["total_pnl"] >= 0 else "inverse"
            st.metric("P&L", f"${row['total_pnl']:,.2f}", delta_color=pnl_color)
            st.metric("Win Rate", f"{row['win_rate']:.1f}%")
            st.metric("R:R Ratio", f"{row['risk_reward']:.2f}")
            st.metric("Trades", f"{row['num_trades']:.0f}")

    st.divider()

# === P&L BY SYMBOL ===
st.subheader("P&L by Symbol")

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

# === MEGA-CAP vs SPECULATIVE ===
st.subheader("Mega-Cap vs Speculative")

by_cat = df.groupby("category").agg(
    total_pnl=("realized_pnl", "sum"),
    num_trades=("realized_pnl", "count"),
    win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
    avg_pnl=("realized_pnl", "mean"),
).reset_index()

col1, col2 = st.columns(2)
with col1:
    colors_map = {"mega_cap": "#2ecc71", "speculative": "#e74c3c",
                  "index_etf": "#3498db", "other": "#95a5a6", "crypto": "#f39c12"}
    cat_colors = [colors_map.get(c, "#95a5a6") for c in by_cat["category"]]
    fig = go.Figure(go.Bar(
        x=by_cat["category"], y=by_cat["total_pnl"],
        marker_color=cat_colors,
        text=[f"${v:,.0f}" for v in by_cat["total_pnl"]],
        textposition="outside",
    ))
    fig.update_layout(height=350, xaxis_title="", yaxis_title="P&L ($)", title="P&L")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig = go.Figure(go.Bar(
        x=by_cat["category"], y=by_cat["win_rate"],
        marker_color=cat_colors,
        text=[f"{v:.1f}%" for v in by_cat["win_rate"]],
        textposition="outside",
    ))
    fig.add_hline(y=50, line_dash="dash", line_color="gray")
    fig.update_layout(height=350, xaxis_title="", yaxis_title="Win Rate %", title="Win Rate")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# === TRADE FREQUENCY vs P&L (Overtrading Detection) ===
st.subheader("Trade Frequency vs P&L (Overtrading Check)")

df["month"] = df["trade_date"].dt.to_period("M").astype(str)
monthly = df.groupby("month").agg(
    total_pnl=("realized_pnl", "sum"),
    num_trades=("realized_pnl", "count"),
    win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
).reset_index()

fig = px.scatter(monthly, x="num_trades", y="total_pnl",
                 text="month", size="num_trades",
                 labels={"num_trades": "# Trades in Month", "total_pnl": "Monthly P&L ($)"},
                 color_discrete_sequence=["#3498db"])
fig.add_hline(y=0, line_dash="dash", line_color="gray")
fig.update_traces(textposition="top center")
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

st.caption("Months with fewer, selective trades tend to perform better. "
           "Months with high trade counts may indicate overtrading.")

st.divider()

# === HOLDING DAYS DISTRIBUTION ===
st.subheader("Holding Days Distribution")
has_days = df[df["holding_days"].notna() & (df["holding_days"] >= 0)]
if not has_days.empty:
    fig = px.histogram(has_days, x="holding_days", color="realized_pnl",
                       color_continuous_scale=["#e74c3c", "#95a5a6", "#2ecc71"],
                       color_continuous_midpoint=0,
                       nbins=30,
                       labels={"holding_days": "Days Held", "realized_pnl": "P&L ($)"})
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)
