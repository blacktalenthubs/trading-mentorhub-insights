"""Alert system configuration — watchlist, thresholds, credentials."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


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

# Support Breakdown: volume must be >= this multiple of average
BREAKDOWN_VOLUME_RATIO = 1.5

# Support Breakdown: close must be in lower N% of bar range to confirm conviction
BREAKDOWN_CONVICTION_PCT = 0.30

# EMA Crossover: minimum bars needed to compute 20-bar EMA
EMA_MIN_BARS = 25

# Noise filter: skip BUY signals when volume ratio is below this
LOW_VOLUME_SKIP_RATIO = 0.4

# Day-trade risk cap: max allowed risk per trade as % of entry price
DAY_TRADE_MAX_RISK_PCT = 0.003  # 0.3%

# Cooldown: minutes to suppress BUY signals after a stop-out
COOLDOWN_MINUTES = 30

# Intraday Support Bounce: bar low must be within this % of support
SUPPORT_BOUNCE_PROXIMITY_PCT = 0.003  # 0.3%

# Opening Range Breakout: minimum OR range as % of price
ORB_MIN_RANGE_PCT = 0.003  # 0.3%

# Opening Range Breakout: volume must be >= this multiple of average
ORB_VOLUME_RATIO = 1.2

# Session Low Double-Bottom
SESSION_LOW_PROXIMITY_PCT = 0.003       # 0.3% — how close bar low must be to session low
SESSION_LOW_RECOVERY_PCT = 0.003        # 0.3% — minimum bounce above session low between touches
SESSION_LOW_MIN_AGE_BARS = 6            # ~30 min — session low must be established this long ago
SESSION_LOW_MIN_RECOVERY_BARS = 4       # ~20 min — consecutive bars above recovery threshold
SESSION_LOW_MAX_RETEST_VOL_RATIO = 1.2  # retest must be exhaustion, not panic (< 1.2x avg)
SESSION_LOW_STOP_OFFSET_PCT = 0.005     # 0.5% below session low for stop

# Planned Level Touch: bar low must be within this % of Scanner's planned entry
PLANNED_LEVEL_PROXIMITY_PCT = 0.003  # 0.3%

# Weekly Level Touch: bar low must be within this % of prior week level
WEEKLY_LEVEL_PROXIMITY_PCT = 0.004  # 0.4% — wider than daily for broader weekly zones

# Weekly Level Touch: stop offset below prior week low
WEEKLY_LEVEL_STOP_OFFSET_PCT = 0.005  # 0.5%

# Support Breakdown: proximity to session low for "SESSION LOW BREAK" tag
SESSION_LOW_BREAK_PROXIMITY_PCT = 0.002  # 0.2%

# SPY Level Reaction: proximity for classifying SPY "at support" or "at resistance"
SPY_SUPPORT_PROXIMITY_PCT = 0.003  # 0.3% — daily S/R proximity
SPY_WEEKLY_PROXIMITY_PCT = 0.005   # 0.5% — weekly S/R proximity

# SPY Level Reaction: minimum bounce rate for "strong" support
SPY_STRONG_BOUNCE_RATE = 0.50  # >= 50% historical bounce rate = strong support

# Relative Strength: underperformance factor vs SPY for confidence demotion
RS_UNDERPERFORM_FACTOR = 2.0

# Per-symbol risk overrides (defaults to DAY_TRADE_MAX_RISK_PCT if not listed)
PER_SYMBOL_RISK: dict[str, float] = {
    "SPY": 0.002, "QQQ": 0.002,       # tight for ETFs
    "NVDA": 0.004, "TSLA": 0.005,     # wider for volatile stocks
}

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

# Alpaca Paper Trading
ALPACA_API_KEY = _get_secret("ALPACA_API_KEY")
ALPACA_SECRET_KEY = _get_secret("ALPACA_SECRET_KEY")
PAPER_TRADE_ENABLED = _get_secret("PAPER_TRADE_ENABLED", "false").lower() == "true"
PAPER_TRADE_POSITION_SIZE = int(_get_secret("PAPER_TRADE_POSITION_SIZE", "10000"))
PAPER_TRADE_MAX_DAILY = int(_get_secret("PAPER_TRADE_MAX_DAILY", "4"))
PAPER_TRADE_MIN_SCORE = int(_get_secret("PAPER_TRADE_MIN_SCORE", "75"))

# Real trade position sizing (max dollar exposure per trade)
REAL_TRADE_POSITION_SIZE = 50_000
REAL_TRADE_SPY_POSITION_SIZE = 100_000
