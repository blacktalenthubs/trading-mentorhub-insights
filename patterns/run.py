"""Breakout scanner runner.

  Nightly batch (master watchlist → Today tab):
    DATABASE_URL=... python3 -m patterns.run --universe --publish --earnings-filter

  On-demand (a smaller watchlist, mid-day, no wait):
    python3 -m patterns.run AMD MRNA QQQ NVDA
    python3 -m patterns.run --universe            # scan the master list, print only

  Flags: --publish (write Today tab) · --earnings-filter (drop names reporting ≤10d) ·
         --chart (PNG per hit) · --date YYYY-MM-DD (default: today).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patterns import writer  # noqa: E402
from patterns.screener import scan  # noqa: E402

_DEMO = ["AMD", "MRNA", "QQQ", "NVDA", "NKE", "META", "AVGO", "PLTR"]


def _print(rep):
    f = rep["funnel"]
    print(f"\n=== BREAKOUT SCAN === scanned {f['scanned']} · passed pre-filter {f.get('passed_prefilter', 0)} "
          f"· {len(rep['rows'])} setups")
    print("  funnel:", {k: v for k, v in f.items() if v and k not in ('scanned', 'passed_prefilter')})
    for r in rep["rows"]:
        mark = "▲" if r["stage"] == "breakout" else "·"
        print(f"  {mark} [{r['stage']:>8}] {r['ticker']:<6} {r['pattern']:<18} "
              f"buy {r['buy_point']:>8.2f} ({r['pct_to_buy']:+.1f}%) stop {r['suggested_stop']:>8.2f} "
              f"risk {r['risk_pct']:.1f}% · score {r['score']:>3} — {r['reason']}")
    if rep["empty"]:
        print("  (no qualified setups)")


def main():  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Breakout pattern scanner → Today tab")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--universe", action="store_true", help="scan the master watchlist (needs DATABASE_URL)")
    ap.add_argument("--publish", action="store_true", help="write results to the Today tab")
    ap.add_argument("--earnings-filter", action="store_true", help="drop names reporting within 10 days")
    ap.add_argument("--chart", action="store_true", help="render a PNG per hit into ./pattern_charts/")
    ap.add_argument("--date", default=_dt.date.today().isoformat())
    a = ap.parse_args()

    if a.universe:
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(os.environ["DATABASE_URL"])
    else:
        symbols = [s.upper() for s in a.symbols] or _DEMO

    rep = scan(symbols, earnings_filter=a.earnings_filter)
    _print(rep)

    if a.chart and rep["rows"]:
        from patterns.charts import render_hit
        from patterns.screener import _default_fetch
        from patterns.indicators import add_indicators
        outdir = "pattern_charts"
        os.makedirs(outdir, exist_ok=True)
        for r in rep["rows"]:
            try:
                df = add_indicators(_default_fetch(r["ticker"]))
                p = render_hit(df, r, outdir)
                print(f"  chart: {p}")
            except Exception as exc:
                print(f"  chart failed for {r['ticker']}: {exc}")

    if a.publish:
        body = writer.publish(rep, a.date)
        print(f"\npublished: {writer.KIND} {a.date} ({len(body['rows'])} rows)", file=sys.stderr)


if __name__ == "__main__":
    main()
