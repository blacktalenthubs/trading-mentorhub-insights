"""Alert system configuration — watchlist, thresholds, credentials."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_secret(key: str, default: str = "") -> str:
    """Read from env vars, then V2 FastAPI config, then Streamlit secrets."""
    val = os.environ.get(key, "")
    if val:
        return val
    # V2 FastAPI pydantic-settings resolves Railway reference vars that os.environ misses
    try:
        from app.config import get_settings
        val = getattr(get_settings(), key, "")
        if val:
            return str(val)
    except Exception:
        pass
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

POLL_INTERVAL_MINUTES = 2

# Market hours (US Eastern)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# ---------------------------------------------------------------------------
# Rule thresholds
# ---------------------------------------------------------------------------

# MA Bounce BUY trigger: bar low must actually TOUCH the MA (tight proximity)
MA_BOUNCE_PROXIMITY_PCT = 0.004  # 0.4% — BUY only on real touch (20/50 MA)
MA100_BOUNCE_PROXIMITY_PCT = 0.004  # 0.4% — BUY only on real touch (100 MA)
MA200_BOUNCE_PROXIMITY_PCT = 0.004  # 0.4% — BUY only on real touch (200 MA)

# MA Approach NOTICE: wider proximity for heads-up alerts
MA_APPROACH_PROXIMITY_PCT = 0.005  # 0.5% — NOTICE for 20/50 MA approach
MA100_APPROACH_PROXIMITY_PCT = 0.007  # 0.7% — NOTICE for 100 MA approach
MA200_APPROACH_PROXIMITY_PCT = 0.010  # 1.0% — NOTICE for 200 MA approach

# MA Bounce: stop offset below the MA
MA_STOP_OFFSET_PCT = 0.005  # 0.5%

# MA100 Bounce: wider stop for intermediate timeframe
MA100_STOP_OFFSET_PCT = 0.007  # 0.7%

# MA200 Bounce: widest stop for long-term institutional level
MA200_STOP_OFFSET_PCT = 0.010  # 1.0%

# MA/EMA Bounce Lookback: scan last N bars for a touch (30 min at 5-min bars)
# Catches bounces that happened 2-3 bars ago and are already running.
MA_BOUNCE_LOOKBACK_BARS = 6

# MA/EMA Bounce Max Distance: don't fire if price ran >2% above the MA
# (wider than support bounce — MA bounces are higher-conviction setups)
MA_BOUNCE_MAX_DISTANCE_PCT = 0.020  # 2.0%

# MA Bounce: structural stop buffer below session low
MA_BOUNCE_SESSION_STOP_PCT = 0.002  # 0.2% below session low

# Prior Day Low Reclaim: minimum dip below prior low to qualify
PDL_DIP_MIN_PCT = 0.0003  # 0.03% — any meaningful touch below PDL counts
PDL_RECLAIM_MAX_DISTANCE_PCT = 0.020  # 2.0% — skip if price already ran past entry (widened for volatile names)

# PDL level-based stop: stop just below the level itself (0.5% below PDL)
# Data-driven (2yr, 10 symbols): 78% survival for SPY, 3-5x R:R.
# Volatile names stop out more but only cleanest reclaims survive — by design.
PDL_STOP_OFFSET_PCT = 0.005   # 0.5% below PDL for both reclaim and bounce stops

# Prior Day Low Bounce: price approaches PDL and holds above it (no break below)
PDL_BOUNCE_PROXIMITY_PCT = 0.002     # 0.2% — bar low must be within this of PDL (tightened from 0.5%)
PDL_BOUNCE_HOLD_BARS = 1             # 1 bar (5 min) closing above PDL after touch
PDL_BOUNCE_MAX_DISTANCE_PCT = 0.015  # 1.5% — skip if price ran too far above PDL (widened for volatile names)
PDL_BOUNCE_MAX_DISTANCE_CRYPTO_PCT = 0.008  # 0.8% — tighter for crypto (24/7 polling lag)
PDL_BOUNCE_STOP_OFFSET_PCT = 0.003   # 0.3% below PDL for stop (legacy, superseded by PDL_STOP_OFFSET_PCT)

# Prior Day High Retest & Hold: after breakout, price pulls back to PDH and holds
PDH_RETEST_PROXIMITY_PCT = 0.005     # 0.5% — bar low must be within this of PDH
PDH_RETEST_HOLD_BARS = 1             # 1 bar (5 min) closing above PDH after pullback
PDH_RETEST_MAX_DISTANCE_PCT = 0.010  # 1.0% — skip if price ran too far above PDH
PDH_RETEST_STOP_OFFSET_PCT = 0.005   # 0.5% below PDH for stop

# Inside Day Reclaim: minimum dip below inside low to qualify
INSIDE_DAY_DIP_MIN_PCT = 0.0003  # 0.03% — same as PDL (any meaningful touch)

# Inside Day Forming: detect when today's range is within yesterday's range
INSIDE_DAY_FORMING_MIN_BARS = 13   # ~65 min — first hour must pass before declaring
INSIDE_DAY_SCORE_BOOST = 10        # +10 score for PDL/PDH boundary alerts on inside days

# Resistance at Prior High: proximity threshold
RESISTANCE_PROXIMITY_PCT = 0.0015  # 0.15% — must actually touch (~$1 for SPY). Tightened from 0.3%

# Prior Day High Rejection: confirmed rejection (high touched, close below)
PDH_REJECTION_PROXIMITY_PCT = 0.0015  # 0.15% — must actually touch. Tightened from 0.3%

# Hourly Resistance Detection
HOURLY_RESISTANCE_CLUSTER_PCT = 0.003   # 0.3% — merge swing highs within this distance
HOURLY_RESISTANCE_APPROACH_PCT = 0.003  # 0.3% — NOTICE only, can be wider

# Hourly Resistance Rejection SHORT: price rallies into horizontal resistance and gets rejected
HOURLY_RES_REJECTION_PROXIMITY_PCT = 0.0015  # 0.15% — bar high must actually touch level (~$1 for SPY). Tightened from 0.3% ($2 was too loose)
HOURLY_RES_REJECTION_CLOSE_PCT = 0.40       # close must be in lower 40% of bar range (rejection)
HOURLY_RES_REJECTION_MIN_BARS = 12          # 60 min into session minimum
HOURLY_RES_REJECTION_STOP_OFFSET_PCT = 0.003  # 0.3% above resistance for stop

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

# Session High Double Top (SHORT) — mirror of session low double bottom
SESSION_HIGH_PROXIMITY_PCT = 0.002       # 0.2% — bar high must nearly touch session high. Tightened from 0.3%
SESSION_HIGH_WEAKNESS_PCT = 0.003        # 0.3% — minimum pullback below session high between touches
SESSION_HIGH_MIN_AGE_BARS = 3            # ~15 min — session high must be established this long ago
SESSION_HIGH_MIN_WEAKNESS_BARS = 1       # ~5 min — consecutive bars below weakness threshold
SESSION_HIGH_STOP_OFFSET_PCT = 0.005     # 0.5% above session high for stop

# Cooldown: minutes to suppress BUY signals after a stop-out
COOLDOWN_MINUTES = 30

# Burst cooldown: after a BUY notification is sent for a symbol, suppress
# Telegram for additional BUY alerts on the same symbol for this many minutes.
# Alerts still get recorded to DB for later review — just no push notification.
BUY_BURST_COOLDOWN_MINUTES = 10  # after a BUY notification, suppress next BUY for same symbol for 10 min

# Crypto Telegram hours: only send crypto alerts to Telegram during US waking
# hours (Central Time).  Outside this window, alerts are still recorded to DB
# and visible on the dashboard — just no push notification.
CRYPTO_TELEGRAM_START_HOUR = 7   # 7 AM Central
CRYPTO_TELEGRAM_END_HOUR = 21    # 9 PM Central

# Intraday Support Bounce: bar low must be at or within this % ABOVE support
# to count as a touch.  Using a directional check — bar low must actually
# reach the support level (not just be "near" it from above).
SUPPORT_BOUNCE_PROXIMITY_PCT = 0.0015  # 0.15% (tightened from 0.3%)

# Support Bounce Lookback: scan last N bars for a touch (30 min at 5-min bars)
SUPPORT_BOUNCE_LOOKBACK_BARS = 6

# Support Bounce Max Distance: don't fire if price ran >1% above support
SUPPORT_BOUNCE_MAX_DISTANCE_PCT = 0.010  # 1.0%

# Minimum touch count to qualify as real support (1x swing low = noise)
SUPPORT_BOUNCE_MIN_TOUCHES = 2

# Consolidation filter: if >30% of recent bars closed below the support
# level, the level is mid-range chop, not real support — suppress alert.
SUPPORT_BOUNCE_MAX_CLOSE_BELOW_PCT = 0.30  # 30%

# Opening Range Breakout: minimum OR range as % of price
ORB_MIN_RANGE_PCT = 0.003  # 0.3%

# Opening Range Breakout: volume must be >= this multiple of average
ORB_VOLUME_RATIO = 1.2

# Session Low Double-Bottom
SESSION_LOW_PROXIMITY_PCT = 0.003       # 0.3% — how close bar low must be to session low
SESSION_LOW_RECOVERY_PCT = 0.003        # 0.3% — minimum bounce above session low between touches
SESSION_LOW_MIN_AGE_BARS = 3            # ~15 min — session low must be established this long ago
SESSION_LOW_MIN_RECOVERY_BARS = 1       # ~5 min — consecutive bars above recovery threshold
SESSION_LOW_MAX_RETEST_VOL_RATIO = 1.2  # retest must be exhaustion, not panic (< 1.2x avg)
SESSION_LOW_STOP_OFFSET_PCT = 0.005     # 0.5% below session low for stop

# Multi-Day Double Bottom (daily swing lows tested 2+ times across days)
DAILY_DB_LOOKBACK_DAYS = 20            # scan last 20 completed daily bars (~1 month)
DAILY_DB_SWING_LOW_CLUSTER_PCT = 0.005  # 0.5% — cluster daily lows within this range
DAILY_DB_MIN_TOUCHES = 2               # minimum touches to qualify as double bottom
DAILY_DB_MIN_DAYS_BETWEEN = 1          # at least 1 day between first and last touch
DAILY_DB_MIN_RECOVERY_PCT = 0.005      # 0.5% recovery above zone between touches
DAILY_DB_INTRADAY_PROXIMITY_PCT = 0.005  # 0.5% — how close intraday bar must be to zone
DAILY_DB_STOP_OFFSET_PCT = 0.005       # 0.5% below zone low for stop
DAILY_DB_MAX_DISTANCE_PCT = 0.02       # 2% — skip if price already ran past zone
DAILY_DB_MAX_DISTANCE_CRYPTO_PCT = 0.01  # 1% — tighter for crypto (24/7 polling lag)

# Planned Level Touch: bar low must be within this % of Scanner's planned entry
PLANNED_LEVEL_PROXIMITY_PCT = 0.003  # 0.3%

# Buy Zone Approach: bar low must be within this % of nearest support
BUY_ZONE_PROXIMITY_PCT = 0.005  # 0.5% — matches Scanner's AT SUPPORT threshold

# Weekly Level Touch: bar low must be within this % of prior week level
WEEKLY_LEVEL_PROXIMITY_PCT = 0.004  # 0.4% — wider than daily for broader weekly zones

# Weekly Level Touch: stop offset below prior week low
WEEKLY_LEVEL_STOP_OFFSET_PCT = 0.005  # 0.5%

# Monthly Level Touch: bar low must be within this % of prior month level
MONTHLY_LEVEL_PROXIMITY_PCT = 0.005  # 0.5% — wider than weekly for broader monthly zones

# Monthly Level Touch: stop offset below prior month low
MONTHLY_LEVEL_STOP_OFFSET_PCT = 0.007  # 0.7% — wider stop for monthly levels

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
PDH_BREAKOUT_VOLUME_RATIO = 0.8

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
    "ema_bounce_20", "ema_bounce_50", "ema_bounce_100", "ema_bounce_200",
    "prior_day_low_reclaim",
    "prior_day_low_bounce",
    "inside_day_reclaim",
    "session_low_double_bottom",
    "multi_day_double_bottom",
    "intraday_support_bounce",
    "vwap_reclaim",
    "opening_low_base",
    "morning_low_retest",
    "session_low_bounce_vwap",
    "first_hour_high_breakout",
    "ma_reclaim_20", "ma_reclaim_50", "ma_reclaim_100", "ma_reclaim_200",
    "ema_reclaim_20", "ema_reclaim_50", "ema_reclaim_100", "ema_reclaim_200",
    "weekly_level_touch",
    "monthly_level_touch",
    "monthly_ema_touch",
    "planned_level_touch",
}

# MA/EMA bounce subset — the MA itself is the level being tested, so
# "below both MAs" actually *validates* the signal (full 25 pts).
MA_BOUNCE_ALERT_TYPES: set[str] = {
    "ma_bounce_20", "ma_bounce_50", "ma_bounce_100", "ma_bounce_200",
    "ema_bounce_20", "ema_bounce_50", "ema_bounce_100", "ema_bounce_200",
}

# Risk:Reward bonus for v2 scoring
SCORE_V2_RR_BONUS_THRESHOLD = 1.5   # T1 reward / risk >= this → bonus
SCORE_V2_RR_BONUS_POINTS = 5        # bonus points added

# Overhead MA resistance: suppress BUY when an MA is within this % above entry
OVERHEAD_MA_RESISTANCE_PCT = 0.005  # 0.5%

# MA Confluence: MA within this % of entry = confluence with horizontal level
CONFLUENCE_BAND_PCT = 0.005  # 0.5%

# VWAP alerts: only fire for these symbols (SPY for market structure, NVDA for AI
# sentiment, crypto for 24h VWAP relevance).  Other equities get noise from
# bounce-then-fade behaviour around VWAP.
VWAP_SYMBOLS: set[str] = {"SPY", "NVDA", "BTC-USD", "ETH-USD"}

# VWAP Reclaim: morning reversal pattern — session low in first hour, reclaims VWAP
VWAP_RECLAIM_MORNING_BARS = 12          # low must be in first 60 min (12 × 5-min bars)
VWAP_RECLAIM_MIN_RECOVERY_PCT = 0.005   # 0.5% minimum bounce from session low
VWAP_RECLAIM_VOLUME_RATIO = 1.2         # volume confirmation threshold
VWAP_RECLAIM_MIN_BARS_AFTER_LOW = 3     # 15 min after low before firing
VWAP_RECLAIM_STOP_OFFSET_PCT = 0.003    # 0.3% below session low for stop
VWAP_RECLAIM_MAX_DISTANCE_PCT = 0.003   # 0.3% — skip if price already ran past VWAP

# VWAP Bounce: pullback to VWAP that holds — continuation signal
VWAP_BOUNCE_MIN_BARS = 18              # ~90 min context (after 11:00 AM)
VWAP_BOUNCE_ABOVE_PCT = 0.60           # 60% of lookback bars must have closed above VWAP
VWAP_BOUNCE_TOUCH_PCT = 0.003          # 0.3% — bar low must be within this of VWAP
VWAP_BOUNCE_MAX_DISTANCE_PCT = 0.005   # 0.5% — close can't be too far above VWAP
VWAP_BOUNCE_STOP_OFFSET_PCT = 0.003    # 0.3% below VWAP for stop

# Opening Low Base: session low in first 15 min, then price holds above it
OPENING_LOW_BASE_WINDOW_BARS = 3       # first 15 min (3 × 5-min bars) to set the low
OPENING_LOW_BASE_HOLD_BARS = 2         # 10 min of holding above low to confirm base
OPENING_LOW_BASE_HOLD_PCT = 0.003      # 0.3% — bars must stay above low * (1 + this)
OPENING_LOW_BASE_MIN_DIP_PCT = 0.003   # 0.3% — low must be meaningful dip from open
OPENING_LOW_BASE_STOP_OFFSET_PCT = 0.003  # 0.3% below session low for stop

# Morning Low Retest: price retests first-hour low after rallying away
MORNING_LOW_RETEST_MIN_BARS = 12       # 60 min — must be past first hour (12 × 5-min)
MORNING_LOW_RETEST_RALLY_PCT = 0.005   # 0.5% — price must have rallied this far above first-hour low
MORNING_LOW_RETEST_PROXIMITY_PCT = 0.004  # 0.4% — bar low must be within this of first-hour low
MORNING_LOW_RETEST_STOP_OFFSET_PCT = 0.003  # 0.3% below first-hour low for stop

# First Hour High Breakout: price breaks above first-hour high later in session
FIRST_HOUR_HIGH_BREAKOUT_MIN_BARS = 12  # must be past first hour
FIRST_HOUR_HIGH_BREAKOUT_VOLUME_RATIO = 0.8  # volume confirmation

# Prior Day Low Breakdown: price breaks below PDL on volume — bearish exit signal
PDL_BREAKDOWN_VOLUME_RATIO = 0.8  # volume must be >= 0.8x avg for conviction
PDL_BREAKDOWN_MAX_DISTANCE_PCT = 0.015  # 1.5% — skip if price already far below

# Prior Day Low Resistance: after PDL breaks, it becomes overhead resistance
PDL_RESISTANCE_PROXIMITY_PCT = 0.004  # 0.4% — bar high must reach within this of PDL
PDL_RESISTANCE_REJECTION_PCT = 0.003  # 0.3% — close must be this far below PDL

# SPY Gate: suppress BUY alerts when SPY is bearish intraday
# Uses VWAP dominance (% of recent bars above VWAP) + intraday EMA trend
SPY_GATE_LOOKBACK_BARS = 6     # 30 min window (6 × 5-min bars) for VWAP dominance
SPY_GATE_GREEN_PCT = 0.70      # 70%+ bars above VWAP = green light (longs OK)
SPY_GATE_RED_PCT = 0.40        # <40% bars above VWAP = red light (suppress BUY)
SPY_GATE_EMA_PERIOD = 60       # 60-bar EMA on 5-min = ~20 EMA on 15-min equivalent
SPY_GATE_ENABLED = True        # feature flag

# Hourly Consolidation Breakout: detect tight ranges then trade the break
# Uses ATR-based threshold instead of fixed % — adapts to each symbol's volatility
HOURLY_CONSOL_ATR_LOOKBACK = 10       # 10 hourly bars for ATR calculation
HOURLY_CONSOL_ATR_MULT = 1.2          # range must be < 1.2x hourly ATR
HOURLY_CONSOL_MAX_RANGE_PCT = 0.015   # 1.5% absolute cap (safety net)
HOURLY_CONSOL_MIN_BARS = 2            # 2 hourly bars minimum (catch fast staircases)
HOURLY_CONSOL_ENABLED = True          # feature flag

# 15-min consolidation breakout (tighter, faster breakouts)
CONSOL_15M_ATR_LOOKBACK = 10          # 10 fifteen-min bars for ATR
CONSOL_15M_ATR_MULT = 1.2             # range must be < 1.2x 15m ATR
CONSOL_15M_MAX_RANGE_PCT = 0.010      # 1.0% absolute cap (tighter than hourly)
CONSOL_15M_MIN_BARS = 4               # 4 x 15-min = 1 hour of consolidation minimum

# Per-symbol consolidation breakout signals
CONSOL_BREAKOUT_ENABLED = True
CONSOL_BREAKOUT_STOP_OFFSET_PCT = 0.001  # 0.1% buffer beyond range for stop
CONSOL_BREAKOUT_MIN_VOL_RATIO = 0.8      # minimum volume ratio for confirmation

# SPY Short Entry: fire SHORT signals when gate is RED + key level breaks
SPY_SHORT_ENABLED = True       # feature flag
SPY_SHORT_STOP_OFFSET_PCT = 0.003  # 0.3% above broken level for stop
SPY_SHORT_SYMBOLS = {"SPY", "QQQ"}    # index ETFs for short entries

# Wick rejection: demote confidence when touch was wick-only (no body involvement)
# In choppy markets, wicks create false touches at support levels
WICK_REJECTION_CLOSE_PCT = 0.005  # 0.5% — close must be within this of entry level
WICK_REJECTION_RATIO = 0.6  # lower wick > 60% of bar range = wick touch

# MA/EMA Reclaim: price crosses above a key daily MA/EMA from below
MA_RECLAIM_STOP_OFFSET_PCT = 0.005  # 0.5% below the MA for stop
MA_RECLAIM_MAX_DISTANCE_PCT = 0.015  # 1.5% — skip if price ran too far above MA

# Session High Retracement: stock rallies then pulls back near session low
RETRACEMENT_MIN_RALLY_PCT = 0.015       # 1.5% — minimum rally from open to session high
RETRACEMENT_MIN_AGE_BARS = 6            # 30 min — high must be established this long ago
RETRACEMENT_PROXIMITY_PCT = 0.006       # 0.6% — how close to session low for entry
RETRACEMENT_STOP_OFFSET_PCT = 0.005     # 0.5% below session low for stop

# Minimum target distance: T1 must be at least this % above entry.
# Prevents "T1 hit" firing 5 min after BUY on a trivial move.
MIN_TARGET_DISTANCE_PCT = 0.008  # 0.8% (raised from 0.5%)

# Minimum stop distance: stop must be at least this % below entry.
# Prevents noise stop-outs on $0.12 moves (e.g., touch_bar_low barely
# below support).  ATR floor is applied separately on top of this.
MIN_STOP_DISTANCE_PCT = 0.003  # 0.3%

# Options play: minimum score to flag as options-worthy (requires high confidence)
OPTIONS_MIN_SCORE = 80
OPTIONS_ELIGIBLE_SYMBOLS = {"SPY", "QQQ", "DIA"}  # index ETFs only — predictable movement

# ---------------------------------------------------------------------------
# Weekly setup detection
# ---------------------------------------------------------------------------
WEEKLY_BASE_LOOKBACK = 8                    # scan last 8 weekly bars
WEEKLY_BASE_MIN_WEEKS = 3                   # minimum weeks for valid base
WEEKLY_BASE_MAX_RANGE_PCT = 0.12            # 12% max range to qualify as base
WEEKLY_BASE_TIGHT_RANGE_PCT = 0.08          # 8% = "tight" base (score boost)
WEEKLY_VOLUME_CONTRACTION_RATIO = 0.85      # base avg vol < 85% of prior = contraction
WEEKLY_BREAKOUT_VOLUME_RATIO = 1.2          # breakout week vol > 1.2x base avg
WEEKLY_PULLBACK_WMA_PCT = 0.02              # 2% proximity to WMA10/WMA20
WEEKLY_STOP_OFFSET_PCT = 0.02              # 2% below WMA50 for pullback stop

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
SWING_200MA_RECLAIM_CONFIRM_EMA10 = False         # disabled — 200MA reclaim is significant on its own during selloffs
SWING_REGIME_GATE = True                          # require SPY > 20 EMA

# ---------------------------------------------------------------------------
# MACD parameters (standard 12/26/9)
# ---------------------------------------------------------------------------
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# ---------------------------------------------------------------------------
# Bollinger Band Squeeze & Breakout
# ---------------------------------------------------------------------------
BB_PERIOD = 20
BB_STD_DEV = 2.0
BB_SQUEEZE_LOOKBACK = 20           # bars to look back for width percentile
BB_SQUEEZE_PERCENTILE = 10         # width < 10th percentile of lookback = squeeze

# ---------------------------------------------------------------------------
# ATR-Based Dynamic Stops (feature flag: set False to use fixed % stops only)
# ---------------------------------------------------------------------------
ATR_PERIOD = 14
ATR_DAY_TRADE_MULTIPLIER = 1.5     # 1.5x ATR for day-trade stops
ATR_SWING_MULTIPLIER = 2.0         # 2.0x ATR for swing-trade stops
USE_ATR_STOPS = True               # feature flag — False reverts to fixed % stops

# ---------------------------------------------------------------------------
# Trailing Stops
# ---------------------------------------------------------------------------
TRAILING_STOP_ATR_MULTIPLIER = 1.5  # trail by 1.5x ATR from highest high
ENABLE_TRAILING_STOPS = True        # feature flag

# ---------------------------------------------------------------------------
# Fibonacci Retracement
# ---------------------------------------------------------------------------
FIB_LEVELS = [0.382, 0.5, 0.618]
FIB_BOUNCE_PROXIMITY_PCT = 0.003   # 0.3% — bar low within this of fib level

# ---------------------------------------------------------------------------
# Bull Flag Pattern Detection
# ---------------------------------------------------------------------------
FLAG_IMPULSE_MIN_PCT = 0.05        # 5% minimum impulse move
FLAG_PULLBACK_MAX_RETRACE = 0.50   # max 50% retracement of impulse
FLAG_CONSOLIDATION_MIN_DAYS = 3
FLAG_CONSOLIDATION_MAX_DAYS = 8

# ---------------------------------------------------------------------------
# Gap and Go
# ---------------------------------------------------------------------------
GAP_AND_GO_MIN_PCT = 0.01         # 1% minimum gap size
GAP_AND_GO_VOLUME_RATIO = 2.0     # first bar volume > 2x average

# ---------------------------------------------------------------------------
# Relative Volume (RVOL)
# ---------------------------------------------------------------------------
RVOL_HIGH_THRESHOLD = 2.0         # 2x same-time-of-day average = high RVOL
RVOL_LOOKBACK_DAYS = 20           # days of history for RVOL calculation

# ---------------------------------------------------------------------------
# Candle Patterns (Swing)
# ---------------------------------------------------------------------------
HAMMER_WICK_RATIO = 2.0           # lower wick > 2x body = hammer
ENGULFING_MIN_BODY_RATIO = 1.1    # engulfing body > 1.1x prior body

# ---------------------------------------------------------------------------
# Consecutive Red/Green Days (Swing)
# ---------------------------------------------------------------------------
CONSECUTIVE_DAYS_THRESHOLD = 3     # 3+ consecutive red/green days

# ---------------------------------------------------------------------------
# RSI/Price Divergence Detection (Swing)
# ---------------------------------------------------------------------------
DIVERGENCE_LOOKBACK_BARS = 20      # bars to look back for divergence
DIVERGENCE_MIN_SWING_SIZE = 0.02   # 2% minimum swing size

# ---------------------------------------------------------------------------
# Enabled rules — only rules listed here will fire via evaluate_rules().
# Uses string values (not AlertType enum) to avoid circular imports.
# Disabled: breakout-based (ORB, inside day), momentum (EMA crossover),
#           informational noise (gap fill), choppy-day noise (intraday bounce).
# ---------------------------------------------------------------------------
ENABLED_RULES: set[str] = {
    # ── Tier 1: Highest-probability setups ──────────────────────────────────
    # BUY — MA/EMA support bounce (candle filter applied in rules)
    "ma_bounce_20",
    "ma_bounce_50",
    "ma_bounce_100",
    "ma_bounce_200",
    "ema_bounce_20",
    "ema_bounce_50",
    "ema_bounce_100",
    "ema_bounce_200",
    # BUY — daily high/low (institutional levels)
    "prior_day_low_reclaim",
    "prior_day_low_bounce",
    "prior_day_high_breakout",
    # "pdh_test",                     # NOISE: downgraded — test is not a setup, break is
    "pdh_retest_hold",
    # BUY — weekly high/low
    "weekly_level_touch",
    "weekly_high_breakout",
    # "weekly_high_test",             # NOISE: downgraded — test without break
    # "weekly_low_test",              # DISABLED (P4): informational, not an entry
    # "weekly_low_breakdown",         # DISABLED (P4): informational, not an entry
    # BUY — monthly high/low + monthly EMA
    "monthly_level_touch",
    "monthly_high_breakout",
    # "monthly_high_test",            # NOISE: downgraded — test without break
    # "monthly_low_test",             # DISABLED (P4): informational, not an entry
    # "monthly_low_breakdown",        # DISABLED (P4): informational, not an entry
    # "monthly_ema_touch",            # DISABLED (P4): 229 alerts in 4 days — pure noise, not an entry
    # BUY — VWAP
    "vwap_reclaim",                    # RE-ENABLED (AF-7): key level — VWAP reclaim is the regime inflection point
    "vwap_bounce",                     # RE-ENABLED (AF-7): pullback to VWAP that holds — continuation signal
    # BUY — opening range (Crabel methodology)
    # "opening_low_base",              # DISABLED: redundant with morning_low_retest, 0% win rate
    "morning_low_retest",
    # "first_hour_high_breakout",      # DISABLED: 0% win rate in bearish regime, chases momentum
    # BUY — inside day (volatility compression → expansion)
    "inside_day_breakout",
    "inside_day_reclaim",
    # BUY — support structure
    "session_low_double_bottom",
    "multi_day_double_bottom",
    "planned_level_touch",
    # "intraday_support_bounce",       # DISABLED: redundant with double bottom + PDL, 0% win rate
    "session_low_bounce_vwap",
    # BUY — EMA reclaims only (consolidated from 8 → 4, EMA preferred)
    "ema_reclaim_20", "ema_reclaim_50", "ema_reclaim_100", "ema_reclaim_200",
    # "ma_reclaim_20", "ma_reclaim_50", "ma_reclaim_100", "ma_reclaim_200",  # CONSOLIDATED: use EMA only
    # ── Tier 1: Professional rules ──────────────────────────────────────────
    "bb_squeeze_breakout",
    # "macd_histogram_flip",  # PAUSED — low trust, needs more evaluation data
    "gap_and_go",
    "fib_retracement_bounce",
    # BUY — session low reversal (candle + volume at the low itself)
    "session_low_reversal",
    # SHORT — session patterns
    "vwap_loss",
    "session_low_breakdown",
    "morning_low_breakdown",
    "pdh_failed_breakout",
    # ── SELL / SHORT — exits & breakdowns ───────────────────────────────────
    # DISABLED (P4): informational SELL alerts — not entries, SHORT rules cover resistance
    # "resistance_prior_high",         # DISABLED (P4): 104 alerts/4 days — "watch for rejection" not actionable
    # "pdh_rejection",                 # DISABLED (P4): 98 alerts — SHORT entry rules (double_top, failed_breakout) cover this
    # "resistance_prior_low",          # DISABLED (P4): 11 alerts — not an entry
    # "weekly_high_resistance",        # DISABLED (P4): 65 alerts — not an entry
    # "monthly_high_resistance",       # DISABLED (P4): 6 alerts — not an entry
    # "inside_day_breakdown",          # DISABLED (P4): informational, not an entry
    # "support_breakdown",             # DISABLED (P4): informational, not an entry
    # "prior_day_low_breakdown",       # DISABLED (P4): 32 alerts — not an entry
    # "prior_day_low_resistance",      # DISABLED (P4): 89 alerts — not an entry
    "spy_short_entry",
    "consol_breakout_long",
    "consol_breakout_short",
    "consol_15m_breakout_long",
    "consol_15m_breakout_short",
    # SHORT — MA/EMA rejection, hourly resistance rejection, double top, intraday EMA
    "ema_rejection_short",
    "hourly_resistance_rejection_short",
    "session_high_double_top",
    "intraday_ema_rejection_short",
    # "ema_loss_short",  # disabled — too noisy during evaluation
    # ── Trade management — exit alerts (critical) ───────────────────────────
    "target_1_hit",
    "target_2_hit",
    "stop_loss_hit",
    "auto_stop_out",
    # ── NOTICE — informational only (ALL DISABLED per P4) ──────────────────
    # "first_hour_summary",            # DISABLED: noise, 5 alerts/day with no value
    # "inside_day_forming",            # DISABLED (P4): 6 alerts — not an entry, premature
    # ── DISABLED — noise alerts removed ─────────────────────────────────────
    # "ma_approach",                  # NOISE: price always near some MA
    # "ma_resistance",               # NOISE: use as filter, not alert
    # "ema_resistance",              # NOISE: use as filter, not alert
    # "hourly_consolidation",        # NOISE: 40% of hours are tight range
    # "session_high_retracement",    # NOISE: describes normal intraday action
}

# ---------------------------------------------------------------------------
# Alert Categories — user-facing groupings for preference toggles
# ---------------------------------------------------------------------------

ALERT_CATEGORIES: dict[str, dict] = {
    "entry_signals": {
        "name": "Entry Signals",
        "description": "BUY alerts at support levels (MA/EMA bounces, PDL reclaim, double bottoms, fib bounce)",
        "alert_types": {
            "ma_bounce_20", "ma_bounce_50", "ma_bounce_100", "ma_bounce_200",
            "ema_bounce_20", "ema_bounce_50", "ema_bounce_100", "ema_bounce_200",
            "prior_day_low_reclaim", "prior_day_low_bounce",
            "inside_day_reclaim",
            "session_low_double_bottom", "multi_day_double_bottom",
            "fib_retracement_bounce",
            "vwap_reclaim", "vwap_bounce",
            "opening_low_base", "morning_low_retest",
            "session_low_bounce_vwap", "session_low_reversal",
            "planned_level_touch", "weekly_level_touch", "monthly_level_touch",
            "intraday_support_bounce",
            "ema_reclaim_20", "ema_reclaim_50", "ema_reclaim_100", "ema_reclaim_200",
            "ma_reclaim_20", "ma_reclaim_50", "ma_reclaim_100", "ma_reclaim_200",
            "pdh_retest_hold",
        },
    },
    "breakout_signals": {
        "name": "Breakout Signals",
        "description": "Price breaking above key levels (PDH, inside day, consolidation, ORB)",
        "alert_types": {
            "prior_day_high_breakout", "pdh_test",
            "inside_day_breakout", "outside_day_breakout",
            "opening_range_breakout",
            "weekly_high_breakout", "monthly_high_breakout",
            "consol_breakout_long", "consol_15m_breakout_long",
            "first_hour_high_breakout",
            "gap_and_go", "bb_squeeze_breakout",
        },
    },
    "short_signals": {
        "name": "Short Signals",
        "description": "SHORT entry and rejection alerts (EMA rejection, double top, breakdown)",
        "alert_types": {
            "ema_rejection_short", "ema_loss_short",
            "hourly_resistance_rejection_short",
            "intraday_ema_rejection_short",
            "session_high_double_top",
            "consol_breakout_short", "consol_15m_breakout_short",
            "spy_short_entry",
            "pdh_failed_breakout",
            "vwap_loss",
            "session_low_breakdown", "morning_low_breakdown",
            "opening_range_breakdown",
            "inside_day_breakdown",
        },
    },
    "exit_alerts": {
        "name": "Exit Alerts",
        "description": "Target hits, stop losses, and trade management (always recommended ON)",
        "alert_types": {
            "target_1_hit", "target_2_hit",
            "stop_loss_hit", "auto_stop_out",
            "trailing_stop_hit",
            "swing_target_hit", "swing_stopped_out",
        },
    },
    "resistance_warnings": {
        "name": "Resistance Warnings",
        "description": "Approaching or rejected at resistance levels (PDH, MA, weekly/monthly highs)",
        "alert_types": {
            "resistance_prior_high", "pdh_rejection",
            "hourly_resistance_approach",
            "ma_resistance", "ema_resistance",
            "weekly_high_resistance", "weekly_high_test",
            "monthly_high_resistance", "monthly_high_test",
            "resistance_prior_low",
        },
    },
    "support_warnings": {
        "name": "Support Warnings",
        "description": "Breakdown and support loss alerts (PDL breakdown, weekly/monthly low breaks)",
        "alert_types": {
            "support_breakdown",
            "prior_day_low_breakdown", "prior_day_low_resistance",
            "weekly_low_test", "weekly_low_breakdown",
            "monthly_low_test", "monthly_low_breakdown",
        },
    },
    "swing_trade": {
        "name": "Swing Trade",
        "description": "Multi-day swing setups (RSI, MACD, EMA crossovers, bull flags)",
        "alert_types": {
            "swing_rsi_approaching_oversold", "swing_rsi_oversold",
            "swing_rsi_approaching_overbought", "swing_rsi_overbought",
            "swing_ema_crossover_5_20", "swing_200ma_reclaim", "swing_pullback_20ema",
            "swing_macd_crossover", "swing_rsi_divergence",
            "swing_bull_flag", "swing_candle_pattern", "swing_consecutive_red",
            "ema_crossover_5_20",
        },
    },
    "informational": {
        "name": "Informational",
        "description": "Context and market structure (summaries, consolidation notices, MA approach)",
        "alert_types": {
            "first_hour_summary",
            "monthly_ema_touch",
            "ma_approach",
            "hourly_consolidation",
            "session_high_retracement",
            "gap_fill",
            "inside_day_forming",
        },
    },
}

# Reverse lookup: alert_type_value → category_id
ALERT_TYPE_TO_CATEGORY: dict[str, str] = {}
for _cat_id, _cat in ALERT_CATEGORIES.items():
    for _at in _cat["alert_types"]:
        ALERT_TYPE_TO_CATEGORY[_at] = _cat_id

# Exit alert types — bypass score filter, always deliver
EXIT_ALERT_TYPES: set[str] = {
    "target_1_hit", "target_2_hit",
    "stop_loss_hit", "auto_stop_out",
    "trailing_stop_hit",
    "swing_target_hit", "swing_stopped_out",
}

# Per-symbol risk overrides (defaults to DAY_TRADE_MAX_RISK_PCT if not listed)
PER_SYMBOL_RISK: dict[str, float] = {
    "SPY": 0.002, "QQQ": 0.002,           # tight for ETFs
    "NVDA": 0.004, "TSLA": 0.005,         # wider for volatile stocks
    "BTC-USD": 0.008, "ETH-USD": 0.010,   # crypto — wider for 24h volatility
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
PAPER_TRADE_MIN_SCORE = int(_get_secret("PAPER_TRADE_MIN_SCORE", "70"))

# Claude AI Trade Narrator
ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
CLAUDE_NARRATIVE_ENABLED = _get_secret("CLAUDE_NARRATIVE_ENABLED", "true").lower() == "true"
CLAUDE_MODEL = _get_secret("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_MODEL_SONNET = _get_secret("CLAUDE_MODEL_SONNET", "claude-sonnet-4-20250514")
NARRATIVE_SONNET_MIN_SCORE = int(_get_secret("NARRATIVE_SONNET_MIN_SCORE", "65"))

# Intraday Regime Narrator — AI push on SPY regime shifts
REGIME_NARRATOR_ENABLED = _get_secret("REGIME_NARRATOR_ENABLED", "true").lower() == "true"
REGIME_NARRATOR_MAX_PER_SESSION = int(_get_secret("REGIME_NARRATOR_MAX_PER_SESSION", "4"))

# Alert Clustering Intelligence — AI synthesis for multi-signal confluence
CLUSTER_NARRATOR_ENABLED = _get_secret("CLUSTER_NARRATOR_ENABLED", "true").lower() == "true"

# AI Conviction Filter (Phase 3)
AI_CONVICTION_ENABLED = _get_secret("AI_CONVICTION_ENABLED", "false").lower() == "true"
AI_CONVICTION_SUPPRESS_BELOW = int(_get_secret("AI_CONVICTION_SUPPRESS_BELOW", "30"))
AI_CONVICTION_BOOST_ABOVE = int(_get_secret("AI_CONVICTION_BOOST_ABOVE", "80"))
AI_CONVICTION_BOOST_POINTS = int(_get_secret("AI_CONVICTION_BOOST_POINTS", "10"))

# Free tier: max push notifications (DM/email) per day
FREE_DAILY_ALERT_LIMIT = 3

# Real trade position sizing
REAL_TRADE_POSITION_SIZE = 50_000        # $50k cap for regular stocks
REAL_TRADE_SPY_SHARES = 200              # Fixed 200 shares for SPY
