"""Tests for check_ma_reclaim — the open-above RECLAIM rule.

Reclaim = today OPENED ABOVE the level (support), WICKED down to tag it, and
CLOSED back above it. Distinct from a bounce (any touch) and a cross-up
(prior close below). Anchored on the Sept-4 chart-validated cases.
"""

import pandas as pd

from analytics.intraday_rules import AlertType, check_ma_reclaim


def _bars(rows):
    """rows = list of (open, high, low, close) → intraday DataFrame."""
    return pd.DataFrame([{"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000}
                         for o, h, l, c in rows])


def test_qualifies_open_above_wick_reclaim():
    """LRCX-style: opened above the 100 EMA, wicked to it, closed above."""
    lvl = 302.80
    bars = _bars([(304.0, 305.0, 303.5, 304.2),   # opened above
                  (304.2, 304.5, 302.75, 303.4),  # wicked to/through the level
                  (303.4, 303.8, 303.0, 303.5)])  # closed back above
    sig = check_ma_reclaim("LRCX", bars, lvl, "100 EMA",
                           AlertType.EMA_RECLAIM_100, today_open=304.0)
    assert sig is not None
    assert sig.alert_type == AlertType.EMA_RECLAIM_100
    assert sig.direction == "BUY"
    assert sig.stop < lvl < sig.entry  # stop below the reclaimed level, entry above


def test_rejects_open_below_crossup():
    """MRVL-style: opened BELOW the 21 EMA then crossed up — NOT a reclaim."""
    lvl = 220.63
    bars = _bars([(219.40, 221.0, 219.30, 220.8),   # opened below the level
                  (220.8, 223.0, 220.5, 222.5)])     # crossed up, closed above
    sig = check_ma_reclaim("MRVL", bars, lvl, "21 EMA",
                           AlertType.EMA_RECLAIM_21, today_open=219.40)
    assert sig is None  # open was below → disqualified


def test_rejects_never_wicked_to_level():
    """Opened above and stayed above — never came back to tag the level."""
    lvl = 302.80
    bars = _bars([(305.0, 307.0, 304.5, 306.0),
                  (306.0, 308.0, 305.5, 307.5)])   # session low 304.5 > level
    sig = check_ma_reclaim("X", bars, lvl, "100 EMA",
                           AlertType.EMA_RECLAIM_100, today_open=305.0)
    assert sig is None


def test_rejects_close_still_below_level():
    """Wicked to it but the last bar is still under the level (not reclaimed)."""
    lvl = 302.80
    bars = _bars([(305.0, 305.5, 301.0, 302.0),
                  (302.0, 302.5, 301.5, 302.10)])   # close 302.10 <= level
    sig = check_ma_reclaim("X", bars, lvl, "100 EMA",
                           AlertType.EMA_RECLAIM_100, today_open=305.0)
    assert sig is None


def test_rejects_stale_ran_too_far():
    """Reclaimed but price ran > MAX_DISTANCE above the level (chasing)."""
    lvl = 300.0
    bars = _bars([(305.0, 312.0, 299.5, 310.0)])   # low tagged 299.5, close 310 (+3.3%)
    sig = check_ma_reclaim("X", bars, lvl, "50 EMA",
                           AlertType.EMA_RECLAIM_50, today_open=305.0)
    assert sig is None


def test_rejects_bad_inputs():
    bars = _bars([(304.0, 305.0, 302.5, 303.5)])
    assert check_ma_reclaim("X", bars, None, "50 EMA", AlertType.EMA_RECLAIM_50, 304.0) is None
    assert check_ma_reclaim("X", bars, 302.8, "50 EMA", AlertType.EMA_RECLAIM_50, 0) is None
    assert check_ma_reclaim("X", _bars([]), 302.8, "50 EMA", AlertType.EMA_RECLAIM_50, 304.0) is None
