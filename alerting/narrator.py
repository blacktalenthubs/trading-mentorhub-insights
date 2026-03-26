"""AI Trade Narrator — Claude-powered trade thesis generation."""

from __future__ import annotations

import logging
from datetime import date

from alert_config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_MODEL_SONNET,
    CLAUDE_NARRATIVE_ENABLED,
    NARRATIVE_SONNET_MIN_SCORE,
)
from analytics.intraday_rules import AlertSignal, AlertType
from db import get_db

logger = logging.getLogger(__name__)

# In-memory cache: (symbol, alert_type_value, session_date) → narrative string
_narrative_cache: dict[tuple[str, str, str], str] = {}
_cache_session: str = ""

# Exit signals — mechanical, no thesis needed
_SKIP_TYPES = {
    AlertType.TARGET_1_HIT,
    AlertType.TARGET_2_HIT,
    AlertType.STOP_LOSS_HIT,
    AlertType.AUTO_STOP_OUT,
}

_SYSTEM_PROMPT = """\
You are a stock market pattern educator. Given a detected pattern's full context, \
write a 2-3 sentence educational explanation of why this pattern is worth studying \
(or why it shows signs of weakness).

Rules:
- Lead with the pattern type and key price level
- Mention volume, VWAP position, and market regime if relevant
- Include the risk/reward ratio and quality grade
- Frame as education: "This pattern shows..." not "You should buy..."
- Never use more than 3 sentences
- No markdown formatting (no bold, italic, headers) — plain text only
- This is for educational purposes only — never give financial advice"""

_SYSTEM_PROMPT_ENHANCED = """\
You are a stock market educator writing a detailed pattern analysis. Given a \
detected pattern's full context, write a 4-5 sentence educational analysis covering:

1. The pattern — what setup was detected and at what price level
2. Quality assessment — rate this HIGH, MEDIUM, or LOW quality with a one-line reason
3. Key invalidation level — the price where this pattern thesis breaks
4. Context — how market regime, volume, and nearby S/R levels affect this pattern
5. Lesson — what a disciplined trader would watch for before considering action

Rules:
- Be specific — use actual numbers from the context
- Include risk/reward ratio and quality grade
- Frame as education, never as recommendations
- Use language like "this pattern suggests" not "you should"
- No markdown formatting — plain text only
- Keep to 4-5 sentences max
- This is for educational purposes only"""


def _build_user_prompt(signal: AlertSignal) -> str:
    """Format all AlertSignal fields into a structured context block."""
    entry = signal.entry or signal.price
    stop = signal.stop or 0.0
    risk = entry - stop if stop > 0 else 0.0
    reward_t1 = (signal.target_1 - entry) if signal.target_1 else 0.0
    rr = reward_t1 / risk if risk > 0 else 0.0

    lines = [
        f"Symbol: {signal.symbol}",
        f"Direction: {signal.direction}",
        f"Alert Type: {signal.alert_type.value.replace('_', ' ').title()}",
        f"Price: ${signal.price:.2f}",
        f"Entry: ${entry:.2f}",
        f"Stop: ${stop:.2f}" if stop > 0 else "Stop: N/A",
        f"Target 1: ${signal.target_1:.2f}" if signal.target_1 else "Target 1: N/A",
        f"Target 2: ${signal.target_2:.2f}" if signal.target_2 else "Target 2: N/A",
        f"Risk: ${risk:.2f} ({risk / entry * 100:.1f}%)" if risk > 0 else "Risk: N/A",
        f"R:R Ratio: {rr:.1f}:1" if rr > 0 else "R:R Ratio: N/A",
        f"Score: {signal.score}/100 ({signal.score_label})" if signal.score > 0 else "Score: N/A",
        f"Confidence: {signal.confidence}" if signal.confidence else "",
        f"Volume: {signal.volume_label}" if signal.volume_label else "",
        f"VWAP: {signal.vwap_position}" if signal.vwap_position else "",
        f"SPY Trend: {signal.spy_trend}" if signal.spy_trend else "",
        f"Session Phase: {signal.session_phase}" if signal.session_phase else "",
        f"Gap Info: {signal.gap_info}" if signal.gap_info else "",
        f"Relative Strength: {signal.rs_ratio:.2f}" if signal.rs_ratio else "",
        f"MTF Aligned: {'Yes' if signal.mtf_aligned else 'No'}",
        f"Confluence: {'Yes' if signal.confluence else 'No'}"
        + (f" ({signal.confluence_ma})" if signal.confluence_ma else ""),
        f"Prior Day Pattern: {signal.day_pattern}" if signal.day_pattern else "",
        f"MA Defending: {signal.ma_defending}" if signal.ma_defending else "",
        f"MA Rejected By: {signal.ma_rejected_by}" if signal.ma_rejected_by else "",
        f"Message: {signal.message}" if signal.message else "",
    ]
    return "\n".join(line for line in lines if line)


def _resolve_api_key() -> str:
    """Return Anthropic API key: per-user DB key first, then env var."""
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT anthropic_api_key FROM user_notification_prefs "
                "WHERE anthropic_api_key != '' LIMIT 1"
            ).fetchone()
            return row["anthropic_api_key"] if row else ""
    except Exception:
        return ""


def generate_narrative(signal: AlertSignal) -> str:
    """Generate a 2-3 sentence trade thesis using Claude API.

    Returns empty string on failure (graceful fallback).
    Caches per (symbol, alert_type, session_date).
    """
    global _cache_session

    api_key = _resolve_api_key()

    # Guard: disabled or no API key
    if not CLAUDE_NARRATIVE_ENABLED or not api_key:
        return ""

    # Skip exit signals
    if signal.alert_type in _SKIP_TYPES:
        return ""

    session = date.today().isoformat()

    # Clear cache on new session
    if _cache_session != session:
        _narrative_cache.clear()
        _cache_session = session

    # Cache lookup
    cache_key = (signal.symbol, signal.alert_type.value, session)
    if cache_key in _narrative_cache:
        logger.debug("Narrative cache hit: %s", cache_key)
        return _narrative_cache[cache_key]

    # Use Haiku for all narratives (cost savings during evaluation phase)
    model = CLAUDE_MODEL
    system_prompt = _SYSTEM_PROMPT
    max_tokens = 256

    # Call Claude API
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": _build_user_prompt(signal)}],
            timeout=15.0 if use_sonnet else 10.0,
        )
        narrative = response.content[0].text.strip()
        _narrative_cache[cache_key] = narrative
        logger.info(
            "Narrative [%s] for %s %s: %s",
            "sonnet" if use_sonnet else "haiku",
            signal.symbol, signal.alert_type.value, narrative[:80],
        )
        return narrative

    except Exception:
        logger.exception("Failed to generate narrative for %s %s", signal.symbol, signal.alert_type.value)
        return ""
