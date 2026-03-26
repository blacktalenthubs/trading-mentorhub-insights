"""Alert Clustering Intelligence — AI synthesis for consolidated multi-signal alerts.

When _consolidate_signals() merges 2+ BUY signals for the same symbol, this module
generates a richer narrative that explains WHY the confluence matters, replacing the
default narrator output.
"""

from __future__ import annotations

import logging

from alert_config import (
    CLAUDE_MODEL,
    CLAUDE_MODEL_SONNET,
    NARRATIVE_SONNET_MIN_SCORE,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a concise day-trading analyst. Given a multi-signal confluence alert \
(2+ rules fired simultaneously for the same symbol), write a 3-4 sentence \
synthesis explaining why this confluence is significant.

Cover:
1. Name the confluence pattern (e.g., "triple support confluence")
2. Why these specific signals together are stronger than individually
3. Key level that multiple signals agree on
4. One-line actionable take (entry conviction level, where to set stop)

Rules:
- Be direct and specific — reference actual price levels and signal types
- Explain the STRUCTURAL reason the confluence matters (e.g., "institutional \
level with volume confirmation")
- Use probability language, never guarantee outcomes
- No markdown formatting — plain text only
- Keep the entire response under 80 words"""


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


def _build_prompt(signal, confirming_types: list[str]) -> str:
    """Build the user prompt with cluster context."""
    lines = [
        f"Symbol: {signal.symbol}",
        f"Primary signal: {signal.alert_type.value}",
        f"Direction: {signal.direction}",
        f"Price: ${signal.price:.2f}",
    ]

    if signal.entry:
        lines.append(f"Entry: ${signal.entry:.2f}")
    if signal.stop:
        lines.append(f"Stop: ${signal.stop:.2f}")
    if signal.target_1:
        lines.append(f"T1: ${signal.target_1:.2f}")
    if signal.target_2:
        lines.append(f"T2: ${signal.target_2:.2f}")

    lines.append(f"Score: {signal.score} ({signal.score_label})")
    lines.append(f"Confidence: {signal.confidence}")

    if signal.volume_label:
        lines.append(f"Volume: {signal.volume_label}")
    if signal.vwap_position:
        lines.append(f"VWAP: {signal.vwap_position}")
    if signal.spy_trend:
        lines.append(f"SPY trend: {signal.spy_trend}")
    if signal.confluence_ma:
        lines.append(f"MA confluence: {signal.confluence_ma}")

    lines.append("")
    lines.append(f"CONFIRMING SIGNALS ({len(confirming_types)}):")
    for ct in confirming_types:
        lines.append(f"  - {ct}")

    lines.append("")
    lines.append(f"Context: {signal.message}")

    return "\n".join(lines)


def narrate_cluster(
    signal,
    confirming_types: list[str],
) -> str:
    """Generate AI synthesis for a consolidated multi-signal cluster.

    Args:
        signal: The primary AlertSignal (highest-scored from consolidation).
        confirming_types: List of confirming signal type names
            (e.g., ["ma_bounce_50", "prior_day_low_reclaim"]).

    Returns:
        AI-generated narrative string, or empty string on failure.
    """
    from alert_config import CLUSTER_NARRATOR_ENABLED

    if not CLUSTER_NARRATOR_ENABLED:
        return ""

    if not confirming_types:
        return ""

    api_key = _resolve_api_key()
    if not api_key:
        return ""

    prompt = _build_prompt(signal, confirming_types)

    # Use Haiku for all narratives (cost savings during evaluation phase)
    model = CLAUDE_MODEL
    max_tokens = 192
    timeout = 10.0

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout,
        )
        narrative = response.content[0].text.strip()
        logger.info(
            "%s: cluster narrative generated (%d confirming, model=%s)",
            signal.symbol, len(confirming_types), model.split("-")[1] if "-" in model else model,
        )
        return narrative

    except Exception:
        logger.exception("%s: cluster narrator failed", signal.symbol)
        return ""
