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
from alerting.notifier import _send_telegram, _send_telegram_to

logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")

# Module-level state — tracks last known regime per session
_last_regime: str | None = None
_last_regime_session: str = ""
_narrations_today: int = 0
_last_narration_time: datetime | None = None
_REGIME_COOLDOWN_MINUTES = 15  # min time between regime shift notifications

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are a stock market educator. Given a mid-session SPY regime change, \
write a 2-3 sentence educational explanation for a learning trader.

Cover:
1. What changed in the intraday trend and why it matters
2. How this regime affects pattern quality (tailwind or headwind for setups)
3. What to watch for next (key level to confirm or invalidate the shift)

Rules:
- Be direct and specific — reference the INTRADAY price action, not daily MAs
- Use probability language, never guarantee outcomes
- No markdown formatting — plain text only
- Write dollar amounts WITHOUT the $ symbol to avoid rendering issues
- Keep the entire response under 60 words
- This is educational, not financial advice"""


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
        f"INTRADAY REGIME SHIFT: {prev_regime} → {new_regime}",
        f"SPY current price: {close:.2f} | Intraday trend: {trend}",
        f"Daily MAs (for reference, NOT intraday): 20MA={ma20:.2f}, 50MA={ma50:.2f}",
        f"SPY has been {'above' if close > ma20 else 'BELOW'} daily 20MA for multiple days",
        f"Intraday change today: {intraday_chg:+.2f}%",
        f"EMA20/50 spread: {ema_spread:.3f}%",
    ]
    if ma200:
        lines.append(f"Daily 200MA: {ma200:.2f} ({'above' if close > ma200 else 'BELOW'})")
    if rsi is not None:
        lines.append(f"RSI14: {rsi:.1f}")
    if at_support:
        lines.append(f"AT SUPPORT: {level_label}")
    if at_resistance:
        lines.append(f"AT RESISTANCE: {level_label}")
    if ma_support:
        lines.append(f"Near MA support: {ma_support}")

    return "\n".join(lines)


def _send_to_pro_users(msg: str) -> bool:
    """Send a message to all Pro users with Telegram enabled."""
    try:
        from db import get_pro_users_with_telegram
        users = get_pro_users_with_telegram()
    except Exception:
        users = []

    any_sent = False
    for u in users:
        chat_id = u.get("telegram_chat_id", "")
        if not chat_id:
            continue
        try:
            ok = _send_telegram_to(msg, chat_id)
            if ok:
                any_sent = True
        except Exception:
            pass
    return any_sent


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

    # Cooldown: skip if we just sent a narration recently
    global _last_narration_time
    if _last_narration_time is not None:
        elapsed = (datetime.now(ET) - _last_narration_time).total_seconds()
        if elapsed < _REGIME_COOLDOWN_MINUTES * 60:
            logger.info(
                "Regime shift %s → %s (cooldown — %ds since last narration)",
                prev_regime, new_regime, int(elapsed),
            )
            return False

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
        _send_to_pro_users(msg)
        _narrations_today += 1
        _last_narration_time = datetime.now(ET)
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
        sent = _send_to_pro_users(msg)
        if sent:
            _narrations_today += 1
            _last_narration_time = datetime.now(ET)
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
        _send_to_pro_users(msg)
        _narrations_today += 1
        _last_narration_time = datetime.now(ET)
        return True


# ---------------------------------------------------------------------------
# Daily EMA regime shift tracker (8/21 EMA: TRENDING / CAUTIOUS / TACTICAL)
# ---------------------------------------------------------------------------
_last_daily_regime: str | None = None
_last_daily_regime_session: str = ""

_DAILY_REGIME_LABELS = {
    "TRENDING": "TRENDING \u2014 SPY above 8 & 21 EMA. Portfolio mode: buy MA bounces, suppress shorts.",
    "CAUTIOUS": "CAUTIOUS \u2014 SPY below 8 EMA (above 21). Reduce exposure, tighter long criteria.",
    "TACTICAL": "TACTICAL \u2014 SPY below 21 EMA. No swings/overnight. Trade around levels & MAs, both directions, intraday focus.",
}


def check_daily_regime_shift(spy_ctx: dict | None) -> bool:
    """Check for SPY daily EMA regime change and notify if shifted."""
    global _last_daily_regime, _last_daily_regime_session

    from alert_config import SPY_REGIME_ENABLED
    if not SPY_REGIME_ENABLED:
        return False

    if spy_ctx is None:
        return False

    session = today_session()
    new_regime = spy_ctx.get("spy_daily_regime", "TACTICAL")

    if _last_daily_regime_session != session:
        _last_daily_regime = None
        _last_daily_regime_session = session

    if _last_daily_regime is None:
        _last_daily_regime = new_regime
        return False

    if new_regime == _last_daily_regime:
        return False

    prev = _last_daily_regime
    _last_daily_regime = new_regime

    logger.info("SPY daily regime shift: %s \u2192 %s", prev, new_regime)

    now_et = datetime.now(ET)
    time_str = now_et.strftime("%I:%M %p ET")
    ema8 = spy_ctx.get("spy_ema8", 0)
    ema21 = spy_ctx.get("spy_ema21", 0)
    close = spy_ctx.get("close", 0)
    label = _DAILY_REGIME_LABELS.get(new_regime, new_regime)

    msg = (
        f"DAILY REGIME SHIFT \u2014 {time_str}\n"
        f"{prev} \u2192 {new_regime}\n\n"
        f"{label}\n\n"
        f"SPY {close:.2f} | 8 EMA {ema8:.2f} | 21 EMA {ema21:.2f}"
    )
    return _send_to_pro_users(msg)
