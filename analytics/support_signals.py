"""Support / Oversold engine — where price is at support you'd buy the dip / sell a put.

One board, several ways a name lands on it (any fires):
  Rising 20/50 MA  the bar wicks to a RISING 20- or 50-day SMA and closes back above it
  200 SMA          same at the 200-day SMA (the institutional line)
  VWAP / POC / VAL a bounce off the rolling VWAP, the volume POC, or the value-area low
  Daily RSI        RSI(14) turned up from under the oversold zone (reclaim)
  Weekly RSI       the WEEKLY RSI turned up from under the zone

Selling a put isn't a separate strategy — it's what you do AT these support points, so each
row carries the suggested strike (price - OTM%). Names that are oversold on the weekly but
not yet bouncing come back too (weekly_oversold) as the watch ladder. Timing only — verify
IV in-broker; this is not option data.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from analytics.volume_profile_signals import compute_profile, rolling_vwap

OVERSOLD_ZONE = 40.0
MA_TOL = 0.01      # how close the low must get to a level to count as tagging it (1%)
OTM = 0.05         # put strike this far out-of-the-money
DTE = 30
RISE_LOOKBACK = 5  # a MA is "rising" if it's higher than this many bars ago


@dataclass
class SupportSignal:
    symbol: str
    price: float
    rsi_d: float
    rsi_w: float
    weekly_oversold: bool                 # weekly RSI < the zone (the watch ladder)
    triggers: list[str] = field(default_factory=list)   # which supports fired NOW
    levels: list[str] = field(default_factory=list)      # "POC 123.4" refs for the tooltip
    strike: float = 0.0                   # suggested put strike (price - OTM%)
    dte: int = DTE

    @property
    def at_support(self) -> bool:
        return bool(self.triggers)


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI — same as the pine + the volume-profile engine."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def _rsi_reversal(rsi: pd.Series, zone: float) -> bool:
    """Prior bar was a local RSI trough inside the oversold zone; RSI is now turning up."""
    if len(rsi) < 3:
        return False
    r, r1, r2 = float(rsi.iloc[-1]), float(rsi.iloc[-2]), float(rsi.iloc[-3])
    return r1 < r and r1 <= r2 and r1 < zone


def _sma(close: pd.Series, n: int) -> float | None:
    return float(close.rolling(n).mean().iloc[-1]) if len(close) >= n else None


def _rising(close: pd.Series, n: int, look: int = RISE_LOOKBACK) -> bool:
    """The n-SMA is sloping up (now > `look` bars ago)."""
    if len(close) < n + look:
        return False
    ma = close.rolling(n).mean()
    return float(ma.iloc[-1]) > float(ma.iloc[-1 - look])


def _bounce(o: float, l: float, c: float, level: float | None, tol: float) -> bool:
    """A bounce OPENS above the level (support from above), wicks down to tag it, closes green."""
    return level is not None and o > level and l <= level * (1 + tol) and c > o


def detect_support(daily: pd.DataFrame, weekly: pd.DataFrame, symbol: str, *,
                   zone: float = OVERSOLD_ZONE, ma_tol: float = MA_TOL,
                   otm: float = OTM, dte: int = DTE) -> SupportSignal | None:
    """Return a signal if `symbol` is bouncing at a support / oversold point, OR is oversold
    on the weekly (the watch ladder). None when there's nothing to surface.

    `daily` / `weekly` are OHLC frames (capitalised cols, oldest→newest) from
    analytics.market_data.fetch_ohlc. `daily` needs a Volume column for the profile.
    """
    if daily is None or weekly is None or len(daily) < 3 or len(weekly) < 3:
        return None
    dc = daily["Close"].astype(float)
    do = daily["Open"].astype(float)
    dl = daily["Low"].astype(float)
    c, o, l = float(dc.iloc[-1]), float(do.iloc[-1]), float(dl.iloc[-1])

    rsi_d = _rsi(dc)
    rsi_w = _rsi(weekly["Close"].astype(float))
    rd, rw = float(rsi_d.iloc[-1]), float(rsi_w.iloc[-1])

    triggers: list[str] = []
    levels: list[str] = []

    # Rising 20 & 50 MA bounces — combined into one "rising short-MA support" trigger.
    sma20, sma50 = _sma(dc, 20), _sma(dc, 50)
    r20 = _rising(dc, 20) and _bounce(o, l, c, sma20, ma_tol)
    r50 = _rising(dc, 50) and _bounce(o, l, c, sma50, ma_tol)
    if r20 or r50:
        triggers.append("Rising 20/50 MA")
        if r20 and sma20:
            levels.append(f"20MA {sma20:.2f}")
        if r50 and sma50:
            levels.append(f"50MA {sma50:.2f}")

    # 200 SMA bounce (the institutional line).
    sma200 = _sma(dc, 200)
    if _bounce(o, l, c, sma200, ma_tol):
        triggers.append("200 SMA")
        levels.append(f"200MA {sma200:.2f}")

    # Volume-profile supports: rolling VWAP, POC, value-area low — a bounce off each.
    prof = compute_profile(daily)
    vwap = rolling_vwap(daily)
    if _bounce(o, l, c, vwap, ma_tol):
        triggers.append("VWAP")
        levels.append(f"VWAP {vwap:.2f}")
    if prof is not None:
        if _bounce(o, l, c, prof.poc, ma_tol):
            triggers.append("POC")
            levels.append(f"POC {prof.poc:.2f}")
        if _bounce(o, l, c, prof.val, ma_tol):
            triggers.append("VAL")
            levels.append(f"VAL {prof.val:.2f}")

    # RSI reclaims (daily + weekly turn up from oversold).
    if _rsi_reversal(rsi_d, zone):
        triggers.append("Daily RSI")
    if _rsi_reversal(rsi_w, zone):
        triggers.append("Weekly RSI")

    weekly_oversold = rw < zone
    # Surface it if a support fired, or it's oversold enough to watch for the turn.
    if not triggers and not weekly_oversold and rd >= 35:
        return None

    return SupportSignal(
        symbol=symbol, price=round(c, 2), rsi_d=round(rd, 1), rsi_w=round(rw, 1),
        weekly_oversold=weekly_oversold, triggers=triggers, levels=levels,
        strike=round(c * (1 - otm), 2), dte=dte,
    )
