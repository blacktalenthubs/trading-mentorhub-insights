"""20-MA ACTION scan — find names HOLDING a rising daily 20 SMA (the ma20_direction
pine's "LONG ✓"). Mirrors the pine: rising in/above the ideal band + price in the hold
zone (a genuine pullback/hold, not extended). Prints, and optionally posts to Telegram.

    python3 analytics/ma20_action_scan.py AAPL NVDA MRNA COIN
    DATABASE_URL=... python3 analytics/ma20_action_scan.py --universe --telegram
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pine constants (ma20_direction defaults)
SLOPE_LB, ATR_LEN, SCALE45 = 5, 14, 0.15
IDEAL_LO, EXT_THR, SIDE_TOL, NEAR_MA = 30.0, 3.0, 0.2, 1.5


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def read(sym: str, fetch) -> dict | None:
    df = fetch(sym)
    if df is None or len(df) < 40:
        return None
    df = df.dropna()
    close = df["Close"].astype(float)
    ma = close.rolling(20).mean()
    if pd.isna(ma.iloc[-1]) or pd.isna(ma.iloc[-1 - SLOPE_LB]):
        return None
    atr = _atr(df, ATR_LEN)
    if not atr or atr <= 0:
        return None
    c, m, mlb = float(close.iloc[-1]), float(ma.iloc[-1]), float(ma.iloc[-1 - SLOPE_LB])
    angle = math.degrees(math.atan(((m - mlb) / SLOPE_LB) / (atr * SCALE45)))
    ext = (c - m) / atr  # ATRs above/below the 20
    rising = angle >= IDEAL_LO
    holding = rising and -SIDE_TOL <= ext <= NEAR_MA      # LONG ✓
    reclaim = rising and ext < -SIDE_TOL                  # rising but below → watch reclaim
    return {"sym": sym, "close": round(c, 2), "angle": round(angle, 1), "ma20": round(m, 2),
            "ext": round(ext, 2), "pct": round((c / m - 1) * 100, 1),
            "holding": holding, "reclaim": reclaim}


def _fetch(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="12mo", interval="1d")
    return None if df is None or df.empty else df.dropna()


def scan(symbols, fetch) -> dict:
    rows = []
    for s in symbols:
        try:
            r = read(s, fetch)
            if r:
                rows.append(r)
        except Exception:
            pass
    longs = sorted([r for r in rows if r["holding"]], key=lambda r: r["angle"], reverse=True)
    watch = sorted([r for r in rows if r["reclaim"]], key=lambda r: r["angle"], reverse=True)
    return {"scanned": len(rows), "longs": longs, "watch": watch}


def _line(r):
    steep = "steep" if r["angle"] > 55 else "ideal"
    return f"  {r['sym']:<7} {r['close']:>9.2f}  {r['angle']:>5.1f}° {steep}  20@{r['ma20']:.2f}  {r['pct']:+.1f}% ({r['ext']:+.1f} ATR)"


def _telegram(rep, date):
    out = [f"<b>20-MA LONG · {date}</b>  ({len(rep['longs'])} holding a rising 20)"]
    for r in rep["longs"]:
        out.append(f"  {r['sym']} — {r['angle']:.0f}°, {r['pct']:+.1f}% vs 20 (20@{r['ma20']:.2f})")
    if rep["watch"]:
        out.append("\n<b>Reclaim watch (rising 20, price below):</b>")
        out += [f"  {r['sym']} — {r['angle']:.0f}°, {r['pct']:+.1f}% vs 20" for r in rep["watch"]]
    return "\n".join(out)


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="20-MA ACTION scan (holding a rising 20)")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--universe", action="store_true", help="scan the master watchlist (needs DATABASE_URL)")
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()

    if args.universe:
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(os.environ["DATABASE_URL"])
    else:
        symbols = [s.upper() for s in args.symbols] or ["AAPL", "NVDA", "MRNA", "COIN", "MU", "TSLA"]

    rep = scan(symbols, _fetch)
    print(f"\n=== 20-MA ACTION === scanned {rep['scanned']} · {len(rep['longs'])} holding a rising 20\n")
    print("LONG ✓ — price holding a RISING 20 (ideal/steep), not extended:")
    for r in rep["longs"]:
        print(_line(r))
    if rep["watch"]:
        print("\nReclaim watch — 20 rising but price below it:")
        for r in rep["watch"]:
            print(_line(r))

    if args.telegram:
        import datetime as _dt
        from analytics.minervini_scan import _send_to_telegram
        _send_to_telegram(_telegram(rep, _dt.date.today().isoformat()))


if __name__ == "__main__":
    main()
