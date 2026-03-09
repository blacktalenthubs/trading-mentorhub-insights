"""Settings — per-user notification preferences."""

from __future__ import annotations

import streamlit as st

from analytics.intraday_rules import AlertSignal, AlertType
from db import get_notification_prefs, upsert_notification_prefs
import ui_theme

user = ui_theme.setup_page("settings", require_login=True)

ui_theme.page_header("Settings", "Configure your notification preferences.")

# ---------------------------------------------------------------------------
# Load current prefs
# ---------------------------------------------------------------------------

prefs = get_notification_prefs(user["id"]) or {
    "telegram_chat_id": "",
    "notification_email": user.get("email", ""),
    "telegram_enabled": 1,
    "email_enabled": 1,
}

# ---------------------------------------------------------------------------
# Notification Preferences Form
# ---------------------------------------------------------------------------

ui_theme.section_header("Notification Preferences")

with st.form("notification_prefs"):
    st.markdown("**Telegram**")
    telegram_chat_id = st.text_input(
        "Telegram Chat ID",
        value=prefs.get("telegram_chat_id", ""),
        help="Your personal Telegram chat ID. Message @userinfobot on Telegram to get it.",
    )
    telegram_enabled = st.checkbox(
        "Enable Telegram notifications",
        value=bool(prefs.get("telegram_enabled", 1)),
    )

    st.markdown("---")
    st.markdown("**Claude AI (Trade Narrator)**")
    anthropic_api_key = st.text_input(
        "Anthropic API Key",
        value=prefs.get("anthropic_api_key", ""),
        type="password",
        help="Your Anthropic API key for AI trade narratives. Get one at console.anthropic.com.",
    )

    st.markdown("---")
    st.markdown("**Email**")
    notification_email = st.text_input(
        "Notification Email",
        value=prefs.get("notification_email", "") or user.get("email", ""),
        help="Email address for alert notifications.",
    )
    email_enabled = st.checkbox(
        "Enable email notifications",
        value=bool(prefs.get("email_enabled", 1)),
    )

    submitted = st.form_submit_button("Save Preferences", use_container_width=True)

if submitted:
    upsert_notification_prefs(
        user["id"],
        telegram_chat_id=telegram_chat_id.strip(),
        notification_email=notification_email.strip(),
        telegram_enabled=telegram_enabled,
        email_enabled=email_enabled,
        anthropic_api_key=anthropic_api_key.strip(),
    )
    st.success("Preferences saved.")
    st.rerun()

# ---------------------------------------------------------------------------
# How to get your Telegram Chat ID
# ---------------------------------------------------------------------------

with st.expander("How to get your Telegram Chat ID"):
    st.markdown("""
1. Open Telegram and search for **@userinfobot**
2. Start a conversation and send `/start`
3. The bot replies with your **Chat ID** (a number like `123456789`)
4. Paste that number in the field above

**Note:** The bot token is shared (configured by the app admin).
Each user only needs their own Chat ID to receive personal notifications.
""")

# ---------------------------------------------------------------------------
# Test Notification
# ---------------------------------------------------------------------------

st.divider()
ui_theme.section_header("Test Notifications")
st.caption("Send a test alert to verify your notification settings.")

if st.button("Send Test Alert"):
    from alerting.notifier import notify_user

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
        message="Test alert from TradeSignal Settings — ignore this message",
    )

    current_prefs = get_notification_prefs(user["id"])
    if not current_prefs:
        st.warning("Save your preferences first before testing.")
    else:
        with st.spinner("Sending test notifications..."):
            email_ok, telegram_ok = notify_user(test_signal, current_prefs)

        if telegram_ok:
            st.success("Test Telegram message sent!")
        elif current_prefs.get("telegram_enabled") and current_prefs.get("telegram_chat_id"):
            st.warning("Telegram failed — check your Chat ID and bot token config.")

        if email_ok:
            st.success("Test email sent!")
        elif current_prefs.get("email_enabled") and current_prefs.get("notification_email"):
            st.warning("Email failed — check SMTP settings in .env.")

        if not telegram_ok and not email_ok:
            st.info("No notifications sent — enable at least one channel and provide the required ID/email.")
