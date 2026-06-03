"""Pure helpers for Social-feed buzz-trend + earnings enrichment.

Kept dependency-free (stdlib only — no sqlalchemy/pandas) so the heuristics are
unit-testable in isolation and importable from analytics/social_buzz.py without
dragging in heavy deps. See refresh_social_buzz() for where these are applied.
"""

from __future__ import annotations

from typing import Optional

# How many prior hourly snapshots to read for the mentions sparkline / trend.
N_HISTORY = 6

# "Accelerating" thresholds — rising attention, not just present.
ACCEL_MIN_POINTS = 3
ACCEL_RECENT_STEP_PCT = 25.0   # last reading >= +25% vs the previous one
ACCEL_WINDOW_PCT = 60.0        # OR first->last >= +60% across the window


def _coerce_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def earnings_in_days(next_earnings_date, today) -> Optional[int]:
    """Calendar days from `today` to `next_earnings_date` (date objects), or
    None when there's no scheduled date. May be negative for a stale date —
    callers gate on 0..7.
    """
    if next_earnings_date is None:
        return None
    return (next_earnings_date - today).days


def mentions_series(symbol: str, prior_newest_first: list, current_mentions) -> list[int]:
    """Mentions for `symbol` across prior snapshots (oldest->newest) with the
    current run's count appended last. Snapshots where the symbol is absent are
    skipped, so the series is sparsity-tolerant (gaps don't create false zeros).

    `prior_newest_first` is a list of snapshot `entries` lists, newest first.
    """
    series: list[int] = []
    sym = (symbol or "").upper()
    for snap_entries in reversed(prior_newest_first or []):   # oldest -> newest
        for ent in (snap_entries or []):
            if (ent.get("symbol") or "").upper() == sym:
                series.append(_coerce_int(ent.get("mentions")))
                break
    series.append(_coerce_int(current_mentions))
    return series


def is_accelerating(series: list[int]) -> bool:
    """True when mentions are rising: at least ACCEL_MIN_POINTS readings, the
    last 3 non-decreasing, AND either the most recent step or the whole-window
    growth clears its threshold. Thin/flat/falling series -> False.
    """
    pts = [x for x in series if x is not None]
    if len(pts) < ACCEL_MIN_POINTS:
        return False
    last3 = pts[-3:]
    if not (last3[0] <= last3[1] <= last3[2]):
        return False
    prev = pts[-2]
    recent_step = ((pts[-1] - prev) / prev * 100) if prev > 0 else 0.0
    first = pts[0]
    window = ((pts[-1] - first) / first * 100) if first > 0 else 0.0
    return recent_step >= ACCEL_RECENT_STEP_PCT or window >= ACCEL_WINDOW_PCT
