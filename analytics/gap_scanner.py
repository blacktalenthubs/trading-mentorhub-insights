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
LOOKBACK_321  = 10     # days back to find the gap that a 3-2-1 is building off (keep fresh)
NEAR_CEIL_PCT = 6.0    # 3-2-1 "coiling" — within this % below the ceiling
CONTRACT_RATIO = 0.6   # recent third of the post-gap range <= this x the whole range


def _daily(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="14mo", interval="1d")   # enough for the 200 SMA context
    return None if df is None or df.empty else df.dropna()


def _intraday(sym):  # pragma: no cover - network
    from analytics.intraday_data import fetch_intraday
    try:
        df = fetch_intraday(sym, period="1d", interval="5m")
    except Exception:
        return None
    return None if df is None or df.empty else df


def _key_ma_note(df: pd.DataFrame, up: bool) -> str:
    """Where price sits vs the core 20/50/150/200 MAs → a trade bias note."""
    cser = df["Close"].astype(float)
    n = len(df)
    last = float(cser.iloc[-1])
    present = [(p, float(cser.rolling(p).mean().iloc[-1])) for p in (20, 50, 150, 200) if n >= p]
    present = [(p, v) for p, v in present if v and v > 0]
    if not present:
        return ""
    at = next((p for p, v in present if abs(last - v) / last * 100.0 <= 2.0), None)
    if up:
        na_ = sum(1 for _p, v in present if last > v)
        return (f"above all {len(present)} key MAs — long favored" if na_ == len(present)
                else f"at the {at} MA" if at else f"above {na_}/{len(present)} MAs")
    nb = sum(1 for _p, v in present if last < v)
    return (f"below all {len(present)} key MAs — short favored" if nb == len(present)
            else f"at the {at} MA (support) — may hold" if at else f"below {nb}/{len(present)} MAs")


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
            "open": round(o, 2), "prev_close": round(pc, 2), "bias": _key_ma_note(df, gap > 0),
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
    """Setup 2 — a tightening contraction after a gap. The TRADE FOLLOWS THE GAP:
      • gap UP   → continuation up   → LONG  a break of the post-gap HIGH (ceiling),
                   stop = the contraction low.
      • gap DOWN → continuation down → SHORT a break of the post-gap LOW (floor),
                   stop = the gap-day HIGH (the gap's opening high).
    """
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
    ceiling = float(post_h.max())            # post-gap high
    floor = float(post_l.min())              # post-gap low
    gap_day_high = float(h[gap_idx])         # the gap's opening-day high
    last = float(c[-1])
    _cser = df["Close"].astype(float)
    # core key MAs: 20 / 50 / 150 / 200
    key_mas = {p: (float(_cser.rolling(p).mean().iloc[-1]) if n >= p else None) for p in (20, 50, 150, 200)}
    third = max(1, len(post_h) // 3)
    rng_all = ceiling - floor
    rng_recent = post_h[-third:].max() - post_l[-third:].min()
    contracting = rng_all > 0 and rng_recent <= rng_all * CONTRACT_RATIO

    up = g_pct > 0
    if up:
        # continuation UP — long the break of the ceiling; coiling UNDER it
        if last >= ceiling or ceiling <= 0:
            return None
        direction, trigger, stop = "LONG", ceiling, float(post_l[-third:].min())
        near = (ceiling - last) / ceiling * 100.0 <= NEAR_CEIL_PCT
        to_trig = (last / ceiling - 1) * 100.0        # negative = below the trigger
    else:
        # continuation DOWN — short the break of the floor; coiling ABOVE it,
        # stop at the gap-day high
        if last <= floor or floor <= 0:
            return None
        direction, trigger, stop = "SHORT", floor, gap_day_high
        near = (last - floor) / floor * 100.0 <= NEAR_CEIL_PCT
        to_trig = (last / floor - 1) * 100.0          # positive = above the trigger
    if not (contracting and near):
        return None
    # MA context (20/50/150/200) — a gap that LOST the key MAs is a clean continuation;
    # a gap sitting AT a key MA (support/resistance) may hold, so flag it as caution.
    present = [(p, v) for p, v in key_mas.items() if v is not None and v > 0]
    _at = next((p for p, v in present if abs(last - v) / last * 100.0 <= 2.0), None)
    if direction == "SHORT":
        n_below = sum(1 for _p, v in present if last < v)
        context = (f"below all {len(present)} key MAs — lost support (clean short)" if present and n_below == len(present)
                   else f"at the {_at} MA (support) — may hold, caution" if _at
                   else f"below {n_below}/{len(present)} key MAs")
    else:
        n_above = sum(1 for _p, v in present if last > v)
        context = (f"above all {len(present)} key MAs (clean long)" if present and n_above == len(present)
                   else f"at the {_at} MA — needs to reclaim/hold" if _at
                   else f"above {n_above}/{len(present)} key MAs")
    risk = abs(trigger - stop) / trigger * 100.0 if trigger else None
    return {"gap_dir": "UP" if up else "DOWN", "gap_pct": round(g_pct, 1),
            "direction": direction, "days_ago": n - 1 - gap_idx, "context": context,
            "trigger": round(trigger, 2), "stop": round(stop, 2), "last": round(last, 2),
            "to_trigger_pct": round(to_trig, 1), "risk_pct": round(risk, 1) if risk is not None else None}


def _short_universe() -> set[str]:
    """The only symbols we take SHORT gaps on — the index/proxy set. Everything
    else is long-only, so gap-DOWN shorts elsewhere are dropped as noise (we
    already have dedicated short entries for the index set via the reject rules)."""
    try:
        from alert_config import SHORT_UNIVERSE as _su
        return {str(x).upper() for x in _su}
    except Exception:
        return {"SPY", "QQQ", "SMH", "DRAM"}


def scan(symbols, want_intraday: bool = True, short_syms: set[str] | None = None) -> dict:
    if short_syms is None:
        short_syms = _short_universe()
    gaps, setups = [], []
    for s in symbols:
        try:
            df = _daily(s)
            if df is None:
                continue
            g = detect_gap(df)
            # Long-only except the index set: drop gap-DOWN (short) gaps elsewhere.
            if g and g["dir"] == "DOWN" and s.upper() not in short_syms:
                g = None
            if g:
                if want_intraday:
                    orr = opening_range(_intraday(s))
                    if orr:
                        g["or"] = orr
                gaps.append({"sym": s, **g})
            t = three_two_one(df)
            # Same: keep 3-2-1 SHORT continuations only for the index set.
            if t and t["direction"] == "SHORT" and s.upper() not in short_syms:
                t = None
            if t:
                setups.append({"sym": s, **t})
        except Exception:
            pass
    gaps.sort(key=lambda r: abs(r["gap_pct"]), reverse=True)
    setups.sort(key=lambda r: abs(r["to_trigger_pct"]))            # closest to the trigger first
    return {"gaps": gaps, "setups": setups, "scanned": len(symbols)}


def _print(rep: dict) -> None:
    print(f"\n=== GAP SCANNER === {len(rep['gaps'])} big gaps · {len(rep['setups'])} 3-2-1 setups\n")
    print("BIG GAPS (>=4%) — day-of, opening-range break:")
    for r in rep["gaps"]:
        _or = r.get("or")
        ortxt = f"  OR {_or['or_low']}-{_or['or_high']} → {_or['state']}" if _or else "  (OR pending — intraday)"
        _b = f"  · {r['bias']}" if r.get("bias") else ""
        print(f"  {r['sym']:<7} GAP {r['dir']} {r['gap_pct']:+.1f}%  open {r['open']}  (prev {r['prev_close']}){ortxt}{_b}")
    print("\n3-2-1 SETUPS — continuation of the gap (gap up → long ceiling break; gap down → short floor break):")
    for r in rep["setups"]:
        _brk = "break >" if r["direction"] == "LONG" else "break <"
        print(f"  {r['sym']:<7} {r['direction']:<5} (gap {r['gap_dir']} {r['gap_pct']:+.1f}% {r['days_ago']}d)  "
              f"{_brk} {r['trigger']}  {r['to_trigger_pct']:+.1f}%  stop {r['stop']} (risk {r['risk_pct']}%)  · {r['context']}")


def _telegram(rep: dict, date: str) -> str:
    out = [f"<b>GAP SCAN · {date}</b>  ({len(rep['gaps'])} gaps · {len(rep['setups'])} 3-2-1)"]
    if rep["gaps"]:
        out.append("\n<b>Big gaps (OR break):</b>")
        for r in rep["gaps"]:
            _or = r.get("or")
            s = f" · {_or['state']}" if _or else ""
            out.append(f"  {r['sym']} — {r['dir']} {r['gap_pct']:+.1f}%{s}")
    if rep["setups"]:
        out.append("\n<b>3-2-1 (gap continuation):</b>")
        for r in rep["setups"]:
            _brk = "break >" if r["direction"] == "LONG" else "break <"
            out.append(f"  {r['sym']} {r['direction']} — {_brk} {r['trigger']}, {r['to_trigger_pct']:+.1f}% (stop {r['stop']})")
    return "\n".join(out)


def publish(rep: dict, session_date: str) -> None:  # pragma: no cover - DB
    """Store to market_reports (kind=gap_setups) → rendered on the Today tab."""
    import json
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body, created_at) "
        "VALUES ('gap_setups', %s, %s, NOW()) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (session_date, json.dumps(rep)),
    )
    conn.commit()
    cur.close()
    conn.close()


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Gap scanner (>=4% gaps + 3-2-1 setups)")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--universe", action="store_true", help="scan the master watchlist (needs DATABASE_URL)")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--publish", action="store_true", help="store to market_reports for the Today tab (needs DATABASE_URL)")
    ap.add_argument("--no-intraday", action="store_true", help="skip the opening-range fetch (gaps only)")
    args = ap.parse_args()

    if args.universe:
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(os.environ["DATABASE_URL"])
    else:
        symbols = [s.upper() for s in args.symbols] or ["AAPL", "NVDA", "SMCI", "MU", "TSLA", "COIN"]

    import datetime as _dt
    _date = _dt.date.today().isoformat()
    rep = scan(symbols, want_intraday=not args.no_intraday)
    _print(rep)
    if args.publish:
        publish(rep, _date)
        print("published: gap_setups", _date, file=sys.stderr)
    if args.telegram:
        from analytics.minervini_scan import _send_to_telegram
        _send_to_telegram(_telegram(rep, _date))


if __name__ == "__main__":
    main()
