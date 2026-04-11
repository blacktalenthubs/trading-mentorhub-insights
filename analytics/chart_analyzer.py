"""AI Chart Analyzer — multi-timeframe analysis with structured trade plans.

Provides:
- assemble_analysis_context() — gathers bars + indicators + MTF context
- build_analysis_prompt() — constructs AI prompt for structured trade plan
- compute_confluence_score() — scores multi-TF alignment (0-10)
- parse_trade_plan() — extracts structured fields from AI response
"""

from __future__ import annotations

import logging
import re
import time
from typing import Generator

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pattern Library — educational content for each setup type
# ---------------------------------------------------------------------------

PATTERN_LIBRARY = {
    "pdl_bounce": {
        "name": "Prior Day Low Bounce",
        "category": "Support",
        "difficulty": "Beginner",
        "description": "Price tests yesterday's low and holds above it — buyers defend the level",
        "icon": "🟢",
    },
    "pdl_reclaim": {
        "name": "Prior Day Low Reclaim",
        "category": "Support",
        "difficulty": "Beginner",
        "description": "Price dips below yesterday's low then recovers above it — failed breakdown",
        "icon": "🟢",
    },
    "vwap_hold": {
        "name": "VWAP Hold",
        "category": "Support",
        "difficulty": "Beginner",
        "description": "Price pulls back to VWAP and bounces — trend continuation",
        "icon": "🟢",
    },
    "vwap_reclaim": {
        "name": "VWAP Reclaim",
        "category": "Reversal",
        "difficulty": "Intermediate",
        "description": "Price crosses above VWAP from below — momentum shift bullish",
        "icon": "🔄",
    },
    "session_low_double_bottom": {
        "name": "Session Low Double Bottom",
        "category": "Support",
        "difficulty": "Beginner",
        "description": "Price tests the same low twice and holds — classic reversal",
        "icon": "🟢",
    },
    "ma_bounce": {
        "name": "Moving Average Bounce",
        "category": "Support",
        "difficulty": "Intermediate",
        "description": "Price bounces off a key moving average (50/100/200 MA or EMA)",
        "icon": "🟢",
    },
    "pdh_breakout": {
        "name": "PDH Breakout",
        "category": "Breakout",
        "difficulty": "Intermediate",
        "description": "Price breaks above yesterday's high on volume — momentum continuation",
        "icon": "🔵",
    },
    "pdh_rejection": {
        "name": "PDH Rejection",
        "category": "Resistance",
        "difficulty": "Beginner",
        "description": "Price fails at yesterday's high — sellers defend the level",
        "icon": "🔴",
    },
    "session_high_double_top": {
        "name": "Session High Double Top",
        "category": "Resistance",
        "difficulty": "Intermediate",
        "description": "Price tests session high twice and fails — distribution pattern",
        "icon": "🔴",
    },
    "vwap_loss": {
        "name": "VWAP Loss",
        "category": "Reversal",
        "difficulty": "Beginner",
        "description": "Price drops below VWAP — bearish shift, average buyer losing",
        "icon": "🔴",
    },
    "inside_day_breakout": {
        "name": "Inside Day Breakout",
        "category": "Breakout",
        "difficulty": "Advanced",
        "description": "Tight range day followed by expansion — volatility squeeze play",
        "icon": "🔵",
    },
    "fib_bounce": {
        "name": "Fibonacci Retracement Bounce",
        "category": "Support",
        "difficulty": "Advanced",
        "description": "Price bounces at 50% or 61.8% fibonacci level — mean reversion",
        "icon": "🟢",
    },
    "gap_and_go": {
        "name": "Gap & Go",
        "category": "Momentum",
        "difficulty": "Advanced",
        "description": "Stock gaps up and holds above VWAP with volume — trend continuation",
        "icon": "🔵",
    },
    "ema_rejection": {
        "name": "EMA Rejection",
        "category": "Resistance",
        "difficulty": "Intermediate",
        "description": "Price rallies into falling EMA and gets rejected — resistance confirmation",
        "icon": "🔴",
    },
}


def build_education_prompt(setup_type: str, symbol: str, entry: float,
                           stop: float, target: float) -> str:
    """Build AI prompt for pattern education — teaches WHY a setup works."""
    entry_str = f"${entry:.2f}" if entry else "N/A"
    stop_str = f"${stop:.2f}" if stop else "N/A"
    target_str = f"${target:.2f}" if target else "N/A"

    return (
        f"You are a trading educator explaining the \"{setup_type}\" pattern "
        f"to a beginner trader looking at {symbol}.\n\n"
        f"Use these ACTUAL prices from the chart:\n"
        f"Entry: {entry_str}\n"
        f"Stop: {stop_str}\n"
        f"Target: {target_str}\n\n"
        f"Explain in 4 sections:\n\n"
        f"WHAT IS IT: 2 sentences — name the pattern, describe what happened "
        f"on the chart in simple language a beginner understands.\n\n"
        f"WHY IT WORKS: 3 bullet points — the market logic (institutional orders, "
        f"supply/demand, why this level matters).\n\n"
        f"HOW TO CONFIRM:\n"
        f"✓ 3-4 checkmarks — what to verify before entering\n"
        f"✗ 1 item — what invalidates the setup\n\n"
        f"RISK MANAGEMENT:\n"
        f"Entry: {entry_str} (the level)\n"
        f"Stop: {stop_str} (where thesis breaks)\n"
        f"Target: {target_str} (next resistance/support)\n"
        f"R:R: calculate from the prices\n\n"
        f"Keep it under 150 words. Plain text. No markdown.\n"
        f"Speak simply — assume the reader is new to trading."
    )


def parse_education_response(text: str) -> dict:
    """Parse AI education response into structured sections."""
    result = {
        "what": None,
        "why": None,
        "confirm_items": [],
        "invalidation": None,
        "risk": None,
        "raw": text,
    }

    if not text:
        return result

    # WHAT IS IT
    what_match = re.search(r"WHAT IS IT[:\s]*(.+?)(?=WHY IT WORKS|HOW TO CONFIRM|RISK|$)", text, re.DOTALL | re.IGNORECASE)
    if what_match:
        result["what"] = what_match.group(1).strip()

    # WHY IT WORKS
    why_match = re.search(r"WHY IT WORKS[:\s]*(.+?)(?=HOW TO CONFIRM|RISK|$)", text, re.DOTALL | re.IGNORECASE)
    if why_match:
        result["why"] = why_match.group(1).strip()

    # HOW TO CONFIRM — extract checkmarks and X items
    confirm_match = re.search(r"HOW TO CONFIRM[:\s]*(.+?)(?=RISK|$)", text, re.DOTALL | re.IGNORECASE)
    if confirm_match:
        confirm_text = confirm_match.group(1)
        result["confirm_items"] = re.findall(r"[✓✅]\s*(.+?)(?:\n|$)", confirm_text)
        invalidation = re.findall(r"[✗❌]\s*(.+?)(?:\n|$)", confirm_text)
        if invalidation:
            result["invalidation"] = invalidation[0].strip()

    # RISK MANAGEMENT
    risk_match = re.search(r"RISK MANAGEMENT[:\s]*(.+?)$", text, re.DOTALL | re.IGNORECASE)
    if risk_match:
        result["risk"] = risk_match.group(1).strip()

    return result


# ---------------------------------------------------------------------------
# Timeframe hierarchy — maps each TF to its 2 higher timeframes
# ---------------------------------------------------------------------------

TF_HIERARCHY: dict[str, list[str]] = {
    "1m": ["5m", "1H"],
    "5m": ["1H", "D"],
    "15m": ["1H", "D"],
    "30m": ["D", "W"],
    "1H": ["D", "W"],
    "4H": ["D", "W"],
    "D": ["W", "M"],
    "W": ["M", "M"],
}

# Maps timeframe code → (yfinance period, yfinance interval)
TF_FETCH_MAP: dict[str, tuple[str, str]] = {
    "1m": ("1d", "1m"),
    "5m": ("5d", "5m"),
    "15m": ("5d", "15m"),
    "30m": ("5d", "30m"),
    "1H": ("5d", "60m"),
    "4H": ("1mo", "60m"),
    "D": ("1y", "1d"),
    "W": ("2y", "1wk"),
    "M": ("5y", "1mo"),
}

# Timeframe-specific analysis parameters
TF_PARAMS: dict[str, dict] = {
    "1m": {"style": "scalp", "stop_range": "0.1-0.3%", "hold": "minutes to 1 hour", "focus": "momentum, tape, micro-structure"},
    "5m": {"style": "scalp/day", "stop_range": "0.2-0.5%", "hold": "30 min to 2 hours", "focus": "momentum, VWAP, intraday structure"},
    "15m": {"style": "day trade", "stop_range": "0.3-0.8%", "hold": "1-4 hours", "focus": "session structure, VWAP, daily levels"},
    "30m": {"style": "day trade", "stop_range": "0.5-1.0%", "hold": "2-6 hours", "focus": "session structure, daily support/resistance"},
    "1H": {"style": "day/swing", "stop_range": "0.5-1.5%", "hold": "4 hours to 2 days", "focus": "daily MAs, multi-day levels, VWAP"},
    "4H": {"style": "swing", "stop_range": "1-2%", "hold": "1-5 days", "focus": "daily structure, MA support, weekly levels"},
    "D": {"style": "swing", "stop_range": "1-3%", "hold": "3-15 days", "focus": "MA structure, support/resistance zones, weekly trend"},
    "W": {"style": "position", "stop_range": "3-8%", "hold": "2-8 weeks", "focus": "major trend, weekly MAs, monthly levels"},
    "M": {"style": "position", "stop_range": "5-15%", "hold": "1-6 months", "focus": "secular trend, major support/resistance"},
}

# ---------------------------------------------------------------------------
# Analysis cache — 5-min TTL per (user_id, symbol, timeframe)
# ---------------------------------------------------------------------------

_analysis_cache: dict[tuple, tuple[float, dict]] = {}
_CACHE_TTL = 300  # 5 minutes


def _cache_key(user_id: int, symbol: str, timeframe: str) -> tuple:
    return (user_id, symbol.upper(), timeframe)


def get_cached_analysis(user_id: int, symbol: str, timeframe: str) -> dict | None:
    """Return cached analysis if within TTL, else None."""
    key = _cache_key(user_id, symbol, timeframe)
    if key in _analysis_cache:
        ts, result = _analysis_cache[key]
        if time.time() - ts < _CACHE_TTL:
            return result
        del _analysis_cache[key]
    return None


def set_cached_analysis(user_id: int, symbol: str, timeframe: str, result: dict):
    """Cache an analysis result."""
    key = _cache_key(user_id, symbol, timeframe)
    _analysis_cache[key] = (time.time(), result)


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------

def _fetch_bars(symbol: str, timeframe: str, max_bars: int = 100) -> pd.DataFrame:
    """Fetch OHLCV bars for the given timeframe via yfinance."""
    from analytics.market_data import fetch_ohlc

    period, interval = TF_FETCH_MAP.get(timeframe, ("5d", "60m"))
    df = fetch_ohlc(symbol, period=period, interval=interval)
    if df.empty:
        return df
    return df.tail(max_bars)


def _compute_indicators(df: pd.DataFrame) -> dict:
    """Compute basic indicators from OHLCV DataFrame."""
    if df.empty or len(df) < 5:
        return {}

    close = df["Close"]
    indicators = {}

    # Moving averages
    for period in [10, 20, 50, 100, 200]:
        if len(close) >= period:
            indicators[f"sma{period}"] = round(float(close.rolling(period).mean().iloc[-1]), 2)
    for period in [10, 20, 50]:
        if len(close) >= period:
            indicators[f"ema{period}"] = round(float(close.ewm(span=period).mean().iloc[-1]), 2)

    # RSI (Wilder's)
    if len(close) >= 15:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))
        indicators["rsi14"] = round(float(rsi.iloc[-1]), 1)

    # VWAP (session-based, computed from all bars)
    if "Volume" in df.columns and "High" in df.columns and "Low" in df.columns:
        typical = (df["High"] + df["Low"] + df["Close"]) / 3
        cum_vol = df["Volume"].cumsum()
        cum_tp_vol = (typical * df["Volume"]).cumsum()
        vwap = cum_tp_vol / cum_vol
        vwap_val = vwap.iloc[-1]
        if not pd.isna(vwap_val) and vwap_val > 0:
            indicators["vwap"] = round(float(vwap_val), 2)

    # Current price
    indicators["last_close"] = round(float(close.iloc[-1]), 2)
    indicators["bar_count"] = len(df)

    return indicators


def assemble_analysis_context(
    symbol: str,
    timeframe: str,
    bars: list[dict] | None = None,
) -> dict:
    """Gather all data needed for AI chart analysis.

    Args:
        symbol: Ticker to analyze
        timeframe: User's timeframe ("1m", "5m", ..., "W")
        bars: Optional frontend-provided OHLCV bars

    Returns:
        Dict with keys: symbol, timeframe, bars_df, indicators,
        higher_tfs, mtf_analysis, spy_context, sr_levels, win_rates, tf_params
    """
    # 1. User's timeframe bars
    if bars:
        bars_df = pd.DataFrame(bars)
        if "timestamp" in bars_df.columns:
            bars_df.index = pd.to_datetime(bars_df["timestamp"])
        # Normalize column names
        col_map = {c.lower(): c for c in bars_df.columns}
        for expected in ["Open", "High", "Low", "Close", "Volume"]:
            if expected not in bars_df.columns and expected.lower() in col_map:
                bars_df.rename(columns={col_map[expected.lower()]: expected}, inplace=True)
    else:
        bars_df = _fetch_bars(symbol, timeframe)

    indicators = _compute_indicators(bars_df)

    # 2. Higher timeframes
    higher_tfs = []
    for htf in TF_HIERARCHY.get(timeframe, []):
        htf_df = _fetch_bars(symbol, htf, max_bars=50)
        htf_ind = _compute_indicators(htf_df)
        higher_tfs.append({
            "timeframe": htf,
            "bars_df": htf_df,
            "indicators": htf_ind,
        })

    # 3. MTF analysis (daily + weekly structured)
    mtf_analysis = {}
    try:
        from analytics.intel_hub import get_mtf_analysis
        mtf_analysis = get_mtf_analysis(symbol)
    except Exception:
        logger.exception("chart_analyzer: get_mtf_analysis failed for %s", symbol)

    # 4. SPY context
    spy_context = {}
    try:
        from analytics.intraday_data import get_spy_context
        spy_context = get_spy_context() or {}
    except Exception:
        pass

    # 5. S/R levels
    sr_levels = []
    try:
        from analytics.intel_hub import get_sr_levels
        sr_levels = get_sr_levels(symbol) or []
    except Exception:
        pass

    # 6. Win rates
    win_rates = {}
    try:
        from analytics.intel_hub import get_alert_win_rates
        wr = get_alert_win_rates(days=90)
        sym_wr = wr.get("by_symbol", {}).get(symbol, {})
        if sym_wr:
            win_rates = sym_wr
    except Exception:
        pass

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars_df": bars_df,
        "indicators": indicators,
        "higher_tfs": higher_tfs,
        "mtf_analysis": mtf_analysis,
        "spy_context": spy_context,
        "sr_levels": sr_levels,
        "win_rates": win_rates,
        "tf_params": TF_PARAMS.get(timeframe, TF_PARAMS["1H"]),
    }


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_analysis_prompt(context: dict) -> str:
    """Build the system prompt for AI chart analysis.

    Returns a prompt that instructs Claude to produce a structured trade plan.
    """
    symbol = context["symbol"]
    tf = context["timeframe"]
    tf_params = context["tf_params"]
    indicators = context["indicators"]
    bars_df = context["bars_df"]

    parts = []

    # Persona + Trading Playbook
    parts.append(
        "You are TradeCoPilot AI. You analyze charts using our specific trading playbook. "
        "You are direct, precise, and honest — if there is no good trade, say NO_TRADE. "
        "IMPORTANT: This is NOT financial advice — it's educational analysis."
    )

    parts.append("""
[OUR TRADING PLAYBOOK — analyze through this lens]
We trade these high-probability setups. Look for which one applies NOW:

BUY SETUPS (long entries at key support levels):
1. MA/EMA Bounce: Price pulls back to 20/50/100/200 MA or EMA and bounces. Entry on the bounce candle, stop below the MA.
2. Prior Day Low (PDL) Reclaim: Price dips below yesterday's low then recovers above it. Buyers stepping in.
3. Prior Day High (PDH) Breakout: Price breaks and holds above yesterday's high with volume. Momentum continuation.
4. Support Double Bottom: Price tests a session low or multi-day low twice and holds. Classic reversal.
5. Inside Day Breakout: Tight range day followed by expansion above the high. Volatility squeeze play.
6. EMA Reclaim: Price drops below an EMA then reclaims it with a strong close. Failed breakdown = bullish.
7. Gap and Go: Stock gaps up and holds above VWAP with strong volume. Trend continuation.
8. Session Low Reversal: Hammer/doji at session low with volume surge. Capitulation reversal.
9. Consolidation Breakout: Tight 5-15 bar range followed by directional break with volume.
10. VWAP Reclaim: Price was trading below VWAP, closes above it. Momentum shift from bearish to bullish. Entry at VWAP, stop below session low.
11. VWAP Bounce: Price trending above VWAP, pulls back to test it, holds above. Continuation. Entry near VWAP, stop below VWAP.
12. Fibonacci Retracement Bounce: Price retraces to 50% or 61.8% fib level of the prior swing and bounces. Mean reversion at structure.
13. Weekly/Monthly Support: Price pulls back to a weekly or monthly support level and holds. Higher timeframe support = stronger conviction.

SHORT/EXIT SETUPS (at key resistance levels):
1. PDH Rejection/Failed Breakout: Price tests PDH but fails to hold above. Trapped longs.
2. Session High Double Top: Price tests a high twice and reverses. Distribution.
3. VWAP Loss: Price breaks and holds below VWAP. Intraday trend shift.
4. Support Breakdown: Key support level breaks with volume. Trend reversal.
5. EMA Rejection: Price rallies into falling EMA and gets rejected. Resistance confirmation.
6. Hourly Resistance Rejection: Price rallies into a horizontal resistance zone (multiple touches) and gets rejected with a close in the lower half of the bar.

KEY PRINCIPLES:
- Stop loss goes below the structure (MA, support level, swing low) — not arbitrary percentages
- Target 1 is the next resistance level (prior high, MA above, PDH)
- Target 2 is the extended move (weekly level, higher MA)
- Higher timeframe trend matters: don't go long against a daily downtrend
- Volume confirms: breakouts need volume, bounces need volume drying up on the pullback
- If price is stuck in a range with no setup from our playbook, say NO_TRADE""")


    # Timeframe context
    parts.append(f"\n[ANALYSIS CONTEXT]")
    parts.append(f"Symbol: {symbol}")
    parts.append(f"Timeframe: {tf} ({tf_params['style']})")
    parts.append(f"Typical stop range: {tf_params['stop_range']}")
    parts.append(f"Expected hold time: {tf_params['hold']}")
    parts.append(f"Focus areas: {tf_params['focus']}")

    # Current indicators
    if indicators:
        parts.append(f"\n[INDICATORS]")
        for k, v in indicators.items():
            if k not in ("bar_count", "last_close"):
                parts.append(f"{k}: {v}")
        parts.append(f"Current price: ${indicators.get('last_close', 'N/A')}")

    # OHLCV bars
    if not bars_df.empty:
        parts.append(f"\n[CHART BARS — last {len(bars_df)} bars on {tf}]")
        # Show last 30 bars max to keep prompt manageable
        display_df = bars_df.tail(30)
        for idx, row in display_df.iterrows():
            ts = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "strftime") else str(idx)
            parts.append(
                f"{ts}: O={float(row.get('Open', 0)):.2f} "
                f"H={float(row.get('High', 0)):.2f} "
                f"L={float(row.get('Low', 0)):.2f} "
                f"C={float(row.get('Close', 0)):.2f} "
                f"V={int(row.get('Volume', 0)):,}"
            )

    # Higher timeframe data
    for htf_data in context.get("higher_tfs", []):
        htf = htf_data["timeframe"]
        htf_ind = htf_data["indicators"]
        if htf_ind:
            parts.append(f"\n[HIGHER TIMEFRAME: {htf}]")
            for k, v in htf_ind.items():
                if k not in ("bar_count",):
                    parts.append(f"{k}: {v}")

    # MTF analysis
    mtf = context.get("mtf_analysis", {})
    if mtf:
        parts.append(f"\n[MULTI-TIMEFRAME ANALYSIS]")
        if mtf.get("mtf_text"):
            parts.append(mtf["mtf_text"])
        parts.append(f"Alignment: {mtf.get('alignment', 'unknown')}")
        parts.append(f"Confluence score: {mtf.get('confluence_score', 'N/A')}/10")

    # SPY context
    spy = context.get("spy_context", {})
    if spy:
        parts.append(f"\n[MARKET CONTEXT — SPY]")
        parts.append(f"SPY trend: {spy.get('trend', 'unknown')}")
        parts.append(f"SPY price: ${spy.get('close', 'N/A')}")
        parts.append(f"Intraday change: {spy.get('intraday_change_pct', 'N/A')}%")

    # S/R levels
    sr = context.get("sr_levels", [])
    if sr:
        parts.append(f"\n[SUPPORT/RESISTANCE LEVELS]")
        for level in sr[:8]:
            parts.append(f"${level.get('level', 0):.2f} ({level.get('label', '')}) — {level.get('distance_pct', 0):.1f}% away")

    # Win rates
    wr = context.get("win_rates", {})
    if wr and wr.get("total", 0) >= 5:
        parts.append(f"\n[HISTORICAL TRACK RECORD — {symbol}]")
        parts.append(f"Win rate: {wr.get('win_rate', 0):.0f}% ({wr.get('wins', 0)}W / {wr.get('losses', 0)}L over {wr.get('total', 0)} signals in 90 days)")

    # Output format instructions — strict, concise, no markdown
    parts.append(f"""
[OUTPUT FORMAT — STRICT RULES]
Output ONLY these fields, one per line. NO markdown, NO bold, NO headers, NO tables, NO extra sections.

SETUP: which playbook setup applies (e.g. "MA Bounce 20" or "PDH Breakout" or "None — range-bound")
DIRECTION: LONG or SHORT or NO_TRADE
ENTRY: $price — MUST be a key support/resistance level (MA, VWAP, PDL, PDH, swing low/high), NEVER the current price. If price is not at a key level right now, use the nearest level where you would place a limit order.
STOP: $price (below the structure — MA, support, swing low)
TARGET_1: $price (next resistance — prior high, MA, PDH)
TARGET_2: $price (extended target — weekly level, higher MA)
RR_RATIO: number (must be at least 1.5 for a valid trade)
CONFIDENCE: HIGH or MEDIUM or LOW
CONFLUENCE_SCORE: 0-10
TIMEFRAME_FIT: hold duration
KEY_LEVELS: $level1 (label), $level2 (label), $level3 (label)

REASONING:
PATTERN: 1 sentence — which playbook setup and why it applies here.
LEVELS: 1 sentence — the key support/resistance levels from the data (include specific prices).
CONTEXT: 1 sentence — regime, volume, or timeframe context that supports or weakens the trade.

RULES:
- CRITICAL: Entry must be a KEY LEVEL (MA, VWAP, PDL, PDH, swing low, fib level) — NOT the current market price. We are dip buyers, not chasers.
- If price is already past the key level, set Direction to WAIT or NO_TRADE.
- Use N/A for fields that don't apply (e.g. NO_TRADE has no entry/stop)
- Total response under 200 words
- NO markdown formatting (no **, no ##, no ---, no tables, no bullet points)
- Adapt stops/targets to {tf} timeframe ({tf_params['style']} style)
- If no edge, say NO_TRADE and explain what would change your mind""")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Parse structured output
# ---------------------------------------------------------------------------

def parse_trade_plan(ai_text: str) -> dict:
    """Extract structured trade plan fields from AI response text.

    Returns a dict with: direction, entry, stop, target_1, target_2,
    rr_ratio, confidence, confluence_score, timeframe_fit, key_levels,
    reasoning, higher_tf_summary.
    """
    result = {
        "setup": None,
        "direction": None,
        "entry": None,
        "stop": None,
        "target_1": None,
        "target_2": None,
        "rr_ratio": None,
        "confidence": None,
        "confluence_score": None,
        "timeframe_fit": None,
        "key_levels": [],
        "reasoning": None,
        "higher_tf_summary": None,
    }

    if not ai_text:
        return result

    # Strip markdown bold markers so **DIRECTION:** becomes DIRECTION:
    ai_text = ai_text.replace("**", "")

    # Extract simple fields
    field_patterns = {
        "setup": r"SETUP:\s*(.+?)(?:\n|$)",
        "direction": r"DIRECTION:\s*(LONG|SHORT|NO_TRADE|NO TRADE)",
        "confidence": r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW|N/?A)",
        "timeframe_fit": r"TIMEFRAME_FIT:\s*(.+?)(?:\n|$)",
        "key_levels": r"KEY_LEVELS:\s*(.+?)(?:\n|$)",
    }

    for field, pattern in field_patterns.items():
        m = re.search(pattern, ai_text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if field == "direction":
                val = val.upper().replace(" ", "_")
            elif field == "confidence" and val.upper() in ("N/A", "NA"):
                val = None
            elif field == "key_levels":
                # Handle both comma-separated and bullet-point formats
                # Extract section between KEY_LEVELS and next section header (--- or ##)
                kl_start = m.start()
                kl_section = ai_text[kl_start:]
                # Stop at next section (---, ##, REASONING:, HIGHER_TF, or blank line followed by non-bullet)
                kl_end = re.search(r"\n\s*(?:---|\#{2,}|REASONING|HIGHER_TF)", kl_section)
                if kl_end:
                    kl_section = kl_section[:kl_end.start()]
                level_lines = re.findall(r"[-•]\s*(\$[\d,.]+.+?)(?:\n|$)", kl_section)
                if level_lines:
                    val = [lv.strip() for lv in level_lines[:5] if lv.strip()]
                else:
                    val = [lv.strip() for lv in val.split(",") if lv.strip() and lv.strip() != "N/A"]
            result[field] = val

    # Extract numeric fields
    numeric_patterns = {
        "entry": r"ENTRY:\s*\$?([\d.]+)",
        "stop": r"STOP:\s*\$?([\d.]+)",
        "target_1": r"TARGET_1:\s*\$?([\d.]+)",
        "target_2": r"TARGET_2:\s*\$?([\d.]+)",
        "rr_ratio": r"RR_RATIO:\s*([\d.]+)",
        "confluence_score": r"CONFLUENCE_SCORE:\s*(\d+)",
    }

    for field, pattern in numeric_patterns.items():
        m = re.search(pattern, ai_text, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                if field == "confluence_score":
                    val = min(10, max(0, int(val)))
                result[field] = val
            except ValueError:
                pass

    # Extract multi-line sections
    # Match REASONING (with optional ## or #) up to HIGHER_TF or end
    reasoning_m = re.search(
        r"(?:#{0,3}\s*)?REASONING:?\s*\n(.*?)(?=(?:#{0,3}\s*)?HIGHER_TF|$)",
        ai_text, re.DOTALL | re.IGNORECASE,
    )
    if reasoning_m:
        text = reasoning_m.group(1).strip()
        # Strip any trailing --- separator
        text = re.sub(r"\n---+\s*$", "", text).strip()
        if text:
            result["reasoning"] = text

    htf_m = re.search(
        r"(?:#{0,3}\s*)?HIGHER_TF_SUMMARY:?\s*\n(.*?)$",
        ai_text, re.DOTALL | re.IGNORECASE,
    )
    if htf_m:
        result["higher_tf_summary"] = htf_m.group(1).strip()

    return result


# ---------------------------------------------------------------------------
# Confluence scoring
# ---------------------------------------------------------------------------

def compute_confluence_score(
    user_tf_indicators: dict,
    higher_tf_data: list[dict],
    mtf_analysis: dict,
) -> tuple[int, str]:
    """Score multi-timeframe alignment from 0-10.

    Components:
    - Trend alignment (0-4): Are all TFs trending the same direction?
    - Level proximity (0-3): Are higher TFs near conflicting levels?
    - Momentum alignment (0-3): RSI and MA slopes agreeing?

    Returns (score, explanation).
    """
    trend_score = 0
    level_score = 2  # Default neutral
    momentum_score = 0
    explanations = []

    # --- Trend alignment (0-4) ---
    alignment = mtf_analysis.get("alignment", "mixed")
    if alignment == "bullish":
        trend_score = 4
        explanations.append("All timeframes aligned bullish")
    elif alignment == "bearish":
        trend_score = 4
        explanations.append("All timeframes aligned bearish")
    elif alignment == "conflict":
        trend_score = 1
        explanations.append("Timeframes conflicting — higher TF opposes lower")
    else:
        trend_score = 2
        explanations.append("Timeframes mixed — no clear alignment")

    # --- Level proximity (0-3) ---
    # Check if higher TFs show nearby resistance (for longs) or support (for shorts)
    daily = mtf_analysis.get("daily", {})
    if daily.get("setup_type") in ("BREAKOUT", "PULLBACK_TO_MA", "TREND_CONTINUATION"):
        level_score = 3
        explanations.append("Daily structure supportive")
    elif daily.get("setup_type") == "BREAKDOWN":
        level_score = 0
        explanations.append("Daily structure breaking down — caution")
    else:
        level_score = 1

    # --- Momentum alignment (0-3) ---
    user_rsi = user_tf_indicators.get("rsi14")
    higher_rsis = [htf["indicators"].get("rsi14") for htf in higher_tf_data if htf["indicators"].get("rsi14")]

    if user_rsi and higher_rsis:
        all_bullish = user_rsi > 50 and all(r > 50 for r in higher_rsis)
        all_bearish = user_rsi < 50 and all(r < 50 for r in higher_rsis)
        if all_bullish or all_bearish:
            momentum_score = 3
            explanations.append("Momentum aligned across timeframes")
        elif any(abs(user_rsi - r) > 20 for r in higher_rsis):
            momentum_score = 1
            explanations.append("RSI divergence between timeframes")
        else:
            momentum_score = 2
    else:
        momentum_score = 1

    total = min(10, trend_score + level_score + momentum_score)
    explanation = ". ".join(explanations)
    return total, explanation


# ---------------------------------------------------------------------------
# Stream analysis (called from API endpoint)
# ---------------------------------------------------------------------------

def stream_chart_analysis(
    symbol: str,
    timeframe: str,
    bars: list[dict] | None = None,
    model: str | None = None,
) -> Generator[str, None, None]:
    """Assemble context, build prompt, and stream AI analysis.

    Yields text chunks from Claude. The caller should collect the full
    response and pass it to parse_trade_plan() for structured extraction.
    """
    from analytics.trade_coach import ask_coach

    context = assemble_analysis_context(symbol, timeframe, bars)
    prompt = build_analysis_prompt(context)

    messages = [{"role": "user", "content": f"Analyze the {timeframe} chart for {symbol} and provide a structured trade plan."}]

    yield from ask_coach(
        system_prompt=prompt,
        messages=messages,
        max_tokens=512,
        model=model,
    )


# ---------------------------------------------------------------------------
# Alert auto-analysis — lightweight "AI Take" for alert follow-ups
# ---------------------------------------------------------------------------

def generate_alert_analysis(symbol: str, timeframe: str = "5m") -> str:
    """Generate a short AI Take for an alert — 2-3 lines max.

    Returns a formatted string like:
    "AI Take: Long $142.50, Stop $141.80, T1 $144.20 (2.4:1). Confluence 7/10."
    or empty string on failure.
    """
    try:
        from analytics.trade_coach import ask_coach

        context = assemble_analysis_context(symbol, timeframe)

        # Build a compact prompt for short analysis
        prompt = build_analysis_prompt(context)
        prompt += (
            "\n\nIMPORTANT: Keep response under 100 words. "
            "Output ONLY the structured format, no extra commentary."
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Quick analysis of {symbol} on {timeframe}. "
                    "Short structured plan only."
                ),
            }
        ]

        chunks = []
        for chunk in ask_coach(system_prompt=prompt, messages=messages, max_tokens=256):
            chunks.append(chunk)

        full_text = "".join(chunks)
        plan = parse_trade_plan(full_text)

        if not plan.get("direction"):
            return ""

        direction = plan["direction"]
        if direction == "NO_TRADE":
            return f"AI Take: No clear edge on {symbol}. Wait for setup."

        parts = [f"AI Take: {direction}"]
        if plan.get("entry"):
            parts.append(f"${plan['entry']:.2f}")
        if plan.get("stop"):
            parts.append(f"Stop ${plan['stop']:.2f}")
        if plan.get("target_1"):
            parts.append(f"T1 ${plan['target_1']:.2f}")
        if plan.get("rr_ratio"):
            parts.append(f"({plan['rr_ratio']:.1f}:1)")
        if plan.get("confluence_score") is not None:
            parts.append(f"Confluence {plan['confluence_score']}/10")

        return " ".join(parts)
    except Exception:
        logger.exception("generate_alert_analysis failed for %s", symbol)
        return ""
