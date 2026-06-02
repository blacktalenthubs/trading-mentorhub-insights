"""Aggregate per-pattern forward returns and classify each as a swing-trade
or day-trade strategy, then have AI recommend keep / stop / promote.

Reads the real close-to-close forward returns computed by
analytics/forward_returns.py (ret_eod_pct, ret_eow_pct on the alerts table),
groups by alert_type, and classifies:

  Swing  — end-of-week gains hold/build beyond same-day (worth holding)
  Day    — pops at EOD but fades by Friday (capture same day, exit)
  Avoid  — neither horizon is net-positive

The aggregation + classification are pure (no DB, no network) so they're
unit-testable without pandas/sqlalchemy. The DB query lives in the router; the
Claude call lives here.
"""

from __future__ import annotations

import json
import logging
from statistics import mean, median
from typing import Optional

logger = logging.getLogger(__name__)

# Classification thresholds.
MIN_SAMPLE = 8           # below this a pattern is flagged low-confidence
SWING_EDGE_PCT = 0.5     # EOW avg must beat EOD avg by >= this many pts for "Swing"
EOW_WIN_HEALTHY = 50.0   # EOW win-rate floor for "Swing"
PROMOTE_WIN_PCT = 60.0   # win-rate floor to recommend "promote"


def classify_pattern(avg_eod: Optional[float], win_eod: Optional[float],
                     avg_eow: Optional[float], win_eow: Optional[float],
                     n: int, n_eow: int) -> dict:
    """Deterministic Swing / Day / Avoid label + confidence + keep/stop/promote.

    Inputs are per-pattern averages (percent) and win-rates (percent). avg_eow
    / win_eow may be None when no EOW horizon has matured yet.
    """
    ae = avg_eod if avg_eod is not None else 0.0
    aw = avg_eow

    # Label. (eps keeps the >= boundary robust against float drift.)
    eps = 1e-9
    if ae <= 0 and (aw is None or aw <= 0):
        label = "Avoid"
    elif aw is not None and (aw - ae) >= SWING_EDGE_PCT - eps and (win_eow or 0) >= EOW_WIN_HEALTHY:
        label = "Swing"
    elif ae > 0 and (aw is None or ae >= aw):
        label = "Day"
    else:
        label = "Day" if ae > 0 else "Avoid"

    # Confidence.
    low = n < MIN_SAMPLE or (label == "Swing" and n_eow < MIN_SAMPLE)
    confidence = "low" if low else "ok"

    # Recommendation.
    if label == "Avoid":
        recommendation = "stop"
    elif confidence == "ok":
        horizon_win = (win_eow if label == "Swing" else win_eod) or 0.0
        horizon_avg = (aw if label == "Swing" else ae) or 0.0
        recommendation = "promote" if (horizon_win >= PROMOTE_WIN_PCT and horizon_avg > 0) else "keep"
    else:
        recommendation = "keep"

    return {"classification": label, "confidence": confidence, "recommendation": recommendation}


def _stats(values: list[float]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """(avg, median, win_pct) for a list of forward-return %. None on empty."""
    if not values:
        return None, None, None
    wins = sum(1 for v in values if v > 0)
    return round(mean(values), 3), round(median(values), 3), round(wins / len(values) * 100, 1)


def aggregate_patterns(rows: list[dict], label_map: Optional[dict] = None,
                       describe=None, min_sample: int = MIN_SAMPLE) -> list[dict]:
    """Group per-alert rows by alert_type into a ranked pattern leaderboard.

    `rows`: dicts with keys alert_type, ret_eod_pct, ret_eow_pct (either pct
    may be None). `label_map`/`describe` are optional pretty-name lookups
    (from alert_type_config) — fall back to the raw alert_type.
    """
    label_map = label_map or {}
    by_type: dict[str, dict[str, list]] = {}
    for r in rows:
        at = r["alert_type"]
        bucket = by_type.setdefault(at, {"eod": [], "eow": []})
        if r.get("ret_eod_pct") is not None:
            bucket["eod"].append(float(r["ret_eod_pct"]))
        if r.get("ret_eow_pct") is not None:
            bucket["eow"].append(float(r["ret_eow_pct"]))

    patterns: list[dict] = []
    for at, b in by_type.items():
        n, n_eow = len(b["eod"]), len(b["eow"])
        if n == 0:
            continue
        avg_eod, med_eod, win_eod = _stats(b["eod"])
        avg_eow, med_eow, win_eow = _stats(b["eow"])
        cls = classify_pattern(avg_eod, win_eod, avg_eow, win_eow, n, n_eow)
        patterns.append({
            "alert_type": at,
            "label": label_map.get(at, at),
            "description": describe(at) if describe else None,
            "n": n,
            "avg_ret_eod": avg_eod,
            "median_ret_eod": med_eod,
            "win_eod_pct": win_eod,
            "n_eow": n_eow,
            "avg_ret_eow": avg_eow,
            "median_ret_eow": med_eow,
            "win_eow_pct": win_eow,
            **cls,
        })

    # Rank by EOW avg return (the "did the gains hold" signal); None last.
    patterns.sort(key=lambda p: (p["avg_ret_eow"] is None, -(p["avg_ret_eow"] or 0.0)))
    return patterns


# ── AI recommendation ────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are a quantitative trading strategist. You are given a \
table of trading PATTERNS with their REAL forward returns measured close-to-close:
- EOD = same-day close vs the alert price
- EOW = end-of-week close vs the alert price
Plus a deterministic Swing/Day/Avoid label per pattern.

Write a concise plain-text briefing with exactly three sections:

KEEP: patterns that are working — name them with their EOW win% and avg%.
STOP: patterns to drop — those that are net-negative or pure noise.
PROMOTE: the 1-3 strongest patterns to feature, and for EACH say whether to \
trade it as a SWING (hold into the week) or a DAY trade (exit at close) and why, \
citing the EOD-vs-EOW numbers.

Rules:
- Cite the actual numbers you were given. Never invent data.
- Treat patterns flagged confidence="low" as UNPROVEN — mention them only as \
"needs more data", never promote them.
- Plain text, no markdown. No preamble or signoff. Education only, not financial advice."""


def generate_recommendation(patterns: list[dict]) -> str:
    """Claude briefing over the aggregated leaderboard. Returns "" when
    Anthropic is disabled/unkeyed or on any failure (the leaderboard still
    renders without it).
    """
    from alerting.narrator import _resolve_api_key
    from alert_config import CLAUDE_MODEL_SONNET

    api_key = _resolve_api_key()
    if not api_key or not patterns:
        return ""

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        user_msg = (
            "Here is the pattern performance table. Write the keep/stop/promote "
            "briefing.\n\n" + json.dumps(patterns, indent=2, default=str)
        )
        resp = client.messages.create(
            model=CLAUDE_MODEL_SONNET,
            max_tokens=900,
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
            timeout=30.0,
        )
        return resp.content[0].text.strip()
    except Exception:
        logger.exception("Strategy-analysis Claude call failed")
        return ""
