"""Performance — consolidated scorecard, active trades, journal, and options."""

import io

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from config import STOP_LOSS_PCT, LOSS_ACCEPTABLE_PCT, LOSS_CAUTION_PCT
from db import (
    get_user_trades,
    get_user_options,
    get_annotations,
    upsert_annotation,
    STRATEGY_TAGS,
    get_db,
    _pd_read_sql,
)
from alerting.paper_trader import (
    get_account_info,
    get_open_positions,
    get_paper_trade_stats,
    get_paper_trades_history,
    is_enabled as paper_is_enabled,
    sync_open_trades,
)
from alerting.real_trade_store import (
    close_real_trade,
    get_closed_trades,
    get_open_trades,
    get_real_trade_stats,
    stop_real_trade,
    update_trade_notes,
)
from alerting.options_trade_store import (
    close_options_trade,
    expire_options_trade,
    get_closed_options_trades,
    get_open_options_trades,
    get_options_trade_stats,
    update_options_trade_notes,
)
from analytics.intraday_data import fetch_intraday
import ui_theme
from ui_theme import get_current_tier, render_inline_upgrade

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
user = ui_theme.setup_page("performance", tier_required="pro", tier_preview="free")
_is_free = get_current_tier() == "free"

ui_theme.page_header("Performance", "Scorecard, active trades, journal, and options")

tab_overview, tab_active, tab_journal, tab_options = st.tabs([
    "Overview", "Active Trades", "Journal", "Options",
])

# =========================================================================
# TAB 1: Overview (from Scorecard)
# =========================================================================
with tab_overview:
    df_imported = get_user_trades(user["id"])
    if df_imported.empty:
        ui_theme.empty_state("No trade data. Go to Import page to upload PDFs.")
    else:
        # ── KPIs via shared helper ──────────────────────────────────
        stats = ui_theme.compute_trade_stats(df_imported, pnl_col="realized_pnl")
        ui_theme.render_kpi_row(stats)

        # Options P&L callout
        opts = get_user_options(user["id"])
        if not opts.empty:
            opt_pnl = opts["realized_pnl"].sum()
            st.info(f"Options P&L: **${opt_pnl:,.2f}** across {len(opts)} trades (excluded from analysis).")

        st.divider()

        # Free tier: show KPIs only, gate the rest
        if _is_free:
            render_inline_upgrade(
                "Full scorecard -- monthly charts, equity curve, drawdown analysis, strategy breakdown",
                "pro",
            )
        else:
            # ── Precompute monthly aggregates ───────────────────────
            df_imported["month"] = df_imported["trade_date"].dt.to_period("M").astype(str)

            monthly = df_imported.groupby("month").agg(
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
            period_mix = df_imported.groupby(["month", "holding_period_type"]).size().unstack(fill_value=0)
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

            monthly["risk_reward"] = abs(
                monthly["avg_win"] / monthly["avg_loss"].where(monthly["avg_loss"] != 0, 1)
            )

            # ── P&L Trend ──────────────────────────────────────────
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

            # ── Win Rate & R:R Trend ───────────────────────────────
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

            # ── Strategy Performance ───────────────────────────────
            annotations = get_annotations(user["id"])
            if not annotations.empty:
                df_tagged = df_imported.copy()
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
                df_tagged = df_imported.copy()
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
                    fig.update_layout(height=300, xaxis_title="", yaxis_title="P&L ($)",
                                      title="P&L by Strategy")
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    st.dataframe(by_tag.rename(columns={
                        "strategy_tag": "Strategy", "total_pnl": "Total P&L",
                        "num_trades": "Trades", "win_rate": "Win Rate %",
                        "avg_pnl": "Avg P&L",
                    }).set_index("Strategy").style.format({
                        "Total P&L": "${:,.2f}", "Avg P&L": "${:,.2f}",
                        "Win Rate %": "{:.1f}%",
                    }), use_container_width=True)

                st.caption(
                    f"{len(tagged)} of {len(df_imported)} trades tagged. "
                    "Tag more in the Journal tab."
                )
                st.divider()

            # ── Best & Worst Symbols ───────────────────────────────
            ui_theme.section_header("Best & Worst Symbols")

            by_symbol = df_imported.groupby("symbol").agg(
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
                    "win_rate": "Win Rate %", "avg_pnl": "Avg P&L",
                    "total_proceeds": "Volume",
                }).set_index("Symbol").style.format({
                    "Total P&L": "${:,.2f}", "Avg P&L": "${:,.2f}",
                    "Win Rate %": "{:.1f}%", "Volume": "${:,.0f}",
                }),
                use_container_width=True,
            )

            st.divider()

            # ── Day Trade vs Swing Trend ───────────────────────────
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

            # ── Equity Curve & Drawdown (shared helper) ────────────
            ui_theme.section_header("Equity Curve & Drawdown")
            ui_theme.render_equity_curve(
                df_imported,
                pnl_col="realized_pnl",
                sort_col="trade_date",
                show_drawdown=True,
            )

            st.divider()

            # ── Monthly Summary Table ──────────────────────────────
            ui_theme.section_header("Monthly Summary")

            has_days = df_imported[df_imported["holding_days"].notna()]
            if not has_days.empty:
                hold = has_days.groupby(
                    has_days["trade_date"].dt.to_period("M").astype(str)
                ).agg(avg_hold=("holding_days", "mean")).reset_index().rename(
                    columns={"trade_date": "month"}
                )
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
                disp[list(disp_cols.keys())].rename(columns=disp_cols)
                .set_index("Month").style.format(fmt),
                use_container_width=True,
            )


# =========================================================================
# TAB 2: Active Trades (Paper Trading + Real Trades)
# =========================================================================
with tab_active:
    if _is_free:
        render_inline_upgrade(
            "Active trade tracking -- paper & real positions, P&L, AI position checks",
            "pro",
        )
    else:
        # ── Sub-tabs for Paper vs Real ─────────────────────────────
        sub_paper, sub_real, sub_closed = st.tabs(["Paper Positions", "Real Positions", "Closed Trades"])

        # ────────────────────────────────────────────────────────────
        # Paper Positions
        # ────────────────────────────────────────────────────────────
        with sub_paper:
            if not paper_is_enabled():
                st.warning(
                    "Paper trading is not configured. Set the following in your `.env` file:\n\n"
                    "```\n"
                    "ALPACA_API_KEY=your-key\n"
                    "ALPACA_SECRET_KEY=your-secret\n"
                    "PAPER_TRADE_ENABLED=true\n"
                    "PAPER_TRADE_POSITION_SIZE=50000\n"
                    "```"
                )
            else:
                # Sync local DB with Alpaca
                sync_open_trades()

                # Account Overview
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

                # Performance Summary
                ui_theme.section_header("Performance Summary")
                paper_stats = get_paper_trade_stats()
                if paper_stats["total_trades"] > 0:
                    ui_theme.render_kpi_row(paper_stats)
                else:
                    ui_theme.empty_state(
                        "No closed paper trades yet. "
                        "Trades will appear once patterns are detected and positions close."
                    )

                st.divider()

                # Open Positions
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
                        df_pos.set_index("Symbol").style.format(
                            {
                                "Avg Entry": "${:,.2f}",
                                "Current Price": "${:,.2f}",
                                "Market Value": "${:,.2f}",
                                "Unrealized P&L": "${:,.2f}",
                                "P&L %": "{:+.2f}%",
                            },
                            na_rep="---",
                        ),
                        use_container_width=True,
                    )

                    # AI Position Check
                    if st.button("AI Position Check", key="perf_paper_ai_check"):
                        with st.spinner("Analyzing paper positions..."):
                            from analytics.position_advisor import check_positions_stream
                            paper_trades = []
                            for p in positions:
                                paper_trades.append({
                                    "symbol": p["symbol"],
                                    "direction": "BUY",
                                    "shares": p["qty"],
                                    "entry_price": p["avg_entry_price"],
                                    "current_price": p["current_price"],
                                    "stop_price": None,
                                    "target_price": None,
                                    "_paper": True,
                                })
                            response_box = st.empty()
                            full_text = ""
                            for chunk in check_positions_stream(paper_trades):
                                full_text += chunk
                                response_box.text(full_text)
                else:
                    ui_theme.empty_state("No open positions.")

                st.divider()

                # AI EOD Review
                with st.expander("AI EOD Review"):
                    if st.button("Generate EOD Review", key="perf_paper_eod_review"):
                        with st.spinner("Building EOD review..."):
                            from analytics.eod_review import build_eod_review
                            review = build_eod_review()
                            if review:
                                st.text(review)
                            else:
                                st.info(
                                    "No review available -- either no alerts today "
                                    "or no API key configured."
                                )

        # ────────────────────────────────────────────────────────────
        # Real Positions
        # ────────────────────────────────────────────────────────────
        with sub_real:
            # Trade type filter
            real_filter = st.radio(
                "Trade Type", ["All", "Intraday", "Swing"],
                horizontal=True, key="perf_real_filter",
            )
            type_param = {"All": None, "Intraday": "intraday", "Swing": "swing"}[real_filter]

            # Performance Summary
            ui_theme.section_header("Performance Summary")
            real_stats = get_real_trade_stats(trade_type=type_param)
            if real_stats["total_trades"] > 0:
                col1, col2, col3 = st.columns(3)
                pnl_color = "normal" if real_stats["total_pnl"] >= 0 else "inverse"
                col1.metric("Total P&L", f"${real_stats['total_pnl']:,.2f}",
                            delta=f"${real_stats['total_pnl']:+,.2f}",
                            delta_color=pnl_color)
                col2.metric("Win Rate", f"{real_stats['win_rate']:.1f}%")
                col3.metric("Total Trades", f"{real_stats['total_trades']}")

                col4, col5, col6 = st.columns(3)
                col4.metric("Expectancy/Trade", f"${real_stats['expectancy']:,.2f}")
                col5.metric("Avg Winner", f"${real_stats['avg_win']:,.2f}")
                col6.metric("Avg Loser", f"${real_stats['avg_loss']:,.2f}")
            else:
                ui_theme.empty_state(
                    "No closed trades yet. Use 'Track This' on the Dashboard to start tracking setups."
                )

            # Options summary when viewing All
            if real_filter == "All":
                _opt_stats = get_options_trade_stats()
                if _opt_stats["total_trades"] > 0:
                    st.markdown("---")
                    st.markdown(
                        "<span style='color:#9b59b6;font-weight:bold'>Options Summary</span>",
                        unsafe_allow_html=True,
                    )
                    oc1, oc2, oc3 = st.columns(3)
                    _opnl_color = "normal" if _opt_stats["total_pnl"] >= 0 else "inverse"
                    oc1.metric("Options P&L", f"${_opt_stats['total_pnl']:,.2f}",
                               delta=f"${_opt_stats['total_pnl']:+,.2f}",
                               delta_color=_opnl_color)
                    oc2.metric("Options Win Rate", f"{_opt_stats['win_rate']:.1f}%")
                    oc3.metric("Options Trades", f"{_opt_stats['total_trades']}")

            st.divider()

            # Open Positions
            ui_theme.section_header("Open Positions")
            real_positions = get_open_trades(trade_type=type_param)
            if real_positions:
                for pos in real_positions:
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
                    pnl_pct = (
                        (unrealized / (entry * shares) * 100)
                        if entry * shares > 0 else 0
                    )

                    pnl_color_str = "#2ecc71" if unrealized >= 0 else "#e74c3c"
                    st.markdown(
                        f"**{sym}** -- {direction} {shares} shares @ ${entry:,.2f} | "
                        f"Now: ${current:,.2f} | "
                        f"<span style='color:{pnl_color_str}'>"
                        f"${unrealized:+,.2f} ({pnl_pct:+.2f}%)</span>",
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

                        close_col, stop_col = st.columns(2)
                        with close_col:
                            exit_price = st.number_input(
                                "Exit Price", value=current, step=0.01,
                                key=f"perf_exit_{pos['id']}",
                            )
                            close_notes = st.text_input(
                                "Notes", key=f"perf_notes_close_{pos['id']}"
                            )
                            if st.button("Close Trade", key=f"perf_close_{pos['id']}"):
                                pnl = close_real_trade(pos["id"], exit_price, close_notes)
                                st.toast(f"Closed {sym} -- P&L: ${pnl:+,.2f}")
                                st.rerun()

                        with stop_col:
                            stop_exit = st.number_input(
                                "Stop Exit Price",
                                value=stop or current,
                                step=0.01,
                                key=f"perf_stop_exit_{pos['id']}",
                            )
                            stop_notes = st.text_input(
                                "Notes", key=f"perf_notes_stop_{pos['id']}"
                            )
                            if st.button("Stopped Out", key=f"perf_stopped_{pos['id']}"):
                                pnl = stop_real_trade(pos["id"], stop_exit, stop_notes)
                                st.toast(f"Stopped {sym} -- P&L: ${pnl:+,.2f}")
                                st.rerun()

                        # Edit notes on open trade
                        cur_notes = pos.get("notes", "") or ""
                        new_notes = st.text_area(
                            "Journal", value=cur_notes,
                            key=f"perf_journal_{pos['id']}",
                        )
                        if new_notes != cur_notes:
                            if st.button("Save Notes", key=f"perf_save_notes_{pos['id']}"):
                                update_trade_notes(pos["id"], new_notes)
                                st.toast("Notes saved")
                                st.rerun()
            else:
                ui_theme.empty_state("No open positions.")

        # ────────────────────────────────────────────────────────────
        # Closed Trades (Paper + Real unified)
        # ────────────────────────────────────────────────────────────
        with sub_closed:
            closed_source = st.radio(
                "Source", ["Real Trades", "Paper Trades"],
                horizontal=True, key="perf_closed_source",
            )

            if closed_source == "Paper Trades":
                history = get_paper_trades_history(limit=200)
                if history:
                    st.markdown("**Paper Trade History by Day**")
                    paper_df = pd.DataFrame(history)

                    # Equity curve via shared helper
                    ui_theme.render_equity_curve(paper_df, pnl_col="pnl", sort_col="closed_at")

                    # Win/Loss distribution
                    col1, col2 = st.columns(2)
                    with col1:
                        fig_dist = px.histogram(
                            paper_df, x="pnl", nbins=20,
                            title="P&L Distribution",
                            color_discrete_sequence=["#3498db"],
                        )
                        fig_dist.add_vline(x=0, line_dash="dash", line_color="red")
                        fig_dist.update_layout(
                            height=300, xaxis_title="P&L ($)", yaxis_title="Count"
                        )
                        st.plotly_chart(fig_dist, use_container_width=True)

                    with col2:
                        win_count = len(paper_df[paper_df["pnl"] > 0])
                        loss_count = len(paper_df[paper_df["pnl"] <= 0])
                        fig_pie = px.pie(
                            names=["Winners", "Losers"],
                            values=[win_count, loss_count],
                            color_discrete_sequence=["#2ecc71", "#e74c3c"],
                            title="Win/Loss Ratio",
                        )
                        fig_pie.update_layout(height=300)
                        st.plotly_chart(fig_pie, use_container_width=True)

                    # Trade history by day via shared helper
                    ui_theme.render_trade_history_by_day(
                        history,
                        pnl_key="pnl",
                        symbol_key="symbol",
                        date_key="session_date",
                        columns=[
                            "symbol", "shares", "entry_price", "exit_price",
                            "stop_price", "target_price", "pnl", "status",
                            "alert_type",
                        ],
                        money_columns=[
                            "entry_price", "exit_price", "stop_price",
                            "target_price", "pnl",
                        ],
                    )
                else:
                    ui_theme.empty_state("No closed paper trades yet.")

            else:
                # Real closed trades
                real_closed_filter = st.radio(
                    "Type", ["All", "Intraday", "Swing"],
                    horizontal=True, key="perf_real_closed_filter",
                )
                real_closed_type = {
                    "All": None, "Intraday": "intraday", "Swing": "swing",
                }[real_closed_filter]

                history = get_closed_trades(limit=200, trade_type=real_closed_type)
                if history:
                    real_df = pd.DataFrame(history)

                    # Equity curve via shared helper
                    ui_theme.render_equity_curve(
                        real_df, pnl_col="pnl", sort_col="closed_at"
                    )

                    # P&L distribution + Win/Loss pie
                    col1, col2 = st.columns(2)
                    with col1:
                        fig_dist = px.histogram(
                            real_df, x="pnl", nbins=20,
                            title="P&L Distribution",
                            color_discrete_sequence=["#3498db"],
                        )
                        fig_dist.add_vline(x=0, line_dash="dash", line_color="red")
                        fig_dist.update_layout(
                            height=300, xaxis_title="P&L ($)", yaxis_title="Count"
                        )
                        st.plotly_chart(fig_dist, use_container_width=True)

                    with col2:
                        win_count = len(real_df[real_df["pnl"] > 0])
                        loss_count = len(real_df[real_df["pnl"] <= 0])
                        fig_pie = px.pie(
                            names=["Winners", "Losers"],
                            values=[win_count, loss_count],
                            color_discrete_sequence=["#2ecc71", "#e74c3c"],
                            title="Win/Loss Ratio",
                        )
                        fig_pie.update_layout(height=300)
                        st.plotly_chart(fig_pie, use_container_width=True)

                    # Build column list for trade history
                    base_cols = [
                        "symbol", "direction", "shares", "entry_price", "exit_price",
                        "pnl", "status", "alert_type", "session_date", "notes",
                    ]
                    if real_closed_type != "intraday":
                        for col in ("trade_type", "stop_type", "target_type"):
                            if col in real_df.columns:
                                base_cols.append(col)

                    money_cols = ["entry_price", "exit_price", "pnl"]

                    ui_theme.render_trade_history_by_day(
                        history,
                        pnl_key="pnl",
                        symbol_key="symbol",
                        date_key="session_date",
                        columns=[c for c in base_cols if c != "session_date"],
                        money_columns=money_cols,
                    )

                    # AI Trade Review per trade (in expanders after history)
                    st.divider()
                    ui_theme.section_header("AI Trade Reviews")
                    from analytics.trade_review import get_trade_review
                    for trade in history:
                        tid = trade["id"]
                        sym = trade["symbol"]
                        existing_review = get_trade_review(tid)
                        if existing_review:
                            with st.expander(f"AI Review -- {sym} (#{tid})"):
                                st.markdown(existing_review)
                        else:
                            if st.button(
                                f"AI Review {sym} (#{tid})",
                                key=f"perf_ai_review_{tid}",
                            ):
                                from analytics.trade_review import (
                                    generate_trade_review,
                                    save_trade_review,
                                )
                                review_chunks = []
                                try:
                                    placeholder = st.empty()
                                    for chunk in generate_trade_review(trade):
                                        review_chunks.append(chunk)
                                        placeholder.markdown("".join(review_chunks))
                                    full_review = "".join(review_chunks)
                                    save_trade_review(tid, full_review)
                                    st.toast(f"AI review saved for {sym}")
                                except ValueError as e:
                                    st.error(str(e))
                                except Exception as e:
                                    st.error(f"AI review failed: {e}")
                else:
                    ui_theme.empty_state("No closed trades yet.")

        # ── Backup & Restore (always visible) ──────────────────────
        st.divider()
        ui_theme.section_header("Backup & Restore")
        st.caption("Download trades as CSV before a restart. Upload to restore after.")

        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            with get_db() as conn:
                eq_df = _pd_read_sql(
                    "SELECT * FROM real_trades ORDER BY opened_at DESC", conn
                )
            st.download_button(
                "Download Equity Trades CSV",
                data=eq_df.to_csv(index=False).encode(),
                file_name="real_trades_backup.csv",
                mime="text/csv",
                disabled=eq_df.empty,
            )
            st.caption(f"{len(eq_df)} equity trades")

        with dl_col2:
            with get_db() as conn:
                opt_df = _pd_read_sql(
                    "SELECT * FROM real_options_trades ORDER BY opened_at DESC", conn
                )
            st.download_button(
                "Download Options Trades CSV",
                data=opt_df.to_csv(index=False).encode(),
                file_name="real_options_trades_backup.csv",
                mime="text/csv",
                disabled=opt_df.empty,
            )
            st.caption(f"{len(opt_df)} options trades")

        # Upload / Restore
        with st.expander("Restore from CSV"):
            uploaded = st.file_uploader(
                "Upload a backup CSV (equity or options)",
                type=["csv"],
                key="perf_trade_restore_upload",
            )
            if uploaded:
                restore_df = pd.read_csv(uploaded)
                st.dataframe(restore_df.head(10), use_container_width=True)
                st.caption(f"{len(restore_df)} rows found in file")

                is_options = (
                    "option_type" in restore_df.columns
                    and "strike" in restore_df.columns
                )
                table_name = "real_options_trades" if is_options else "real_trades"

                st.warning(
                    f"This will insert **{len(restore_df)} rows** into `{table_name}`. "
                    "Duplicate rows (same id) will be skipped."
                )

                if st.button("Restore Trades", type="primary", key="perf_restore_btn"):
                    inserted = 0
                    skipped = 0
                    with get_db() as conn:
                        cols = [c for c in restore_df.columns if c != "id"]
                        placeholders = ", ".join(["?"] * len(cols))
                        col_names = ", ".join(cols)
                        for _, row in restore_df.iterrows():
                            try:
                                conn.execute(
                                    f"INSERT INTO {table_name} ({col_names}) "
                                    f"VALUES ({placeholders})",
                                    tuple(
                                        None if pd.isna(v) else v
                                        for v in row[cols]
                                    ),
                                )
                                inserted += 1
                            except Exception:
                                skipped += 1
                    st.success(
                        f"Restored {inserted} trades ({skipped} skipped/duplicates)"
                    )
                    st.rerun()


# =========================================================================
# TAB 3: Journal (from History)
# =========================================================================
with tab_journal:
    if _is_free:
        render_inline_upgrade(
            "Trade journal -- log, calendar, stop discipline, symbol lookup",
            "pro",
        )
    else:
        df_journal = get_user_trades(user["id"])
        if df_journal.empty:
            ui_theme.empty_state("No trade data. Go to Import page to upload PDFs.")
        else:
            # ── Sidebar Filters ────────────────────────────────────
            with st.sidebar:
                st.subheader("Journal Filters")

                all_months = sorted(
                    df_journal["trade_date"].dt.to_period("M").astype(str)
                    .unique().tolist()
                )
                month_options = ["All Months"] + all_months
                selected_month = st.selectbox(
                    "Month", month_options, key="perf_j_month"
                )

                source_options = ["All Sources"] + sorted(
                    df_journal["source"].unique().tolist()
                )
                selected_source = st.selectbox(
                    "Source", source_options, key="perf_j_source"
                )

                symbols = sorted(df_journal["symbol"].unique().tolist())
                selected_symbols = st.multiselect(
                    "Symbols", symbols, default=symbols, key="perf_j_symbols"
                )

                period_opts = ["All", "day_trade", "swing", "position"]
                selected_period = st.selectbox(
                    "Holding Period", period_opts, key="perf_j_period"
                )

            mask = df_journal["symbol"].isin(selected_symbols)
            if selected_month != "All Months":
                mask &= (
                    df_journal["trade_date"].dt.to_period("M").astype(str)
                    == selected_month
                )
            if selected_source != "All Sources":
                mask &= df_journal["source"] == selected_source
            if selected_period != "All":
                mask &= df_journal["holding_period_type"] == selected_period
            filtered = df_journal[mask].copy().sort_values("trade_date")

            if filtered.empty:
                ui_theme.empty_state(
                    "No trades match the current filters.", icon="warning"
                )
            else:
                # ── Stop loss computations ─────────────────────────
                filtered["entry_price"] = (
                    filtered["cost_basis"]
                    / filtered["quantity"].where(filtered["quantity"] != 0, 1)
                )
                filtered["exit_price"] = (
                    filtered["proceeds"]
                    / filtered["quantity"].where(filtered["quantity"] != 0, 1)
                )
                filtered["pnl_pct"] = (
                    (filtered["realized_pnl"] / filtered["cost_basis"] * 100)
                    .where(filtered["cost_basis"] != 0, 0)
                )

                filtered["rec_stop_pct"] = (
                    filtered["holding_period_type"].map(STOP_LOSS_PCT).fillna(2.5)
                )
                filtered["rec_stop_price"] = (
                    filtered["entry_price"] * (1 - filtered["rec_stop_pct"] / 100)
                )
                filtered["max_loss_at_stop"] = (
                    -filtered["cost_basis"] * filtered["rec_stop_pct"] / 100
                )
                filtered["excess_loss"] = 0.0
                loser_mask = filtered["realized_pnl"] < filtered["max_loss_at_stop"]
                filtered.loc[loser_mask, "excess_loss"] = (
                    filtered.loc[loser_mask, "realized_pnl"]
                    - filtered.loc[loser_mask, "max_loss_at_stop"]
                )
                filtered["pnl_with_stop"] = filtered["realized_pnl"].copy()
                filtered.loc[loser_mask, "pnl_with_stop"] = (
                    filtered.loc[loser_mask, "max_loss_at_stop"]
                )

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
                avg_win = (
                    winners["realized_pnl"].mean() if len(winners) > 0 else 0
                )
                avg_loss = (
                    losers["realized_pnl"].mean() if len(losers) > 0 else 0
                )
                win_rate = len(winners) / len(filtered) * 100

                # ── Journal Sub-tabs ───────────────────────────────
                jtab_log, jtab_cal, jtab_stop, jtab_sym = st.tabs([
                    "Trade Log", "Calendar", "Stop Discipline", "Symbol Lookup",
                ])

                # ── Trade Log ──────────────────────────────────────
                with jtab_log:
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("Trades", len(filtered))
                    col2.metric("P&L", f"${filtered['realized_pnl'].sum():,.2f}")
                    col3.metric("Win Rate", f"{win_rate:.1f}%")
                    col4.metric("Avg Win", f"${avg_win:,.2f}")
                    col5.metric("Avg Loss", f"${avg_loss:,.2f}")

                    st.divider()

                    # P&L by Symbol
                    ui_theme.section_header("P&L by Symbol")
                    by_symbol = filtered.groupby("symbol").agg(
                        total_pnl=("realized_pnl", "sum"),
                        num_trades=("realized_pnl", "count"),
                        avg_pnl=("realized_pnl", "mean"),
                        win_rate=("realized_pnl", lambda x: (x > 0).mean() * 100),
                    ).reset_index().sort_values("total_pnl", ascending=False)

                    fig = px.bar(
                        by_symbol, x="symbol", y="total_pnl", text_auto="$.2s",
                        color="total_pnl",
                        color_continuous_scale=["#e74c3c", "#95a5a6", "#2ecc71"],
                        color_continuous_midpoint=0,
                    )
                    fig.update_layout(
                        height=400, xaxis_title="", yaxis_title="P&L ($)"
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # Trade table
                    ui_theme.section_header("Trade Log")
                    st.caption(
                        "Rec Stop = recommended stop based on holding period. "
                        "Excess Loss = how much you lost beyond that stop."
                    )

                    log = filtered[[
                        "trade_date", "symbol", "category", "quantity",
                        "entry_price", "exit_price", "realized_pnl", "pnl_pct",
                        "rec_stop_pct", "rec_stop_price", "max_loss_at_stop",
                        "excess_loss", "loss_grade", "holding_days",
                        "holding_period_type", "source",
                    ]].copy()

                    # Merge annotations
                    j_annotations = get_annotations(user["id"])
                    if not j_annotations.empty:
                        log["trade_date_str"] = log["trade_date"].dt.strftime(
                            "%Y-%m-%d"
                        )
                        log = log.merge(
                            j_annotations[[
                                "source", "symbol", "trade_date", "quantity",
                                "strategy_tag", "notes",
                            ]].rename(columns={
                                "trade_date": "trade_date_str",
                                "source": "ann_source",
                            }),
                            left_on=[
                                "source", "symbol", "trade_date_str", "quantity",
                            ],
                            right_on=[
                                "ann_source", "symbol", "trade_date_str",
                                "quantity",
                            ],
                            how="left",
                        )
                        log.drop(
                            columns=["ann_source", "trade_date_str"],
                            errors="ignore",
                            inplace=True,
                        )
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
                        "trade_date": "Date", "symbol": "Symbol",
                        "quantity": "Qty",
                        "entry_price": "Entry $", "exit_price": "Exit $",
                        "rec_stop_price": "Rec Stop $",
                        "realized_pnl": "P&L $",
                        "max_loss_at_stop": "Max Loss @Stop",
                        "excess_loss": "Excess Loss",
                        "pnl_pct": "P&L %", "loss_grade": "Grade",
                        "holding_days": "Days",
                        "holding_period_type": "Period",
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
                        log[display_cols].rename(columns=display_names)
                        .style.format({
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
                    ui_theme.section_header("Tag a Trade")
                    st.caption(
                        "Add strategy tags and notes to individual trades "
                        "for tracking what works"
                    )

                    tag_trades = filtered[[
                        "trade_date", "symbol", "quantity",
                        "realized_pnl", "source",
                    ]].copy()
                    tag_trades["label"] = (
                        tag_trades["trade_date"].dt.strftime("%Y-%m-%d")
                        + " | "
                        + tag_trades["symbol"]
                        + " | "
                        + tag_trades["quantity"].apply(
                            lambda x: f"{x:.0f} shares"
                        )
                        + " | $"
                        + tag_trades["realized_pnl"].apply(
                            lambda x: f"{x:,.2f}"
                        )
                    )
                    trade_labels = tag_trades["label"].tolist()

                    if trade_labels:
                        selected_trade_label = st.selectbox(
                            "Select trade to tag", trade_labels,
                            key="perf_tag_select",
                        )
                        idx = trade_labels.index(selected_trade_label)
                        sel = tag_trades.iloc[idx]

                        tc1, tc2 = st.columns(2)
                        with tc1:
                            tag = st.selectbox(
                                "Strategy Tag",
                                ["(none)"] + STRATEGY_TAGS,
                                key="perf_tag_strat",
                            )
                        with tc2:
                            note = st.text_input(
                                "Note (optional)", key="perf_tag_note"
                            )

                        if st.button("Save Tag", key="perf_tag_save"):
                            upsert_annotation(
                                source=sel["source"],
                                symbol=sel["symbol"],
                                trade_date=sel["trade_date"].strftime(
                                    "%Y-%m-%d"
                                ),
                                quantity=sel["quantity"],
                                user_id=user["id"],
                                strategy_tag=(
                                    tag if tag != "(none)" else None
                                ),
                                notes=note if note else None,
                            )
                            st.success(
                                f"Tagged {sel['symbol']} "
                                f"{sel['trade_date'].strftime('%Y-%m-%d')}"
                            )
                            st.rerun()

                # ── Calendar ───────────────────────────────────────
                with jtab_cal:
                    ui_theme.section_header("Daily P&L Calendar")

                    daily_pnl = filtered.groupby(
                        filtered["trade_date"].dt.date
                    ).agg(
                        pnl=("realized_pnl", "sum"),
                        trades=("realized_pnl", "count"),
                    ).reset_index()
                    daily_pnl.columns = ["date", "pnl", "trades"]
                    daily_pnl["date"] = pd.to_datetime(daily_pnl["date"])
                    daily_pnl["day_of_week"] = daily_pnl["date"].dt.dayofweek
                    daily_pnl["month_str"] = daily_pnl["date"].dt.strftime(
                        "%Y-%m"
                    )

                    months_in_data = sorted(
                        daily_pnl["month_str"].unique()
                    )
                    for month_str in months_in_data:
                        month_data = daily_pnl[
                            daily_pnl["month_str"] == month_str
                        ].copy()
                        if month_data.empty:
                            continue

                        first_day = pd.Timestamp(month_str + "-01")
                        last_day = first_day + pd.offsets.MonthEnd(0)
                        all_days = pd.date_range(
                            first_day, last_day, freq="D"
                        )
                        weekdays = all_days[all_days.dayofweek < 5]

                        grid_data = pd.DataFrame({"date": weekdays})
                        grid_data["day_of_week"] = (
                            grid_data["date"].dt.dayofweek
                        )
                        grid_data["week_num"] = (
                            (
                                grid_data["date"].dt.day
                                - 1
                                + grid_data["date"].iloc[0].dayofweek
                            )
                            // 7
                        )
                        grid_data = grid_data.merge(
                            month_data[["date", "pnl", "trades"]],
                            on="date",
                            how="left",
                        )

                        pivot = grid_data.pivot(
                            index="day_of_week",
                            columns="week_num",
                            values="pnl",
                        )
                        trades_pivot = grid_data.pivot(
                            index="day_of_week",
                            columns="week_num",
                            values="trades",
                        )
                        dates_pivot = grid_data.pivot(
                            index="day_of_week",
                            columns="week_num",
                            values="date",
                        )

                        hover_text = []
                        for dow in pivot.index:
                            row_text = []
                            for wk in pivot.columns:
                                d = (
                                    dates_pivot.loc[dow, wk]
                                    if pd.notna(dates_pivot.loc[dow, wk])
                                    else None
                                )
                                p = pivot.loc[dow, wk]
                                t = trades_pivot.loc[dow, wk]
                                if d is not None and pd.notna(p):
                                    row_text.append(
                                        f"{d.strftime('%b %d')}: "
                                        f"${p:,.0f} ({int(t)} trades)"
                                    )
                                elif d is not None:
                                    row_text.append(
                                        f"{d.strftime('%b %d')}: no trades"
                                    )
                                else:
                                    row_text.append("")
                            hover_text.append(row_text)

                        max_abs = max(
                            abs(month_data["pnl"].min()),
                            abs(month_data["pnl"].max()),
                            1,
                        )

                        fig = go.Figure(go.Heatmap(
                            z=pivot.values,
                            x=[f"Wk {c+1}" for c in pivot.columns],
                            y=["Mon", "Tue", "Wed", "Thu", "Fri"],
                            text=hover_text,
                            hoverinfo="text",
                            colorscale=[
                                [0, "#e74c3c"],
                                [0.5, "#f5f5f5"],
                                [1, "#2ecc71"],
                            ],
                            zmid=0,
                            zmin=-max_abs,
                            zmax=max_abs,
                            showscale=False,
                        ))
                        for i, dow in enumerate(pivot.index):
                            for j, wk in enumerate(pivot.columns):
                                val = pivot.loc[dow, wk]
                                if pd.notna(val):
                                    fig.add_annotation(
                                        x=f"Wk {wk+1}",
                                        y=[
                                            "Mon", "Tue", "Wed", "Thu", "Fri"
                                        ][i],
                                        text=f"${val:,.0f}",
                                        showarrow=False,
                                        font=dict(size=10, color="black"),
                                    )

                        fig.update_layout(
                            title=(
                                f"{pd.Timestamp(month_str + '-01').strftime('%B %Y')}"
                            ),
                            height=200,
                            margin=dict(l=50, r=20, t=40, b=20),
                            yaxis=dict(autorange="reversed"),
                        )
                        st.plotly_chart(fig, use_container_width=True)

                # ── Stop Discipline ────────────────────────────────
                with jtab_stop:
                    ui_theme.section_header("Stop Loss Lab")
                    st.caption(
                        "Analyzing the cost of not using stops and what "
                        "disciplined stops would do for your P&L"
                    )

                    all_losers = filtered[
                        filtered["realized_pnl"] < 0
                    ].copy()
                    blown_stops = filtered[
                        filtered["excess_loss"] < 0
                    ].copy()

                    actual_total_pnl = filtered["realized_pnl"].sum()
                    pnl_with_stops = filtered["pnl_with_stop"].sum()
                    total_excess_loss = blown_stops["excess_loss"].sum()
                    num_blown = len(blown_stops)

                    sc1, sc2, sc3, sc4 = st.columns(4)
                    sc1.metric("Actual P&L", f"${actual_total_pnl:,.2f}")
                    sc2.metric(
                        "P&L with Stops",
                        f"${pnl_with_stops:,.2f}",
                        delta=f"${pnl_with_stops - actual_total_pnl:,.2f}",
                    )
                    sc3.metric(
                        "Excess Loss (No Stops)",
                        f"${total_excess_loss:,.2f}",
                    )
                    sc4.metric(
                        "Trades that Blew Stop",
                        f"{num_blown} of {len(all_losers)} losers",
                    )

                    st.divider()

                    # Loss Severity Breakdown
                    ui_theme.section_header("Loss Severity Breakdown")
                    st.caption(
                        "SMALL LOSS = disciplined exit (<2%). "
                        "CAUTION = held too long (2-5%). "
                        "DANGER = no stop, big damage (>5%)."
                    )

                    grade_counts = filtered["loss_grade"].value_counts()
                    grade_pnl = filtered.groupby("loss_grade")[
                        "realized_pnl"
                    ].sum()

                    gc1, gc2 = st.columns(2)
                    grade_colors = {
                        "WIN": "#2ecc71",
                        "SMALL LOSS": "#f39c12",
                        "CAUTION": "#e67e22",
                        "DANGER": "#e74c3c",
                    }
                    with gc1:
                        grade_df = pd.DataFrame({
                            "Grade": grade_counts.index,
                            "Count": grade_counts.values,
                        })
                        fig = go.Figure(go.Bar(
                            x=grade_df["Grade"],
                            y=grade_df["Count"],
                            marker_color=[
                                grade_colors.get(g, "#95a5a6")
                                for g in grade_df["Grade"]
                            ],
                            text=grade_df["Count"],
                            textposition="outside",
                        ))
                        fig.update_layout(
                            height=300,
                            xaxis_title="",
                            yaxis_title="# Trades",
                            title="Trade Count by Grade",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    with gc2:
                        grade_pnl_df = grade_pnl.reset_index()
                        grade_pnl_df.columns = ["Grade", "P&L"]
                        fig = go.Figure(go.Bar(
                            x=grade_pnl_df["Grade"],
                            y=grade_pnl_df["P&L"],
                            marker_color=[
                                grade_colors.get(g, "#95a5a6")
                                for g in grade_pnl_df["Grade"]
                            ],
                            text=[
                                f"${v:,.0f}" for v in grade_pnl_df["P&L"]
                            ],
                            textposition="outside",
                        ))
                        fig.update_layout(
                            height=300,
                            xaxis_title="",
                            yaxis_title="P&L ($)",
                            title="P&L Impact by Grade",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    st.divider()

                    # What-If Scenarios
                    ui_theme.section_header(
                        "What-If: P&L at Different Stop Levels"
                    )
                    st.caption(
                        "If you had enforced a stop at each % level, "
                        "what would your total P&L be?"
                    )

                    scenarios = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
                    scenario_results = []

                    for stop_pct in scenarios:
                        max_loss_per_trade = (
                            -filtered["cost_basis"] * stop_pct / 100
                        )
                        capped_pnl = filtered["realized_pnl"].copy()
                        blow_mask = (
                            filtered["realized_pnl"] < max_loss_per_trade
                        )
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

                    wc1, wc2 = st.columns(2)
                    with wc1:
                        fig = go.Figure()
                        fig.add_trace(go.Bar(
                            x=scenario_df["Stop %"],
                            y=scenario_df["Total P&L"],
                            marker_color=[
                                "#2ecc71" if v >= 0 else "#e74c3c"
                                for v in scenario_df["Total P&L"]
                            ],
                            text=[
                                f"${v:,.0f}"
                                for v in scenario_df["Total P&L"]
                            ],
                            textposition="outside",
                            name="P&L with Stop",
                        ))
                        fig.add_hline(
                            y=actual_total_pnl,
                            line_dash="dash",
                            line_color="#3498db",
                            annotation_text=(
                                f"Actual: ${actual_total_pnl:,.0f}"
                            ),
                        )
                        fig.update_layout(
                            height=350,
                            xaxis_title="Stop Loss %",
                            yaxis_title="Total P&L ($)",
                            title="Total P&L at Each Stop Level",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    with wc2:
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
                    ui_theme.section_header(
                        "Worst Offenders - Biggest Excess Losses"
                    )
                    st.caption(
                        "These trades blew past the recommended stop. "
                        "This is where your money went."
                    )

                    if not blown_stops.empty:
                        worst = blown_stops.nsmallest(15, "excess_loss")[[
                            "trade_date", "symbol", "quantity",
                            "entry_price", "exit_price",
                            "rec_stop_price", "realized_pnl",
                            "max_loss_at_stop", "excess_loss",
                            "pnl_pct", "holding_period_type",
                        ]].copy()
                        worst["trade_date"] = worst[
                            "trade_date"
                        ].dt.strftime("%Y-%m-%d")

                        st.dataframe(
                            worst.rename(columns={
                                "trade_date": "Date",
                                "symbol": "Symbol",
                                "quantity": "Qty",
                                "entry_price": "Entry $",
                                "exit_price": "Exit $",
                                "rec_stop_price": "Stop Should Be",
                                "realized_pnl": "Actual P&L",
                                "max_loss_at_stop": "Max Loss @Stop",
                                "excess_loss": "Excess Loss",
                                "pnl_pct": "Loss %",
                                "holding_period_type": "Period",
                            }).style.format({
                                "Qty": "{:,.0f}",
                                "Entry $": "${:,.2f}",
                                "Exit $": "${:,.2f}",
                                "Stop Should Be": "${:,.2f}",
                                "Actual P&L": "${:,.2f}",
                                "Max Loss @Stop": "${:,.2f}",
                                "Excess Loss": "${:,.2f}",
                                "Loss %": "{:+.1f}%",
                            }),
                            use_container_width=True,
                        )

                        fig = go.Figure(go.Bar(
                            x=(
                                worst["Date"].astype(str)
                                + " "
                                + worst["Symbol"]
                            ),
                            y=worst["Excess Loss"],
                            marker_color="#e74c3c",
                            text=[
                                f"${v:,.0f}"
                                for v in worst["Excess Loss"]
                            ],
                            textposition="outside",
                        ))
                        fig.update_layout(
                            height=350,
                            xaxis_title="",
                            yaxis_title="Excess Loss ($)",
                            title="Money Left on Table (No Stop)",
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.success(
                            "All losing trades were within stop limits!"
                        )

                    st.divider()

                    # Pre-Trade Risk Calculator
                    ui_theme.section_header("Pre-Trade Risk Calculator")
                    st.caption(
                        "Enter your position and see exactly how much "
                        "you're risking at each stop level."
                    )

                    calc_col1, calc_col2 = st.columns(2)
                    with calc_col1:
                        position_amount = st.number_input(
                            "Position Amount ($)",
                            value=63000.0,
                            step=1000.0,
                            help="Total $ you're putting into this trade",
                            key="perf_risk_pos",
                        )
                    with calc_col2:
                        entry_price_input = st.number_input(
                            "Entry Price ($)",
                            value=635.0,
                            step=1.0,
                            help="Your buy price per share",
                            key="perf_risk_entry",
                        )

                    if entry_price_input > 0 and position_amount > 0:
                        calc_shares = position_amount / entry_price_input

                        stop_levels = [
                            0.25, 0.5, 0.75, 1.0, 1.5,
                            2.0, 2.5, 3.0, 4.0, 5.0,
                        ]
                        risk_rows = []
                        for sp in stop_levels:
                            stop_px = entry_price_input * (1 - sp / 100)
                            loss_per_share = entry_price_input * sp / 100
                            total_loss = calc_shares * loss_per_share
                            risk_rows.append({
                                "Stop %": f"{sp}%",
                                "Stop Price": stop_px,
                                "Loss/Share": loss_per_share,
                                "Total $ Risk": total_loss,
                            })
                        risk_df = pd.DataFrame(risk_rows)

                        rc1, rc2, rc3 = st.columns(3)
                        rc1.metric("Shares", f"{calc_shares:,.0f}")
                        rc2.metric("Position", f"${position_amount:,.0f}")
                        rc3.metric("Entry", f"${entry_price_input:,.2f}")

                        rc_left, rc_right = st.columns([3, 2])
                        with rc_left:
                            st.dataframe(
                                risk_df.style.format({
                                    "Stop Price": "${:,.2f}",
                                    "Loss/Share": "${:,.2f}",
                                    "Total $ Risk": "${:,.2f}",
                                }).applymap(
                                    lambda v: (
                                        "background-color: #2ecc7133"
                                        if isinstance(v, str)
                                        and v in ("0.5%", "1.0%")
                                        else "background-color: #f39c1233"
                                        if isinstance(v, str)
                                        and v in ("2.0%", "2.5%")
                                        else "background-color: #e74c3c33"
                                        if isinstance(v, str)
                                        and v in ("4.0%", "5.0%")
                                        else ""
                                    ),
                                    subset=["Stop %"],
                                ),
                                use_container_width=True,
                            )

                        with rc_right:
                            fig = go.Figure(go.Bar(
                                x=[r["Stop %"] for r in risk_rows],
                                y=[r["Total $ Risk"] for r in risk_rows],
                                marker_color=[
                                    "#2ecc71", "#2ecc71", "#2ecc71",
                                    "#27ae60", "#f39c12", "#e67e22",
                                    "#e67e22", "#e74c3c", "#e74c3c",
                                    "#c0392b",
                                ],
                                text=[
                                    f"${r['Total $ Risk']:,.0f}"
                                    for r in risk_rows
                                ],
                                textposition="outside",
                            ))
                            fig.update_layout(
                                height=350,
                                xaxis_title="Stop %",
                                yaxis_title="$ at Risk",
                                title="Risk by Stop Level",
                                showlegend=False,
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        st.markdown("**Quick Risk Check:**")
                        q1, q2, q3, q4 = st.columns(4)
                        q1.metric(
                            "0.5% Stop",
                            f"-${position_amount * 0.005:,.0f}",
                            delta=(
                                f"Stop @ ${entry_price_input * 0.995:,.2f}"
                            ),
                            delta_color="off",
                        )
                        q2.metric(
                            "1% Stop",
                            f"-${position_amount * 0.01:,.0f}",
                            delta=(
                                f"Stop @ ${entry_price_input * 0.99:,.2f}"
                            ),
                            delta_color="off",
                        )
                        q3.metric(
                            "2% Stop",
                            f"-${position_amount * 0.02:,.0f}",
                            delta=(
                                f"Stop @ ${entry_price_input * 0.98:,.2f}"
                            ),
                            delta_color="off",
                        )
                        q4.metric(
                            "3% Stop",
                            f"-${position_amount * 0.03:,.0f}",
                            delta=(
                                f"Stop @ ${entry_price_input * 0.97:,.2f}"
                            ),
                            delta_color="off",
                        )

                # ── Symbol Lookup ──────────────────────────────────
                with jtab_sym:
                    ui_theme.section_header("Symbol Deep-Dive")
                    st.caption(
                        "Select a symbol to see all your trades and "
                        "whether you should keep trading it"
                    )

                    symbol_stats = df_journal.groupby("symbol").agg(
                        total_pnl=("realized_pnl", "sum"),
                        num_trades=("realized_pnl", "count"),
                    ).reset_index().sort_values(
                        "num_trades", ascending=False
                    )

                    symbol_labels = [
                        f"{row['symbol']} "
                        f"({row['num_trades']} trades, "
                        f"${row['total_pnl']:,.0f})"
                        for _, row in symbol_stats.iterrows()
                    ]
                    symbol_map = dict(
                        zip(symbol_labels, symbol_stats["symbol"])
                    )

                    selected_label = st.selectbox(
                        "Symbol", symbol_labels, key="perf_sym_lookup"
                    )
                    symbol = symbol_map[selected_label]

                    sym_df = (
                        df_journal[df_journal["symbol"] == symbol]
                        .copy()
                        .sort_values("trade_date")
                    )

                    if sym_df.empty:
                        st.warning("No trades for this symbol.")
                    else:
                        # KPIs
                        s_total_pnl = sym_df["realized_pnl"].sum()
                        s_num_trades = len(sym_df)
                        s_winners = sym_df[sym_df["realized_pnl"] > 0]
                        s_losers = sym_df[sym_df["realized_pnl"] < 0]
                        s_win_rate = (
                            len(s_winners) / s_num_trades * 100
                            if s_num_trades > 0 else 0
                        )
                        s_avg_win = (
                            s_winners["realized_pnl"].mean()
                            if len(s_winners) > 0 else 0
                        )
                        s_avg_loss = (
                            s_losers["realized_pnl"].mean()
                            if len(s_losers) > 0 else 0
                        )
                        s_risk_reward = (
                            abs(s_avg_win / s_avg_loss)
                            if s_avg_loss != 0 else 0
                        )
                        s_total_volume = sym_df["proceeds"].sum()

                        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                        sc1.metric("Total P&L", f"${s_total_pnl:,.2f}")
                        sc2.metric("Trades", f"{s_num_trades}")
                        sc3.metric("Win Rate", f"{s_win_rate:.1f}%")
                        sc4.metric("R:R Ratio", f"{s_risk_reward:.2f}")
                        sc5.metric("Volume", f"${s_total_volume:,.0f}")

                        sc1, sc2, sc3, sc4 = st.columns(4)
                        sc1.metric("Avg Win", f"${s_avg_win:,.2f}")
                        sc2.metric("Avg Loss", f"${s_avg_loss:,.2f}")
                        s_avg_hold = (
                            sym_df["holding_days"].mean()
                            if sym_df["holding_days"].notna().any()
                            else 0
                        )
                        sc3.metric("Avg Hold Days", f"{s_avg_hold:.1f}")
                        sc4.metric("Category", sym_df["category"].iloc[0])

                        # Verdict
                        s_expectancy = (
                            (s_win_rate / 100 * s_avg_win)
                            + ((1 - s_win_rate / 100) * s_avg_loss)
                        )
                        if s_total_pnl > 0 and s_win_rate >= 40:
                            verdict = (
                                "KEEP TRADING - Profitable with "
                                "decent win rate"
                            )
                            verdict_color = "#2ecc71"
                        elif s_total_pnl > 0:
                            verdict = (
                                "CAUTION - Profitable but low win rate, "
                                "relies on big wins"
                            )
                            verdict_color = "#f39c12"
                        elif s_num_trades >= 5 and s_win_rate < 30:
                            verdict = (
                                "STOP - Multiple trades, low win rate, "
                                "net loser"
                            )
                            verdict_color = "#e74c3c"
                        elif s_total_pnl < -500:
                            verdict = "STOP - Significant losses"
                            verdict_color = "#e74c3c"
                        else:
                            verdict = (
                                "REVIEW - Small sample or "
                                "marginal results"
                            )
                            verdict_color = "#95a5a6"

                        st.markdown(
                            f"### Verdict: "
                            f"<span style='color:{verdict_color}'>"
                            f"{verdict}</span>",
                            unsafe_allow_html=True,
                        )
                        st.caption(
                            f"Expectancy per trade: ${s_expectancy:,.2f}"
                        )

                        st.divider()

                        # P&L Timeline
                        ui_theme.section_header("P&L Timeline")
                        sym_df["cumulative_pnl"] = (
                            sym_df["realized_pnl"].cumsum()
                        )

                        fig = go.Figure()
                        colors = [
                            "#2ecc71" if v > 0 else "#e74c3c"
                            for v in sym_df["realized_pnl"]
                        ]
                        fig.add_trace(go.Bar(
                            x=sym_df["trade_date"].dt.strftime("%Y-%m-%d"),
                            y=sym_df["realized_pnl"],
                            marker_color=colors,
                            name="Trade P&L",
                            text=[
                                f"${v:,.0f}"
                                for v in sym_df["realized_pnl"]
                            ],
                            textposition="outside",
                            hovertemplate=(
                                "%{x}<br>P&L: $%{y:,.2f}<extra></extra>"
                            ),
                        ))
                        fig.add_trace(go.Scatter(
                            x=sym_df["trade_date"].dt.strftime("%Y-%m-%d"),
                            y=sym_df["cumulative_pnl"],
                            mode="lines+markers",
                            name="Cumulative",
                            yaxis="y2",
                            line=dict(color="#3498db", width=2),
                        ))
                        fig.add_hline(
                            y=0, line_dash="dash", line_color="gray"
                        )
                        fig.update_layout(
                            height=400,
                            yaxis=dict(title="Trade P&L ($)"),
                            yaxis2=dict(
                                title="Cumulative P&L ($)",
                                overlaying="y",
                                side="right",
                            ),
                            legend=dict(orientation="h", y=1.1),
                        )
                        st.plotly_chart(fig, use_container_width=True)

                        st.divider()

                        # Full Trade Table
                        ui_theme.section_header("All Trades")

                        sym_annotations = get_annotations(user["id"])
                        s_display = sym_df[[
                            "trade_date", "quantity", "cost_basis",
                            "proceeds", "realized_pnl", "holding_days",
                            "holding_period_type", "source",
                        ]].copy()
                        s_display["entry_price"] = (
                            s_display["cost_basis"]
                            / s_display["quantity"].where(
                                s_display["quantity"] != 0, 1
                            )
                        )
                        s_display["exit_price"] = (
                            s_display["proceeds"]
                            / s_display["quantity"].where(
                                s_display["quantity"] != 0, 1
                            )
                        )
                        s_display["pnl_pct"] = (
                            (
                                s_display["realized_pnl"]
                                / s_display["cost_basis"]
                                * 100
                            ).where(s_display["cost_basis"] != 0, 0)
                        )

                        if not sym_annotations.empty:
                            sym_ann = sym_annotations[
                                sym_annotations["symbol"] == symbol
                            ]
                            if not sym_ann.empty:
                                s_display["trade_date_str"] = (
                                    s_display["trade_date"].dt.strftime(
                                        "%Y-%m-%d"
                                    )
                                )
                                s_display = s_display.merge(
                                    sym_ann[[
                                        "trade_date", "quantity",
                                        "strategy_tag", "notes",
                                    ]].rename(columns={
                                        "trade_date": "trade_date_str"
                                    }),
                                    on=["trade_date_str", "quantity"],
                                    how="left",
                                )
                                s_display.drop(
                                    columns=["trade_date_str"],
                                    errors="ignore",
                                    inplace=True,
                                )

                        if "strategy_tag" not in s_display.columns:
                            s_display["strategy_tag"] = None

                        s_display["trade_date"] = (
                            s_display["trade_date"].dt.strftime("%Y-%m-%d")
                        )

                        st.dataframe(
                            s_display[[
                                "trade_date", "quantity", "entry_price",
                                "exit_price", "realized_pnl", "pnl_pct",
                                "holding_days", "holding_period_type",
                                "strategy_tag", "source",
                            ]].rename(columns={
                                "trade_date": "Date",
                                "quantity": "Qty",
                                "entry_price": "Entry $",
                                "exit_price": "Exit $",
                                "realized_pnl": "P&L $",
                                "pnl_pct": "P&L %",
                                "holding_days": "Days",
                                "holding_period_type": "Period",
                                "strategy_tag": "Strategy",
                                "source": "Source",
                            }).style.format({
                                "Qty": "{:,.0f}",
                                "Entry $": "${:,.2f}",
                                "Exit $": "${:,.2f}",
                                "P&L $": "${:,.2f}",
                                "P&L %": "{:+.2f}%",
                            }),
                            use_container_width=True,
                        )


# =========================================================================
# TAB 4: Options (from Real Trades options section)
# =========================================================================
with tab_options:
    if _is_free:
        render_inline_upgrade(
            "Options tracking -- P&L, open/closed positions, close/expire actions",
            "pro",
        )
    else:
        # ── Options Performance Summary ────────────────────────────
        ui_theme.section_header("Options Performance Summary")

        opt_stats = get_options_trade_stats()
        if opt_stats["total_trades"] > 0:
            oc1, oc2, oc3 = st.columns(3)
            pnl_color = (
                "normal" if opt_stats["total_pnl"] >= 0 else "inverse"
            )
            oc1.metric(
                "Total P&L",
                f"${opt_stats['total_pnl']:,.2f}",
                delta=f"${opt_stats['total_pnl']:+,.2f}",
                delta_color=pnl_color,
            )
            oc2.metric("Win Rate", f"{opt_stats['win_rate']:.1f}%")
            oc3.metric("Total Trades", f"{opt_stats['total_trades']}")

            oc4, oc5, oc6 = st.columns(3)
            oc4.metric(
                "Expectancy/Trade", f"${opt_stats['expectancy']:,.2f}"
            )
            oc5.metric("Avg Winner", f"${opt_stats['avg_win']:,.2f}")
            oc6.metric("Avg Loser", f"${opt_stats['avg_loss']:,.2f}")
        else:
            ui_theme.empty_state(
                "No closed options trades yet. "
                "Use 'Track Options' on a high-quality pattern."
            )

        st.divider()

        # ── Open Options Positions ─────────────────────────────────
        ui_theme.section_header("Open Options Positions")

        opt_positions = get_open_options_trades()
        if opt_positions:
            for opos in opt_positions:
                sym = opos["symbol"]
                otype = opos["option_type"]
                strike = opos["strike"]
                expiry = opos["expiration"]
                contracts = opos["contracts"]
                premium = opos["premium_per_contract"]
                entry_cost = opos["entry_cost"]

                badge_color = "#2ecc71" if otype == "CALL" else "#9b59b6"
                st.markdown(
                    f"**{sym}** "
                    f"<span style='background:{badge_color};color:white;"
                    f"padding:2px 8px;border-radius:10px;"
                    f"font-size:0.8rem'>{otype}</span> "
                    f"${strike:,.2f} exp {expiry} | "
                    f"{contracts} contracts @ ${premium:,.2f} | "
                    f"Cost: ${entry_cost:,.2f}",
                    unsafe_allow_html=True,
                )

                with st.expander(
                    f"Manage {sym} {otype} ${strike:.0f} "
                    f"(ID: {opos['id']})"
                ):
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("Strike", f"${strike:,.2f}")
                    mc2.metric("Premium", f"${premium:,.2f}")
                    mc3.metric("Contracts", f"{contracts}")
                    mc4.metric("Entry Cost", f"${entry_cost:,.2f}")

                    close_col, expire_col = st.columns(2)
                    with close_col:
                        exit_prem = st.number_input(
                            "Exit Premium",
                            value=premium,
                            step=0.05,
                            format="%.2f",
                            key=f"perf_opt_exit_{opos['id']}",
                        )
                        close_notes = st.text_input(
                            "Notes",
                            key=f"perf_opt_notes_close_{opos['id']}",
                        )
                        exit_proceeds = contracts * exit_prem * 100
                        pnl_preview = exit_proceeds - entry_cost
                        pnl_preview_color = (
                            "#2ecc71" if pnl_preview >= 0 else "#e74c3c"
                        )
                        st.markdown(
                            f"<small>Proceeds: ${exit_proceeds:,.2f} | "
                            f"P&L: <span style='color:{pnl_preview_color}'>"
                            f"${pnl_preview:+,.2f}</span></small>",
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            "Close Trade",
                            key=f"perf_opt_close_{opos['id']}",
                        ):
                            pnl = close_options_trade(
                                opos["id"], exit_prem, close_notes
                            )
                            st.toast(
                                f"Closed {sym} {otype} -- P&L: ${pnl:+,.2f}"
                            )
                            st.rerun()

                    with expire_col:
                        expire_notes = st.text_input(
                            "Notes",
                            key=f"perf_opt_notes_expire_{opos['id']}",
                        )
                        st.caption(f"P&L: -${entry_cost:,.2f} (total loss)")
                        if st.button(
                            "Expired Worthless",
                            key=f"perf_opt_expire_{opos['id']}",
                        ):
                            pnl = expire_options_trade(
                                opos["id"], expire_notes
                            )
                            st.toast(
                                f"Expired {sym} {otype} -- "
                                f"P&L: ${pnl:+,.2f}"
                            )
                            st.rerun()

                    # Journal
                    cur_notes = opos.get("notes", "") or ""
                    new_notes = st.text_area(
                        "Journal",
                        value=cur_notes,
                        key=f"perf_opt_journal_{opos['id']}",
                    )
                    if new_notes != cur_notes:
                        if st.button(
                            "Save Notes",
                            key=f"perf_opt_save_notes_{opos['id']}",
                        ):
                            update_options_trade_notes(
                                opos["id"], new_notes
                            )
                            st.toast("Notes saved")
                            st.rerun()
        else:
            ui_theme.empty_state("No open options positions.")

        st.divider()

        # ── Closed Options Trades ──────────────────────────────────
        ui_theme.section_header("Closed Options Trades")

        opt_history = get_closed_options_trades(limit=200)
        if opt_history:
            odf = pd.DataFrame(opt_history)

            # Equity curve via shared helper
            ui_theme.render_equity_curve(
                odf,
                pnl_col="pnl",
                sort_col="closed_at",
                color="#9b59b6",
            )

            # Trade history table
            st.markdown("**Options Trade History**")
            opt_cols = [
                "symbol", "option_type", "strike", "expiration",
                "contracts", "premium_per_contract", "entry_cost",
                "exit_premium", "exit_proceeds", "pnl", "status",
                "session_date", "notes",
            ]
            opt_rename = {
                "symbol": "Symbol",
                "option_type": "Type",
                "strike": "Strike",
                "expiration": "Expiry",
                "contracts": "Contracts",
                "premium_per_contract": "Premium",
                "entry_cost": "Entry Cost",
                "exit_premium": "Exit Prem",
                "exit_proceeds": "Proceeds",
                "pnl": "P&L",
                "status": "Status",
                "session_date": "Date",
                "notes": "Notes",
            }
            odf_display = odf[
                [c for c in opt_cols if c in odf.columns]
            ].copy()
            odf_display = odf_display.rename(columns=opt_rename)
            st.dataframe(
                odf_display.set_index("Symbol").style.format({
                    "Strike": "${:,.2f}",
                    "Premium": "${:,.2f}",
                    "Entry Cost": "${:,.2f}",
                    "Exit Prem": "${:,.2f}",
                    "Proceeds": "${:,.2f}",
                    "P&L": "${:,.2f}",
                }),
                use_container_width=True,
            )
        else:
            ui_theme.empty_state("No closed options trades yet.")
