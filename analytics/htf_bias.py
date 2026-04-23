"""Higher-timeframe bias for rule-base gating (Phase 2, 2026-04-23).

Ported from `analytics.ai_day_scanner._compute_htf_bias`. Scores 1h and 4h
OHLC bars on EMA-20 position + a 3-bar higher-lows/lower-highs pattern and
returns 'BULL', 'BEAR', or 'NEUTRAL' per timeframe.

Used in `api/app/background/monitor.py` after `evaluate_rules()` returns a
list of signals — counter-trend signals (e.g. 5-min MA20 bounce LONG in a
4h BEAR trend) are suppressed, and the 0–3 confluence score is attached
to every surviving signal so the Telegram 🟢/🟡 emoji lights up.

Pure Python, zero Anthropic calls. Enabled/disabled via env var
HTF_BIAS_GATE_ENABLED (default True).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

BULL = "BULL"
BEAR = "BEAR"
NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class HTFBias:
    """1h + 4h trend bias — one per symbol per poll."""

    htf_1h: str = NEUTRAL
    htf_4h: str = NEUTRAL

    @property
    def aligned_bull(self) -> bool:
        return self.htf_1h == BULL and self.htf_4h == BULL

    @property
    def aligned_bear(self) -> bool:
        return self.htf_1h == BEAR and self.htf_4h == BEAR


def _compute_bias_from_bars(bars: pd.DataFrame | None) -> str:
    """Score OHLC bars on EMA-20 position + 3-bar structure.

    Returns BULL/BEAR/NEUTRAL. Needs at least 5 bars; returns NEUTRAL
    otherwise so missing data never gates a trade (fail-open).
    """
    if bars is None or bars.empty or len(bars) < 5:
        return NEUTRAL

    closes = bars["Close"].astype(float).tolist()
    span = min(20, len(closes))
    alpha = 2 / (span + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = alpha * c + (1 - alpha) * ema

    current = closes[-1]
    price_above = current > ema * 1.001
    price_below = current < ema * 0.999

    recent = bars.tail(3)
    lows = recent["Low"].astype(float).tolist()
    highs = recent["High"].astype(float).tolist()
    higher_lows = lows[-1] > lows[0] and lows[-2] >= lows[0]
    lower_highs = highs[-1] < highs[0] and highs[-2] <= highs[0]

    bull_signals = int(price_above) + int(higher_lows)
    bear_signals = int(price_below) + int(lower_highs)

    if bull_signals >= 2:
        return BULL
    if bear_signals >= 2:
        return BEAR
    if bull_signals > bear_signals:
        return BULL
    if bear_signals > bull_signals:
        return BEAR
    return NEUTRAL


def compute_htf_bias(
    bars_1h: pd.DataFrame | None,
    bars_4h: pd.DataFrame | None,
) -> HTFBias:
    """Compute bias for both timeframes. Missing/insufficient bars → NEUTRAL."""
    return HTFBias(
        htf_1h=_compute_bias_from_bars(bars_1h),
        htf_4h=_compute_bias_from_bars(bars_4h),
    )


def should_gate_long(bias: HTFBias) -> bool:
    """True when a LONG entry should be blocked.

    Gate fires when the 4h trend is BEAR AND 1h has not yet turned BULL
    (i.e. no sign of a tactical bottom inside the larger downtrend).
    NEUTRAL on either timeframe is pass-through.
    """
    return bias.htf_4h == BEAR and bias.htf_1h != BULL


def should_gate_short(bias: HTFBias) -> bool:
    """True when a SHORT entry should be blocked (inverse of should_gate_long)."""
    return bias.htf_4h == BULL and bias.htf_1h != BEAR


def confluence_score(direction: str, bias: HTFBias) -> int:
    """Return 0–3 score for the signal's multi-timeframe confluence.

    Points: +1 rule-base fired (always), +1 1H bias agrees with direction,
    +1 4H bias agrees. RESISTANCE and NOTICE alerts get the baseline 1
    (they don't have a directional "agreement" concept).
    """
    direction = (direction or "").upper()
    score = 1
    if direction in ("BUY", "LONG"):
        if bias.htf_1h == BULL:
            score += 1
        if bias.htf_4h == BULL:
            score += 1
    elif direction == "SHORT":
        if bias.htf_1h == BEAR:
            score += 1
        if bias.htf_4h == BEAR:
            score += 1
    return score
