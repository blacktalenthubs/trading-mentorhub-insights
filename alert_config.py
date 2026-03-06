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
PDL_DIP_MIN_PCT = 0.0003  # 0.03% — any meaningful touch below PDL counts

# Resistance at Prior High: proximity threshold
RESISTANCE_PROXIMITY_PCT = 0.003  # 0.3% — symmetric with support bounce

# Hourly Resistance Detection
HOURLY_RESISTANCE_CLUSTER_PCT = 0.003   # 0.3% — merge swing highs within this distance
HOURLY_RESISTANCE_APPROACH_PCT = 0.003  # 0.3% — symmetric with RESISTANCE_PROXIMITY_PCT

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

# Support Bounce Lookback: scan last N bars for a touch (30 min at 5-min bars)
SUPPORT_BOUNCE_LOOKBACK_BARS = 6

# Support Bounce Max Distance: don't fire if price ran >1% above support
SUPPORT_BOUNCE_MAX_DISTANCE_PCT = 0.010  # 1.0%

# Opening Range Breakout: minimum OR range as % of price
ORB_MIN_RANGE_PCT = 0.003  # 0.3%

# Opening Range Breakout: volume must be >= this multiple of average
ORB_VOLUME_RATIO = 1.2

# Session Low Double-Bottom
SESSION_LOW_PROXIMITY_PCT = 0.003       # 0.3% — how close bar low must be to session low
SESSION_LOW_RECOVERY_PCT = 0.003        # 0.3% — minimum bounce above session low between touches
SESSION_LOW_MIN_AGE_BARS = 4            # ~20 min — session low must be established this long ago
SESSION_LOW_MIN_RECOVERY_BARS = 2       # ~10 min — consecutive bars above recovery threshold
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

# Prior Day High Breakout: volume must be >= this multiple of average
PDH_BREAKOUT_VOLUME_RATIO = 1.2

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

# ---------------------------------------------------------------------------
# Score v2 — signal-type-aware scoring
# ---------------------------------------------------------------------------

# Feature flag: 1 = v1 active (default), 2 = v2 active for Telegram gating
SCORE_VERSION = int(_get_secret("SCORE_VERSION", "1"))

# Bounce / dip-buy signal types — mean-reversion setups that fire when price
# is below MAs and VWAP (conditions that v1 penalises but are *expected*).
BOUNCE_ALERT_TYPES: set[str] = {
    "ma_bounce_20", "ma_bounce_50", "ma_bounce_100", "ma_bounce_200",
    "ema_bounce_20", "ema_bounce_50", "ema_bounce_100",
    "prior_day_low_reclaim",
    "session_low_double_bottom",
    "intraday_support_bounce",
    "vwap_reclaim",
    "opening_low_base",
    "weekly_level_touch",
    "planned_level_touch",
}

# MA/EMA bounce subset — the MA itself is the level being tested, so
# "below both MAs" actually *validates* the signal (full 25 pts).
MA_BOUNCE_ALERT_TYPES: set[str] = {
    "ma_bounce_20", "ma_bounce_50", "ma_bounce_100", "ma_bounce_200",
    "ema_bounce_20", "ema_bounce_50", "ema_bounce_100",
}

# Risk:Reward bonus for v2 scoring
SCORE_V2_RR_BONUS_THRESHOLD = 1.5   # T1 reward / risk >= this → bonus
SCORE_V2_RR_BONUS_POINTS = 5        # bonus points added

# Overhead MA resistance: suppress BUY when an MA is within this % above entry
OVERHEAD_MA_RESISTANCE_PCT = 0.005  # 0.5%

# MA Confluence: MA within this % of entry = confluence with horizontal level
CONFLUENCE_BAND_PCT = 0.005  # 0.5%

# VWAP Reclaim: morning reversal pattern — session low in first hour, reclaims VWAP
VWAP_RECLAIM_MORNING_BARS = 12          # low must be in first 60 min (12 × 5-min bars)
VWAP_RECLAIM_MIN_RECOVERY_PCT = 0.005   # 0.5% minimum bounce from session low
VWAP_RECLAIM_VOLUME_RATIO = 1.2         # volume confirmation threshold
VWAP_RECLAIM_MIN_BARS_AFTER_LOW = 3     # 15 min after low before firing
VWAP_RECLAIM_STOP_OFFSET_PCT = 0.003    # 0.3% below session low for stop

# Opening Low Base: session low in first 15 min, then price holds above it
OPENING_LOW_BASE_WINDOW_BARS = 3       # first 15 min (3 × 5-min bars) to set the low
OPENING_LOW_BASE_HOLD_BARS = 3         # 15 min of holding above low to confirm base
OPENING_LOW_BASE_HOLD_PCT = 0.003      # 0.3% — bars must stay above low * (1 + this)
OPENING_LOW_BASE_MIN_DIP_PCT = 0.003   # 0.3% — low must be meaningful dip from open
OPENING_LOW_BASE_STOP_OFFSET_PCT = 0.003  # 0.3% below session low for stop

# Minimum target distance: T1 must be at least this % above entry
MIN_TARGET_DISTANCE_PCT = 0.005  # 0.5%

# Options play: minimum score to flag as options-worthy (requires high confidence)
OPTIONS_MIN_SCORE = 80
OPTIONS_ELIGIBLE_SYMBOLS = {"SPY", "QQQ", "DIA"}  # index ETFs only — predictable movement

# ---------------------------------------------------------------------------
# Swing trade thresholds
# ---------------------------------------------------------------------------
SWING_RSI_OVERSOLD = 30
SWING_RSI_APPROACHING_OVERSOLD = 35
SWING_RSI_OVERBOUGHT = 70
SWING_RSI_APPROACHING_OVERBOUGHT = 65
SWING_EMA_CROSSOVER_MIN_SEPARATION_PCT = 0.0005  # 0.05% anti-flicker
SWING_PULLBACK_PROXIMITY_PCT = 0.005              # 0.5% near 20 EMA
SWING_PULLBACK_EMA_RISING_LOOKBACK = 5            # EMA20 today > EMA20 5 days ago
SWING_200MA_RECLAIM_CONFIRM_EMA10 = True          # require close > EMA10 too
SWING_REGIME_GATE = True                          # require SPY > 20 EMA

# ---------------------------------------------------------------------------
# Enabled rules — only rules listed here will fire via evaluate_rules().
# Uses string values (not AlertType enum) to avoid circular imports.
# Disabled: breakout-based (ORB, inside day), momentum (EMA crossover),
#           informational noise (gap fill), choppy-day noise (intraday bounce).
# ---------------------------------------------------------------------------
ENABLED_RULES: set[str] = {
    # ── Phase 1: Core S/R levels only — validate accuracy before expanding ──
    # BUY — MA/EMA support bounce
    "ma_bounce_20",
    "ma_bounce_50",
    "ma_bounce_100",
    "ma_bounce_200",
    "ema_bounce_20",
    "ema_bounce_50",
    "ema_bounce_100",
    # BUY — daily high/low
    "prior_day_low_reclaim",
    "prior_day_high_breakout",
    # BUY — weekly high/low
    "weekly_level_touch",
    "weekly_high_breakout",
    # SELL — MA/EMA resistance
    "ma_resistance",
    # SELL — daily high/low resistance
    "resistance_prior_high",
    "resistance_prior_low",
    # SELL — weekly resistance
    "weekly_high_resistance",
    # Trade management — disabled Phase 1 (targets/stops from stored entries
    # can be inaccurate; rely on core S/R alerts for exits instead)
    # "target_1_hit",
    # "target_2_hit",
    # "stop_loss_hit",
    # "auto_stop_out",
    # ── Disabled for Phase 1 — re-enable after accuracy validated ──
    # "session_low_double_bottom",
    # "planned_level_touch",
    # "vwap_reclaim",
    # "opening_low_base",
    # "outside_day_breakout",
    # "ema_crossover_5_20",
    # "hourly_resistance_approach",
    # "support_breakdown",
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

# Claude AI Trade Narrator
ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
CLAUDE_NARRATIVE_ENABLED = _get_secret("CLAUDE_NARRATIVE_ENABLED", "true").lower() == "true"
CLAUDE_MODEL = _get_secret("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# Real trade position sizing (max dollar exposure per trade)
REAL_TRADE_POSITION_SIZE = 50_000
REAL_TRADE_SPY_POSITION_SIZE = 100_000
