"""Import page - Upload PDFs, parse, preview, confirm import."""

import os
import tempfile

import streamlit as st
import pandas as pd

from db import (
    init_db, check_import_exists, create_import, update_import_count,
    insert_trades_1099, insert_trades_monthly, insert_account_summary,
    get_imports, delete_import, insert_matched_trades,
)
from models import ImportRecord
from parsers.parser_1099 import parse_1099
from parsers.parser_statement import parse_statement
from analytics.trade_matcher import match_trades_fifo
from auth import auto_login

init_db()
user = auto_login()
st.title("Import Data")

# --- File Upload ---
st.subheader("Upload PDF")
file_type = st.radio("Document Type", ["1099 (Annual)", "Monthly Statement"], horizontal=True)

uploaded = st.file_uploader("Choose a PDF file", type=["pdf"])

if uploaded:
    # Save to temp file for pdftotext
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name

    try:
        # Check for duplicate
        ft = "1099" if "1099" in file_type else "monthly_statement"
        if check_import_exists(uploaded.name, ft, user["id"]):
            st.warning(f"'{uploaded.name}' has already been imported as {ft}. "
                       "Delete the previous import first if you want to re-import.")
        else:
            with st.spinner("Parsing PDF..."):
                if ft == "1099":
                    trades = parse_1099(tmp_path)
                    st.success(f"Parsed {len(trades)} trades from 1099.")

                    # Preview
                    if trades:
                        preview_data = []
                        for t in trades[:50]:
                            preview_data.append({
                                "Account": t.account,
                                "Symbol": t.symbol,
                                "Date Sold": t.date_sold.isoformat(),
                                "Proceeds": t.proceeds,
                                "Cost Basis": t.cost_basis,
                                "P&L": t.gain_loss,
                                "Wash Sale": t.wash_sale_disallowed,
                                "Type": t.asset_type,
                                "Category": t.category,
                            })
                        preview_df = pd.DataFrame(preview_data)
                        st.markdown(f"**Preview** (first {min(50, len(trades))} of {len(trades)} trades)")
                        st.dataframe(preview_df.style.format({
                            "Proceeds": "${:,.2f}",
                            "Cost Basis": "${:,.2f}",
                            "P&L": "${:,.2f}",
                            "Wash Sale": "${:,.2f}",
                        }), use_container_width=True, height=400)

                        # Summary stats
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Total Trades", len(trades))
                        col2.metric("Total P&L", f"${sum(t.gain_loss for t in trades):,.2f}")
                        col3.metric("Total Wash", f"${sum(t.wash_sale_disallowed for t in trades):,.2f}")
                        from collections import Counter
                        accts = Counter(t.account for t in trades)
                        col4.metric("Accounts", len(accts))

                        # Confirm import
                        if st.button("Confirm Import", type="primary"):
                            period = str(trades[0].date_sold.year)
                            record = ImportRecord(
                                filename=uploaded.name,
                                file_type=ft,
                                period=period,
                                records_imported=len(trades),
                            )
                            import_id = create_import(record, user["id"])
                            insert_trades_1099(trades, import_id, user["id"])
                            update_import_count(import_id, len(trades))
                            st.success(f"Imported {len(trades)} trades!")
                            st.rerun()

                else:  # monthly statement
                    trades, summaries = parse_statement(tmp_path)
                    st.success(f"Parsed {len(trades)} trades and {len(summaries)} account summaries.")

                    if trades:
                        preview_data = []
                        for t in trades[:50]:
                            preview_data.append({
                                "Account": t.account,
                                "Symbol": t.symbol,
                                "Type": t.transaction_type,
                                "Date": t.trade_date.isoformat(),
                                "Qty": t.quantity,
                                "Price": t.price,
                                "Amount": t.amount,
                                "Asset": t.asset_type,
                                "Recurring": t.is_recurring,
                            })
                        preview_df = pd.DataFrame(preview_data)
                        st.markdown(f"**Preview** (first {min(50, len(trades))} of {len(trades)} trades)")
                        st.dataframe(preview_df.style.format({
                            "Price": "${:,.2f}",
                            "Amount": "${:,.2f}",
                            "Qty": "{:,.4f}",
                        }), use_container_width=True, height=400)

                        # FIFO matching preview
                        non_recurring = [t for t in trades if not t.is_recurring]
                        matched = match_trades_fifo(non_recurring)
                        if matched:
                            st.markdown(f"**FIFO Matched Trades:** {len(matched)} pairs")
                            match_preview = []
                            for m in matched[:20]:
                                match_preview.append({
                                    "Symbol": m.symbol,
                                    "Buy Date": m.buy_date.isoformat(),
                                    "Sell Date": m.sell_date.isoformat(),
                                    "Qty": m.quantity,
                                    "Buy Price": m.buy_price,
                                    "Sell Price": m.sell_price,
                                    "P&L": m.realized_pnl,
                                    "Hold Days": m.holding_days,
                                })
                            st.dataframe(pd.DataFrame(match_preview).style.format({
                                "Buy Price": "${:,.2f}",
                                "Sell Price": "${:,.2f}",
                                "P&L": "${:,.2f}",
                                "Qty": "{:,.4f}",
                            }), use_container_width=True)

                        if st.button("Confirm Import", type="primary"):
                            # Determine period
                            if trades:
                                dates = [t.trade_date for t in trades]
                                period = max(dates).strftime("%Y-%m")
                            else:
                                period = "unknown"

                            record = ImportRecord(
                                filename=uploaded.name,
                                file_type=ft,
                                period=period,
                                records_imported=len(trades),
                            )
                            import_id = create_import(record, user["id"])
                            insert_trades_monthly(trades, import_id, user["id"])
                            for s in summaries:
                                insert_account_summary(s, import_id, user["id"])

                            # Also save matched trades
                            if matched:
                                insert_matched_trades(matched, user["id"])

                            update_import_count(import_id, len(trades))
                            st.success(f"Imported {len(trades)} trades + {len(summaries)} summaries + {len(matched)} matched trades!")
                            st.rerun()
    finally:
        os.unlink(tmp_path)

# --- Import History ---
st.divider()
st.subheader("Import History")

imports_df = get_imports(user["id"])
if imports_df.empty:
    st.info("No imports yet.")
else:
    st.dataframe(imports_df[["id", "filename", "file_type", "period", "records_imported", "imported_at"]],
                 use_container_width=True)

    # Delete import
    with st.expander("Delete an import"):
        import_ids = imports_df["id"].tolist()
        labels = [f"#{r['id']} - {r['filename']} ({r['file_type']}, {r['records_imported']} records)"
                  for _, r in imports_df.iterrows()]
        selected = st.selectbox("Select import to delete", options=import_ids,
                                format_func=lambda x: labels[import_ids.index(x)])
        if st.button("Delete", type="secondary"):
            delete_import(selected, user["id"])
            st.success("Import deleted.")
            st.rerun()
