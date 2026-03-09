"""Settings — Profile, Notifications, Subscription management."""

from __future__ import annotations

import streamlit as st

import ui_theme
from db import (
    get_notification_prefs,
    get_subscription,
    get_user_tier,
    get_watchlist,
    set_watchlist,
    upsert_notification_prefs,
)

user = ui_theme.setup_page("settings", tier_required="free")

ui_theme.page_header("Settings")

tier = get_user_tier(user["id"])
is_admin = tier == "admin"

if is_admin:
    tab_profile, tab_notifications, tab_subscription = st.tabs(
        ["Profile", "Notifications", "Subscription"]
    )
else:
    tab_profile, tab_subscription = st.tabs(
        ["Profile", "Subscription"]
    )

# ── Profile ──────────────────────────────────────────────────────────────────

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

    # Watchlist — admin only (admin watchlist is the global alert watchlist)
    if is_admin:
        st.divider()
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

# ── Notifications (admin only) ──────────────────────────────────────────────

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
                email_ok, tg_ok = notify(test_signal)

            if tg_ok:
                st.success("Test alert sent to Telegram group")
            else:
                st.error("Telegram failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")

            if email_ok:
                st.success("Test email also sent")

# ── Subscription ─────────────────────────────────────────────────────────────

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
