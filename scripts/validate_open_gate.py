#!/usr/bin/env python3
"""Is the open-above condition a good filter? Measure it, don't argue about it.

For every MA level the scanner watches, this finds every intraday TAG of that
level over the last N sessions and splits them two ways:

    PASSED  — the day opened ABOVE the level (the scanner fires)
    BLOCKED — the day opened BELOW it (the scanner stays silent)

Then it scores what happened next, so the gate can be judged on outcomes rather
than on reasoning. A tag "worked" if price closed the session above the level
after reclaiming it; the R column is (session close − reclaim close) / risk,
where risk = reclaim close − level × 0.995 — the scanner's actual stop.

If BLOCKED tags win as often as PASSED ones, the gate is costing you money.
If PASSED wins materially more, it is doing its job.

Also prints the same table for WEEKLY 8/21 EMA levels, because the Pine chart
plots those while the scanner computes daily ones — worth knowing which level
set actually separates the winners.

Run from the repo root, on a machine with market data access:

    python3 scripts/validate_open_gate.py                # last 3 sessions
    python3 scripts/validate_open_gate.py --days 10      # last 10
    python3 scripts/validate_open_gate.py --symbols ASML,ETH-USD
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

import pandas as pd
import yfinance as yf

sys.path.insert(0, ".")

# The scanner's own numbers, imported so this can't drift from production.
from alert_config import MA_RECLAIM_MAX_DISTANCE_PCT, MA_RECLAIM_STOP_OFFSET_PCT  # noqa: E402

try:
    sys.path.insert(0, "api")
    from app.background.monitor import SCANNER_UNIVERSE
except Exception:  # standalone fallback
    SCANNER_UNIVERSE = ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AVGO", "ASML"]


def daily_levels(hist: pd.DataFrame, upto: pd.Timestamp) -> dict[str, float]:
    """The scanner's daily MA ladder as of the close BEFORE `upto`."""
    prior = hist[hist.index < upto]
    if len(prior) < 200:
        return {}
    c = prior["Close"]
    out = {}
    for p in (8, 21, 50, 100, 200):
        out[f"{p} SMA"] = float(c.rolling(p).mean().iloc[-1])
        out[f"{p} EMA"] = float(c.ewm(span=p, adjust=False).mean().iloc[-1])
    return out


def weekly_levels(hist: pd.DataFrame, upto: pd.Timestamp) -> dict[str, float]:
    """Weekly 8/21 EMA — what the Pine chart plots. Not in the scanner today."""
    prior = hist[hist.index < upto]
    if len(prior) < 60:
        return {}
    wk = prior["Close"].resample("W-FRI").last().dropna()
    if len(wk) < 21:
        return {}
    return {
        "8 EMA (W)": float(wk.ewm(span=8, adjust=False).mean().iloc[-1]),
        "21 EMA (W)": float(wk.ewm(span=21, adjust=False).mean().iloc[-1]),
    }


def score_session(bars: pd.DataFrame, levels: dict[str, float]) -> list[dict]:
    """Every level this session TAGGED, with the gate verdict and the outcome."""
    if bars.empty:
        return []
    day_open = float(bars.iloc[0]["Open"])
    session_low = float(bars["Low"].min())
    session_close = float(bars.iloc[-1]["Close"])
    rows = []

    for label, lvl in levels.items():
        if not lvl or lvl <= 0:
            continue
        if session_low > lvl:
            continue  # never tagged — not a candidate either way

        # The reclaim: first bar after the tag that closes back above the level.
        tagged = False
        reclaim_close = None
        for _, b in bars.iterrows():
            if float(b["Low"]) <= lvl:
                tagged = True
            if tagged and float(b["Close"]) > lvl:
                reclaim_close = float(b["Close"])
                break
        if reclaim_close is None:
            continue  # tagged and never got back above — no entry either way

        # The scanner would also skip an entry already extended past the level.
        if (reclaim_close - lvl) / lvl > MA_RECLAIM_MAX_DISTANCE_PCT:
            continue

        stop = lvl * (1 - MA_RECLAIM_STOP_OFFSET_PCT)
        risk = reclaim_close - stop
        r = (session_close - reclaim_close) / risk if risk > 0 else 0.0
        rows.append({
            "level": label,
            "gate": "PASSED" if day_open > lvl else "BLOCKED",
            "held": session_close > lvl,
            "r": r,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="sessions to score (default 3)")
    ap.add_argument("--symbols", type=str, default="", help="comma list; default = SCANNER_UNIVERSE")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or SCANNER_UNIVERSE
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period="2y", interval="1d")
            intraday = yf.Ticker(sym).history(period="1mo", interval="5m")
        except Exception as exc:
            print(f"  {sym}: fetch failed — {exc}")
            continue
        if hist.empty or intraday.empty:
            print(f"  {sym}: no data")
            continue

        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        intraday.index = pd.to_datetime(intraday.index).tz_localize(None)
        sessions = sorted({d.date() for d in intraday.index})[-args.days:]

        for d in sessions:
            bars = intraday[intraday.index.date == d]
            if len(bars) < 6:
                continue
            ts = pd.Timestamp(d)
            for kind, fn in (("daily", daily_levels), ("weekly", weekly_levels)):
                for row in score_session(bars, fn(hist, ts)):
                    buckets[(kind, row["gate"])].append(row)
        print(f"  {sym}: {len(sessions)} sessions scored")

    print("\n" + "=" * 68)
    print(f"OPEN-GATE VALIDATION — last {args.days} sessions, {len(symbols)} symbols")
    print("=" * 68)
    for kind in ("daily", "weekly"):
        print(f"\n{kind.upper()} levels")
        print(f"  {'gate':<9} {'tags':>6} {'held':>6} {'win%':>7} {'avg R':>8}")
        for gate in ("PASSED", "BLOCKED"):
            rows = buckets[(kind, gate)]
            if not rows:
                print(f"  {gate:<9} {0:>6}")
                continue
            held = sum(1 for r in rows if r["held"])
            avg_r = sum(r["r"] for r in rows) / len(rows)
            print(f"  {gate:<9} {len(rows):>6} {held:>6} "
                  f"{100 * held / len(rows):>6.0f}% {avg_r:>8.2f}")

    print("\nRead it this way:")
    print("  PASSED  = what the scanner alerts on today.")
    print("  BLOCKED = what the open gate is throwing away.")
    print("  If BLOCKED's win% and avg R match PASSED's, the gate is not earning")
    print("  its keep. If PASSED is clearly better, it is.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
