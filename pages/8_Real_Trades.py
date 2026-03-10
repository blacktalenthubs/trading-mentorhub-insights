"""Real Trades — Track real trades tied to alerts with P&L dashboard."""

import io

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from analytics.intraday_data import fetch_intraday
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
from db import get_db, _pd_read_sql
import ui_theme

user = ui_theme.setup_page("real_trades", tier_required="pro")

ui_theme.page_header("Real Trades", "Track real trades tied to alerts — $50k cap ($100k SPY)")

# ── Trade Type Filter ─────────────────────────────────────────────────
trade_filter = st.radio("Trade Type", ["All", "Intraday", "Swing", "Options"], horizontal=True)
type_param = {"All": None, "Intraday": "intraday", "Swing": "swing", "Options": "options"}[trade_filter]

# =====================================================================
# OPTIONS TAB
# =====================================================================
if trade_filter == "Options":
    # ── Options Performance Summary ──────────────────────────────────
    ui_theme.section_header("Options Performance Summary")

    opt_stats = get_options_trade_stats()
    if opt_stats["total_trades"] > 0:
        col1, col2, col3 = st.columns(3)
        pnl_color = "normal" if opt_stats["total_pnl"] >= 0 else "inverse"
        col1.metric("Total P&L", f"${opt_stats['total_pnl']:,.2f}",
                     delta=f"${opt_stats['total_pnl']:+,.2f}", delta_color=pnl_color)
        col2.metric("Win Rate", f"{opt_stats['win_rate']:.1f}%")
        col3.metric("Total Trades", f"{opt_stats['total_trades']}")

        col4, col5, col6 = st.columns(3)
        col4.metric("Expectancy/Trade", f"${opt_stats['expectancy']:,.2f}")
        col5.metric("Avg Winner", f"${opt_stats['avg_win']:,.2f}")
        col6.metric("Avg Loser", f"${opt_stats['avg_loss']:,.2f}")
    else:
        ui_theme.empty_state("No closed options trades yet. Use 'Track Options' on a high-score signal.")

    st.divider()

    # ── Open Options Positions ───────────────────────────────────────
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
                f"<span style='background:{badge_color};color:white;padding:2px 8px;"
                f"border-radius:10px;font-size:0.8rem'>{otype}</span> "
                f"${strike:,.2f} exp {expiry} | "
                f"{contracts} contracts @ ${premium:,.2f} | "
                f"Cost: ${entry_cost:,.2f}",
                unsafe_allow_html=True,
            )

            with st.expander(f"Manage {sym} {otype} ${strike:.0f} (ID: {opos['id']})"):
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Strike", f"${strike:,.2f}")
                mc2.metric("Premium", f"${premium:,.2f}")
                mc3.metric("Contracts", f"{contracts}")
                mc4.metric("Entry Cost", f"${entry_cost:,.2f}")

                close_col, expire_col = st.columns(2)
                with close_col:
                    exit_prem = st.number_input(
                        "Exit Premium", value=premium, step=0.05,
                        format="%.2f", key=f"opt_exit_{opos['id']}",
                    )
                    close_notes = st.text_input("Notes", key=f"opt_notes_close_{opos['id']}")
                    exit_proceeds = contracts * exit_prem * 100
                    pnl_preview = exit_proceeds - entry_cost
                    pnl_preview_color = "#2ecc71" if pnl_preview >= 0 else "#e74c3c"
                    st.markdown(
                        f"<small>Proceeds: ${exit_proceeds:,.2f} | "
                        f"P&L: <span style='color:{pnl_preview_color}'>"
                        f"${pnl_preview:+,.2f}</span></small>",
                        unsafe_allow_html=True,
                    )
                    if st.button("Close Trade", key=f"opt_close_{opos['id']}"):
                        pnl = close_options_trade(opos["id"], exit_prem, close_notes)
                        st.toast(f"Closed {sym} {otype} — P&L: ${pnl:+,.2f}")
                        st.rerun()

                with expire_col:
                    expire_notes = st.text_input("Notes", key=f"opt_notes_expire_{opos['id']}")
                    st.caption(f"P&L: -${entry_cost:,.2f} (total loss)")
                    if st.button("Expired Worthless", key=f"opt_expire_{opos['id']}"):
                        pnl = expire_options_trade(opos["id"], expire_notes)
                        st.toast(f"Expired {sym} {otype} — P&L: ${pnl:+,.2f}")
                        st.rerun()

                # Journal
                cur_notes = opos.get("notes", "") or ""
                new_notes = st.text_area(
                    "Journal", value=cur_notes, key=f"opt_journal_{opos['id']}",
                )
                if new_notes != cur_notes:
                    if st.button("Save Notes", key=f"opt_save_notes_{opos['id']}"):
                        update_options_trade_notes(opos["id"], new_notes)
                        st.toast("Notes saved")
                        st.rerun()
    else:
        ui_theme.empty_state("No open options positions.")

    st.divider()

    # ── Closed Options Trades ────────────────────────────────────────
    ui_theme.section_header("Closed Options Trades")

    opt_history = get_closed_options_trades(limit=200)
    if opt_history:
        odf = pd.DataFrame(opt_history)

        # Equity curve
        odf_sorted = odf.sort_values("closed_at")
        odf_sorted["cumulative_pnl"] = odf_sorted["pnl"].cumsum()
        odf_sorted["trade_num"] = range(1, len(odf_sorted) + 1)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=odf_sorted["trade_num"], y=odf_sorted["cumulative_pnl"],
            mode="lines+markers", name="Cumulative P&L",
            line=dict(color="#9b59b6", width=2),
            hovertemplate=(
                "Trade #%{x}<br>"
                "%{customdata[0]} %{customdata[1]}<br>"
                "P&L: $%{customdata[2]:,.2f}<br>"
                "Cumulative: $%{y:,.2f}<extra></extra>"
            ),
            customdata=list(zip(
                odf_sorted["symbol"], odf_sorted["option_type"], odf_sorted["pnl"],
            )),
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.update_layout(
            height=400,
            xaxis_title="Trade #",
            yaxis_title="Cumulative P&L ($)",
            title="Options Equity Curve",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Trade history table
        st.markdown("**Options Trade History**")
        opt_cols = [
            "symbol", "option_type", "strike", "expiration", "contracts",
            "premium_per_contract", "entry_cost", "exit_premium",
            "exit_proceeds", "pnl", "status", "session_date", "notes",
        ]
        opt_rename = {
            "symbol": "Symbol", "option_type": "Type", "strike": "Strike",
            "expiration": "Expiry", "contracts": "Contracts",
            "premium_per_contract": "Premium", "entry_cost": "Entry Cost",
            "exit_premium": "Exit Prem", "exit_proceeds": "Proceeds",
            "pnl": "P&L", "status": "Status",
            "session_date": "Date", "notes": "Notes",
        }
        odf_display = odf_sorted[[c for c in opt_cols if c in odf_sorted.columns]].copy()
        odf_display = odf_display.rename(columns=opt_rename)
        st.dataframe(
            odf_display.set_index("Symbol").style.format({
                "Strike": "${:,.2f}", "Premium": "${:,.2f}",
                "Entry Cost": "${:,.2f}", "Exit Prem": "${:,.2f}",
                "Proceeds": "${:,.2f}", "P&L": "${:,.2f}",
            }),
            use_container_width=True,
        )
    else:
        ui_theme.empty_state("No closed options trades yet.")

else:
    # =====================================================================
    # EQUITY TRADES (All / Intraday / Swing)
    # =====================================================================

    # ── 1. Performance Summary ───────────────────────────────────────
    ui_theme.section_header("Performance Summary")

    stats = get_real_trade_stats(trade_type=type_param)
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

    # Options summary when viewing All
    if trade_filter == "All":
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
                        delta=f"${_opt_stats['total_pnl']:+,.2f}", delta_color=_opnl_color)
            oc2.metric("Options Win Rate", f"{_opt_stats['win_rate']:.1f}%")
            oc3.metric("Options Trades", f"{_opt_stats['total_trades']}")

    st.divider()

    # ── 2. Open Positions ────────────────────────────────────────────
    ui_theme.section_header("Open Positions")

    positions = get_open_trades(trade_type=type_param)
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

    # ── 3. Closed Trades ─────────────────────────────────────────────
    ui_theme.section_header("Closed Trades")

    history = get_closed_trades(limit=200, trade_type=type_param)
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

        # ── Trade History — Grouped by Day ────────────────────────────
        st.markdown("**Trade History**")

        # Build column list
        base_cols = [
            "symbol", "direction", "shares", "entry_price", "exit_price",
            "pnl", "status", "alert_type", "session_date", "notes",
        ]
        rename_map = {
            "symbol": "Symbol", "direction": "Direction", "shares": "Shares",
            "entry_price": "Entry", "exit_price": "Exit",
            "pnl": "P&L", "status": "Status",
            "alert_type": "Signal", "session_date": "Date", "notes": "Notes",
        }
        if type_param != "intraday":
            for col in ("trade_type", "stop_type", "target_type"):
                if col in df_sorted.columns:
                    base_cols.append(col)
                    rename_map[col] = col.replace("_", " ").title()

        # Group by session_date (most recent first)
        df_by_day = df_sorted.copy()
        df_by_day["_session"] = df_by_day["session_date"].fillna("")
        day_groups = df_by_day.groupby("_session", sort=False)

        # Sort days descending
        day_order = sorted(day_groups.groups.keys(), reverse=True)

        for day_date in day_order:
            day_df = day_groups.get_group(day_date)
            day_pnl = day_df["pnl"].sum()
            day_wins = len(day_df[day_df["pnl"] > 0])
            day_losses = len(day_df[day_df["pnl"] <= 0])
            n_trades = len(day_df)

            pnl_sign = "+" if day_pnl >= 0 else ""
            pnl_color = "#2ecc71" if day_pnl >= 0 else "#e74c3c"
            wr = round(day_wins / n_trades * 100) if n_trades else 0

            header = (
                f"{day_date or 'Unknown'} — "
                f"{n_trades} trade{'s' if n_trades != 1 else ''} | "
                f"{day_wins}W/{day_losses}L ({wr}%) | "
                f"P&L: {pnl_sign}${day_pnl:,.2f}"
            )

            with st.expander(header, expanded=(day_date == day_order[0])):
                # Day summary metrics
                dc1, dc2, dc3, dc4 = st.columns(4)
                with dc1:
                    st.metric("Trades", n_trades)
                with dc2:
                    st.metric("Win Rate", f"{wr}%")
                with dc3:
                    st.metric("Day P&L", f"${day_pnl:+,.2f}")
                with dc4:
                    symbols = ", ".join(day_df["symbol"].unique())
                    st.metric("Symbols", symbols)

                # Day's trade table
                display_cols = [c for c in base_cols if c in day_df.columns and c != "session_date"]
                day_display = day_df[display_cols].copy()
                day_rename = {k: v for k, v in rename_map.items() if k in display_cols}
                day_display = day_display.rename(columns=day_rename)
                st.dataframe(
                    day_display.set_index("Symbol").style.format({
                        "Entry": "${:,.2f}", "Exit": "${:,.2f}", "P&L": "${:,.2f}",
                    }),
                    use_container_width=True,
                )
    else:
        ui_theme.empty_state("No closed trades yet.")

# =====================================================================
# BACKUP & RESTORE (always visible regardless of trade type filter)
# =====================================================================
st.divider()
ui_theme.section_header("Backup & Restore")
st.caption("Download trades as CSV before a restart. Upload to restore after.")

dl_col1, dl_col2 = st.columns(2)

with dl_col1:
    with get_db() as conn:
        eq_df = _pd_read_sql("SELECT * FROM real_trades ORDER BY opened_at DESC", conn)
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
        opt_df = _pd_read_sql("SELECT * FROM real_options_trades ORDER BY opened_at DESC", conn)
    st.download_button(
        "Download Options Trades CSV",
        data=opt_df.to_csv(index=False).encode(),
        file_name="real_options_trades_backup.csv",
        mime="text/csv",
        disabled=opt_df.empty,
    )
    st.caption(f"{len(opt_df)} options trades")

# ── Upload / Restore ──────────────────────────────────────────────────
with st.expander("Restore from CSV"):
    uploaded = st.file_uploader(
        "Upload a backup CSV (equity or options)",
        type=["csv"],
        key="trade_restore_upload",
    )
    if uploaded:
        restore_df = pd.read_csv(uploaded)
        st.dataframe(restore_df.head(10), use_container_width=True)
        st.caption(f"{len(restore_df)} rows found in file")

        # Detect which table based on columns
        is_options = "option_type" in restore_df.columns and "strike" in restore_df.columns
        table_name = "real_options_trades" if is_options else "real_trades"

        st.warning(
            f"This will insert **{len(restore_df)} rows** into `{table_name}`. "
            "Duplicate rows (same id) will be skipped."
        )

        if st.button("Restore Trades", type="primary"):
            inserted = 0
            skipped = 0
            with get_db() as conn:
                cols = [c for c in restore_df.columns if c != "id"]
                placeholders = ", ".join(["?"] * len(cols))
                col_names = ", ".join(cols)
                for _, row in restore_df.iterrows():
                    try:
                        conn.execute(
                            f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})",
                            tuple(None if pd.isna(v) else v for v in row[cols]),
                        )
                        inserted += 1
                    except Exception:
                        skipped += 1
            st.success(f"Restored {inserted} trades ({skipped} skipped/duplicates)")
            st.rerun()
