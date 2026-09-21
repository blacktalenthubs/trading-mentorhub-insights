"""Put-seller signal engine — sell puts ONLY at oversold reversal / support points.

Mirrors pine_scripts/sept_pine/green_red_put_seller.pine exactly. Four triggers, any
one fires a ~30-DTE cash-secured put:
  Daily RSI reversal   RSI(14) dipped under the oversold zone (40) and turned back up
  Weekly RSI reversal  the WEEKLY RSI turned up from under the zone
  50 SMA bounce        the bar wicked to the 50-day SMA, closed back above it (green)
  200 SMA bounce       same at the 200-day SMA

No EMA cloud, no fixed % drop — those don't time a reversal. Also reports the weekly
RSI so the app can list every name currently UNDER 40 weekly RSI (the "armed" watchlist)
even before a trigger fires. Timing only — verify IV in-broker; this is not option data.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

OVERSOLD_ZONE = 40.0
MA_TOL = 0.01      # how close the low must get to an SMA to count as tagging it (1%)
OTM = 0.05         # put strike this far out-of-the-money
DTE = 30


@dataclass
class PutSellSignal:
    symbol: str
    price: float
    rsi_d: float
    rsi_w: float
    weekly_oversold: bool           # weekly RSI < the zone (the finder's core list)
    triggers: list[str] = field(default_factory=list)   # which of the 4 fired NOW
    strike: float = 0.0             # suggested put strike (price - OTM%)
    dte: int = DTE

    @property
    def fired(self) -> bool:
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


def detect_putsell(daily: pd.DataFrame, weekly: pd.DataFrame, symbol: str, *,
                   zone: float = OVERSOLD_ZONE, ma_tol: float = MA_TOL,
                   otm: float = OTM, dte: int = DTE) -> PutSellSignal | None:
    """Return a signal if `symbol` is at a put-sell trigger OR is oversold on the weekly.

    `daily` / `weekly` are OHLC frames (capitalised columns, oldest→newest) from
    analytics.market_data.fetch_ohlc. Returns None when the name is neither firing a
    trigger nor under the weekly zone — nothing to surface.
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

    sma50 = float(dc.rolling(50).mean().iloc[-1]) if len(dc) >= 50 else None
    sma200 = float(dc.rolling(200).mean().iloc[-1]) if len(dc) >= 200 else None

    triggers: list[str] = []
    if _rsi_reversal(rsi_d, zone):
        triggers.append("Daily RSI reversal")
    if _rsi_reversal(rsi_w, zone):
        triggers.append("Weekly RSI reversal")
    # A bounce OPENS above the SMA (support from above), wicks down to tag it, and closes
    # green — not a bar that straddles a flat SMA in chop (that's noise, not support).
    if sma50 and o > sma50 and l <= sma50 * (1 + ma_tol) and c > o:
        triggers.append("50 SMA bounce")
    if sma200 and o > sma200 and l <= sma200 * (1 + ma_tol) and c > o:
        triggers.append("200 SMA bounce")

    weekly_oversold = rw < zone
    if not triggers and not weekly_oversold:
        return None

    return PutSellSignal(
        symbol=symbol, price=round(c, 2), rsi_d=round(rd, 1), rsi_w=round(rw, 1),
        weekly_oversold=weekly_oversold, triggers=triggers,
        strike=round(c * (1 - otm), 2), dte=dte,
    )
