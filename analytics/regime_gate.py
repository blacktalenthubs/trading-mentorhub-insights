"""SPY-regime gate + hourly consolidation breakout detection.

Extracted from `analytics/intraday_rules.py` per Spec 49 FR-408 (amended A1).
The function is named `compute_spy_gate` (not `spy_regime_gate` as some
earlier draft text suggested). Returns gate ∈ {"green", "yellow", "red"}.

V2 consumers today:
  - `api/app/background/monitor.py:214` calls `compute_spy_gate` lazily (this
    consumer is being deleted with the V1 monitor stack).
  - `triage-agent` will adopt `compute_spy_gate` in a follow-up; today its
    SPY-regime logic is inline and slightly different. That migration is
    out of scope for Spec 49.

Dependency closure (no `analytics.*` imports beyond what's already inline):
  - stdlib: logging
  - pandas
  - alert_config: SPY_GATE_*, HOURLY_CONSOL_*
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def detect_hourly_consolidation_break(
    bars_5m: pd.DataFrame,
) -> dict | None:
    """Detect hourly consolidation range breakout from 5-min bars.

    Resamples 5-min bars to 1-hour, checks if recent hourly bars
    formed a tight range (< 1.2x hourly ATR), and if the current bar
    breaks out.

    Uses ATR-based threshold instead of fixed % — adapts to each
    symbol's volatility and current market regime.

    Returns dict with:
      direction: "UP", "DOWN", or "RANGE"
      status: "breakout" or "consolidating"
      range_high: float
      range_low: float
      range_pct: float (% width)
      break_price: float
      hourly_atr: float (for logging)
    Or None if no consolidation detected.
    """
    from alert_config import (
        HOURLY_CONSOL_ATR_LOOKBACK, HOURLY_CONSOL_ATR_MULT,
        HOURLY_CONSOL_MAX_RANGE_PCT, HOURLY_CONSOL_MIN_BARS,
    )

    if bars_5m.empty or len(bars_5m) < 12 * (HOURLY_CONSOL_MIN_BARS + 1):
        return None

    # Resample 5-min bars to 1-hour
    hourly = bars_5m.resample("1h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()

    if len(hourly) < HOURLY_CONSOL_MIN_BARS + 1:
        return None

    # Compute hourly ATR (true range = High - Low for intraday)
    hourly_tr = hourly["High"] - hourly["Low"]
    atr_bars = min(len(hourly) - 1, HOURLY_CONSOL_ATR_LOOKBACK)
    if atr_bars < 2:
        return None
    hourly_atr = hourly_tr.iloc[-(atr_bars + 1):-1].mean()
    if hourly_atr <= 0:
        return None

    # Check if the prior N hourly bars form a tight range
    consol_window = hourly.iloc[-(HOURLY_CONSOL_MIN_BARS + 1):-1]
    range_high = consol_window["High"].max()
    range_low = consol_window["Low"].min()
    if range_low <= 0:
        return None

    range_width = range_high - range_low
    range_pct = range_width / range_low
    atr_threshold = hourly_atr * HOURLY_CONSOL_ATR_MULT

    # ATR-based check: range must be tighter than 1.2x ATR
    if range_width > atr_threshold:
        return None  # range too wide relative to recent volatility

    # Absolute cap: safety net for extreme cases
    if range_pct > HOURLY_CONSOL_MAX_RANGE_PCT:
        return None  # range too wide in absolute terms

    # Check current hourly bar for breakout
    current = hourly.iloc[-1]
    base = {
        "range_high": round(range_high, 2),
        "range_low": round(range_low, 2),
        "range_pct": round(range_pct * 100, 2),
        "break_price": round(float(current["Close"]), 2),
        "hourly_atr": round(float(hourly_atr), 2),
    }

    if current["Close"] > range_high:
        return {"direction": "UP", "status": "breakout", **base}
    elif current["Close"] < range_low:
        return {"direction": "DOWN", "status": "breakout", **base}

    # Still in range — consolidation forming
    return {"direction": "RANGE", "status": "consolidating", **base}


def compute_spy_gate(spy_bars: pd.DataFrame, spy_vwap: pd.Series | None) -> dict:
    """Compute SPY gate status for BUY alert suppression.

    Returns dict with:
      gate: "green" | "yellow" | "red"
      vwap_dominance: float (0-1, % of recent bars above VWAP)
      above_ema: bool (price above 60-period EMA on 5-min ≈ 20 EMA on 15-min)
      reason: str (human-readable explanation)
    """
    from alert_config import (
        SPY_GATE_LOOKBACK_BARS, SPY_GATE_GREEN_PCT, SPY_GATE_RED_PCT,
        SPY_GATE_EMA_PERIOD,
    )

    result = {"gate": "green", "vwap_dominance": 1.0, "above_ema": True, "hourly_break": None, "reason": ""}

    if spy_bars.empty:
        return result

    # 1. VWAP dominance: % of recent bars closing above VWAP
    if spy_vwap is not None and not spy_vwap.empty:
        lookback = min(SPY_GATE_LOOKBACK_BARS, len(spy_bars))
        recent_closes = spy_bars["Close"].iloc[-lookback:]
        recent_vwap = spy_vwap.iloc[-lookback:]
        if len(recent_closes) == len(recent_vwap) and lookback > 0:
            above = (recent_closes.values > recent_vwap.values).sum()
            result["vwap_dominance"] = above / lookback
        else:
            result["vwap_dominance"] = 0.5  # can't compute, assume neutral

    # 2. Intraday EMA trend (60-bar EMA on 5-min ≈ 20 EMA on 15-min)
    if len(spy_bars) >= SPY_GATE_EMA_PERIOD:
        ema = spy_bars["Close"].ewm(span=SPY_GATE_EMA_PERIOD, adjust=False).mean()
        result["above_ema"] = float(spy_bars["Close"].iloc[-1]) > float(ema.iloc[-1])
    else:
        result["above_ema"] = True  # not enough data, assume neutral

    # 3. Hourly consolidation breakout detection
    from alert_config import HOURLY_CONSOL_ENABLED
    if HOURLY_CONSOL_ENABLED:
        hbreak = detect_hourly_consolidation_break(spy_bars)
        if hbreak:
            result["hourly_break"] = hbreak
            logger.info(
                "Hourly consolidation break: %s (range %.2f%%, high $%.2f, low $%.2f)",
                hbreak["direction"], hbreak["range_pct"],
                hbreak["range_high"], hbreak["range_low"],
            )

    # 4. Determine gate level
    vd = result["vwap_dominance"]
    ae = result["above_ema"]
    hb = result.get("hourly_break")

    # Hourly breakout overrides — highest conviction signal (only on actual breakouts)
    if hb and hb.get("status") == "breakout":
        if hb["direction"] == "UP" and ae:
            result["gate"] = "green"
            result["reason"] = (
                f"HOURLY BREAKOUT UP ${hb['break_price']} "
                f"(range {hb['range_pct']:.1f}%) + above EMA"
            )
            return result
        elif hb["direction"] == "DOWN" and not ae:
            result["gate"] = "red"
            result["reason"] = (
                f"HOURLY BREAKDOWN ${hb['break_price']} "
                f"(range {hb['range_pct']:.1f}%) + below EMA — NO LONGS"
            )
            return result

    # Standard VWAP + EMA gate
    if vd >= SPY_GATE_GREEN_PCT and ae:
        result["gate"] = "green"
        result["reason"] = f"SPY above VWAP ({vd:.0%}) + above 15m EMA"
    elif vd < SPY_GATE_RED_PCT and not ae:
        result["gate"] = "red"
        result["reason"] = f"SPY below VWAP ({vd:.0%}) + below 15m EMA — NO LONGS"
    elif vd < SPY_GATE_RED_PCT or not ae:
        result["gate"] = "yellow"
        result["reason"] = f"SPY mixed — VWAP {vd:.0%}, EMA {'above' if ae else 'below'}"
    else:
        result["gate"] = "yellow"
        result["reason"] = f"SPY neutral — VWAP {vd:.0%}"

    return result
