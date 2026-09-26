"""Synthetic OHLCV fixtures for each breakout pattern + near-miss rejections, and a Today-tab
idempotency test. False negatives are cheap; these lock the true positives and the rejections."""
import numpy as np
import pandas as pd

from patterns.config import CONFIG
from patterns.indicators import add_indicators
from patterns import (ascending_triangle, bull_flag, cup_handle, flat_base,
                      horizontal_tba, trendline_break, writer)
from patterns.detect_utils import prefilter


# ── fixture helpers ──────────────────────────────────────────────────────────
def _to_df(close, vol=None, high=None, low=None):
    c = np.asarray(close, float)
    n = len(c)
    hi = np.asarray(high, float) if high is not None else c * 1.004
    lo = np.asarray(low, float) if low is not None else c * 0.996
    op = np.concatenate([[c[0]], c[:-1]])
    v = np.asarray(vol, float) if vol is not None else np.full(n, 1_000_000.0)
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    df = pd.DataFrame({"Open": op, "High": np.maximum(hi, np.maximum(op, c)),
                       "Low": np.minimum(lo, np.minimum(op, c)), "Close": c, "Volume": v}, index=idx)
    return add_indicators(df, CONFIG)


def _uptrend(n=360, start=40.0, end=104.0):
    return np.linspace(start, end, n)


def _ease(a, b, n):
    """Smooth (cosine) transition a→b over n bars — rounded, not linear."""
    t = np.arange(n)
    return a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * t / max(1, n - 1)))


def _breakout_bar(level, vol_mult=2.2, base_vol=1_000_000.0):
    """One green bar that closes well above `level` in the upper half of its range, on volume."""
    c = level * 1.03
    return c, level * 1.033, level * 0.999, base_vol * vol_mult   # close, high, low, vol


# ── the good fixtures ────────────────────────────────────────────────────────
def _cup_handle():
    base = _uptrend(360, 40, 104)
    rim = np.array([105.0])
    down = _ease(105, 82, 22)                 # rounded decline to the cup low
    up = _ease(82, 101, 22)                   # rounded recovery to within 5% of the rim
    handle = _ease(101, 96, 8)                # shallow handle in the cup's upper half
    close = np.concatenate([base, rim, down, up, handle])
    vol = np.full(len(close), 1_000_000.0)
    vol[-30:-8] = 1_300_000.0                 # heavier on the cup's right side
    vol[-8:] = 600_000.0                       # handle dry-up
    bc, bh, bl, bv = _breakout_bar(close[-8:].max())
    close = np.append(close, bc)
    vol = np.append(vol, bv)
    hi = close * 1.004; lo = close * 0.996; hi[-1] = bh; lo[-1] = bl
    return _to_df(close, vol, hi, lo)


def _flat_base():
    base = _uptrend(360, 40, 88)
    adv = _ease(88, 108, 40)                   # ≥20% advance before the base
    b1 = 108 + np.random.RandomState(1).uniform(-3.5, 3.0, 15)   # wider first half
    b2 = 108 + np.random.RandomState(2).uniform(-2.0, 1.8, 15)   # tighter second half
    close = np.concatenate([base, adv, b1, b2])
    vol = np.full(len(close), 1_000_000.0)
    vol[-30:-15] = 1_200_000.0
    vol[-15:] = 750_000.0                       # dry-up second half
    return _to_df(close, vol)


def _ascending_triangle():
    base = _uptrend(360, 40, 92)
    seg = []
    lows = [93, 95, 97, 99]
    for lo in lows:
        seg += list(_ease(lo, 100.0, 6)) + list(_ease(100.0, lo + 1.5, 5))   # touch ceiling ~100, rising lows
    close = np.concatenate([base, np.array(seg)])
    vol = np.full(len(close), 1_000_000.0)
    vol[-len(seg):] = np.linspace(1_400_000, 700_000, len(seg))              # declining
    hi = close * 1.004
    return _to_df(close, vol, hi)


def _bull_flag():
    base = _uptrend(360, 40, 90)
    pole = _ease(90, 112, 8)                    # +24% pole
    flag = _ease(112, 106, 6)                   # shallow drift down
    close = np.concatenate([base, pole, flag])
    vol = np.full(len(close), 1_000_000.0)
    vol[-14:-6] = 1_800_000.0                   # pole rvol high
    vol[-6:] = 650_000.0                         # flag quiet
    return _to_df(close, vol)


def _horizontal_tba():
    base = _uptrend(360, 40, 92)
    seg = []
    for _ in range(4):
        seg += list(_ease(94, 100.0, 5)) + list(_ease(100.0, 94.5, 5))       # flat ceiling ~100, flat-ish lows
    close = np.concatenate([base, np.array(seg)])
    vol = np.full(len(close), 1_000_000.0)
    vol[-len(seg):] = np.linspace(1_200_000, 850_000, len(seg))
    hi = close * 1.004
    return _to_df(close, vol, hi)


def _trendline_break():
    base = _uptrend(360, 40, 95)
    # A run of lower highs (descending trendline) then a break above.
    highs_seq = []
    for hi in (112, 108, 104, 100):
        highs_seq += list(_ease(hi, hi - 8, 6)) + list(_ease(hi - 8, hi - 4, 5))
    close = np.concatenate([base, np.array(highs_seq)])
    # break above the projected line
    close = np.append(close, close[-1] * 1.03)
    vol = np.full(len(close), 1_000_000.0)
    hi = close * 1.008
    return _to_df(close, vol, hi)


# ── the near-misses (must be REJECTED) ───────────────────────────────────────
def _v_bottom():
    base = _uptrend(360, 40, 104)
    v = np.concatenate([_ease(105, 82, 3), _ease(82, 101, 3)])   # sharp V, not rounded
    handle = _ease(101, 96, 8)
    close = np.concatenate([base, [105], v, handle])
    return _to_df(close)


def _deep_base():
    base = _uptrend(360, 40, 108)
    b = 108 + np.random.RandomState(3).uniform(-16, 4, 30)        # ~18% deep — too deep
    return _to_df(np.concatenate([base, b]))


def _deep_flag():
    base = _uptrend(360, 40, 90)
    pole = _ease(90, 112, 8)
    flag = _ease(112, 96, 6)                                      # gave back ~70% of the pole
    close = np.concatenate([base, pole, flag])
    vol = np.full(len(close), 1_000_000.0); vol[-14:-6] = 1_800_000.0; vol[-6:] = 650_000.0
    return _to_df(close, vol)


# ── tests: good fixtures fire ────────────────────────────────────────────────
def test_prefilter_passes_on_uptrend():
    assert prefilter(_cup_handle(), CONFIG) == ""


def test_cup_handle_detected():
    assert cup_handle.detect(_cup_handle(), CONFIG) is not None


def test_flat_base_detected():
    assert flat_base.detect(_flat_base(), CONFIG) is not None


def test_ascending_triangle_detected():
    assert ascending_triangle.detect(_ascending_triangle(), CONFIG) is not None


def test_bull_flag_detected():
    assert bull_flag.detect(_bull_flag(), CONFIG) is not None


def test_horizontal_tba_detected():
    assert horizontal_tba.detect(_horizontal_tba(), CONFIG) is not None


def test_trendline_break_detected():
    assert trendline_break.detect(_trendline_break(), CONFIG) is not None


# ── tests: near-misses rejected ──────────────────────────────────────────────
def test_v_bottom_rejected():
    assert cup_handle.detect(_v_bottom(), CONFIG) is None


def test_deep_base_rejected():
    assert flat_base.detect(_deep_base(), CONFIG) is None


def test_deep_flag_rejected():
    assert bull_flag.detect(_deep_flag(), CONFIG) is None


# ── Today-tab idempotency ────────────────────────────────────────────────────
def test_writer_idempotent():
    rows = [
        {"ticker": "AMD", "pattern": "flat_base", "stage": "breakout", "score": 80},
        {"ticker": "AMD", "pattern": "flat_base", "stage": "breakout", "score": 60},   # dup, lower
        {"ticker": "MRNA", "pattern": "bull_flag", "stage": "forming", "score": 70},
    ]
    b1 = writer.build_body({"rows": rows, "scanned": 2})
    b2 = writer.build_body({"rows": rows, "scanned": 2})
    keys = [(r["ticker"], r["pattern"]) for r in b1["rows"]]
    assert len(keys) == len(set(keys)) == 2                       # deduped by (ticker, pattern)
    assert [r["score"] for r in b1["rows"] if r["ticker"] == "AMD"] == [80]  # kept the best
    assert [(r["ticker"], r["pattern"], r["score"]) for r in b1["rows"]] == \
           [(r["ticker"], r["pattern"], r["score"]) for r in b2["rows"]]      # same across runs


def test_writer_empty_marker():
    b = writer.build_body({"rows": [], "scanned": 50})
    assert b["empty"] is True and b["rows"] == []
