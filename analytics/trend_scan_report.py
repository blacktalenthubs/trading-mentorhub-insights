"""Trend Setups briefing — a READ-ONLY daily report (not an alert source).

Reuses the validated engine (analytics/ema_trend_scan.py) to classify a watchlist
into three buckets a busy trader can act on at a glance:

  • ready_now   — above a RISING 20 EMA, ADX-confirmed, sitting WITHIN the entry
                  band (~2.5%) of the 20. Entry = the 20-EMA level (a limit), stop
                  just below. These are the "buy the line tomorrow if it holds" names.
                  (Backtest: entering AT the line ≈ 4.5× the R of chasing the close.)
  • extended    — same strong trend, but MORE than the band above the 20 → don't
                  chase; wait for a pullback to the line.
  • rolling_off — below the 20 (lost the line) → not a trend entry right now.

Pure over daily OHLC — no app/DB deps — so it's unit-testable and reusable by a
triage-worker job that publishes it to `market_reports` (like premarket/EOD).
"""

from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from analytics.ema_trend_scan import adx_series

ENTRY_BAND_PCT = 2.5   # within this % of the 20 = "ready to buy the line"
ADX_MIN = 20.0
SLOPE_BARS = 5


def _row(symbol: str, df: pd.DataFrame) -> Optional[dict]:
    if df is None or len(df) < 60:
        return None
    h, l, c = df["High"], df["Low"], df["Close"]
    e20 = c.ewm(span=20).mean()
    e50 = c.ewm(span=50).mean()
    adx = adx_series(h, l, c)
    cl = float(c.iloc[-1]); m20 = float(e20.iloc[-1]); m50 = float(e50.iloc[-1]); a = float(adx.iloc[-1])
    if m20 <= 0:
        return None
    rising20 = m20 > float(e20.iloc[-1 - SLOPE_BARS])
    above20 = cl > m20
    dist = (cl - m20) / m20 * 100.0
    return {
        "symbol": symbol,
        "price": round(cl, 2),
        "ema20": round(m20, 2),
        "ema50": round(m50, 2),
        "adx": round(a, 0),
        "dist_pct": round(dist, 1),
        "stop": round(min(float(l.iloc[-1]), m20 * 0.995), 2),  # the line / today's low, whichever protects
        "rising20": rising20,
        "above20": above20,
    }


def build_trend_report(symbols: list[str], fetch: Callable[[str], Optional[pd.DataFrame]]) -> dict:
    """Classify `symbols` into ready_now / extended / rolling_off.

    `fetch(symbol)` returns a daily OHLC DataFrame (High/Low/Close) or None.
    Returns a report dict ready to persist as JSON.
    """
    ready, extended, rolling = [], [], []
    for s in symbols:
        r = _row(s, fetch(s))
        if r is None:
            continue
        trend = r["rising20"] and r["above20"] and r["adx"] >= ADX_MIN
        if trend and r["dist_pct"] <= ENTRY_BAND_PCT:
            ready.append(r)
        elif trend:
            extended.append(r)
        elif not r["above20"]:
            rolling.append(r)
    ready.sort(key=lambda x: -x["adx"])
    extended.sort(key=lambda x: -x["adx"])
    rolling.sort(key=lambda x: x["dist_pct"])
    return {
        "kind": "trend_setups",
        "entry_band_pct": ENTRY_BAND_PCT,
        "ready_now": ready,        # at the line — buy on a hold, entry = the 20
        "extended": extended,      # strong but far — wait for a pullback
        "rolling_off": rolling,    # lost the 20 — not a trend entry
        "counts": {"ready": len(ready), "extended": len(extended), "rolling": len(rolling)},
    }


def _yf_fetch(symbol: str):  # pragma: no cover - network
    import yfinance as yf, warnings
    warnings.filterwarnings("ignore")
    df = yf.download(symbol, period="6mo", interval="1d", progress=False, auto_adjust=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


if __name__ == "__main__":  # pragma: no cover - manual/cron entrypoint
    import json, sys
    syms = sys.argv[1:] or ["AAPL", "MSFT", "NVDA"]
    rep = build_trend_report(syms, _yf_fetch)
    print(json.dumps(rep, indent=2))
