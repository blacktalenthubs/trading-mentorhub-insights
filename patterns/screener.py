"""Breakout pattern scanner — orchestration + CLI.

Pipeline per symbol:
    fetch daily history (analytics.market_data.fetch_daily_history)
      → derived columns (analytics.indicators.add_derived_columns)
      → pre-filter (patterns.prefilter) with funnel counts
      → the four detectors → score + reason
    then rows → Today tab (patterns.today_writer) and optional CSV / charts.

Run modes
---------
Nightly batch (registered in api/app/main.py, 16:22 ET Mon-Fri) over the master
watchlist, writing the ``breakout_patterns`` report for the next session.

On demand, from the repo root:
    python -m patterns.screener AAPL NVDA MSFT              # print only
    python -m patterns.screener --universe --publish        # full watchlist → Today tab
    python -m patterns.screener AAPL --publish --chart --earnings-filter --csv out.csv

``--publish`` needs DATABASE_URL (Postgres) or writes to the local SQLite DB.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:  # allow `python patterns/screener.py` as well as `-m`
    sys.path.insert(0, _ROOT)

from patterns.ascending_triangle import detect_ascending_triangle  # noqa: E402
from patterns.bull_flag import detect_bull_flag  # noqa: E402
from patterns.common import PatternHit  # noqa: E402
from patterns.config import DEFAULT_CONFIG, ScannerConfig  # noqa: E402
from patterns.cup_handle import detect_cup_handle  # noqa: E402
from patterns.flat_base import detect_flat_base  # noqa: E402
from patterns.prefilter import FILTER_ORDER, empty_funnel, prefilter  # noqa: E402
from patterns.scoring import reason_for, score_hit  # noqa: E402
from patterns.today_writer import build_body, write_csv, write_today  # noqa: E402

logger = logging.getLogger("patterns.screener")

Fetcher = Callable[[str], pd.DataFrame]


@dataclass
class ScanResult:
    session_date: str
    scanned_at: str
    rows: list[dict] = field(default_factory=list)
    hits: list[PatternHit] = field(default_factory=list)
    funnel: dict = field(default_factory=dict)
    skipped: dict = field(default_factory=dict)      # ticker → reason
    scanned: int = 0
    frames: dict = field(default_factory=dict)       # ticker → prepared frame (for charts)

    def body(self, universe: str = "") -> dict:
        return build_body(
            self.rows, session_date=self.session_date, scanned_at=self.scanned_at,
            scanned=self.scanned, funnel=self.funnel, skipped=self.skipped, universe=universe,
        )


# ── data ─────────────────────────────────────────────────────────────────────

def default_fetch(cfg: ScannerConfig = DEFAULT_CONFIG) -> Fetcher:
    """The project's data layer: yfinance-first daily bars with consolidated volume."""
    from analytics.market_data import fetch_daily_history

    def _fetch(symbol: str) -> pd.DataFrame:
        return fetch_daily_history(symbol, period=cfg.data.fetch_period)

    return _fetch


def prepare_frame(df: pd.DataFrame, cfg: ScannerConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Attach the derived columns the detectors and pre-filter read."""
    from analytics.indicators import add_derived_columns

    d = cfg.data
    return add_derived_columns(
        df, slope_bars=d.slope_bars, vol_window=d.vol_window, atr_period=d.atr_period,
        rsi_period=d.rsi_period, year_bars=d.year_bars,
    )


# ── per-symbol ───────────────────────────────────────────────────────────────

def detect_all(df: pd.DataFrame, ticker: str, cfg: ScannerConfig = DEFAULT_CONFIG) -> list[PatternHit]:
    """Run the four detectors on a prepared frame; score and annotate every hit."""
    hits: list[PatternHit] = []
    detectors = (
        (detect_cup_handle, cfg.cup_handle),
        (detect_flat_base, cfg.flat_base),
        (detect_ascending_triangle, cfg.ascending_triangle),
        (detect_bull_flag, cfg.bull_flag),
    )
    for fn, pcfg in detectors:
        try:
            hit = fn(df, pcfg, cfg.breakout, ticker)
        except Exception:
            logger.exception("%s: %s raised", ticker, fn.__name__)
            continue
        if hit is None:
            continue
        hit.score = score_hit(hit, df, cfg.weights)
        hit.reason = reason_for(hit)
        hits.append(hit)
    return hits


def hit_to_row(hit: PatternHit, df: pd.DataFrame, scanned_at: str) -> dict:
    """The per-row payload the Today tab renders (see spec)."""
    last = df.iloc[-1]
    sma200 = float(last["sma200"]) if pd.notna(last.get("sma200")) else None
    rsi = float(last["rsi14"]) if pd.notna(last.get("rsi14")) else None
    lc = hit.last_close
    return {
        "ticker": hit.ticker,
        "pattern": hit.pattern,
        "stage": hit.stage,
        "buy_point": round(hit.buy_point, 2),
        "last_close": round(lc, 2),
        "pct_to_buy": round((hit.buy_point - lc) / lc * 100.0, 2) if lc else None,
        "suggested_stop": round(hit.suggested_stop, 2),
        "risk_pct": round((lc - hit.suggested_stop) / lc * 100.0, 2) if lc else None,
        "rvol": round(hit.rvol, 2),
        "volume_ok": bool(hit.volume_ok),
        "base_depth_pct": round(hit.base_depth_pct, 2),
        "base_length_days": int(hit.base_length_days),
        "rsi14": round(rsi, 1) if rsi is not None else None,
        "dist_from_200sma_pct": round((lc - sma200) / sma200 * 100.0, 2) if sma200 else None,
        "score": hit.score,
        "reason": hit.reason,
        "scanned_at": scanned_at,
        "days_to_earnings": None,
        "chart_path": None,
    }


# ── earnings filter ──────────────────────────────────────────────────────────

def earnings_calendar(symbols: Iterable[str]) -> dict[str, _dt.date]:
    """ticker → next earnings date, from the nightly-refreshed ``earnings`` table
    (analytics/earnings_refresh.py). Falls back to the Finnhub fetcher per symbol
    when the table is unavailable and FINNHUB_API_KEY is set. Best-effort."""
    out: dict[str, _dt.date] = {}
    wanted = {s.upper() for s in symbols}
    try:
        import db as _db
        with _db.get_db() as conn:
            cur = conn.execute("SELECT symbol, next_earnings_date FROM earnings WHERE next_earnings_date IS NOT NULL")
            for row in cur.fetchall():
                sym, d = row[0], row[1]
                if sym is None or d is None:
                    continue
                if isinstance(d, str):
                    d = _dt.date.fromisoformat(d[:10])
                elif isinstance(d, _dt.datetime):
                    d = d.date()
                if str(sym).upper() in wanted:
                    out[str(sym).upper()] = d
        if out:
            return out
    except Exception as e:  # table missing locally, no DB, etc.
        logger.info("earnings table unavailable (%s) — trying Finnhub", str(e)[:80])
    if os.environ.get("FINNHUB_API_KEY"):
        try:
            from analytics.earnings_fetcher import fetch_upcoming_earnings
            for s in wanted:
                up = fetch_upcoming_earnings(s, days_ahead=30)
                if up and up.next_earnings_date:
                    out[s] = up.next_earnings_date
        except Exception:
            logger.exception("Finnhub earnings lookup failed")
    return out


# ── universe ─────────────────────────────────────────────────────────────────

def load_universe(dsn: Optional[str] = None) -> tuple[list[str], str]:
    """The scan universe: the master watchlist (what every other Today producer
    scans), else the static screener universe. Returns (symbols, label)."""
    dsn = dsn or os.environ.get("DATABASE_URL")
    if dsn:
        try:
            from analytics.swing_setups_report import _watchlist
            syms = _watchlist(dsn)
            if syms:
                return syms, "master_watchlist"
        except Exception:
            logger.exception("master watchlist unavailable — using static universe")
    from analytics.screener import MEGA_CAP_UNIVERSE, SMALL_CAP_UNIVERSE, STATIC_UNIVERSE
    syms = sorted({*STATIC_UNIVERSE, *MEGA_CAP_UNIVERSE, *SMALL_CAP_UNIVERSE})
    return syms, "static_universe"


# ── the run ──────────────────────────────────────────────────────────────────

def run_scan(
    symbols: Iterable[str],
    cfg: ScannerConfig = DEFAULT_CONFIG,
    *,
    fetch: Optional[Fetcher] = None,
    earnings_filter: bool = False,
    chart_dir: Optional[str] = None,
    session_date: Optional[str] = None,
    keep_frames: bool = False,
) -> ScanResult:
    """Scan ``symbols`` and return the rows + funnel. Never raises on a bad ticker."""
    fetch = fetch or default_fetch(cfg)
    now = _dt.datetime.now(_dt.timezone.utc)
    res = ScanResult(
        session_date=session_date or _dt.date.today().isoformat(),
        scanned_at=now.isoformat(timespec="seconds"),
        funnel=empty_funnel(),
    )
    symbols = [s.upper().strip() for s in symbols if s and s.strip()]
    res.scanned = len(symbols)
    edates = earnings_calendar(symbols) if earnings_filter else {}
    today = _dt.date.today()

    for sym in symbols:
        try:
            raw = fetch(sym)
        except Exception as e:
            res.skipped[sym] = f"fetch failed: {str(e)[:80]}"
            logger.warning("%s skipped — fetch failed: %s", sym, str(e)[:80])
            continue
        if raw is None or raw.empty:
            res.skipped[sym] = "no data"
            logger.warning("%s skipped — no data", sym)
            continue
        if len(raw) < cfg.data.min_bars:
            res.skipped[sym] = f"only {len(raw)} bars (< {cfg.data.min_bars})"
            logger.info("%s skipped — %s", sym, res.skipped[sym])
            continue
        try:
            df = prepare_frame(raw, cfg)
        except Exception as e:
            res.skipped[sym] = f"indicators failed: {str(e)[:80]}"
            logger.warning("%s skipped — indicators failed: %s", sym, str(e)[:80])
            continue

        gate = prefilter(df, cfg.prefilter)
        if gate is not None:
            res.funnel[gate] += 1
            continue
        res.funnel["passed"] += 1

        days_to_er: Optional[int] = None
        if sym in edates:
            days_to_er = (edates[sym] - today).days
            if earnings_filter and 0 <= days_to_er <= cfg.earnings_window_days:
                res.skipped[sym] = f"earnings in {days_to_er}d"
                logger.info("%s dropped — earnings in %d days", sym, days_to_er)
                continue

        hits = detect_all(df, sym, cfg)
        if not hits:
            continue
        if keep_frames or chart_dir:
            res.frames[sym] = df
        for hit in hits:
            row = hit_to_row(hit, df, res.scanned_at)
            row["days_to_earnings"] = days_to_er
            if chart_dir:
                try:
                    from patterns.charts import render_chart
                    row["chart_path"] = str(render_chart(df, hit, chart_dir))
                except Exception:
                    logger.exception("%s chart failed", sym)
            res.rows.append(row)
            res.hits.append(hit)

    _log_funnel(res)
    return res


def _log_funnel(res: ScanResult) -> None:
    remaining = res.scanned - len([k for k, v in res.skipped.items() if not v.startswith("earnings")])
    parts = [f"scanned={res.scanned}", f"skipped={len(res.skipped)}", f"eligible={remaining}"]
    for name in FILTER_ORDER:
        removed = res.funnel.get(name, 0)
        remaining -= removed
        parts.append(f"-{name}={removed} → {remaining}")
    parts.append(f"passed={res.funnel.get('passed', 0)}")
    parts.append(f"hits={len(res.rows)}")
    logger.info("funnel: " + " | ".join(parts))


# ── CLI ──────────────────────────────────────────────────────────────────────

def _print(res: ScanResult) -> None:
    body = res.body()
    print(f"\n=== BREAKOUT PATTERNS {res.session_date} === scanned {res.scanned} · "
          f"passed pre-filter {res.funnel.get('passed', 0)} · {body['breakouts']} breakout · {body['forming']} forming")
    f = res.funnel
    print("  funnel: " + " · ".join(f"{k} -{f.get(k, 0)}" for k in FILTER_ORDER))
    if res.skipped:
        print(f"  skipped {len(res.skipped)}: " + ", ".join(f"{k} ({v})" for k, v in list(res.skipped.items())[:15]))
    if not body["rows"]:
        print(f"\n  {body['message']}\n")
        return
    print()
    for r in body["rows"]:
        tag = "🚀 BREAKOUT" if r["stage"] == "breakout" else "   forming "
        vol = "vol✓" if r["volume_ok"] else "vol✗"
        print(f"  {tag} {r['ticker']:<6} {r['pattern']:<19} score {r['score']:>5.1f}  "
              f"buy {r['buy_point']:>8.2f} ({r['pct_to_buy']:+.1f}%)  stop {r['suggested_stop']:>8.2f} "
              f"risk {r['risk_pct']:.1f}%  rvol {r['rvol']:.2f} {vol}  — {r['reason']}")
    print()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Breakout pattern scanner (cup-and-handle, flat base, ascending triangle, bull flag)")
    ap.add_argument("symbols", nargs="*", help="tickers to scan (on-demand); omit with --universe")
    ap.add_argument("--universe", action="store_true", help="scan the master watchlist (nightly universe)")
    ap.add_argument("--publish", action="store_true", help="write results to the Today tab (market_reports)")
    ap.add_argument("--csv", metavar="PATH", help="also dump rows to a CSV")
    ap.add_argument("--json", action="store_true", help="print the report body as JSON")
    ap.add_argument("--chart", action="store_true", help="render a PNG per hit")
    ap.add_argument("--chart-dir", default=None, help="where PNGs go (default reports/pattern_charts/<date>)")
    ap.add_argument("--earnings-filter", action="store_true", help="drop names reporting within the config window (10d)")
    ap.add_argument("--date", default=None, help="session date to write (YYYY-MM-DD, default today)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.universe:
        symbols, label = load_universe()
    else:
        symbols, label = [s.upper() for s in args.symbols], "on_demand"
    if not symbols:
        ap.error("no symbols — pass tickers or --universe")

    chart_dir = None
    if args.chart:
        chart_dir = args.chart_dir or os.path.join(_ROOT, "reports", "pattern_charts", args.date or _dt.date.today().isoformat())

    res = run_scan(symbols, earnings_filter=args.earnings_filter, chart_dir=chart_dir, session_date=args.date)
    body = res.body(universe=label)
    if args.json:
        print(json.dumps(body, indent=2, default=str))
    else:
        _print(res)
    if args.csv:
        p = write_csv(res.rows, args.csv)
        print(f"csv: {p}", file=sys.stderr)
    if args.publish:
        write_today(body, res.session_date)
        print(f"published: {res.session_date} breakout_patterns ({len(body['rows'])} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
