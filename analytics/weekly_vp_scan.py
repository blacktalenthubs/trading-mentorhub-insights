"""RESEARCH — stocks trading at their WEEKLY POC / VWAP / VAL (by today's close).

Exploratory tool for "how does volume profile behave on the weekly chart?". For each
symbol it builds a weekly volume profile over a rolling window of weekly bars and reports
where TODAY'S close sits relative to the weekly POC, the anchored VWAP, and the VAL — and
flags the names whose close is sitting AT one of those (within a tolerance you set). VAH is
excluded by design (value-area low is the support we care about, not the high).

Method
------
- Weekly bars from ROBINHOOD (`get_stock_historicals`, interval=week). Its volume matches
  TradingView's weekly VP (validated: AVGO POC 169≈chart 165) and its prices are clean —
  unlike yfinance, whose weekly volume put AVGO's POC at 355. The last bar's Close is today's.
- `compute_profile()` + `rolling_vwap()` (shared with the daily engine + volume_profile.pine):
  volume-by-price + volume-weighted average over the window. Feed weekly bars → weekly VP.
    · POC  most-traded price in the window
    · VWAP window's anchored volume-weighted average (HLC3-weighted)
    · VAL  value-area low (bottom of the 70% value area)
- "At a level" = |close − level| / close ≤ tol (default 1%).

⚠️  WINDOW CAVEAT: your chart's VP is VISIBLE-RANGE, so the right lookback varies by name —
    AVGO matched at ~156w, NVDA at ~104w (156w reaches its pre-run base and distorts). The
    window is a cap; newer names use all their history. `peak_ratio` near ~0.9+ flags two
    near-tied nodes (bimodal) where the POC can still jump — verify those on the chart.
    Requires a Robinhood session (SESSION_B64 in prod; a local ~/.tokens pickle for research).

CLI:
    python3 -m analytics.weekly_vp_scan AAPL MSFT NVDA GOOGL
    python3 -m analytics.weekly_vp_scan --watchlist --weeks 52 --tol 0.012 --at-only
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.volume_profile_signals import compute_profile, rolling_vwap  # noqa: E402

DEFAULT_WEEKS = 156    # window cap (≈3yr); newer names use all available bars
DEFAULT_TOL = 0.010    # "at a level" = within this fraction of price
AMBIG = 0.90           # peak_ratio at/above this = near-tied nodes → POC may flip by source

# Data source is ROBINHOOD (not yfinance): its volume distribution matches TradingView's
# weekly VP (AVGO POC 169≈chart 165, vs yfinance's wrong 355) and its prices are clean.
_RH_READY = False


def _ensure_rh():  # pragma: no cover - network
    """Log into Robinhood once. Prod restores SESSION_B64 via RobinhoodClient; local rides
    the ~/.tokens pickle. Either way robin_stocks' session is set for get_stock_historicals."""
    global _RH_READY
    import robin_stocks.robinhood as rh
    if not _RH_READY:
        try:
            from brokers.robinhood import RobinhoodClient
            RobinhoodClient().login()
        except Exception:
            try:
                rh.login()
            except Exception:
                pass
        _RH_READY = True
    return rh


def _weekly(sym: str):  # pragma: no cover - network
    import pandas as pd
    rh = _ensure_rh()
    try:
        h = rh.stocks.get_stock_historicals(sym, interval="week", span="5year", bounds="regular") or []
    except Exception:
        return None
    rows = []
    for b in h:
        try:
            rows.append({"Open": float(b["open_price"]), "High": float(b["high_price"]),
                         "Low": float(b["low_price"]), "Close": float(b["close_price"]),
                         "Volume": float(b["volume"])})
        except Exception:
            pass
    df = pd.DataFrame(rows)
    return None if df.empty else df


def _current(sym: str) -> dict | None:  # pragma: no cover - network
    """THIS week's open + the live price. Robinhood's WEEKLY feed omits the current,
    in-progress week (its last weekly bar is last Friday's completed week), so the current
    week's open comes from the first DAILY bar of the week that contains today, and the
    current price from the live quote (not the stale last weekly close)."""
    import datetime as _dt
    rh = _ensure_rh()
    try:
        d = rh.stocks.get_stock_historicals(sym, interval="day", span="month", bounds="regular") or []
    except Exception:
        return None
    if not d:
        return None
    today = _dt.date.today()
    monday = (today - _dt.timedelta(days=today.weekday())).isoformat()   # Monday of this week
    week = [b for b in d if (b.get("begins_at", "")[:10] >= monday)]
    try:
        week_open = float((week[0] if week else d[-1])["open_price"])    # first bar this week
    except Exception:
        return None
    price = 0.0
    try:
        lp = rh.stocks.get_latest_price(sym) or []
        price = float(lp[0]) if lp and lp[0] else 0.0
    except Exception:
        price = 0.0
    if price <= 0:
        price = float(d[-1]["close_price"])                             # fallback: last daily close
    return {"price": round(price, 2), "week_open": round(week_open, 2)}


def check(sym: str, weeks: int = DEFAULT_WEEKS, tol: float = DEFAULT_TOL) -> dict | None:  # pragma: no cover - network
    w = _weekly(sym)                        # completed weekly bars → the volume profile
    if w is None or len(w) < 8:
        return None
    prof = compute_profile(w, bars_back=weeks)
    if prof is None:
        return None
    cur = _current(sym)                     # THIS week's open + the live price
    if cur is None:
        return None
    vwap = rolling_vwap(w, bars_back=weeks) or 0.0
    return classify(sym, cur["price"], prof.poc, prof.val, vwap, prof.peak_ratio, tol, cur["week_open"])


def classify(sym: str, close: float, poc: float, val: float, vwap: float,
             peak_ratio: float, tol: float = DEFAULT_TOL, week_open: float | None = None) -> dict:
    """Pure: where does `close` sit vs the weekly POC / VWAP / VAL? (unit-testable).

    Three value levels only (VAH excluded by design): POC (most-traded price), the
    anchored VWAP (the window's volume-weighted average), and VAL (value-area low).

    `week_open` = this week's open. A level the week OPENED ABOVE is acting as support
    (tradeable, stop under it — the reclaim/hold rule); opened below = testing from below."""
    def d(level: float) -> float:
        return (close - level) / close * 100 if close else 0.0   # signed % (close above = +)
    dp, dw, dv = d(poc), d(vwap), d(val)
    at_poc = abs(dp) <= tol * 100
    at_vwap = abs(dw) <= tol * 100
    at_val = abs(dv) <= tol * 100
    nearest, nd = min((("POC", dp), ("VWAP", dw), ("VAL", dv)), key=lambda x: abs(x[1]))
    wo = week_open if week_open is not None else close
    # Opened above the level → the level is support beneath the open.
    oa = {"POC": wo >= poc, "VWAP": wo >= vwap, "VAL": wo >= val}
    at_level = nearest if abs(nd) <= tol * 100 else ""
    # HELD = at a level AND this week opened above THAT level (support hold, not a reclaim
    # from below). `opened_above` reports it for whichever level the name is at.
    opened_above = oa.get(at_level, False)
    held = bool(at_level) and opened_above
    return {
        "sym": sym, "close": round(close, 2), "week_open": round(wo, 2),
        "poc": round(poc, 2), "vwap": round(vwap, 2), "val": round(val, 2),
        "d_poc": round(dp, 2), "d_vwap": round(dw, 2), "d_val": round(dv, 2),
        "at_poc": at_poc, "at_vwap": at_vwap, "at_val": at_val,
        "oa_poc": oa["POC"], "oa_vwap": oa["VWAP"], "oa_val": oa["VAL"],
        "at": at_level, "opened_above": opened_above, "held": held,
        "nearest": nearest, "nearest_d": round(nd, 2),
        "ambiguous": peak_ratio >= AMBIG, "peak_ratio": round(peak_ratio, 2),
    }


def scan(symbols, weeks: int = DEFAULT_WEEKS, tol: float = DEFAULT_TOL) -> list[dict]:  # pragma: no cover - network
    rows = []
    for s in symbols:
        try:
            r = check(s, weeks, tol)
            if r:
                rows.append(r)
        except Exception:
            pass
    # Holding a level as support first (at + opened above), then at-level, then nearest.
    rows.sort(key=lambda r: (0 if r["held"] else 1, 0 if r["at"] else 1, abs(r["nearest_d"])))
    return rows


def _print(rows, weeks, tol, at_only, held_only=False):
    held = [r for r in rows if r["held"]]
    hits = [r for r in rows if r["at"]]
    print(f"\n=== WEEKLY VP · {weeks}w window · tol ±{tol*100:.1f}% · Robinhood === "
          f"{len(held)} holding support · {len(hits)} at level · {len(rows)} scanned\n")
    print(f"  {'SYM':<7}{'PRICE':>10}{'WK OPEN':>10}{'POC':>10}{'VWAP':>10}{'VAL':>10}   "
          f"{'ΔPOC':>7}{'ΔVWAP':>7}{'ΔVAL':>7}  SIGNAL")
    for r in rows:
        if held_only and not r["held"]:
            continue
        if at_only and not r["at"]:
            continue
        if r["held"]:
            tag = f"🛡 holding {r['at']} (opened above)"
        elif r["at"]:
            tag = f"🎯 at {r['at']} (opened below — testing)"
        else:
            tag = ""
        amb = " ⚠tied" if r["ambiguous"] else ""
        print(f"  {r['sym']:<7}{r['close']:>10.2f}{r['week_open']:>10.2f}{r['poc']:>10.2f}{r['vwap']:>10.2f}{r['val']:>10.2f}   "
              f"{r['d_poc']:>6.2f}%{r['d_vwap']:>6.2f}%{r['d_val']:>6.2f}%  {tag}{amb}")


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Research: stocks at their WEEKLY VP POC/VAL by today's close")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--watchlist", action="store_true", help="scan the master watchlist")
    ap.add_argument("--weeks", type=int, default=DEFAULT_WEEKS, help="weekly bars in the profile window")
    ap.add_argument("--tol", type=float, default=DEFAULT_TOL, help='"at level" tolerance (fraction, e.g. 0.01)')
    ap.add_argument("--at-only", action="store_true", help="print only names at a level")
    ap.add_argument("--held", action="store_true", help="print only names HOLDING a level as support (at it + opened above this week)")
    args = ap.parse_args()
    if args.watchlist:
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(os.environ["DATABASE_URL"])
    else:
        symbols = [s.upper() for s in args.symbols] or ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "QQQ", "SPY"]
    rows = scan(symbols, args.weeks, args.tol)
    _print(rows, args.weeks, args.tol, args.at_only, args.held)


if __name__ == "__main__":
    main()
