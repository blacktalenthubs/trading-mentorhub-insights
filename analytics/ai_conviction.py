"""AI Conviction Filter — LLM-based signal quality assessment.

Runs after evaluate_rules() scores a signal. Sends the full signal context
to Claude for a conviction score (0-100) and reasoning. Feature-flagged
via AI_CONVICTION_ENABLED.

No alert trigger logic here — purely additive scoring layer.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def score_conviction(
    signal,
    spy_context: dict | None = None,
) -> tuple[int, str]:
    """Score a signal's conviction via Claude.

    Returns (conviction_score 0-100, reasoning_text).
    On any failure returns (50, "") — neutral, no impact.
    """
    from alert_config import ANTHROPIC_API_KEY, CLAUDE_MODEL

    if not ANTHROPIC_API_KEY:
        return 50, ""

    # Build compact context for the LLM
    parts = [
        f"Signal: {signal.symbol} {signal.direction} {signal.alert_type.value}",
        f"Price: ${signal.price:.2f}",
    ]
    if signal.entry is not None:
        parts.append(f"Entry: ${signal.entry:.2f}")
    if signal.stop is not None:
        parts.append(f"Stop: ${signal.stop:.2f}")
    if signal.target_1 is not None:
        parts.append(f"T1: ${signal.target_1:.2f}")
    if signal.target_2 is not None:
        parts.append(f"T2: ${signal.target_2:.2f}")
    parts.append(f"Confidence: {signal.confidence}")
    parts.append(f"Score: {signal.score_label} ({signal.score})")

    if signal.score_factors:
        factors = ", ".join(f"{k}={v}" for k, v in signal.score_factors.items() if v)
        parts.append(f"Score factors: {factors}")

    parts.append(f"VWAP: {signal.vwap_position}")
    parts.append(f"Volume: {signal.volume_label}")
    parts.append(f"MTF aligned: {signal.mtf_aligned}")
    parts.append(f"Confluence: {signal.confluence}")
    if signal.gap_info:
        parts.append(f"Gap: {signal.gap_info}")
    if signal.day_pattern:
        parts.append(f"Prior day: {signal.day_pattern}")
    if signal.ma_defending:
        parts.append(f"MA defending: {signal.ma_defending}")
    if signal.ma_rejected_by:
        parts.append(f"MA rejected by: {signal.ma_rejected_by}")

    if spy_context:
        parts.append(f"SPY trend: {spy_context.get('trend', 'unknown')}")
        parts.append(f"SPY regime: {spy_context.get('regime', 'unknown')}")
        if spy_context.get("spy_rsi14"):
            parts.append(f"SPY RSI: {spy_context['spy_rsi14']:.1f}")

    if signal.message:
        # Truncate to keep prompt small
        msg = signal.message[:200]
        parts.append(f"Context: {msg}")

    # Fetch win rate for this alert type
    try:
        from analytics.intel_hub import get_alert_win_rates
        wr = get_alert_win_rates(90)
        by_type = wr.get("by_alert_type", {})
        atype = signal.alert_type.value
        if atype in by_type:
            wr_data = by_type[atype]
            parts.append(
                f"Historical win rate for this rule: {wr_data['win_rate']}% "
                f"({wr_data['wins']}W/{wr_data['losses']}L of {wr_data['total']})"
            )
    except Exception:
        pass

    context = "\n".join(parts)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=150,
            system=(
                "You are a trade signal quality filter. Given a signal's context, "
                "return a JSON object with exactly two keys: "
                '"conviction" (integer 0-100, where 0=definitely skip, 50=neutral, '
                '100=highest conviction) and "reasoning" (one sentence why). '
                "Consider: MA alignment, volume confirmation, VWAP position, "
                "MTF alignment, historical win rate for this rule type, "
                "SPY regime, and risk/reward. Return ONLY valid JSON."
            ),
            messages=[{"role": "user", "content": context}],
        )
        text = response.content[0].text.strip()

        # Parse JSON response
        data = json.loads(text)
        conviction = int(data.get("conviction", 50))
        conviction = max(0, min(100, conviction))
        reasoning = str(data.get("reasoning", ""))
        return conviction, reasoning

    except json.JSONDecodeError:
        logger.debug("ai_conviction: failed to parse JSON from response")
        return 50, ""
    except Exception:
        logger.debug("ai_conviction: API call failed", exc_info=True)
        return 50, ""
