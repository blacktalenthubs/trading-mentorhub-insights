"""Intraday Regime Narrator — AI-powered push when SPY regime shifts mid-session.

Detects when SPY's market regime changes (e.g., TRENDING_UP → PULLBACK) and
sends a 2-3 sentence Claude interpretation via Telegram.  Fires at most
REGIME_NARRATOR_MAX_PER_SESSION times per day to avoid noise in choppy markets.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytz

from alerting.alert_store import today_session
from alerting.notifier import _send_telegram

logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")

# Module-level state — tracks last known regime per session
_last_regime: str | None = None
_last_regime_session: str = ""
_narrations_today: int = 0

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are a concise day-trading coach. Given a mid-session SPY regime change, \
write a 2-3 sentence interpretation for an active day trader.

Cover:
1. What changed and why it matters (regime shift direction)
2. How it affects open BUY setups (tailwind or headwind)
3. One actionable adjustment (e.g., tighten stops, favor bounces, pause entries)

Rules:
- Be direct and specific — reference actual price levels
- Use probability language, never guarantee outcomes
- No markdown formatting — plain text only
- Write dollar amounts WITHOUT the $ symbol to avoid rendering issues
- Keep the entire response under 60 words"""


def _resolve_api_key() -> str:
    """Return Anthropic API key (env var first, then DB fallback)."""
    from alert_config import ANTHROPIC_API_KEY

    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    try:
        from db import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT anthropic_api_key FROM user_notification_prefs "
                "WHERE anthropic_api_key != '' LIMIT 1"
            ).fetchone()
            return row["anthropic_api_key"] if row else ""
    except Exception:
        return ""


def _build_prompt(
    prev_regime: str,
    new_regime: str,
    spy_ctx: dict,
) -> str:
    """Build the user prompt with regime shift context."""
    close = spy_ctx.get("close", 0)
    ma20 = spy_ctx.get("ma20", 0)
    ma50 = spy_ctx.get("ma50", 0)
    ma200 = spy_ctx.get("ma200", 0)
    trend = spy_ctx.get("trend", "neutral")
    rsi = spy_ctx.get("spy_rsi14")
    ema_spread = spy_ctx.get("spy_ema_spread_pct", 0)
    intraday_chg = spy_ctx.get("intraday_change_pct", 0)
    at_support = spy_ctx.get("spy_at_support", False)
    at_resistance = spy_ctx.get("spy_at_resistance", False)
    level_label = spy_ctx.get("spy_level_label", "")
    ma_support = spy_ctx.get("spy_at_ma_support")

    lines = [
        f"REGIME SHIFT: {prev_regime} → {new_regime}",
        f"SPY: {close:.2f} | Trend: {trend}",
        f"MAs: 20MA={ma20:.2f}, 50MA={ma50:.2f}",
        f"Intraday change: {intraday_chg:+.2f}%",
        f"EMA20/50 spread: {ema_spread:.3f}%",
    ]
    if ma200:
        lines.append(f"200MA: {ma200:.2f}")
    if rsi is not None:
        lines.append(f"RSI14: {rsi:.1f}")
    if at_support:
        lines.append(f"AT SUPPORT: {level_label}")
    if at_resistance:
        lines.append(f"AT RESISTANCE: {level_label}")
    if ma_support:
        lines.append(f"Near MA support: {ma_support}")

    return "\n".join(lines)


def check_regime_shift(spy_ctx: dict | None) -> bool:
    """Check for SPY regime change and send AI narration if shifted.

    Called every poll cycle from monitor.py.
    Returns True if a narration was sent.
    """
    global _last_regime, _last_regime_session, _narrations_today

    from alert_config import REGIME_NARRATOR_ENABLED, REGIME_NARRATOR_MAX_PER_SESSION

    if not REGIME_NARRATOR_ENABLED:
        return False

    if spy_ctx is None:
        return False

    session = today_session()
    new_regime = spy_ctx.get("regime", "CHOPPY")

    # Reset state on new session
    if _last_regime_session != session:
        _last_regime = None
        _last_regime_session = session
        _narrations_today = 0

    # First poll of the day — just record, don't narrate
    if _last_regime is None:
        _last_regime = new_regime
        return False

    # No change
    if new_regime == _last_regime:
        return False

    prev_regime = _last_regime
    _last_regime = new_regime

    # Rate limit
    if _narrations_today >= REGIME_NARRATOR_MAX_PER_SESSION:
        logger.info(
            "Regime shift %s → %s (suppressed — %d/%d narrations today)",
            prev_regime, new_regime, _narrations_today,
            REGIME_NARRATOR_MAX_PER_SESSION,
        )
        return False

    logger.info("SPY regime shift: %s → %s", prev_regime, new_regime)

    # Generate AI narration
    api_key = _resolve_api_key()
    if not api_key:
        # Send raw shift notification without AI
        now_et = datetime.now(ET)
        time_str = now_et.strftime("%I:%M %p ET")
        msg = (
            f"REGIME SHIFT \u2014 {time_str}\n"
            f"{prev_regime} \u2192 {new_regime}\n"
            f"SPY ${spy_ctx.get('close', 0):.2f}"
        )
        _send_telegram(msg)
        _narrations_today += 1
        return True

    prompt = _build_prompt(prev_regime, new_regime, spy_ctx)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=128,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            timeout=10.0,
        )
        analysis = response.content[0].text.strip()

        now_et = datetime.now(ET)
        time_str = now_et.strftime("%I:%M %p ET")
        msg = (
            f"REGIME SHIFT \u2014 {time_str}\n"
            f"{prev_regime} \u2192 {new_regime}\n\n"
            f"{analysis}"
        )
        sent = _send_telegram(msg)
        if sent:
            _narrations_today += 1
            logger.info("Regime narration sent (%d today)", _narrations_today)
        return sent

    except Exception:
        logger.exception("Regime narrator: AI call failed")
        # Fallback: send raw shift
        now_et = datetime.now(ET)
        time_str = now_et.strftime("%I:%M %p ET")
        msg = (
            f"REGIME SHIFT \u2014 {time_str}\n"
            f"{prev_regime} \u2192 {new_regime}\n"
            f"SPY ${spy_ctx.get('close', 0):.2f}"
        )
        _send_telegram(msg)
        _narrations_today += 1
        return True
