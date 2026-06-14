#!/usr/bin/env python3
"""Swing-alert backfill — replay the SWING logic on daily price bars for any date.

Mirrors the swing rules that fire from the Pines (levels-day-vwap momentum +
ma-ema-daily slow-MA bounces) so you can validate "what swing alerts would have
fired" on a given session WITHOUT TradingView. Useful for spot-checking the book
against a trader's posted trades (Steve Burns) or your own notes.

    python3 analytics/swing_backfill.py                       # most-recent session
    python3 analytics/swing_backfill.py --date 2026-06-12
    python3 analytics/swing_backfill.py --date 2026-06-12 --watchlist SPY,QQQ,NVDA

Caveat: prices come from yfinance, which can differ from TradingView/StockCharts by
a few cents — so borderline 5/20 EMA crosses may not register here even though the
Pine (on TV data) marks them. Treat the count as a LOWER bound. The Pine is the
source of truth at runtime; this is a sanity replay.
"""
from __future__ import annotations
import argparse

# Default watchlist (the names traded/discussed). Override with --watchlist or
# point it at your real list.
DEFAULT_WATCHLIST = [
    "SPY", "QQQ", "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
    "MU", "MRVL", "TSM", "NBIS", "HOOD", "ASTS", "RKLB", "MDB", "NFLX", "INTC",
    "AMD", "VGT", "AIQ", "ORCL", "DRAM",
]
# Slow MAs whose bounce = a SWING (50/100/200, EMA and SMA). 8/21 EMA are
# day-trade scalps and excluded.
SLOW_MAS = ("SMA50", "SMA100", "SMA200", "EMA50", "EMA100", "EMA200")
OVERSOLD_LO, OVERSOLD_HI = 30.0, 35.0


def _rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    ag = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    al = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    return 100 - 100 / (1 + ag / al)


def _ma_series(close):
    return {
        "SMA50": close.rolling(50).mean(), "SMA100": close.rolling(100).mean(),
        "SMA200": close.rolling(200).mean(), "EMA50": close.ewm(span=50, adjust=False).mean(),
        "EMA100": close.ewm(span=100, adjust=False).mean(), "EMA200": close.ewm(span=200, adjust=False).mean(),
    }


def swing_fires_on(df, idx=-1):
    """Return the list of SWING alerts firing on bar `idx` of a daily DataFrame.
    Each entry is (rule, detail). Mirrors the Pine swing logic."""
    import pandas as pd
    c, o, lo = df["Close"], df["Open"], df["Low"]
    r = _rsi(c)
    e5 = c.ewm(span=5, adjust=False).mean()
    e20 = c.ewm(span=20, adjust=False).mean()
    mas = _ma_series(c)
    i = idx
    fires = []
    # rsi_70 — daily RSI crosses above 70 (parabolic ignition)
    if r.iloc[i - 1] <= 70 and r.iloc[i] > 70:
        fires.append(("rsi_70", f"RSI {r.iloc[i]:.1f} — momentum heads-up"))
    # rsi_oversold — first close in the 30-35 zone (never below 30); T1 50 / T2 70, stop close<30
    in_zone = lambda j: OVERSOLD_LO <= r.iloc[j] <= OVERSOLD_HI
    if in_zone(i) and not in_zone(i - 1):
        fires.append(("rsi_oversold", f"RSI {r.iloc[i]:.1f} in 30-35 · T1 RSI50 T2 RSI70 · stop close<30"))
    # ema_5_20_cross — daily 5 EMA crosses above 20 EMA; stop 5/20 cross-under, target RSI70
    if e5.iloc[i - 1] <= e20.iloc[i - 1] and e5.iloc[i] > e20.iloc[i]:
        fires.append(("ema_5_20_cross", f"5>20 EMA · stop {e20.iloc[i]:.2f} · target RSI70"))
    # slow-MA bounce — open above the MA, dip to it, close back above (held)
    for nm, ma in mas.items():
        if pd.notna(ma.iloc[i]) and o.iloc[i] > ma.iloc[i] and lo.iloc[i] <= ma.iloc[i] and c.iloc[i] >= ma.iloc[i]:
            fires.append((f"ma_bounce_{nm}", f"held {nm} {ma.iloc[i]:.2f} · stop close<{nm} · target next MA up"))
    return fires


def main():
    import pandas as pd, yfinance as yf
    ap = argparse.ArgumentParser(description="Replay SWING alerts on daily bars for a date.")
    ap.add_argument("--date", help="Session date YYYY-MM-DD (default: most recent bar)")
    ap.add_argument("--watchlist", help="Comma-separated tickers (default: built-in)")
    ap.add_argument("--history-months", type=int, default=14, help="History to pull (need ~210d for SMA200)")
    args = ap.parse_args()

    wl = [s.strip().upper() for s in args.watchlist.split(",")] if args.watchlist else DEFAULT_WATCHLIST
    target = pd.Timestamp(args.date).date() if args.date else None
    period = f"{args.history_months}mo"

    print(f"SWING-alert backfill — {'session ' + str(target) if target else 'most recent session'}\n")
    total = 0
    for s in wl:
        try:
            d = yf.download(s, period=period, interval="1d", progress=False, auto_adjust=False)
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            d = d.dropna()
            if target is not None:
                d = d[d.index.date <= target]
            if len(d) < 210:
                continue
            fires = swing_fires_on(d, -1)
            if fires:
                total += 1
                tags = " · ".join(f"{rule}" for rule, _ in fires)
                print(f"  {s:6} {d.index[-1].date()}  SWING → {tags}")
                for rule, detail in fires:
                    print(f"           - {detail}")
        except Exception as e:
            print(f"  {s:6} (skipped: {str(e)[:40]})")
    print(f"\n{total} names fired a swing alert. (yfinance prices — borderline 5/20 crosses may under-count.)")


if __name__ == "__main__":
    main()
