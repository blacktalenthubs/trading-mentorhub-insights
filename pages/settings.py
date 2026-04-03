"""Settings — Profile, Import Data, Watchlist, Notifications, Subscription."""

from __future__ import annotations

import os
import tempfile

import pandas as pd
import streamlit as st

import ui_theme
from ui_theme import get_current_tier, render_inline_upgrade
from db import (
    check_import_exists,
    create_import,
    delete_import,
    get_imports,
    get_notification_prefs,
    get_subscription,
    get_user_tier,
    get_watchlist,
    insert_account_summary,
    insert_matched_trades,
    insert_trades_1099,
    insert_trades_monthly,
    set_watchlist,
    update_import_count,
    upsert_notification_prefs,
)
from models import ImportRecord
from parsers.parser_1099 import parse_1099
from parsers.parser_statement import parse_statement
from analytics.trade_matcher import match_trades_fifo

user = ui_theme.setup_page("settings", tier_required="free")

ui_theme.page_header("Settings")

tier = get_user_tier(user["id"])
is_admin = tier == "admin"

# ── Build tabs based on role ─────────────────────────────────────────────

if is_admin:
    tab_profile, tab_import, tab_watchlist, tab_notifications, tab_subscription = st.tabs(
        ["Profile", "Import Data", "Watchlist", "Notifications", "Subscription"]
    )
else:
    tab_profile, tab_import, tab_subscription = st.tabs(
        ["Profile", "Import Data", "Subscription"]
    )

# ── Profile Tab ──────────────────────────────────────────────────────────

with tab_profile:
    ui_theme.section_header("Profile")

    st.text_input("Email", value=user["email"], disabled=True)

    new_name = st.text_input("Display Name", value=user["display_name"] or "")
    if st.button("Save Profile", key="save_profile"):
        if new_name.strip():
            from db import get_db
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET display_name = ? WHERE id = ?",
                    (new_name.strip(), user["id"]),
                )
            st.success("Profile updated.")
            st.rerun()
        else:
            st.error("Display name cannot be empty.")

    st.divider()
    ui_theme.section_header("Change Password")

    with st.form("change_password_form"):
        current_pw = st.text_input("Current Password", type="password", key="cur_pw")
        new_pw = st.text_input("New Password", type="password", key="new_pw")
        confirm_pw = st.text_input("Confirm New Password", type="password", key="confirm_pw")
        pw_submitted = st.form_submit_button("Change Password", use_container_width=True)

    if pw_submitted:
        if not current_pw or not new_pw or not confirm_pw:
            st.error("Please fill in all password fields.")
        elif new_pw != confirm_pw:
            st.error("New passwords do not match.")
        elif len(new_pw) < 6:
            st.error("New password must be at least 6 characters.")
        else:
            from auth import change_password
            ok, msg = change_password(user["id"], current_pw, new_pw)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

# ── Import Data Tab ──────────────────────────────────────────────────────

with tab_import:
    current_tier = get_current_tier()
    if current_tier not in ("pro", "elite", "admin"):
        ui_theme.section_header("Import Data")
        render_inline_upgrade(
            "Import Data is a Pro feature. Upgrade to import PDFs and track your trades.",
            required_tier="pro",
        )
    else:
        # --- File Upload ---
        ui_theme.section_header("Upload PDF")
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
                                if st.button("Confirm Import", type="primary", key="confirm_import_1099"):
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

                                if st.button("Confirm Import", type="primary", key="confirm_import_monthly"):
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
        ui_theme.section_header("Import History")

        imports_df = get_imports(user["id"])
        if imports_df.empty:
            ui_theme.empty_state("No imports yet.")
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
                if st.button("Delete", type="secondary", key="delete_import"):
                    delete_import(selected, user["id"])
                    st.success("Import deleted.")
                    st.rerun()

# ── Watchlist Tab (admin only) ───────────────────────────────────────────

if is_admin:
    with tab_watchlist:
        ui_theme.section_header("Watchlist")
        st.caption("This watchlist controls which symbols the monitor alerts on.")
        current_watchlist = get_watchlist(user["id"])
        watchlist_text = st.text_area(
            "Symbols (one per line or comma-separated)",
            value=", ".join(current_watchlist),
            height=100,
        )
        if st.button("Save Watchlist", key="save_watchlist"):
            symbols = [
                s.strip().upper()
                for s in watchlist_text.replace("\n", ",").split(",")
                if s.strip()
            ]
            if symbols:
                set_watchlist(symbols, user["id"])
                st.session_state.pop("watchlist", None)
                st.success(f"Watchlist updated: {', '.join(symbols)}")
            else:
                st.error("Please enter at least one symbol.")

# ── Notifications Tab (admin only) ───────────────────────────────────────

if is_admin:
    with tab_notifications:
        ui_theme.section_header("Notification Preferences")

        prefs = get_notification_prefs(user["id"]) or {}

        email_enabled = st.toggle(
            "Email Alerts",
            value=bool(prefs.get("email_enabled", 1)),
            key="notif_email",
        )
        notif_email = st.text_input(
            "Alert Email",
            value=prefs.get("notification_email", user["email"]),
            key="notif_email_addr",
        )

        st.divider()
        st.markdown("**Telegram Group Alerts**")
        st.info(
            "Alerts are sent to the Telegram group via TELEGRAM_CHAT_ID. "
            "Add users to the group manually to give them access."
        )

        if st.button("Save Notification Settings", key="save_notif"):
            upsert_notification_prefs(
                user["id"],
                telegram_chat_id=prefs.get("telegram_chat_id", ""),
                notification_email=notif_email,
                telegram_enabled=True,
                email_enabled=email_enabled,
            )
            st.success("Notification settings saved.")

        st.divider()
        st.markdown("**Test Notifications**")
        st.caption("Send a test alert to the Telegram group to verify delivery.")

        if st.button("Send Test Alert", key="send_test_notif"):
            from analytics.intraday_rules import AlertSignal, AlertType
            from alerting.notifier import notify
            from alerting.alert_store import record_alert, today_session

            test_signal = AlertSignal(
                symbol="TEST",
                alert_type=AlertType.MA_BOUNCE_20,
                direction="BUY",
                price=100.00,
                entry=100.00,
                stop=99.00,
                target_1=101.00,
                target_2=102.00,
                confidence="high",
                message="Test alert from TradeCoPilot — ignore this message",
            )

            with st.spinner("Sending test alert..."):
                alert_id = record_alert(test_signal, today_session(), user_id=user["id"])
                email_ok, tg_ok = notify(test_signal, alert_id=alert_id)

            if tg_ok:
                st.success("Test alert sent to Telegram group")
            else:
                st.error("Telegram failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")

            if email_ok:
                st.success("Test email also sent")

        st.divider()
        ui_theme.section_header("Trading Style & Alert Preferences")
        st.caption(
            "Choose which trading patterns you want alerts for. "
            "Disabled patterns are still recorded to the dashboard — just no Telegram push."
        )

        from alert_config import ALERT_CATEGORIES
        from db import get_alert_category_prefs, upsert_alert_category_prefs, get_min_alert_score, set_min_alert_score

        cat_prefs = get_alert_category_prefs(user["id"])
        current_min_score = get_min_alert_score(user["id"])

        # Trading pattern toggles — organized by trading style
        _new_prefs: dict[str, bool] = {}

        st.markdown("**Entry Patterns**")
        col1, col2 = st.columns(2)
        with col1:
            _new_prefs["entry_signals"] = st.toggle(
                "Support Bounces & Reclaims",
                value=cat_prefs.get("entry_signals", True),
                help="MA/EMA bounces, PDL reclaim, double bottoms, fib bounce, VWAP reclaim",
                key="cat_entry_signals",
            )
            _new_prefs["breakout_signals"] = st.toggle(
                "Breakouts",
                value=cat_prefs.get("breakout_signals", True),
                help="PDH breakout, consolidation breakout, inside day breakout, gap and go",
                key="cat_breakout_signals",
            )
        with col2:
            _new_prefs["short_signals"] = st.toggle(
                "Short / Rejection Setups",
                value=cat_prefs.get("short_signals", True),
                help="EMA rejection, double top, breakdown, VWAP loss",
                key="cat_short_signals",
            )
            _new_prefs["swing_trade"] = st.toggle(
                "Swing Trade Setups",
                value=cat_prefs.get("swing_trade", True),
                help="RSI zones, MACD crossover, EMA crossover, bull flags, multi-day patterns",
                key="cat_swing_trade",
            )

        st.markdown("**Trade Management**")
        col3, col4 = st.columns(2)
        with col3:
            _new_prefs["exit_alerts"] = st.toggle(
                "Exit Alerts (T1/T2/Stop)",
                value=cat_prefs.get("exit_alerts", True),
                help="Target hits, stop losses — always recommended ON",
                key="cat_exit_alerts",
            )
            _new_prefs["resistance_warnings"] = st.toggle(
                "Resistance Warnings",
                value=cat_prefs.get("resistance_warnings", True),
                help="Approaching PDH, MA resistance, weekly/monthly highs",
                key="cat_resistance_warnings",
            )
        with col4:
            _new_prefs["support_warnings"] = st.toggle(
                "Support Warnings",
                value=cat_prefs.get("support_warnings", True),
                help="PDL breakdown, support loss, weekly/monthly low breaks",
                key="cat_support_warnings",
            )
            _new_prefs["informational"] = st.toggle(
                "Market Context",
                value=cat_prefs.get("informational", True),
                help="First hour summary, consolidation notices, monthly EMA touch",
                key="cat_informational",
            )

        st.markdown("")

        # Score filter
        new_min_score = st.slider(
            "Minimum Alert Score",
            min_value=0,
            max_value=100,
            value=current_min_score,
            step=5,
            help="Only send alerts with score above this threshold. Exit alerts (T1/T2/Stop) always send regardless.",
            key="min_score_slider",
        )

        if st.button("Save Alert Preferences", key="save_alert_prefs"):
            for cat_id, enabled in _new_prefs.items():
                upsert_alert_category_prefs(user["id"], cat_id, enabled)
            set_min_alert_score(user["id"], new_min_score)
            st.success("Alert preferences saved. Changes take effect on the next poll cycle.")

# ── Subscription Tab ─────────────────────────────────────────────────────

with tab_subscription:
    ui_theme.section_header("Your Subscription")

    sub = get_subscription(user["id"])
    display_tier = sub["tier"] if sub else ("admin" if is_admin else "free")
    color = ui_theme.TIER_COLORS.get(display_tier, "#888")

    st.markdown(
        f"<div style='margin-bottom:1rem'>"
        f"<span style='background:{color};color:white;padding:4px 12px;"
        f"border-radius:4px;font-size:0.9rem;font-weight:600;"
        f"text-transform:uppercase'>{display_tier}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Show current tier features
    features = ui_theme.TIER_FEATURES.get(display_tier, [])
    for f in features:
        st.markdown(f"&#10003; {f}")

    if not is_admin:
        st.divider()

        if display_tier != "elite":
            st.markdown("**Upgrade Your Plan**")
            upgrade_cols = st.columns(2)

            if display_tier == "free":
                with upgrade_cols[0]:
                    st.markdown(
                        "<div style='background:#16213e;border:1px solid #3498db40;"
                        "border-radius:8px;padding:1rem;text-align:center'>"
                        "<div style='font-weight:600;color:#3498db'>Pro</div>"
                        "<div style='font-size:1.5rem;font-weight:700;color:#fafafa'>$29<span style='font-size:0.8rem;color:#888'>/mo</span></div>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
            with upgrade_cols[-1]:
                st.markdown(
                    "<div style='background:#16213e;border:1px solid #f39c1240;"
                    "border-radius:8px;padding:1rem;text-align:center'>"
                    "<div style='font-weight:600;color:#f39c12'>Elite</div>"
                    "<div style='font-size:1.5rem;font-weight:700;color:#fafafa'>$59<span style='font-size:0.8rem;color:#888'>/mo</span></div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("")
            st.link_button(
                "Subscribe Now \u2192",
                "https://square.link/u/FdEAnalM",
                use_container_width=True,
            )
            st.caption("Powered by Square \u00b7 Secure checkout")
        else:
            st.success("You have the highest tier. All features are unlocked.")
