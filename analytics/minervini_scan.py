"""Minervini Trend Template + VCP base scanner — find the stocks that QUALIFY.

Mirrors the two pines (`minervini_trend_template.pine` + `vcp_base_breakout.pine`):
for each name it scores the 8-rule Stage-2 Trend Template and reads whether the stock
is coiling in a tight VCP base near a pivot — so you can see, at a glance, WHICH names
are buyable and WHICH are set up to break out.

Pure over daily OHLC + one benchmark fetch (SPY) for relative strength. Runs LOCALLY
and PRINTS a ranked report — it does not publish anything by default (no stored-but-
unviewable report). Pass an explicit symbol list, or --universe with DATABASE_URL set
to scan the master watchlist.

    # a few names
    python3 analytics/minervini_scan.py AAPL MSFT NVDA CRWD PLTR MU
    # the whole master watchlist
    DATABASE_URL=postgresql://... python3 analytics/minervini_scan.py --universe
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Callable, Optional

import pandas as pd

# Run either as `python3 analytics/minervini_scan.py …` or `python3 -m analytics.…`:
# ensure the repo root is importable so `from analytics.… import …` resolves.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── rule thresholds (mirror the pine inputs) ────────────────────────────────────
RISE_BARS      = 21      # rule 3 — 200 SMA higher than N bars ago (≈ 1 month)
LOOKBACK_52W   = 252     # 52-week window for the high/low (rules 6 & 7)
MIN_ABOVE_LOW  = 30.0    # rule 6 — ≥ 30% above the 52-week low
MAX_BELOW_HIGH = 25.0    # rule 7 — within 25% of the 52-week high
RS_MIN         = 0.0     # rule 8 — RS score must beat the benchmark (> 0)

# ── VCP base read (mirror vcp_base_breakout.pine) ───────────────────────────────
BASE_LEN        = 40
MAX_BASE_DEPTH  = 35.0
CONTRACT_RATIO  = 0.6
NEAR_PIVOT_PCT  = 6.0
VOL_DRY_PCT     = 0.85
BRK_VOL_MULT    = 1.4


def _sma(s: pd.Series, n: int) -> Optional[float]:
    if len(s) < n:
        return None
    return float(s.tail(n).mean())


def _rel_ret(close: pd.Series, bench: pd.Series, bars: int) -> Optional[float]:
    """Stock return minus benchmark return over `bars` sessions."""
    if len(close) <= bars or len(bench) <= bars:
        return None
    s = float(close.iloc[-1]) / float(close.iloc[-1 - bars]) - 1.0
    b = float(bench.iloc[-1]) / float(bench.iloc[-1 - bars]) - 1.0
    return s - b


def compute_minervini(symbol: str, df: pd.DataFrame, bench: pd.Series) -> Optional[dict]:
    """Score the 8 Trend Template rules + the VCP base read for one symbol.

    `df` = daily OHLCV (needs ≥ ~252 bars); `bench` = benchmark daily close (SPY).
    Returns a per-symbol dict, or None if there isn't enough history.
    """
    if df is None or len(df) < LOOKBACK_52W + RISE_BARS:
        return None
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    vol = df["Volume"].astype(float)

    c = float(close.iloc[-1])
    ma50 = _sma(close, 50)
    ma150 = _sma(close, 150)
    ma200 = _sma(close, 200)
    if None in (ma50, ma150, ma200):
        return None
    ma200_prev = float(close.tail(200 + RISE_BARS).head(200).mean())  # 200 SMA as of RISE_BARS ago

    hi52 = float(high.tail(LOOKBACK_52W).max())
    lo52 = float(low.tail(LOOKBACK_52W).min())

    # relative-strength proxy — IBD's 3m/6m/9m/12m weighting
    rets = [_rel_ret(close, bench, b) for b in (63, 126, 189, 252)]
    if any(r is None for r in rets):
        rs_score = None
    else:
        rs_score = 0.4 * rets[0] + 0.2 * rets[1] + 0.2 * rets[2] + 0.2 * rets[3]

    # the 8 rules
    r1 = c > ma150 and c > ma200
    r2 = ma150 > ma200
    r3 = ma200 > ma200_prev
    r4 = ma50 > ma150 and ma50 > ma200
    r5 = c > ma50
    r6 = c >= lo52 * (1 + MIN_ABOVE_LOW / 100)
    r7 = c >= hi52 * (1 - MAX_BELOW_HIGH / 100)
    r8 = (rs_score is not None) and (rs_score > RS_MIN)
    rules = {"1_above_150_200": r1, "2_150_gt_200": r2, "3_200_rising": r3,
             "4_50_above": r4, "5_above_50": r5, "6_above_52w_low": r6,
             "7_near_52w_high": r7, "8_rs_leading": r8}
    pass_count = sum(1 for v in rules.values() if v)
    all_pass = pass_count == 8

    # ── VCP base read ──────────────────────────────────────────────────────────
    third = max(3, BASE_LEN // 3)
    pivot = float(high.iloc[:-1].tail(BASE_LEN).max())     # base ceiling, excl. today
    floor = float(low.iloc[:-1].tail(BASE_LEN).min())
    base_depth = (pivot - floor) / pivot * 100 if pivot else None
    range_base = float(high.tail(BASE_LEN).max() - low.tail(BASE_LEN).min())
    range_recent = float(high.tail(third).max() - low.tail(third).min())
    contracting = range_base > 0 and range_recent <= range_base * CONTRACT_RATIO
    stop_level = float(low.tail(third).min())
    vol_avg = _sma(vol, 50)
    vol_recent = _sma(vol, 5)
    dry_up = bool(vol_avg and vol_recent is not None and vol_recent <= vol_avg * VOL_DRY_PCT)
    near_pivot = bool(pivot and c < pivot and c >= pivot * (1 - NEAR_PIVOT_PCT / 100))
    depth_ok = base_depth is not None and base_depth <= MAX_BASE_DEPTH
    dist_pivot = (c / pivot - 1) * 100 if pivot else None
    risk_pct = (pivot - stop_level) / pivot * 100 if pivot else None
    vol_today = float(vol.iloc[-1])
    breakout = bool(all_pass and depth_ok and pivot and c > pivot and vol_avg and vol_today >= vol_avg * BRK_VOL_MULT)
    forming = bool(all_pass and depth_ok and contracting and dry_up and near_pivot)

    return {
        "symbol": symbol, "close": round(c, 2),
        "pass_count": pass_count, "all_pass": all_pass, "rules": rules,
        "rs_score_pct": None if rs_score is None else round(rs_score * 100, 1),
        "base": {
            "pivot": round(pivot, 2), "stop": round(stop_level, 2),
            "depth_pct": None if base_depth is None else round(base_depth, 1),
            "dist_pivot_pct": None if dist_pivot is None else round(dist_pivot, 1),
            "risk_pct": None if risk_pct is None else round(risk_pct, 1),
            "contracting": contracting, "dry_up": dry_up, "near_pivot": near_pivot,
            "forming": forming, "breakout": breakout,
        },
    }


def build_report(symbols: list[str], fetch: Callable[[str], Optional[pd.DataFrame]],
                 bench_close: pd.Series) -> dict:
    rows: list[dict] = []
    errors: list[str] = []
    for sym in symbols:
        try:
            df = fetch(sym)
            r = compute_minervini(sym, df, bench_close)
            if r is not None:
                rows.append(r)
        except Exception as e:  # pragma: no cover - network/data
            errors.append(f"{sym}: {e}")

    qualifiers = sorted([r for r in rows if r["all_pass"]],
                        key=lambda r: (r["rs_score_pct"] or -999), reverse=True)
    near_miss = sorted([r for r in rows if r["pass_count"] == 7],
                       key=lambda r: (r["rs_score_pct"] or -999), reverse=True)
    breakouts = [r for r in qualifiers if r["base"]["breakout"]]
    ready = [r for r in qualifiers if r["base"]["forming"]]  # coiling under pivot

    return {
        "scanned": len(rows), "errors": errors,
        "counts": {"qualified_8of8": len(qualifiers), "near_miss_7of8": len(near_miss),
                   "ready_to_break": len(ready), "breakout_today": len(breakouts)},
        "qualifiers": qualifiers, "near_miss": near_miss,
        "ready": ready, "breakouts": breakouts,
    }


def _print_human(rep: dict) -> None:
    c = rep["counts"]
    print(f"\n═══ MINERVINI SCAN ═══  scanned {rep['scanned']}  ·  "
          f"{c['qualified_8of8']} qualified (8/8)  ·  {c['ready_to_break']} ready  ·  "
          f"{c['breakout_today']} breaking out today\n")

    def _line(r: dict) -> str:
        b = r["base"]
        tags = []
        if b["breakout"]:
            tags.append("★ BREAKOUT TODAY")
        elif b["forming"]:
            tags.append("● READY (coiling under pivot)")
        elif b["contracting"] and b["near_pivot"]:
            tags.append("tightening near pivot")
        tag = ("  — " + ", ".join(tags)) if tags else ""
        return (f"  {r['symbol']:<7} {r['close']:>9.2f}  RS {str(r['rs_score_pct']):>6}%  "
                f"pivot {b['pivot']:>9.2f}  stop {b['stop']:>9.2f}  "
                f"risk {b['risk_pct']}%  {b['dist_pivot_pct']:+.1f}% to pivot{tag}")

    if rep["breakouts"]:
        print("BREAKING OUT TODAY (8/8 + cleared pivot on volume):")
        for r in rep["breakouts"]:
            print(_line(r))
        print()
    if rep["ready"]:
        print("READY — qualified + coiling in a tight base under the pivot:")
        for r in rep["ready"]:
            print(_line(r))
        print()
    print(f"ALL QUALIFIERS (8/8), by relative strength:")
    for r in rep["qualifiers"]:
        print(_line(r))
    if rep["near_miss"]:
        print(f"\nNEAR MISS (7/8 — one rule away):")
        for r in rep["near_miss"]:
            fails = [k for k, v in r["rules"].items() if not v]
            print(f"  {r['symbol']:<7} {r['close']:>9.2f}  RS {str(r['rs_score_pct']):>6}%  "
                  f"— failing: {', '.join(fails)}")
    if rep["errors"]:
        print(f"\n({len(rep['errors'])} fetch/data errors)")


def _format_telegram(rep: dict, date: str) -> str:
    """Compact Telegram (HTML) digest — leaders, what's READY, what's breaking out."""
    c = rep["counts"]
    lines = [f"<b>MINERVINI · {date}</b>",
             f"{c['qualified_8of8']} qualified (8/8) · {c['ready_to_break']} ready · "
             f"{c['breakout_today']} breaking out"]

    def _one(r: dict) -> str:
        b = r["base"]
        return f"  {r['symbol']} — pivot {b['pivot']} · {b['dist_pivot_pct']:+.1f}% · stop {b['stop']}"

    if rep["breakouts"]:
        lines.append("\n<b>★ Breaking out today:</b>")
        lines += [_one(r) for r in rep["breakouts"]]
    if rep["ready"]:
        lines.append("\n<b>● Ready (coiling near pivot):</b>")
        lines += [_one(r) for r in rep["ready"]]
    top = rep["qualifiers"][:10]
    if top:
        lines.append("\n<b>Top qualifiers by RS:</b>")
        lines += [f"  {r['symbol']} +{r['rs_score_pct']}% — pivot {r['base']['pivot']} "
                  f"({r['base']['dist_pivot_pct']:+.1f}%)" for r in top]
    return "\n".join(lines)


def _send_to_telegram(text: str) -> bool:  # pragma: no cover - network
    from alerting.notifier import _send_telegram_to, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping send", file=sys.stderr)
        return False
    return _send_telegram_to(text, TELEGRAM_CHAT_ID, parse_mode="HTML")


def _fetch(symbol: str) -> Optional[pd.DataFrame]:  # pragma: no cover - network
    """Daily bars via the shared multi-source helper (Alpaca → yfinance)."""
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(symbol, period="18mo", interval="1d")
    if df is None or df.empty:
        return None
    return df.dropna()


def main() -> None:  # pragma: no cover - manual entrypoint
    ap = argparse.ArgumentParser(description="Minervini Trend Template + VCP base scanner")
    ap.add_argument("symbols", nargs="*", help="symbols to scan (default: a demo set)")
    ap.add_argument("--universe", action="store_true", help="scan the master watchlist (needs DATABASE_URL)")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--telegram", action="store_true", help="post the digest to Telegram (needs TELEGRAM_BOT_TOKEN/CHAT_ID)")
    args = ap.parse_args()

    if args.universe:
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            print("--universe needs DATABASE_URL set", file=sys.stderr)
            sys.exit(2)
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(dsn)
    else:
        symbols = [s.upper() for s in args.symbols] or \
            ["AAPL", "MSFT", "NVDA", "CRWD", "PLTR", "MU", "AVGO", "META", "AMZN", "NBIS"]

    bench_df = _fetch("SPY")
    if bench_df is None or bench_df.empty:
        print("could not fetch benchmark (SPY) — RS rule will fail for all", file=sys.stderr)
        bench_close = pd.Series(dtype=float)
    else:
        bench_close = bench_df["Close"].astype(float)

    rep = build_report(symbols, _fetch, bench_close)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        _print_human(rep)

    if args.telegram:
        import datetime as _dt
        ok = _send_to_telegram(_format_telegram(rep, _dt.date.today().isoformat()))
        print(f"telegram: {'sent' if ok else 'not sent'}", file=sys.stderr)


if __name__ == "__main__":
    main()
