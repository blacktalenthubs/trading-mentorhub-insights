"""Per-trade-style exit plan — ONE simple target/exit rule per alert.

Backend-owned and unit-tested, so the fragile logic NEVER lives in Pine again
(2026-06-21). The Pine fires a dumb trigger; this turns the trigger + a couple of
RSI values into the single target + exit instruction the user actually trades.

Design (locked with the user):
  Day        → next resistance (a price target)
  Gap-and-go → exit at RSI 75+, stop = morning low
  Swing      → exit at RSI 70, or trail stop up to each daily PDL
  Long hold  → trim at RSI 70+, or trail the 5-week EMA
"""
from __future__ import annotations

from typing import Optional


def trade_style(alert_type: str) -> str:
    """Map an alert rule → its trade style. Self-contained (keyed on the rule)
    so it's testable without the API; mirrors alert_config.CATEGORY_TO_GROUP."""
    a = (alert_type or "").replace("tv_", "")
    if a.startswith("gap"):
        return "Gap-and-go"
    if a.startswith("weekly_rc") or a.startswith("monthly_rc") or a.startswith("staged_pwl"):
        return "Day"   # a reclaim/level-hold is a day-trade tool, not a hold-for-days swing (2026-07-07)
    if a.startswith("weekly_") or a.startswith("monthly_") or "_sma200" in a or "_ema200" in a:
        return "Long hold"
    if (a.startswith("rsi_oversold") or a.startswith("swing_rsi") or a.startswith("ema_5_20")
            or a.startswith("ema_trend") or a.startswith("ema_pullback")
            or a.startswith("character_change") or a.startswith("base_buy")
            or a.startswith("monthly_ma_reclaim") or a.startswith("rsi_70")):
        return "Swing"   # ma_bounce dropped → it's a DAY trade; 20-EMA trend/base setups are the swings (2026-07-07)
    return "Day"  # levels (PDH/PDL/PWH/PWL…), rc_4h, ORL, pullback, etc.


def _now(rsi: Optional[float]) -> str:
    return f" (now {rsi:.0f})" if rsi is not None else ""


def build_exit_plan(
    alert_type: str,
    direction: str,
    entry: Optional[float],
    stop: Optional[float],
    rsi: Optional[float] = None,
    weekly_rsi: Optional[float] = None,
    next_resistance: Optional[float] = None,
    morning_low: Optional[float] = None,
) -> dict:
    """Return {style, target, stop, exit} — one simple plan per trade style."""
    style = trade_style(alert_type)

    if style == "Gap-and-go":
        return {
            "style": "gap",           # short code → alerts.trade_type (String(10))
            "label": "Gap-and-go",
            "target": "RSI 75+",
            "stop": morning_low if morning_low is not None else stop,
            "exit": f"Exit at RSI 75+{_now(rsi)}",
        }

    if style == "Day":
        # The target PRICE already has its own field on the card — restating it here
        # double-printed the target (and `:.4g` rendered it as ugly sci-notation). So
        # describe the LEVEL instead, keyed off direction: a long aims at resistance
        # ABOVE, a short covers into support BELOW (saying "resistance" on a short was
        # just wrong). No number — the Target field carries it.
        is_short = direction.upper() in ("SELL", "SHORT")
        return {
            "style": "day",
            "label": "Day trade",
            "target": next_resistance,
            "stop": stop,
            "exit": "Target: next support below" if is_short else "Target: next resistance above",
        }

    # Swing AND Long hold are managed IDENTICALLY (user, 2026-06-21): begin trimming at
    # DAILY RSI 70+ (most names pause there before the next leg — discretionary how much /
    # how long you hold after), and the HARD stop is the reclaim/setup low (below entry).
    # No weekly-close wait, no 5w-EMA trail — same plan whether you call it swing or long.
    is_long = style == "Long hold"
    return {
        "style": "long" if is_long else "swing",
        "label": "Long hold" if is_long else "Swing trade",
        "target": "RSI 70 (daily)",
        "stop": stop,
        "exit": f"Trim at daily RSI 70+{_now(rsi)}",
    }
