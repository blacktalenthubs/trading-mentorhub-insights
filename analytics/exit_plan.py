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
    if a.startswith("weekly_") or "_sma200" in a or "_ema200" in a:
        return "Long hold"
    if (a.startswith("rsi_oversold") or a.startswith("ema_5_20")
            or a.startswith("ma_bounce") or a.startswith("rsi_70")):
        return "Swing"
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
        return {
            "style": "day",
            "label": "Day trade",
            "target": next_resistance,
            "stop": stop,
            "exit": (f"Target: next resistance ${next_resistance:.4g}"
                     if next_resistance else "Target: next resistance above"),
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
