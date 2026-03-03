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
MA_BOUNCE_PROXIMITY_PCT = 0.003  # 0.3% (used by 20MA and 50MA)

# MA100 Bounce: wider proximity — institutional levels wick through more
MA100_BOUNCE_PROXIMITY_PCT = 0.005  # 0.5%

# MA200 Bounce: widest proximity — major level, deep wicks common
MA200_BOUNCE_PROXIMITY_PCT = 0.008  # 0.8%

# MA Bounce: stop offset below the MA
MA_STOP_OFFSET_PCT = 0.005  # 0.5%

# MA100 Bounce: wider stop for intermediate timeframe
MA100_STOP_OFFSET_PCT = 0.007  # 0.7%

# MA200 Bounce: widest stop for long-term institutional level
MA200_STOP_OFFSET_PCT = 0.010  # 1.0%

# MA Bounce: structural stop buffer below session low
MA_BOUNCE_SESSION_STOP_PCT = 0.002  # 0.2% below session low

# Prior Day Low Reclaim: minimum dip below prior low to qualify
PDL_DIP_MIN_PCT = 0.001  # 0.1%

# Resistance at Prior High: proximity threshold
RESISTANCE_PROXIMITY_PCT = 0.002  # 0.2%

# Hourly Resistance Detection
HOURLY_RESISTANCE_CLUSTER_PCT = 0.003   # 0.3% — merge swing highs within this distance
HOURLY_RESISTANCE_APPROACH_PCT = 0.002  # 0.2% — same as RESISTANCE_PROXIMITY_PCT

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

# Buy Zone Approach: bar low must be within this % of nearest support
BUY_ZONE_PROXIMITY_PCT = 0.005  # 0.5% — matches Scanner's AT SUPPORT threshold

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

# SPY RSI / EMA enrichment
SPY_RSI_OVERSOLD = 35
SPY_RSI_OVERBOUGHT = 70
SPY_EMA_CONVERGENCE_PCT = 0.005   # 0.5% — EMAs within this spread = compressed
SPY_MA_SUPPORT_PROXIMITY_PCT = 0.005  # 0.5% — SPY near its own 50/100/200 MA

# Per-symbol RSI thresholds
SYM_RSI_OVERSOLD = 35     # RSI < 35 = crash risk, suppress BUY
SYM_RSI_OVERBOUGHT = 70   # RSI > 70 = overbought, caution on BUY

# Volume Exhaustion Detection
SELLER_EXHAUSTION_VOL_RATIO = 0.6    # current bar vol < 0.6x avg = sellers drying up
SELLER_EXHAUSTION_MIN_BARS = 3       # need 3+ declining volume bars
BUYER_EXHAUSTION_SPIKE_RATIO = 2.0   # volume spike >= 2x avg = climax

# Relative Strength: underperformance factor vs SPY for confidence demotion
RS_UNDERPERFORM_FACTOR = 2.0

# Intraday Support Strength: thresholds for "strong" support classification
SUPPORT_STRONG_HOLD_HOURS = 2
SUPPORT_STRONG_RETEST_COUNT = 2

# Opening Range Breakdown: volume must be >= this multiple of average
ORB_BREAKDOWN_VOLUME_RATIO = 1.2  # same threshold as upside breakout

# Telegram Priority Tiers: minimum score to send via Telegram (A+ and A signals)
TELEGRAM_TIER1_MIN_SCORE = 65

# Daily Scanner cross-reference: penalise intraday BUY when daily setup is weak
DAILY_SCORE_WEAK_THRESHOLD = 50       # daily score below this → small penalty
DAILY_SCORE_VERY_WEAK_THRESHOLD = 35  # daily score below this → large penalty
DAILY_SCORE_WEAK_PENALTY = 15         # points deducted for weak daily setup
DAILY_SCORE_VERY_WEAK_PENALTY = 25    # points deducted for very weak daily setup

# Signal Consolidation: score boost when multiple BUY signals confirm
CONSOLIDATION_SCORE_BOOST = 5   # points per confirming signal
CONSOLIDATION_MAX_BOOST = 15    # max boost from consolidation

# Overhead MA resistance: suppress BUY when an MA is within this % above entry
OVERHEAD_MA_RESISTANCE_PCT = 0.005  # 0.5%

# Minimum target distance: T1 must be at least this % above entry
MIN_TARGET_DISTANCE_PCT = 0.005  # 0.5%

# ---------------------------------------------------------------------------
# Enabled rules — only rules listed here will fire via evaluate_rules().
# Uses string values (not AlertType enum) to avoid circular imports.
# Disabled: breakout-based (ORB, inside day), momentum (EMA crossover),
#           informational noise (gap fill), choppy-day noise (intraday bounce).
# ---------------------------------------------------------------------------
ENABLED_RULES: set[str] = {
    # BUY — support bounce / S/R reclaim
    "ma_bounce_20",
    "ma_bounce_50",
    "ma_bounce_100",
    "ma_bounce_200",
    "prior_day_low_reclaim",
    "session_low_double_bottom",
    "planned_level_touch",
    "weekly_level_touch",
    "buy_zone_approach",
    # BUY — breakout / momentum
    "outside_day_breakout",
    # Momentum
    "ema_crossover_5_20",
    # SELL / resistance warnings
    "resistance_prior_high",
    "hourly_resistance_approach",
    "ma_resistance",
    "resistance_prior_low",
    # Trade management
    "target_1_hit",
    "target_2_hit",
    "stop_loss_hit",
    "auto_stop_out",
    # Exit-only (fires only with active position)
    "support_breakdown",
}

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

# Telegram Bot (primary SMS replacement)
TELEGRAM_BOT_TOKEN = _get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get_secret("TELEGRAM_CHAT_ID")

# SMS via email-to-SMS gateway (carrier gateway, fallback)
SMS_GATEWAY_TO = _get_secret("SMS_GATEWAY_TO")  # e.g. "8325551234@txt.att.net"

# Legacy Twilio config (kept for fallback)
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
PAPER_TRADE_MIN_SCORE = int(_get_secret("PAPER_TRADE_MIN_SCORE", "65"))

# Real trade position sizing (max dollar exposure per trade)
REAL_TRADE_POSITION_SIZE = 50_000
REAL_TRADE_SPY_POSITION_SIZE = 100_000
