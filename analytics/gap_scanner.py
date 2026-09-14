"""Gap scanner — big (>=4%) opening gaps + two setups. Watchlist only.

Setup 1 (day-of): on a gap day, after the ~10-min opening range, LONG a break of the OR
high / SHORT a break of the OR low (stop = the other side of the range).

Setup 2 (3-2-1): after a gap, price levels off and its swings TIGHTEN (a ~3→2→1
contraction) under the post-gap high (the ceiling). A break of that ceiling is the long
entry (stop = the contraction low). Forms same day or days later.

    python3 analytics/gap_scanner.py AAPL NVDA SMCI
    DATABASE_URL=... python3 analytics/gap_scanner.py --universe --telegram
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GAP_MIN_PCT   = 4.0    # |open - prevClose| / prevClose
OR_MINUTES    = 10     # opening-range window (Setup 1)
LOOKBACK_321  = 15     # days back to find the gap that a 3-2-1 is building off
NEAR_CEIL_PCT = 6.0    # 3-2-1 "coiling" — within this % below the ceiling
CONTRACT_RATIO = 0.6   # recent third of the post-gap range <= this x the whole range


def _daily(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="4mo", interval="1d")
    return None if df is None or df.empty else df.dropna()


def _intraday(sym):  # pragma: no cover - network
    from analytics.intraday_data import fetch_intraday
    try:
        df = fetch_intraday(sym, period="1d", interval="5m")
    except Exception:
        return None
    return None if df is None or df.empty else df


def detect_gap(df: pd.DataFrame) -> dict | None:
    """Latest session's gap vs the prior close."""
    if df is None or len(df) < 2:
        return None
    o = float(df["Open"].iloc[-1])
    pc = float(df["Close"].iloc[-2])
    if pc <= 0:
        return None
    gap = (o - pc) / pc * 100.0
    if abs(gap) < GAP_MIN_PCT:
        return None
    return {"dir": "UP" if gap > 0 else "DOWN", "gap_pct": round(gap, 1),
            "open": round(o, 2), "prev_close": round(pc, 2),
            "day_high": round(float(df["High"].iloc[-1]), 2),
            "day_low": round(float(df["Low"].iloc[-1]), 2)}


def opening_range(intr: pd.DataFrame) -> dict | None:
    """Setup 1 — the first OR_MINUTES of the latest session + break state."""
    if intr is None or len(intr) < 2:
        return None
    nbars = max(1, OR_MINUTES // 5)
    orh = float(intr["High"].iloc[:nbars].max())
    orl = float(intr["Low"].iloc[:nbars].min())
    c = float(intr["Close"].iloc[-1])
    state = "LONG (broke OR high)" if c > orh else "SHORT (broke OR low)" if c < orl else "inside OR — pending"
    return {"or_high": round(orh, 2), "or_low": round(orl, 2), "last": round(c, 2), "state": state}


def three_two_one(df: pd.DataFrame) -> dict | None:
    """Setup 2 — a tightening contraction under the post-gap high; ceiling break = entry."""
    if df is None or len(df) < 6:
        return None
    o = df["Open"].astype(float).values
    c = df["Close"].astype(float).values
    h = df["High"].astype(float).values
    l = df["Low"].astype(float).values
    n = len(df)
    gap_idx = None
    for i in range(n - 1, max(0, n - LOOKBACK_321) - 1, -1):
        if i == 0:
            break
        g = (o[i] - c[i - 1]) / c[i - 1] * 100.0 if c[i - 1] else 0.0
        if abs(g) >= GAP_MIN_PCT:
            gap_idx = i
            g_pct = g
            break
    if gap_idx is None or n - gap_idx < 3:   # need a few bars to build the 3-2-1
        return None
    post_h = h[gap_idx:]
    post_l = l[gap_idx:]
    ceiling = float(post_h.max())
    floor = float(post_l.min())
    last = float(c[-1])
    if last >= ceiling or ceiling <= 0:       # already broken out (or bad data)
        return None
    # contraction: the recent third of the post-gap range vs the whole
    third = max(1, len(post_h) // 3)
    rng_all = post_h.max() - post_l.min()
    rng_recent = post_h[-third:].max() - post_l[-third:].min()
    contracting = rng_all > 0 and rng_recent <= rng_all * CONTRACT_RATIO
    near = (ceiling - last) / ceiling * 100.0 <= NEAR_CEIL_PCT
    if not (contracting and near):
        return None
    stop = round(float(post_l[-third:].min()), 2)     # the tight contraction low
    return {"gap_dir": "UP" if g_pct > 0 else "DOWN", "gap_pct": round(g_pct, 1),
            "days_ago": n - 1 - gap_idx, "ceiling": round(ceiling, 2), "stop": stop,
            "last": round(last, 2), "to_ceiling_pct": round((last / ceiling - 1) * 100, 1),
            "risk_pct": round((ceiling - stop) / ceiling * 100, 1) if ceiling else None}


def scan(symbols, want_intraday: bool = True) -> dict:
    gaps, setups = [], []
    for s in symbols:
        try:
            df = _daily(s)
            if df is None:
                continue
            g = detect_gap(df)
            if g:
                if want_intraday:
                    orr = opening_range(_intraday(s))
                    if orr:
                        g["or"] = orr
                gaps.append({"sym": s, **g})
            t = three_two_one(df)
            if t:
                setups.append({"sym": s, **t})
        except Exception:
            pass
    gaps.sort(key=lambda r: abs(r["gap_pct"]), reverse=True)
    setups.sort(key=lambda r: r["to_ceiling_pct"], reverse=True)   # closest to the ceiling first
    return {"gaps": gaps, "setups": setups, "scanned": len(symbols)}


def _print(rep: dict) -> None:
    print(f"\n=== GAP SCANNER === {len(rep['gaps'])} big gaps · {len(rep['setups'])} 3-2-1 setups\n")
    print("BIG GAPS (>=4%) — day-of, opening-range break:")
    for r in rep["gaps"]:
        _or = r.get("or")
        ortxt = f"  OR {_or['or_low']}-{_or['or_high']} → {_or['state']}" if _or else "  (OR pending — intraday)"
        print(f"  {r['sym']:<7} GAP {r['dir']} {r['gap_pct']:+.1f}%  open {r['open']}  (prev {r['prev_close']}){ortxt}")
    print("\n3-2-1 SETUPS — contraction under the post-gap ceiling (break = long):")
    for r in rep["setups"]:
        print(f"  {r['sym']:<7} gap {r['gap_dir']} {r['gap_pct']:+.1f}% {r['days_ago']}d ago  "
              f"ceiling {r['ceiling']}  {r['to_ceiling_pct']:+.1f}%  stop {r['stop']} (risk {r['risk_pct']}%)")


def _telegram(rep: dict, date: str) -> str:
    out = [f"<b>GAP SCAN · {date}</b>  ({len(rep['gaps'])} gaps · {len(rep['setups'])} 3-2-1)"]
    if rep["gaps"]:
        out.append("\n<b>Big gaps (OR break):</b>")
        for r in rep["gaps"]:
            _or = r.get("or")
            s = f" · {_or['state']}" if _or else ""
            out.append(f"  {r['sym']} — {r['dir']} {r['gap_pct']:+.1f}%{s}")
    if rep["setups"]:
        out.append("\n<b>3-2-1 (ceiling break = long):</b>")
        for r in rep["setups"]:
            out.append(f"  {r['sym']} — ceiling {r['ceiling']}, {r['to_ceiling_pct']:+.1f}% (stop {r['stop']})")
    return "\n".join(out)


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Gap scanner (>=4% gaps + 3-2-1 setups)")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--universe", action="store_true", help="scan the master watchlist (needs DATABASE_URL)")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--no-intraday", action="store_true", help="skip the opening-range fetch (gaps only)")
    args = ap.parse_args()

    if args.universe:
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(os.environ["DATABASE_URL"])
    else:
        symbols = [s.upper() for s in args.symbols] or ["AAPL", "NVDA", "SMCI", "MU", "TSLA", "COIN"]

    rep = scan(symbols, want_intraday=not args.no_intraday)
    _print(rep)
    if args.telegram:
        import datetime as _dt
        from analytics.minervini_scan import _send_to_telegram
        _send_to_telegram(_telegram(rep, _dt.date.today().isoformat()))


if __name__ == "__main__":
    main()
