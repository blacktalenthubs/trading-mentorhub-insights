"""Hand-built synthetic OHLCV fixtures for the breakout pattern tests.

Every builder returns a Title-case OHLCV DataFrame of >= 400 bars (the scanner's
minimum) whose last segment is the pattern under test. Deterministic — no RNG.

The base uptrend keeps every fixture inside the pre-filter (close > rising
200 SMA, within 25% of the 52-week high, > 30% above the 52-week low, liquid).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BASE_VOL = 1_000_000.0


def bars_from_closes(closes, vols, wick: float = 0.004, first_open: float | None = None) -> pd.DataFrame:
    """OHLC from a close path: open = prior close, small symmetric wicks."""
    closes = np.asarray(closes, dtype=float)
    vols = np.asarray(vols, dtype=float)
    opens = np.concatenate([[first_open if first_open is not None else closes[0]], closes[:-1]])
    hi = np.maximum(opens, closes) * (1.0 + wick)
    lo = np.minimum(opens, closes) * (1.0 - wick)
    return pd.DataFrame({"Open": opens, "High": hi, "Low": lo, "Close": closes, "Volume": vols})


def uptrend_closes(n: int, start: float, end: float, wobble: float = 0.006) -> np.ndarray:
    """Linear ramp with a gentle deterministic wobble so bars aren't identical."""
    t = np.arange(n)
    base = np.linspace(start, end, n)
    return base * (1.0 + wobble * np.sin(t / 3.0))


def append(df: pd.DataFrame, seg: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([df, seg], ignore_index=True)


def breakout_bar(prev_close: float, buy_point: float, rvol_mult: float = 2.2, avg_vol: float = BASE_VOL) -> pd.DataFrame:
    """A confirming breakout bar: closes 2% over the buy point, near its high, up-bar, big volume."""
    close = buy_point * 1.02
    return pd.DataFrame({
        "Open": [prev_close], "High": [close * 1.004], "Low": [prev_close * 0.995],
        "Close": [close], "Volume": [avg_vol * rvol_mult],
    })


def weak_breakout_bar(prev_close: float, buy_point: float, avg_vol: float = BASE_VOL) -> pd.DataFrame:
    """Closes over the buy point but on average volume — must NOT be marked breakout."""
    close = buy_point * 1.01
    return pd.DataFrame({
        "Open": [prev_close], "High": [close * 1.004], "Low": [prev_close * 0.995],
        "Close": [close], "Volume": [avg_vol * 1.0],
    })


# ── base trend shared by every fixture ───────────────────────────────────────

def base_uptrend(n: int = 340, start: float = 50.0, end: float = 100.0) -> pd.DataFrame:
    return bars_from_closes(uptrend_closes(n, start, end), np.full(n, BASE_VOL))


# ── Pattern 1: cup and handle ────────────────────────────────────────────────

def cup_handle(
    *, depth: float = 0.25, cup_bars: int = 50, handle_bars: int = 8, handle_depth: float = 0.07,
    handle_vol: float = 700_000.0, v_shape: bool = False, with_breakout: bool = False,
) -> pd.DataFrame:
    """Rim at 100 → rounded (cosine) cup → recovery within 5% → handle dry-up."""
    df = base_uptrend(n=370, start=40.0, end=100.0)  # ends at the rim (100)
    rim = 100.0
    low = rim * (1.0 - depth)
    if v_shape:
        # sharp V: 5 bars straight down, then a slow grind back — the low sits at 10% of the span
        down = np.linspace(rim, low, 6)[1:]
        up = np.linspace(low, rim * 0.96, cup_bars - 5 + 1)[1:]
        cup = np.concatenate([down, up])
    else:
        # cosine bowl: rim down to `low` over the first half, back up to 96% of the rim
        down = rim - (rim - low) * (1.0 - np.cos(np.linspace(0, np.pi, cup_bars // 2 + 1)[1:])) / 2.0
        up = low + (rim * 0.96 - low) * (1.0 - np.cos(np.linspace(0, np.pi, cup_bars - cup_bars // 2 + 1)[1:])) / 2.0
        cup = np.concatenate([down, up])
    cup_vols = np.full(len(cup), 1_200_000.0)
    df = append(df, bars_from_closes(cup, cup_vols, first_open=rim))

    h_high = rim * 0.96
    h_low = h_high * (1.0 - handle_depth)
    handle = np.linspace(h_high, h_low, handle_bars)
    df = append(df, bars_from_closes(handle, np.full(handle_bars, handle_vol), first_open=h_high))
    if with_breakout:
        buy_point = float(df["High"].iloc[-handle_bars:].max())
        df = append(df, breakout_bar(float(df["Close"].iloc[-1]), buy_point))
    return df


# ── Pattern 2: flat base ─────────────────────────────────────────────────────

def flat_base(
    *, base_bars: int = 30, lo1: float = 99.2, hi1: float = 102.0, lo2: float = 99.8, hi2: float = 102.0,
    vol1: float = 1_200_000.0, vol2: float = 800_000.0, prior_advance: bool = True,
    with_breakout: bool = False, weak_breakout: bool = False,
) -> pd.DataFrame:
    """+25% advance over 60 bars, then a tight base that contracts in range and volume."""
    if prior_advance:
        df = base_uptrend(n=320, start=50.0, end=80.0)
        adv = uptrend_closes(60, 80.0, 100.0, wobble=0.0)
    else:
        df = base_uptrend(n=320, start=50.0, end=100.0)
        adv = np.full(60, 100.0) * (1.0 + 0.004 * np.sin(np.arange(60) / 2.0))
    df = append(df, bars_from_closes(adv, np.full(60, BASE_VOL)))
    half = base_bars // 2
    first = np.where(np.arange(half) % 2 == 0, hi1, lo1).astype(float)
    second = np.where(np.arange(base_bars - half) % 2 == 0, hi2, lo2).astype(float)
    closes = np.concatenate([first, second])
    vols = np.concatenate([np.full(half, vol1), np.full(base_bars - half, vol2)])
    df = append(df, bars_from_closes(closes, vols, wick=0.002))
    if with_breakout or weak_breakout:
        buy_point = float(df["High"].iloc[-base_bars:].max())
        mk = weak_breakout_bar if weak_breakout else breakout_bar
        df = append(df, mk(float(df["Close"].iloc[-1]), buy_point))
    return df


# ── Pattern 3: ascending triangle ────────────────────────────────────────────

def ascending_triangle(
    *, troughs=(90.0, 93.0, 96.0, 98.0), ceiling: float = 100.0, with_breakout: bool = False,
) -> pd.DataFrame:
    """Four cycles: each rises from its trough to the ceiling in 5 bars and falls to the
    next trough in 5 bars; volume declines across the window."""
    df = base_uptrend(n=360, start=50.0, end=90.0)
    closes = []
    for i, tr in enumerate(troughs):
        nxt = troughs[i + 1] if i + 1 < len(troughs) else 99.0
        closes.extend(np.linspace(tr, ceiling, 6)[1:])          # up to the ceiling (5 bars)
        closes.extend(np.linspace(ceiling, nxt, 6)[1:])         # down to the next trough (5 bars)
    closes = np.asarray(closes)
    vols = np.linspace(1_500_000.0, 800_000.0, len(closes))
    df = append(df, bars_from_closes(closes, vols, wick=0.002))
    if with_breakout:
        df = append(df, breakout_bar(float(df["Close"].iloc[-1]), float(df["High"].iloc[-40:].max())))
    return df


# ── Pattern 4: bull flag ─────────────────────────────────────────────────────

def bull_flag(
    *, pole_gain: float = 0.20, pole_bars: int = 6, flag_bars: int = 6, retrace: float = 0.25,
    flag_vol: float = 650_000.0, pole_vol: float = 1_900_000.0, with_breakout: bool = False,
) -> pd.DataFrame:
    """Sharp pole on heavy volume, then a quiet downward-drifting flag."""
    df = base_uptrend(n=400, start=50.0, end=80.0)
    start = 80.0
    top = start * (1.0 + pole_gain)
    pole = np.linspace(start, top, pole_bars + 1)[1:]
    df = append(df, bars_from_closes(pole, np.full(pole_bars, pole_vol), wick=0.002))
    flag_low = top - retrace * (top - start)
    flag = np.linspace(top * 0.995, flag_low * 1.003, flag_bars)
    df = append(df, bars_from_closes(flag, np.full(flag_bars, flag_vol), wick=0.002))
    if with_breakout:
        df = append(df, breakout_bar(float(df["Close"].iloc[-1]), float(df["High"].iloc[-flag_bars:].max())))
    return df
