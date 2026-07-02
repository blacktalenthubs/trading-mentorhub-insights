"""EMA trend-pullback detection — the VALIDATED engine.

Backtested (2yr, 45 leaders): the 20-EMA trend = +0.91R avg / +333R total; the
50-EMA pullback = +0.72R / +319R. (The 200-EMA "dip buy" was flat/negative and is
NOT included.) Pure functions over daily OHLC — no app/DB deps — so this is
unit-testable and reusable by the EOD scanner and the ad-hoc scans.

ENTRY (on the confirmed daily close):
  - uptrend: the MA is RISING over `slope_bars` AND ADX ≥ `adx_min` (skip chop),
  - pullback: the bar's LOW tags the MA (within `touch_band_pct`),
  - reclaim: it closes back ABOVE the MA on a GREEN bar,
  - not extended: the close is within `max_dist_pct` of the MA (drops the big
    gap-reclaims that close 10%+ above the line — those faded in testing).
STOP = the pullback low. TRAIL/EXIT = a confirmed close below the MA (handled
downstream, not here).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TrendConfig:
    key: str                       # alert_type emitted
    ma_len: int                    # 20 (trend) or 50 (pullback)
    slope_bars: int                # MA-rising lookback (proportional to depth)
    touch_band_pct: float = 0.4    # how close the low must tag the MA
    max_dist_pct: float = 4.0      # close must be within X% of the MA (no extended gap-reclaims)
    adx_min: float = 20.0
    require_adx: bool = True


# The two validated archetypes.
EMA_TREND_20 = TrendConfig(key="ema_trend_20", ma_len=20, slope_bars=5, touch_band_pct=0.4, max_dist_pct=4.0, adx_min=20.0)
EMA_PULLBACK_50 = TrendConfig(key="ema_pullback_50", ma_len=50, slope_bars=10, touch_band_pct=1.0, max_dist_pct=6.0, adx_min=15.0)
CONFIGS = (EMA_TREND_20, EMA_PULLBACK_50)


def adx_series(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's ADX(14)."""
    up = h.diff()
    dn = -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def detect_entry(df: pd.DataFrame, cfg: TrendConfig, i: int = -1) -> Optional[dict]:
    """Return an entry dict for bar `i` (default the last bar), or None.

    `df` must have High/Low/Close/Open columns (daily). Returns
    {alert_type, direction, entry, ma, stop, adx, dist_pct} on a valid setup.
    """
    need = cfg.ma_len + cfg.slope_bars + 15
    if df is None or len(df) < need:
        return None
    h, l, c, o = df["High"], df["Low"], df["Close"], df["Open"]
    ma = c.ewm(span=cfg.ma_len).mean()
    adx = adx_series(h, l, c)
    idx = i if i >= 0 else len(df) + i
    if idx - cfg.slope_bars < 0:
        return None
    cl = float(c.iloc[idx]); op = float(o.iloc[idx]); lo = float(l.iloc[idx])
    m = float(ma.iloc[idx]); a = float(adx.iloc[idx])
    if m <= 0 or np.isnan(m) or np.isnan(a):
        return None

    rising = m > float(ma.iloc[idx - cfg.slope_bars])
    touched = lo <= m * (1.0 + cfg.touch_band_pct / 100.0)
    green = cl > op and cl > m
    dist = (cl - m) / m * 100.0
    not_extended = dist <= cfg.max_dist_pct
    adx_ok = (not cfg.require_adx) or a >= cfg.adx_min

    if rising and touched and green and not_extended and adx_ok:
        return {
            "alert_type": cfg.key,
            "direction": "BUY",
            "entry": round(cl, 4),
            "ma": round(m, 4),
            "stop": round(lo, 4),
            "adx": round(a, 1),
            "dist_pct": round(dist, 2),
        }
    return None


def scan(df: pd.DataFrame) -> list[dict]:
    """Run both archetypes on the latest bar of `df`. Returns 0–2 entry dicts."""
    out = []
    for cfg in CONFIGS:
        hit = detect_entry(df, cfg)
        if hit:
            out.append(hit)
    return out
