"""20-MA Setups scanner — a READ-ONLY, on-demand report (not an alert source).

Mirrors the `ma20_direction` Pine: for each name in the master universe it computes the
20-day SMA's slope/angle (scale-free, in ATRs per bar), the stock's EXTENSION from the
MA, and the resulting SETUP with entry / stop / target / risk-reward, plus the 200 SMA
for long-term trend context. It keeps only names that are AT an entry RIGHT NOW —

  • PULLBACK  — price is at the 20 (within `near_atr` ATRs) in a real trend →
                LONG a rising MA (support) / SHORT a falling MA (resistance).
  • FADE      — price is EXTENDED from the 20 (≥ `ext_atr` ATRs) → fade back to it.

…and only when the trend is real (|angle| ≥ flat) and the R:R clears the floor. Each
row flags whether it's WITH or COUNTER the 200-day trend.

Pure over daily OHLC + a DB read for the universe — runs LOCALLY and publishes to
`market_reports` (kind=`ma20_setups`) like the other report scripts.

    DATABASE_URL=postgresql://... python3 analytics/ma20_scan_report.py
    # offline smoke (no DB): prints the report for the given symbols
    python3 analytics/ma20_scan_report.py AAPL MSFT NVDA MU PLTR
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Callable, Optional

import pandas as pd

# ── tunables — mirror the ma20_direction Pine defaults ───────────────────────────
MA_LEN     = 20
LT_LEN     = 200
SLOPE_LB   = 5       # measure the MA's rise over this many bars
ATR_LEN    = 14
SCALE_45   = 0.15    # ATRs/bar that reads as 45°
FLAT_THR   = 12.0    # |angle| below this = chop (no trend)
IDEAL_LO   = 30.0
IDEAL_HI   = 55.0
EXT_ATR    = 3.0     # |price - MA| ≥ this many ATRs = EXTENDED (fade candidate)
NEAR_ATR   = 0.5     # |price - MA| ≤ this many ATRs = at the MA (pullback candidate)
STOP_BUF   = 0.5     # stop this many ATRs beyond the MA / entry
TGT_EXT    = 3.0     # trend target = this many ATRs of extension out of the MA
RR_FLOOR   = 1.5     # keep only setups with reward:risk ≥ this
SIDE_TOL   = 0.2     # a pullback must be on the RIGHT side of the MA: a short only when
                     # price is ≤ this many ATRs ABOVE a falling MA (rejecting it as
                     # resistance), a long only when ≤ this many ATRs BELOW a rising MA
                     # (holding it as support). Price the wrong side = not that setup.


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def compute_ma20_setup(symbol: str, df: pd.DataFrame) -> Optional[dict]:
    """Compute the 20-MA setup for one symbol. Returns a row dict when the name is at an
    entry that meets the rules, else None."""
    if df is None or len(df) < LT_LEN + SLOPE_LB + 2:
        return None
    close = df["Close"].astype(float)
    ma    = close.rolling(MA_LEN).mean()
    ma200 = close.rolling(LT_LEN).mean()
    atr_s = _atr(df, ATR_LEN)

    c    = float(close.iloc[-1])
    m    = float(ma.iloc[-1])
    m_lb = float(ma.iloc[-1 - SLOPE_LB])
    atr  = float(atr_s.iloc[-1])
    m200 = float(ma200.iloc[-1])
    if any(map(lambda x: x != x, (c, m, m_lb, atr, m200))) or atr <= 0 or m <= 0:  # NaN / bad
        return None

    # angle — scale-free: MA rise in ATRs/bar → degrees
    per_bar = (m - m_lb) / SLOPE_LB
    angle   = math.degrees(math.atan(per_bar / (atr * SCALE_45)))
    abs_a   = abs(angle)
    if abs_a < FLAT_THR:                        # no real trend → not a setup
        return None
    up = angle > 0

    # slope state label
    band = "shallow" if abs_a < IDEAL_LO else ("ideal" if abs_a <= IDEAL_HI else "steep")
    state = ("RISING" if up else "FALLING") + " · " + band

    # extension
    ext_atr = (c - m) / atr
    ext_pct = (c - m) / m * 100.0
    extended = abs(ext_atr) >= EXT_ATR
    near     = abs(ext_atr) <= NEAR_ATR

    # only names at an entry NOW: at the MA (pullback) or extended (fade)
    if not (near or extended):
        return None

    stop_buf = STOP_BUF * atr
    tgt_ext  = TGT_EXT * atr
    if extended and ext_atr > 0:
        side, trig, setup = "SHORT", "fade", "fade to MA (extended above)"
        entry, stop, tgt = c, c + stop_buf, m
    elif extended:
        side, trig, setup = "LONG", "fade", "snap to MA (extended below)"
        entry, stop, tgt = c, c - stop_buf, m
    elif not up:
        # falling MA → short pullback, but ONLY if price is at/below it (rejecting the MA
        # as resistance). Price ABOVE a falling MA = a reclaim, not a short.
        if ext_atr > SIDE_TOL:
            return None
        side, trig, setup = "SHORT", "pullback", "pullback to falling MA (resistance)"
        entry, stop, tgt = m, m + stop_buf, m - tgt_ext
    else:
        # rising MA → long pullback, but ONLY if price is at/above it (holding support).
        # Price BELOW a rising MA = support broke, not a long.
        if ext_atr < -SIDE_TOL:
            return None
        side, trig, setup = "LONG", "pullback", "pullback to rising MA (support)"
        entry, stop, tgt = m, m - stop_buf, m + tgt_ext

    risk = abs(entry - stop)
    rew  = abs(tgt - entry)
    if risk <= 0:
        return None
    rr = rew / risk
    if rr < RR_FLOOR:
        return None

    with_trend = (side == "LONG" and c >= m200) or (side == "SHORT" and c < m200)
    return {
        "symbol": symbol,
        "side": side,
        "trigger": trig,                       # "pullback" | "fade"
        "setup": setup,
        "angle": round(angle, 1),
        "state": state,
        "ext_atr": round(ext_atr, 2),
        "ext_pct": round(ext_pct, 2),
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(tgt, 2),
        "rr": round(rr, 2),
        "close": round(c, 2),
        "lt_trend": "up" if c >= m200 else "down",   # vs 200 SMA
        "with_trend": bool(with_trend),
    }


def build_ma20_report(
    symbols: list[str], fetch: Callable[[str], Optional[pd.DataFrame]], session_date: str = ""
) -> dict:
    """Scan `symbols`, keep those meeting entry rules, return a report dict."""
    rows: list[dict] = []
    scanned = 0
    for s in symbols:
        try:
            df = fetch(s)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        scanned += 1
        row = compute_ma20_setup(s, df)
        if row is not None:
            rows.append(row)
    # best first: with-the-200-trend, then highest reward:reward
    rows.sort(key=lambda r: (0 if r["with_trend"] else 1, -r["rr"]))
    longs  = [r for r in rows if r["side"] == "LONG"]
    shorts = [r for r in rows if r["side"] == "SHORT"]
    return {
        "kind": "ma20_setups",
        "session_date": session_date,
        "universe": scanned,
        "rows": rows,
        "counts": {"long": len(longs), "short": len(shorts)},
        "total": len(rows),
    }


# ── universe + fetch + publish (mirror swing_setups_report) ──────────────────────


def _fetch(symbol: str) -> Optional[pd.DataFrame]:  # pragma: no cover - network
    """Daily bars via the shared multi-source helper (Alpaca → yfinance)."""
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(symbol, period="15mo", interval="1d")
    if df is None or df.empty:
        return None
    return df.dropna()


def publish(report: dict, session_date: str) -> None:  # pragma: no cover - DB
    import psycopg2
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(dsn, connect_timeout=15)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body, created_at) "
        "VALUES ('ma20_setups', %s, %s, NOW()) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (session_date, json.dumps(report)),
    )
    conn.commit()
    cur.close(); conn.close()


def main() -> None:  # pragma: no cover - manual/cron entrypoint
    import datetime as _dt
    dsn = os.getenv("DATABASE_URL")
    session_date = _dt.date.today().isoformat()
    if not dsn:
        # offline smoke: scan a few names, print the report, don't publish
        syms = [s.upper() for s in sys.argv[1:]] or ["AAPL", "MSFT", "NVDA", "MU", "PLTR"]
        rep = build_ma20_report(syms, _fetch, session_date)
        print(json.dumps(rep, indent=2))
        return
    from analytics.swing_setups_report import _watchlist
    syms = _watchlist(dsn)
    rep = build_ma20_report(syms, _fetch, session_date)
    publish(rep, session_date)
    print(json.dumps({"published": "ma20_setups", "date": session_date,
                      "universe": rep["universe"], "counts": rep["counts"], "total": rep["total"]}))


if __name__ == "__main__":
    main()
