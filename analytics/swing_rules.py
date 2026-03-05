"""Swing-trade rule functions — daily timeframe, Burns-style setups.

Rules run once daily after market close via ``swing_scan_eod()``.
They use the ``AlertSignal`` dataclass from ``intraday_rules`` but fire
through their own pipeline (not ``evaluate_rules``).
"""

from __future__ import annotations

import logging

from alert_config import (
    SWING_200MA_RECLAIM_CONFIRM_EMA10,
    SWING_EMA_CROSSOVER_MIN_SEPARATION_PCT,
    SWING_PULLBACK_PROXIMITY_PCT,
    SWING_REGIME_GATE,
    SWING_RSI_APPROACHING_OVERBOUGHT,
    SWING_RSI_APPROACHING_OVERSOLD,
    SWING_RSI_OVERBOUGHT,
    SWING_RSI_OVERSOLD,
)
from analytics.intraday_rules import AlertSignal, AlertType

logger = logging.getLogger("swing_rules")


# ---------------------------------------------------------------------------
# Regime gate
# ---------------------------------------------------------------------------

def check_spy_regime(spy_context: dict) -> bool:
    """Return True if SPY close > EMA20 (swing trading enabled).

    When ``SWING_REGIME_GATE`` is False the gate is always open.
    """
    if not SWING_REGIME_GATE:
        return True
    ema20 = spy_context.get("spy_ema20", 0.0)
    close = spy_context.get("close", 0.0)
    if not ema20 or not close:
        return False
    return close > ema20


# ---------------------------------------------------------------------------
# RSI zone crossovers
# ---------------------------------------------------------------------------

def check_rsi_zones(
    symbol: str, rsi_today: float, rsi_prev: float | None, price: float,
) -> AlertSignal | None:
    """Fire RSI zone crossover alerts at 30/35/65/70 thresholds."""
    if rsi_prev is None:
        return None

    # Approaching oversold: crossed below 35
    if rsi_today < SWING_RSI_APPROACHING_OVERSOLD <= rsi_prev:
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.SWING_RSI_APPROACHING_OVERSOLD,
            direction="NOTICE",
            price=price,
            message=(
                f"[SWING] RSI approaching oversold zone "
                f"({rsi_prev:.1f} → {rsi_today:.1f})"
            ),
        )

    # Oversold: crossed below 30
    if rsi_today < SWING_RSI_OVERSOLD <= rsi_prev:
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.SWING_RSI_OVERSOLD,
            direction="BUY",
            price=price,
            message=(
                f"[SWING] RSI oversold — potential buy zone "
                f"({rsi_prev:.1f} → {rsi_today:.1f})"
            ),
        )

    # Approaching overbought: crossed above 65
    if rsi_today > SWING_RSI_APPROACHING_OVERBOUGHT >= rsi_prev:
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.SWING_RSI_APPROACHING_OVERBOUGHT,
            direction="NOTICE",
            price=price,
            message=(
                f"[SWING] RSI approaching overbought zone "
                f"({rsi_prev:.1f} → {rsi_today:.1f})"
            ),
        )

    # Overbought: crossed above 70
    if rsi_today > SWING_RSI_OVERBOUGHT >= rsi_prev:
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.SWING_RSI_OVERBOUGHT,
            direction="SELL",
            price=price,
            message=(
                f"[SWING] RSI overbought — consider taking profits "
                f"({rsi_prev:.1f} → {rsi_today:.1f})"
            ),
        )

    return None


# ---------------------------------------------------------------------------
# Burns-style setups
# ---------------------------------------------------------------------------

def check_swing_ema_crossover_5_20(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """Daily EMA5 crosses above EMA20 (Burns META trade pattern).

    Entry: close.  Stop type: ema_cross_under_5_20.  Target: RSI 70.
    """
    ema5 = prior_day.get("ema5")
    ema5_prev = prior_day.get("ema5_prev")
    ema20 = prior_day.get("ema20")
    ema20_prev = prior_day.get("ema20_prev")
    close = prior_day.get("close")
    open_ = prior_day.get("open")

    if None in (ema5, ema5_prev, ema20, ema20_prev, close, open_):
        return None

    # Crossover: EMA5 was at/below EMA20, now above
    if ema5_prev > ema20_prev or ema5 <= ema20:
        return None

    # Anti-flicker: separation must exceed threshold
    sep = abs(ema5 - ema20) / ema20
    if sep < SWING_EMA_CROSSOVER_MIN_SEPARATION_PCT:
        return None

    # Confirm bar was green
    if close <= open_:
        return None

    score = _score_signal(prior_day)

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_EMA_CROSSOVER_5_20,
        direction="BUY",
        price=close,
        entry=close,
        message=(
            f"[SWING] EMA5/20 bullish crossover — "
            f"EMA5 {ema5:.2f} > EMA20 {ema20:.2f} | "
            f"Stop: EMA5 crosses back under EMA20 | Target: RSI 70"
        ),
        score=score,
        score_label=_score_label(score),
    )


def check_swing_200ma_reclaim(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """Close crosses back above 200 MA and above 10 EMA (Burns XLY pattern).

    Entry: close.  Stop type: close_below_200ma.  Target: RSI 70.
    """
    close = prior_day.get("close")
    prev_close = prior_day.get("prev_close")
    ma200 = prior_day.get("ma200")
    ema10 = prior_day.get("ema10")

    if None in (close, prev_close, ma200):
        return None

    # Previous close below 200MA, today above
    if prev_close >= ma200 or close <= ma200:
        return None

    # Optionally confirm close > EMA10
    if SWING_200MA_RECLAIM_CONFIRM_EMA10:
        if ema10 is None or close <= ema10:
            return None

    score = _score_signal(prior_day)

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_200MA_RECLAIM,
        direction="BUY",
        price=close,
        entry=close,
        message=(
            f"[SWING] 200 MA reclaim — close {close:.2f} > 200MA {ma200:.2f} | "
            f"Stop: close below 200MA | Target: RSI 70"
        ),
        score=score,
        score_label=_score_label(score),
    )


def check_swing_pullback_20ema(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """Close near rising 20 EMA (within 0.5%, EMA20 rising).

    Entry: close.  Stop type: close_below_20ema.  Target: RSI 70.
    """
    close = prior_day.get("close")
    ema20 = prior_day.get("ema20")
    ema20_prev = prior_day.get("ema20_prev")

    if None in (close, ema20, ema20_prev):
        return None

    # Check proximity: close within SWING_PULLBACK_PROXIMITY_PCT of EMA20
    distance_pct = abs(close - ema20) / ema20
    if distance_pct > SWING_PULLBACK_PROXIMITY_PCT:
        return None

    # EMA20 must be rising
    if ema20 <= ema20_prev:
        return None

    # Close must be at or above EMA20 (pullback *to* support, not breakdown)
    if close < ema20 * (1 - SWING_PULLBACK_PROXIMITY_PCT):
        return None

    score = _score_signal(prior_day)

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_PULLBACK_20EMA,
        direction="BUY",
        price=close,
        entry=close,
        message=(
            f"[SWING] Pullback to rising 20 EMA — "
            f"close {close:.2f}, EMA20 {ema20:.2f} "
            f"({distance_pct:.2%} away) | "
            f"Stop: close below 20 EMA | Target: RSI 70"
        ),
        score=score,
        score_label=_score_label(score),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def evaluate_swing_rules(
    symbol: str,
    prior_day: dict,
    spy_context: dict,
    fired_today: set[tuple[str, str]],
) -> list[AlertSignal]:
    """Run all swing rules for a symbol. Returns list of signals."""
    signals: list[AlertSignal] = []

    rsi_today = prior_day.get("rsi14")
    rsi_prev = prior_day.get("rsi14_prev")
    close = prior_day.get("close", 0.0)

    # RSI zone crossovers (always run, even without regime gate)
    if rsi_today is not None:
        sig = check_rsi_zones(symbol, rsi_today, rsi_prev, close)
        if sig and (symbol, sig.alert_type.value) not in fired_today:
            signals.append(sig)

    # Setup rules (require regime gate passed — caller checks)
    for check_fn in (
        check_swing_ema_crossover_5_20,
        check_swing_200ma_reclaim,
        check_swing_pullback_20ema,
    ):
        sig = check_fn(symbol, prior_day)
        if sig and (symbol, sig.alert_type.value) not in fired_today:
            # Enrich with SPY trend
            sig.spy_trend = spy_context.get("trend", "")
            signals.append(sig)

    return signals


# ---------------------------------------------------------------------------
# Watchlist categorisation
# ---------------------------------------------------------------------------

def categorize_symbol(prior_day: dict) -> str:
    """Classify symbol into Burns-style bucket.

    Categories: buy_zone | strongest | building_base | overbought | weak
    """
    close = prior_day.get("close", 0)
    ema5 = prior_day.get("ema5")
    ema10 = prior_day.get("ema10")
    ema20 = prior_day.get("ema20")
    ma50 = prior_day.get("ma50")
    rsi = prior_day.get("rsi14")

    # Defaults for missing data
    if close == 0:
        return "weak"

    # Weak: close < EMA20 or RSI < 40
    if ema20 and close < ema20:
        return "weak"
    if rsi is not None and rsi < 40:
        return "weak"

    # Overbought: RSI > 65
    if rsi is not None and rsi > 65:
        return "overbought"

    # Strongest: close > EMA5, EMA10, EMA20 and RSI 50-65
    if (
        ema5 and ema10 and ema20
        and close > ema5
        and close > ema10
        and close > ema20
        and rsi is not None
        and 50 <= rsi <= 65
    ):
        return "strongest"

    # Building base: close near MA50 (within 2%) and RSI 40-55
    if (
        ma50
        and abs(close - ma50) / ma50 < 0.02
        and rsi is not None
        and 40 <= rsi <= 55
    ):
        return "building_base"

    # Buy zone: close near EMA20 (within 1%)
    if ema20 and abs(close - ema20) / ema20 < 0.01:
        return "buy_zone"

    # Default fallback
    if rsi is not None and rsi >= 50:
        return "strongest"
    return "building_base"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_signal(prior_day: dict, spy_context: dict | None = None) -> int:
    """Score a swing signal 0-100."""
    score = 50

    close = prior_day.get("close", 0)
    open_ = prior_day.get("open", 0)
    ema20 = prior_day.get("ema20")
    rsi = prior_day.get("rsi14")

    # Green candle confirmation
    if close > open_:
        score += 10

    # RSI in favorable zone for BUY entries (40-60)
    if rsi is not None and 40 <= rsi <= 60:
        score += 10

    # Multiple MA confluence (close near multiple MAs)
    ma_near = 0
    for ma_key in ("ma20", "ma50", "ema20", "ema5", "ema10"):
        ma_val = prior_day.get(ma_key)
        if ma_val and close and abs(close - ma_val) / ma_val < 0.01:
            ma_near += 1
    if ma_near >= 2:
        score += 10

    # SPY regime strength
    if spy_context:
        spy_ema20 = spy_context.get("spy_ema20", 0)
        spy_close = spy_context.get("close", 0)
        if spy_ema20 and spy_close:
            spy_dist = (spy_close - spy_ema20) / spy_ema20
            if spy_dist > 0.01:
                score += 10

    return min(score, 100)


def _score_label(score: int) -> str:
    """Convert numeric score to letter grade."""
    if score >= 80:
        return "A+"
    if score >= 70:
        return "A"
    if score >= 55:
        return "B"
    return "C"
