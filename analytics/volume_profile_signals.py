"""Volume-profile signal engine — POC / value area / VWAP interactions.

Pure, dependency-light functions (pandas only) so they're unit-testable and can be
validated against live data BEFORE wiring into the protected scanner. Mirrors the
`volume_profile.pine` math (150 bars, 35 rows, 70% value area) so the scan and the
chart agree.

Signals (all read the last COMPLETED daily bar):
  poc_reclaim   long   opened & holds above the POC after testing it   (defend value)
  val_bounce    long   tagged the value-area low and bounced           (base buy)
  vah_breakout  long   broke and holds above the value-area high       (leaving value up)
  vwap_reclaim  long   opened & holds above the rolling VWAP           (trend support)
  vwap_loss     short  gapped/closed below the VWAP                    (control flip)

Each carries a `confluence` list naming any 20/50/200 SMA sitting on the same level —
that's the high-conviction stack (NBIS = POC+20SMA, LRCX = 200SMA+VWAP).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Defaults mirror the pine indicator.
BARS_BACK = 150
COLUMNS = 35
VALUE_AREA_PCT = 70.0
HVN_PCT = 55.0
LVN_PCT = 25.0

# How close price must be to a level to count as "at" it (fraction of price).
LEVEL_PROXIMITY = 0.010     # 1.0%
# How close a level must be to an MA to count as confluence.
CONFLUENCE_TOL = 0.010      # 1.0%


@dataclass
class Profile:
    poc: float
    vah: float
    val: float
    hvns: list[float] = field(default_factory=list)
    lvns: list[float] = field(default_factory=list)
    total: float = 0.0
    max_vol: float = 0.0


@dataclass
class Signal:
    symbol: str
    kind: str            # poc_reclaim | val_bounce | vah_breakout | vwap_reclaim | vwap_loss
    direction: str       # long | short
    level: float
    level_name: str
    price: float
    confluence: list[str] = field(default_factory=list)


def compute_profile(df: pd.DataFrame, bars_back: int = BARS_BACK, columns: int = COLUMNS,
                    va_pct: float = VALUE_AREA_PCT, hvn_pct: float = HVN_PCT,
                    lvn_pct: float = LVN_PCT) -> Profile | None:
    """Volume-by-price over the last `bars_back` bars → POC / VAH / VAL / HVN / LVN."""
    w = df.tail(bars_back)
    if len(w) < 2:
        return None
    lo = float(w["Low"].min())
    hi = float(w["High"].max())
    rng = hi - lo
    if rng <= 0:
        return None
    bs = rng / columns
    vol = [0.0] * columns
    for low, high, v in zip(w["Low"], w["High"], w["Volume"]):
        lo_i = int((low - lo) // bs)
        hi_i = int((high - lo) // bs)
        lo_i = max(0, min(columns - 1, lo_i))
        hi_i = max(0, min(columns - 1, hi_i))
        span = hi_i - lo_i + 1
        per = float(v) / span
        for k in range(lo_i, hi_i + 1):
            vol[k] += per

    total = sum(vol)
    max_vol = max(vol)
    if max_vol <= 0:
        return None
    poc_i = vol.index(max_vol)

    # Value area: grow out from the POC by the heavier neighbour to va_pct% of volume.
    va = vol[poc_i]
    up = dn = poc_i
    target = total * va_pct / 100.0
    while va < target:
        up_v = vol[up + 1] if up < columns - 1 else -1.0
        dn_v = vol[dn - 1] if dn > 0 else -1.0
        if up_v < 0 and dn_v < 0:
            break
        if up_v >= dn_v:
            up += 1
            va += up_v
        else:
            dn -= 1
            va += dn_v

    poc = lo + (poc_i + 0.5) * bs
    vah = lo + (up + 1) * bs
    val = lo + dn * bs

    hvns: list[float] = []
    lvns: list[float] = []
    h_min = max_vol * hvn_pct / 100.0
    l_max = max_vol * lvn_pct / 100.0
    for k in range(1, columns - 1):
        price = lo + (k + 0.5) * bs
        if vol[k] >= vol[k - 1] and vol[k] >= vol[k + 1] and vol[k] >= h_min:
            hvns.append(price)
        elif vol[k] <= vol[k - 1] and vol[k] <= vol[k + 1] and vol[k] <= l_max and vol[k] > 0:
            lvns.append(price)

    return Profile(poc=poc, vah=vah, val=val, hvns=hvns, lvns=lvns, total=total, max_vol=max_vol)


def rolling_vwap(df: pd.DataFrame, bars_back: int = BARS_BACK) -> float | None:
    """Volume-weighted average price over the window (the profile's 'anchored VWAP')."""
    w = df.tail(bars_back)
    sv = float(w["Volume"].sum())
    if sv <= 0:
        return None
    hlc = (w["High"] + w["Low"] + w["Close"]) / 3.0
    return float((hlc * w["Volume"]).sum() / sv)


def _mas(df: pd.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    close = df["Close"]
    for name, n in (("20 SMA", 20), ("50 SMA", 50), ("200 SMA", 200)):
        if len(close) >= n:
            out[name] = float(close.rolling(n).mean().iloc[-1])
    return out


def _confluence(level: float, mas: dict[str, float], tol: float = CONFLUENCE_TOL) -> list[str]:
    """MA names sitting within `tol` of the level — the stacked-level tag."""
    hits = []
    for name, v in mas.items():
        if v and abs(level - v) / level <= tol:
            hits.append(name)
    return hits


def detect_signals(df: pd.DataFrame, symbol: str, *, short_ok: bool = False,
                   prox: float = LEVEL_PROXIMITY) -> list[Signal]:
    """Detect the current volume-profile setups on the last completed bar.

    `short_ok` gates the bearish vwap_loss to the short universe. State-based (finds
    names currently AT/reclaiming a level) — the scanner build will edge-trigger it.
    """
    prof = compute_profile(df)
    vwap = rolling_vwap(df)
    if prof is None or vwap is None or len(df) < 2:
        return []
    mas = _mas(df)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    o, h, l, c = float(last["Open"]), float(last["High"]), float(last["Low"]), float(last["Close"])
    pc = float(prev["Close"])
    out: list[Signal] = []

    def near(price: float, level: float) -> bool:
        return abs(price - level) / level <= prox

    # POC reclaim (long): tested the POC, opened above it, holds above (defend value).
    if l <= prof.poc * (1 + prox) and o >= prof.poc and c >= prof.poc:
        out.append(Signal(symbol, "poc_reclaim", "long", prof.poc, "POC", c,
                          _confluence(prof.poc, mas)))

    # VAL bounce (long): tagged the value-area low and closed back up through it.
    if l <= prof.val * (1 + prox) and c > prof.val and c > o:
        out.append(Signal(symbol, "val_bounce", "long", prof.val, "VAL", c,
                          _confluence(prof.val, mas)))

    # VAH breakout (long): broke above the value-area high and holds (leaving value up).
    if c > prof.vah and (pc <= prof.vah or near(c, prof.vah)):
        out.append(Signal(symbol, "vah_breakout", "long", prof.vah, "VAH", c,
                          _confluence(prof.vah, mas)))

    # VWAP reclaim (long): opened above the VWAP and holds, after testing it.
    if l <= vwap * (1 + prox) and o >= vwap and c >= vwap:
        out.append(Signal(symbol, "vwap_reclaim", "long", vwap, "VWAP", c,
                          _confluence(vwap, mas)))

    # VWAP loss (short): gapped or closed below the VWAP after being above (control flip).
    if short_ok and c < vwap and (pc >= vwap or o < vwap):
        out.append(Signal(symbol, "vwap_loss", "short", vwap, "VWAP", c,
                          _confluence(vwap, mas)))

    return out
