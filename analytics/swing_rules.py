"""Swing-trade rule functions — daily timeframe, Burns-style setups.

Rules run once daily after market close via ``swing_scan_eod()``.
They use the ``AlertSignal`` dataclass from ``intraday_rules`` but fire
through their own pipeline (not ``evaluate_rules``).
"""

from __future__ import annotations

import logging

from alert_config import (
    CONSECUTIVE_DAYS_THRESHOLD,
    DIVERGENCE_LOOKBACK_BARS,
    DIVERGENCE_MIN_SWING_SIZE,
    ENGULFING_MIN_BODY_RATIO,
    FLAG_CONSOLIDATION_MAX_DAYS,
    FLAG_CONSOLIDATION_MIN_DAYS,
    FLAG_IMPULSE_MIN_PCT,
    FLAG_PULLBACK_MAX_RETRACE,
    HAMMER_WICK_RATIO,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
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

    # Approaching oversold: DISABLED — noise, fires on every pullback
    # if rsi_today < SWING_RSI_APPROACHING_OVERSOLD <= rsi_prev:
    #     ...

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

    # Approaching overbought: DISABLED — noise, fires in every uptrend
    # if rsi_today > SWING_RSI_APPROACHING_OVERBOUGHT >= rsi_prev:
    #     ...

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
# Professional swing rules — MACD Signal Line Crossover
# ---------------------------------------------------------------------------


def check_swing_macd_crossover(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """Daily MACD crosses above signal line → bullish momentum.

    Requires macd_line, macd_signal, macd_line_prev, macd_signal_prev
    in prior_day dict.
    """
    macd = prior_day.get("macd_line")
    macd_prev = prior_day.get("macd_line_prev")
    signal = prior_day.get("macd_signal")
    signal_prev = prior_day.get("macd_signal_prev")
    close = prior_day.get("close")

    if None in (macd, macd_prev, signal, signal_prev, close):
        return None

    # Crossover: MACD was at/below signal, now above
    if macd_prev > signal_prev or macd <= signal:
        return None

    score = _score_signal(prior_day)

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_MACD_CROSSOVER,
        direction="BUY",
        price=close,
        entry=close,
        message=(
            f"[SWING] MACD bullish crossover — "
            f"MACD {macd:.4f} > Signal {signal:.4f} | "
            f"Stop: MACD crosses back below signal | Target: RSI 70"
        ),
        score=score,
        score_label=_score_label(score),
    )


# ---------------------------------------------------------------------------
# Professional swing rules — RSI Divergence
# ---------------------------------------------------------------------------


def check_swing_rsi_divergence(
    symbol: str, daily_closes: list[float], daily_rsi: list[float],
) -> AlertSignal | None:
    """Detect bullish RSI divergence: price lower low but RSI higher low.

    Args:
        daily_closes: Last N daily close prices (oldest first).
        daily_rsi: Last N daily RSI values (oldest first).
    """
    n = DIVERGENCE_LOOKBACK_BARS
    if len(daily_closes) < n or len(daily_rsi) < n:
        return None

    closes = daily_closes[-n:]
    rsi_vals = daily_rsi[-n:]

    # Find swing lows: local minima in price
    price_lows = []
    for i in range(1, len(closes) - 1):
        if closes[i] < closes[i - 1] and closes[i] < closes[i + 1]:
            price_lows.append((i, closes[i], rsi_vals[i]))

    if len(price_lows) < 2:
        return None

    # Check last two swing lows for divergence
    prev_low = price_lows[-2]
    curr_low = price_lows[-1]

    # Bullish divergence: price lower low, RSI higher low
    price_made_lower_low = curr_low[1] < prev_low[1]
    swing_size = abs(curr_low[1] - prev_low[1]) / prev_low[1]
    rsi_made_higher_low = curr_low[2] > prev_low[2]

    if not (price_made_lower_low and rsi_made_higher_low
            and swing_size >= DIVERGENCE_MIN_SWING_SIZE):
        return None

    close = closes[-1]
    score = 60  # divergence is a moderate-confidence signal

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_RSI_DIVERGENCE,
        direction="BUY",
        price=close,
        entry=close,
        message=(
            f"[SWING] Bullish RSI divergence — "
            f"price ${prev_low[1]:.2f}→${curr_low[1]:.2f} (lower low), "
            f"RSI {prev_low[2]:.1f}→{curr_low[2]:.1f} (higher low)"
        ),
        score=score,
        score_label=_score_label(score),
    )


# ---------------------------------------------------------------------------
# Professional swing rules — Bull Flag Pattern
# ---------------------------------------------------------------------------


def check_swing_bull_flag(
    symbol: str, daily_bars: list[dict],
) -> AlertSignal | None:
    """Detect bull flag: strong impulse → tight consolidation → breakout.

    Args:
        daily_bars: List of dicts with open/high/low/close, oldest first.
                    Needs at least impulse + flag + 1 breakout bar.
    """
    min_bars = 5 + FLAG_CONSOLIDATION_MAX_DAYS + 1
    if len(daily_bars) < min_bars:
        return None

    # Search for impulse move in the window before consolidation
    for impulse_start in range(len(daily_bars) - FLAG_CONSOLIDATION_MIN_DAYS - 2):
        impulse_end = impulse_start + 5  # minimum 5-day impulse
        if impulse_end >= len(daily_bars) - FLAG_CONSOLIDATION_MIN_DAYS:
            break

        impulse_low = daily_bars[impulse_start]["low"]
        impulse_high = max(d["high"] for d in daily_bars[impulse_start:impulse_end])
        if impulse_low <= 0:
            continue
        impulse_pct = (impulse_high - impulse_low) / impulse_low

        if impulse_pct < FLAG_IMPULSE_MIN_PCT:
            continue

        # Look for consolidation (flag) after impulse
        flag_start = impulse_end
        for flag_len in range(FLAG_CONSOLIDATION_MIN_DAYS, FLAG_CONSOLIDATION_MAX_DAYS + 1):
            flag_end = flag_start + flag_len
            if flag_end >= len(daily_bars):
                break

            flag_bars = daily_bars[flag_start:flag_end]
            flag_high = max(d["high"] for d in flag_bars)
            flag_low = min(d["low"] for d in flag_bars)

            # Check retracement: flag low shouldn't drop more than 50% of impulse
            retrace = (impulse_high - flag_low) / (impulse_high - impulse_low)
            if retrace > FLAG_PULLBACK_MAX_RETRACE:
                continue

            # Check breakout: last bar closes above flag high
            breakout_bar = daily_bars[flag_end] if flag_end < len(daily_bars) else daily_bars[-1]
            if breakout_bar["close"] <= flag_high:
                continue

            entry = round(flag_high, 2)
            stop = round(flag_low, 2)
            risk = entry - stop
            if risk <= 0:
                continue

            return AlertSignal(
                symbol=symbol,
                alert_type=AlertType.SWING_BULL_FLAG,
                direction="BUY",
                price=breakout_bar["close"],
                entry=entry,
                stop=stop,
                target_1=round(entry + risk, 2),
                target_2=round(entry + 2 * risk, 2),
                confidence="high",
                message=(
                    f"[SWING] Bull flag breakout — "
                    f"{impulse_pct:.1%} impulse, {flag_len}-day flag, "
                    f"breakout above ${flag_high:.2f}"
                ),
                score=75,
                score_label="A",
            )

    return None


# ---------------------------------------------------------------------------
# Professional swing rules — Candle Patterns (Hammer / Engulfing)
# ---------------------------------------------------------------------------


def check_swing_candle_patterns(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """Detect hammer or bullish engulfing at support.

    Hammer: small body, long lower wick (>2x body).
    Bullish Engulfing: current green candle body > prior red candle body.
    """
    close = prior_day.get("close")
    open_ = prior_day.get("open")
    high = prior_day.get("high")
    low = prior_day.get("low")
    prev_close = prior_day.get("prev_close")
    prev_open = prior_day.get("prev_open")
    ema20 = prior_day.get("ema20")

    if None in (close, open_, high, low):
        return None

    body = abs(close - open_)
    bar_range = high - low
    if bar_range <= 0:
        return None

    # Hammer: long lower wick, small body in upper half
    lower_wick = min(close, open_) - low
    upper_wick = high - max(close, open_)
    is_hammer = (
        body > 0
        and lower_wick >= HAMMER_WICK_RATIO * body
        and upper_wick < body  # small upper wick
        and close > open_  # green candle preferred
    )

    # Bullish Engulfing: current green body > prior red body
    is_engulfing = False
    if prev_close is not None and prev_open is not None:
        prev_body = abs(prev_close - prev_open)
        is_engulfing = (
            close > open_  # current is green
            and prev_close < prev_open  # prior was red
            and prev_body > 0
            and body >= ENGULFING_MIN_BODY_RATIO * prev_body
        )

    if not is_hammer and not is_engulfing:
        return None

    # Prefer signals near support (EMA20 or below)
    near_support = True
    if ema20 and close > 0:
        distance = (close - ema20) / ema20
        near_support = distance < 0.02  # within 2% of EMA20

    pattern_name = "Hammer" if is_hammer else "Bullish Engulfing"
    confidence = "high" if near_support else "medium"
    score = _score_signal(prior_day)

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_CANDLE_PATTERN,
        direction="BUY",
        price=close,
        entry=close,
        message=(
            f"[SWING] {pattern_name} candle at "
            f"{'support' if near_support else 'current level'} — "
            f"close ${close:.2f}"
        ),
        confidence=confidence,
        score=score,
        score_label=_score_label(score),
    )


# ---------------------------------------------------------------------------
# Professional swing rules — Consecutive Red Days
# ---------------------------------------------------------------------------


def check_swing_consecutive_days(
    symbol: str, daily_bars: list[dict],
) -> AlertSignal | None:
    """3+ consecutive red days near support → mean-reversion BUY signal.

    DISABLED: fires on every normal pullback, no candle/volume confluence.
    """
    return None
    if len(daily_bars) < CONSECUTIVE_DAYS_THRESHOLD:  # noqa: E501 — unreachable, kept for reference
        return None

    # Count consecutive red days from the end
    red_count = 0
    for bar in reversed(daily_bars):
        if bar.get("close", 0) < bar.get("open", 0):
            red_count += 1
        else:
            break

    if red_count < CONSECUTIVE_DAYS_THRESHOLD:
        return None

    last = daily_bars[-1]
    close = last.get("close", 0)
    ema20 = last.get("ema20")

    # Check proximity to support (EMA20)
    near_support = False
    if ema20 and close > 0:
        distance = abs(close - ema20) / ema20
        near_support = distance < 0.02  # within 2%

    if not near_support:
        return None

    score = 55  # mean-reversion is moderate confidence

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_CONSECUTIVE_RED,
        direction="BUY",
        price=close,
        entry=close,
        message=(
            f"[SWING] {red_count} consecutive red days near 20 EMA support "
            f"(${ema20:.2f}) — mean-reversion setup"
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

    # RSI 30 bounce (runs even without regime gate — oversold is oversold)
    sig = check_swing_rsi_30_bounce(symbol, prior_day)
    if sig and (symbol, sig.alert_type.value) not in fired_today:
        signals.append(sig)

    # Setup rules (require regime gate passed — caller checks)
    for check_fn in (
        check_swing_ema_crossover_5_20,
        check_swing_200ma_reclaim,
        check_swing_pullback_20ema,
        check_swing_200ma_hold,
        check_swing_50ma_hold,
        check_swing_weekly_support,
        check_swing_macd_crossover,
        check_swing_candle_patterns,
    ):
        sig = check_fn(symbol, prior_day)
        if sig and (symbol, sig.alert_type.value) not in fired_today:
            # Enrich with SPY trend
            sig.spy_trend = spy_context.get("trend", "")
            signals.append(sig)

    # RSI divergence (needs historical series, passed via prior_day)
    daily_closes = prior_day.get("daily_closes", [])
    daily_rsi = prior_day.get("daily_rsi", [])
    if daily_closes and daily_rsi:
        sig = check_swing_rsi_divergence(symbol, daily_closes, daily_rsi)
        if sig and (symbol, sig.alert_type.value) not in fired_today:
            sig.spy_trend = spy_context.get("trend", "")
            signals.append(sig)

    # Consecutive red days (needs daily bar history)
    daily_bars = prior_day.get("daily_bars", [])
    if daily_bars:
        sig = check_swing_consecutive_days(symbol, daily_bars)
        if sig and (symbol, sig.alert_type.value) not in fired_today:
            sig.spy_trend = spy_context.get("trend", "")
            signals.append(sig)

    # Bull flag (needs daily bar history)
    if daily_bars:
        sig = check_swing_bull_flag(symbol, daily_bars)
        if sig and (symbol, sig.alert_type.value) not in fired_today:
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
    """Convert numeric score to quality label."""
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Moderate"
    if score >= 40:
        return "Weak"
    return "Caution"


# ---------------------------------------------------------------------------
# Spec 14 — New Swing Entry Rules
# ---------------------------------------------------------------------------


def check_swing_rsi_30_bounce(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """RSI14 crosses above 30 from below — oversold reversal entry.

    Conditions:
    1. RSI was below 30 yesterday, now above 30
    2. Daily close in upper 50% of range (buying pressure)
    3. Entry: daily close
    4. Stop: close below the low of the oversold period
    """
    rsi = prior_day.get("rsi14")
    rsi_prev = prior_day.get("rsi14_prev")
    close = prior_day.get("close", 0)
    high = prior_day.get("high", 0)
    low = prior_day.get("low", 0)

    if rsi is None or rsi_prev is None or close <= 0:
        return None

    # RSI must cross above 30 (was below, now above)
    if not (rsi_prev < 30 and rsi >= 30):
        return None

    # Close in upper 50% of range (buying pressure confirmation)
    bar_range = high - low
    if bar_range <= 0 or (close - low) / bar_range < 0.5:
        return None

    # Stop: below today's low (the bounce day low)
    stop = round(low * 0.995, 2)  # 0.5% below the low
    entry = round(close, 2)
    risk = entry - stop
    if risk <= 0:
        return None

    score = 60
    ma200 = prior_day.get("ma200") or prior_day.get("ema200")
    if ma200 and close <= ma200 * 1.02:
        score += 20  # near 200MA = higher conviction
    if prior_day.get("volume_ratio", 1) > 1.2:
        score += 10

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_RSI_30_BOUNCE,
        direction="BUY",
        price=close,
        entry=entry,
        stop=stop,
        target_1=round(entry + risk * 2, 2),   # 2R initial target
        target_2=round(entry + risk * 3.5, 2),  # RSI 50 target
        message=(
            f"[SWING] RSI 30 bounce — RSI {rsi_prev:.1f} → {rsi:.1f} | "
            f"Entry ${entry:.2f}, Stop ${stop:.2f} (close below low) | "
            f"T1: RSI 45, T2: RSI 50"
        ),
        score=score,
        score_label=_score_label(score),
    )


def check_swing_200ma_hold(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """Price wicks to 200MA and closes above — structural support hold.

    Conditions:
    1. Daily low within 1% of 200MA
    2. Daily close above 200MA
    3. Was above 200MA previously (pullback, not breakdown)
    """
    close = prior_day.get("close", 0)
    low = prior_day.get("low", 0)
    ma200 = prior_day.get("ma200") or prior_day.get("ema200")
    prev_close = prior_day.get("prev_close")

    if not ma200 or ma200 <= 0 or close <= 0 or not prev_close:
        return None

    # Low must wick to within 1% of 200MA
    if low > ma200 * 1.01:
        return None

    # Close must be above 200MA (held as support)
    if close <= ma200:
        return None

    # Note: we allow both pullbacks (prev_close > 200MA) and reclaims
    # (prev_close < 200MA). The 200MA hold is significant in both cases —
    # closing above it after wicking to it is the key signal.

    entry = round(close, 2)
    stop = round(ma200 * 0.995, 2)  # close below 200MA = invalidated
    risk = entry - stop
    if risk <= 0:
        return None

    score = 70
    rsi = prior_day.get("rsi14")
    if rsi and rsi < 40:
        score += 15
    high = prior_day.get("high", close)
    if high > low and (close - low) / (high - low) > 0.6:
        score += 10  # hammer-like candle

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_200MA_HOLD,
        direction="BUY",
        price=close,
        entry=entry,
        stop=stop,
        target_1=round(prior_day.get("ema50") or entry + risk * 2, 2),
        target_2=round(prior_day.get("ema20") or entry + risk * 3, 2),
        message=(
            f"[SWING] 200MA hold — low ${low:.2f} wicked to 200MA ${ma200:.2f}, "
            f"closed above at ${close:.2f} | "
            f"Stop: close below 200MA | T1: 50MA, T2: 20MA"
        ),
        score=score,
        score_label=_score_label(score),
    )


def check_swing_50ma_hold(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """Price wicks to 50MA and closes above — trend support hold.

    Conditions:
    1. Daily low within 0.5% of 50MA
    2. Daily close above 50MA
    3. 50MA is rising (bullish trend)
    """
    close = prior_day.get("close", 0)
    low = prior_day.get("low", 0)
    ma50 = prior_day.get("ema50") or prior_day.get("ma50")

    if not ma50 or ma50 <= 0 or close <= 0:
        return None

    # Low must wick to within 0.5% of 50MA
    if low > ma50 * 1.005:
        return None

    # Close must be above 50MA
    if close <= ma50:
        return None

    # 50MA should be rising (approximate: close > ma50 by small amount = trend up)
    ema20 = prior_day.get("ema20")
    if ema20 and ema20 < ma50:
        return None  # downtrend — 20MA below 50MA

    entry = round(close, 2)
    stop = round(ma50 * 0.995, 2)
    risk = entry - stop
    if risk <= 0:
        return None

    score = 65
    rsi = prior_day.get("rsi14")
    if rsi and 35 <= rsi <= 45:
        score += 15
    high = prior_day.get("high", close)
    if high > low and (close - low) / (high - low) > 0.5:
        score += 10

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_50MA_HOLD,
        direction="BUY",
        price=close,
        entry=entry,
        stop=stop,
        target_1=round(prior_day.get("ema20") or entry + risk * 2, 2),
        target_2=round(prior_day.get("high", 0) or entry + risk * 3, 2),
        message=(
            f"[SWING] 50MA hold — low ${low:.2f} wicked to 50MA ${ma50:.2f}, "
            f"closed above at ${close:.2f} | "
            f"Stop: close below 50MA | T1: 20MA, T2: prior high"
        ),
        score=score,
        score_label=_score_label(score),
    )


def check_swing_weekly_support(
    symbol: str, prior_day: dict,
) -> AlertSignal | None:
    """Price holds at prior week low / weekly support zone — multi-week support.

    Conditions:
    1. Daily close within 1% of prior_week_low
    2. Daily close above prior_week_low (held)
    3. Close in upper 50% of daily range
    """
    close = prior_day.get("close", 0)
    low = prior_day.get("low", 0)
    pw_low = prior_day.get("prior_week_low")

    if not pw_low or pw_low <= 0 or close <= 0:
        return None

    # Low must wick near prior week low (within 1%)
    if low > pw_low * 1.01:
        return None

    # Close must be above (held as support)
    if close <= pw_low:
        return None

    # Close in upper 50% of range
    high = prior_day.get("high", close)
    bar_range = high - low
    if bar_range > 0 and (close - low) / bar_range < 0.5:
        return None

    entry = round(close, 2)
    stop = round(pw_low * 0.995, 2)
    risk = entry - stop
    if risk <= 0:
        return None

    pw_high = prior_day.get("prior_week_high", entry + risk * 3)

    score = 70
    rsi = prior_day.get("rsi14")
    if rsi and rsi < 35:
        score += 15
    ma200 = prior_day.get("ma200") or prior_day.get("ema200")
    if ma200 and abs(pw_low - ma200) / ma200 < 0.02:
        score += 10  # weekly support + 200MA confluence

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SWING_WEEKLY_SUPPORT,
        direction="BUY",
        price=close,
        entry=entry,
        stop=stop,
        target_1=round(pw_high if pw_high else entry + risk * 2, 2),
        target_2=round(entry + risk * 3, 2),
        message=(
            f"[SWING] Weekly support hold — low ${low:.2f} near PWL ${pw_low:.2f}, "
            f"closed ${close:.2f} | "
            f"Stop: close below weekly low | T1: prior week high ${pw_high:.2f}"
        ),
        score=score,
        score_label=_score_label(score),
    )
