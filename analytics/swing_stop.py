"""Swing prior-day-low trailing stop — Sub-spec L (#64).

A swing position's stop is NOT fixed at entry. It trails up under the rising daily
lows:
  - Day 1  → that morning's low (the entry day's low).
  - Each day after → the prior completed day's low, raised daily.
The stop only RISES (ratchet) — "we raise the stop daily". Exit on a break below it
(or on RSI 70-75, handled by the target side).

Pure + deterministic. The monitor lifecycle calls this once per swing position per
poll, passing the entry-day morning low, the list of completed daily lows since
entry, and the position's current stop.
"""

from __future__ import annotations

from typing import Optional, Sequence


def swing_trailing_stop(
    morning_low: float,
    prior_day_lows: Sequence[float],
    current_stop: Optional[float] = None,
    ratchet: bool = True,
) -> float:
    """Return the swing stop for today.

    - ``morning_low``: the entry day's low (day-1 stop).
    - ``prior_day_lows``: completed daily lows since entry, oldest→newest. Empty on day 1.
    - ``current_stop``: the position's existing stop (for the ratchet).
    - ``ratchet``: when True the stop never lowers — it only rises day to day.
    """
    base = prior_day_lows[-1] if prior_day_lows else morning_low
    if ratchet and current_stop is not None:
        return max(current_stop, base)
    return base
