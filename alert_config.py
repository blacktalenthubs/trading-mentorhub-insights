"""Alert system configuration — watchlist, thresholds, credentials."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Read from env vars first (.env / local), then Streamlit secrets (Cloud)."""
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

ALERT_WATCHLIST = [
    "LRCX", "PLTR", "ONDS", "META", "TSLA",
    "NVDA", "GOOGL", "SPY", "AAPL", "AMD",
]

# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

POLL_INTERVAL_MINUTES = 3

# Market hours (US Eastern)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# ---------------------------------------------------------------------------
# Rule thresholds
# ---------------------------------------------------------------------------

# MA Bounce: bar low must be within this % of the MA to qualify
MA_BOUNCE_PROXIMITY_PCT = 0.003  # 0.3%

# MA Bounce: stop offset below the MA
MA_STOP_OFFSET_PCT = 0.005  # 0.5%

# Prior Day Low Reclaim: minimum dip below prior low to qualify
PDL_DIP_MIN_PCT = 0.001  # 0.1%

# Resistance at Prior High: proximity threshold
RESISTANCE_PROXIMITY_PCT = 0.002  # 0.2%

# ---------------------------------------------------------------------------
# Notification credentials (from .env)
# ---------------------------------------------------------------------------

# SMTP (email)
SMTP_HOST = _get_secret("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_get_secret("SMTP_PORT", "587"))
SMTP_USER = _get_secret("SMTP_USER")
SMTP_PASSWORD = _get_secret("SMTP_PASSWORD")
ALERT_EMAIL_FROM = _get_secret("ALERT_EMAIL_FROM") or SMTP_USER
ALERT_EMAIL_TO = _get_secret("ALERT_EMAIL_TO")

# Twilio (WhatsApp + SMS)
TWILIO_ACCOUNT_SID = _get_secret("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = _get_secret("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = _get_secret("TWILIO_FROM_NUMBER")
ALERT_SMS_TO = _get_secret("ALERT_SMS_TO")
TWILIO_USE_WHATSAPP = _get_secret("TWILIO_USE_WHATSAPP", "true").lower() == "true"
