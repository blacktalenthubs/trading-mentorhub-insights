"""Trade Journal — monthly report of all taken and skipped trades."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from analytics.monthly_report import get_monthly_trades, format_monthly_report
import ui_theme


user = ui_theme.setup_page("journal")

ui_theme.page_header("Trade Journal", "Monthly trade performance report with pattern breakdown.")

# ── Sidebar Controls ──────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("Report Settings")
    today = date.today()
    year = st.selectbox("Year", [today.year, today.year - 1], index=0)
    month = st.selectbox(
        "Month",
        list(range(1, 13)),
        index=today.month - 1,
        format_func=lambda m: date(2026, m, 1).strftime("%B"),
    )
    view = st.radio("View", ["Summary", "Took It (trades)", "Skipped", "Full Report"])

# ── Load Data ─────────────────────────────────────────────────────────────

data = get_monthly_trades(year, month)
s = data["summary"]
month_name = date(year, month, 1).strftime("%B %Y")

# ── Summary Cards ─────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("Trades Taken", s["total_trades"])
col2.metric("Win Rate", f"{s['win_rate']:.0f}%")
col3.metric("Total P&L", f"${s['total_pnl']:+,.2f}")
col4.metric("Skipped", s["total_skipped"])

col5, col6, col7, col8 = st.columns(4)
col5.metric("Winners", s["winners"])
col6.metric("Losers", s["losers"])
col7.metric("Avg Win", f"${s['avg_win']:+,.2f}")
col8.metric("Avg Loss", f"${s['avg_loss']:+,.2f}")

st.divider()

# ── Views ─────────────────────────────────────────────────────────────────

if view == "Summary":
    # Pattern performance
    if s["pattern_stats"]:
        st.subheader("Pattern Performance")
        pat_rows = []
        for pat, stats in s["pattern_stats"].items():
            total = stats["wins"] + stats["losses"]
            pat_rows.append({
                "Pattern": pat.replace("_", " ").title(),
                "Wins": stats["wins"],
                "Losses": stats["losses"],
                "Win Rate": f"{stats['wins'] / total * 100:.0f}%" if total > 0 else "—",
                "P&L": stats["total_pnl"],
            })
        pat_df = pd.DataFrame(pat_rows).sort_values("P&L", ascending=False)
        st.dataframe(
            pat_df, use_container_width=True, hide_index=True,
            column_config={"P&L": st.column_config.NumberColumn(format="$%.2f")},
        )

    # Daily P&L chart
    if s["daily_pnl"]:
        st.subheader("Daily P&L")
        daily_df = pd.DataFrame([
            {"Date": d, "P&L": p} for d, p in sorted(s["daily_pnl"].items())
        ])
        daily_df["Cumulative"] = daily_df["P&L"].cumsum()
        st.line_chart(daily_df.set_index("Date")["Cumulative"])

        st.dataframe(
            daily_df, use_container_width=True, hide_index=True,
            column_config={
                "P&L": st.column_config.NumberColumn(format="$%.2f"),
                "Cumulative": st.column_config.NumberColumn(format="$%.2f"),
            },
        )

elif view == "Took It (trades)":
    st.subheader(f"Trades Taken — {month_name}")
    if data["took_trades"]:
        trades_df = pd.DataFrame(data["took_trades"])
        display_cols = [
            "session_date", "symbol", "direction", "alert_type",
            "entry_price", "exit_price", "pnl", "status", "shares",
        ]
        available = [c for c in display_cols if c in trades_df.columns]
        st.dataframe(
            trades_df[available], use_container_width=True, hide_index=True,
            column_config={
                "entry_price": st.column_config.NumberColumn("Entry", format="$%.2f"),
                "exit_price": st.column_config.NumberColumn("Exit", format="$%.2f"),
                "pnl": st.column_config.NumberColumn("P&L", format="$%.2f"),
            },
        )
    else:
        st.info("No trades taken this month.")

elif view == "Skipped":
    st.subheader(f"Skipped Alerts — {month_name}")
    if data["skipped_alerts"]:
        skip_df = pd.DataFrame(data["skipped_alerts"])
        display_cols = [
            "session_date", "symbol", "direction", "alert_type",
            "price", "entry", "stop", "target_1", "score",
        ]
        available = [c for c in display_cols if c in skip_df.columns]
        st.dataframe(
            skip_df[available], use_container_width=True, hide_index=True,
            column_config={
                "price": st.column_config.NumberColumn("Price", format="$%.2f"),
                "entry": st.column_config.NumberColumn("Entry", format="$%.2f"),
                "stop": st.column_config.NumberColumn("Stop", format="$%.2f"),
                "target_1": st.column_config.NumberColumn("T1", format="$%.2f"),
            },
        )

        # What-if analysis: how would skipped alerts have performed?
        st.caption(
            "Use the Backtest page to replay skipped alerts "
            "and see if they would have hit T1/T2 or stopped out."
        )
    else:
        st.info("No skipped alerts this month.")

elif view == "Full Report":
    st.subheader(f"Full Report — {month_name}")
    report_text = format_monthly_report(year, month)
    st.code(report_text, language="text")

    # Download button
    st.download_button(
        "Download Report (.txt)",
        report_text,
        file_name=f"trade_journal_{year}_{month:02d}.txt",
        mime="text/plain",
    )
