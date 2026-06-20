"""Day-trade vs swing classification — Sub-spec L (#64 Launch Value Master).

Decided at fire time from the alert TYPE (which already names the EMA) + the
daily RSI. No EMA-location math — a `ma_bounce_*_ema50` already tells us it's a
50-EMA bounce.

  SWING  — a slow-EMA bounce (21 / 50 / 100 / 200, EMA or SMA), or a daily
           momentum/weekly type (rsi_oversold, ema_5_20_cross, weekly_rc, rsi_70).
           Target = RSI 70-75; stop = prior-day-low trail.
  DAY    — everything else: core level entries (PDL/PDH/PWH/PWL held, reclaim,
           break), 4h RC, ORL, gap-and-go, proximity, and the fast 8-EMA bounce.
           Target = nearest level (or RSI/EOD in blue sky); stop = morning low.

`swing_eligible` — a DAY trade firing with RSI already > 70 is extended; the user
MAY choose to swing it (strong momentum runs 70 -> 80+). It's a tag only; the user
decides. Pure + deterministic for unit testing.
"""

from __future__ import annotations

from typing import Optional

# Types whose baseline is swing regardless of EMA.
SWING_TYPES = frozenset({
    "tv_rsi_70", "tv_ema_5_20_cross", "tv_rsi_oversold", "tv_weekly_rc",
    "tv_weekly_ma_pullback",
    # also accept the un-prefixed rule codes
    "rsi_70", "ema_5_20_cross", "rsi_oversold", "weekly_rc", "weekly_ma_pullback",
})

# Slow-MA tokens — a bounce off any of these is a multi-day swing. The fast 8-EMA
# is NOT here (it stays a day trade). The MA set is 8/21/50/100/200.
SLOW_MA_TOKENS = ("21", "50", "100", "200")

STRONG_RSI = 70.0


def classify_trade(alert_type: Optional[str], rsi: Optional[float] = None) -> tuple[str, bool]:
    """Return ``(trade_type, swing_eligible)``.

    trade_type is "swing" or "day"; swing_eligible flags a day trade that's
    extended (RSI > 70) and could be held as a swing if momentum holds.
    """
    at = alert_type or ""
    is_swing = at in SWING_TYPES or (
        at.startswith("tv_ma_bounce_long_v3") and any(tok in at for tok in SLOW_MA_TOKENS)
    ) or (
        at.startswith("ma_bounce_long_v3") and any(tok in at for tok in SLOW_MA_TOKENS)
    )
    trade_type = "swing" if is_swing else "day"
    swing_eligible = (
        trade_type == "day" and rsi is not None and rsi > STRONG_RSI
    )
    return trade_type, swing_eligible
