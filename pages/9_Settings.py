"""Settings — notification config status (single-user mode)."""

from __future__ import annotations

import streamlit as st

from alert_config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from analytics.intraday_rules import AlertSignal, AlertType
from alerting.notifier import notify
import ui_theme

ui_theme.setup_page("settings")

ui_theme.page_header("Settings", "Notification configuration status.")

# ---------------------------------------------------------------------------
# Global Telegram Config (from .env)
# ---------------------------------------------------------------------------

ui_theme.section_header("Telegram (Global)")

if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    st.success(f"Telegram configured — group chat ID: `{TELEGRAM_CHAT_ID}`")
else:
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    st.warning(f"Missing in `.env`: {', '.join(missing)}")

st.caption("Telegram alerts go to the global group chat. Edit `.env` to change the bot token or chat ID.")

# ---------------------------------------------------------------------------
# Test Notification
# ---------------------------------------------------------------------------

st.divider()
ui_theme.section_header("Test Notifications")
st.caption("Send a test alert to verify your notification settings.")

if st.button("Send Test Alert"):
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

    with st.spinner("Sending test notifications..."):
        email_ok, telegram_ok = notify(test_signal)

    if telegram_ok:
        st.success("Test Telegram message sent!")
    else:
        st.warning("Telegram failed — check `.env` config.")

    if email_ok:
        st.success("Test email sent!")

    if not telegram_ok and not email_ok:
        st.info("No notifications sent — check `.env` for TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.")
