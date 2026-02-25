"""Alert system configuration — watchlist, thresholds, credentials."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

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
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", SMTP_USER)
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")

# Twilio (SMS)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
ALERT_SMS_TO = os.environ.get("ALERT_SMS_TO", "")
