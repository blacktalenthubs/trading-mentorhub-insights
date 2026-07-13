"""smz_strategy_backtest.py — replicate @pdicarlotrader's "smart money zone" long-term swing
strategy and print his stat panel (win rate, profit factor, avg win/loss, expectancy, total
return, max drawdown, avg hold, R/R) per symbol across the leaders universe.

His rules, from his own narration + the THT strategy panels (all replicable Pine — nothing
proprietary):
  • CONTEXT / regime : long-term bull structure = 33-period Fair Value Band basis RISING.
  • DISCOUNT / entry  : price pulls back and TAPS the lower fair-value band (the "smart money
                        discount zone"), then closes back ABOVE it (the bounce/confirmation).
  • STOP              : the swing low of the tap.
  • TARGET            : the prior swing high (the "equal high" — revert to prior/all-time highs).
  • Hold 6–12 months; he claims ~65% win, ~5:1 R/R.

Two exit models are measured head-to-head:
  A ("his")    : swing-low stop + prior-high target + max-hold cap  → the 5:1 setup.
  B ("regime") : same entry, exit only when the FVB regime flips RED (basis turns down)
                 → the "let it run" panel version (big avg win, big avg loss).

Usage:
  python3 analytics/smz_strategy_backtest.py --symbols MSFT,NVDA,AMD,AAPL,AMZN,META
  python3 analytics/smz_strategy_backtest.py --universe
  python3 analytics/smz_strategy_backtest.py --universe --exit regime --sort pf
"""
from __future__ import annotations

import argparse
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

# ── strategy parameters (his defaults) ─────────────────────────────────────────
FVB_LEN = 33          # fair value band basis length (his "33 FVB")
FVB_MULT = 2.0        # band width in std devs
TOUCH_TOL = 0.01      # "tap" = weekly low within 1% of / below the lower band
SWING_LOOKBACK = 4    # swing-low stop = lowest low of the entry bar + prior N bars
TARGET_LOOKBACK = 104 # prior-high target = highest high over the last ~2y
MAX_HOLD = 52         # weeks — his 6–12mo hold; force-close after 1y (model A)
BARS = 520            # ~10y of weekly bars


def _load_universe() -> list[str]:
    p = Path(__file__).resolve().parents[1] / "triage-agent" / "broad_universe.py"
    spec = importlib.util.spec_from_file_location("broad_universe", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore
    return list(m.BROAD_UNIVERSE)


def _weekly(sym: str, batch: pd.DataFrame | None = None) -> pd.DataFrame | None:
    """Weekly OHLC for one symbol (from a pre-fetched batch, else fetch)."""
    try:
        if batch is not None and sym in batch.columns.get_level_values(0):
            df = batch[sym].dropna()
        else:
            import yfinance as yf
            df = yf.download(sym, period="10y", interval="1wk", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        if df is None or len(df) < FVB_LEN + 20:
            return None
        df = df.rename(columns=str.title)[["Open", "High", "Low", "Close"]].copy()
        return df.dropna()
    except Exception:
        return None


def _signals(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"]
    basis = c.rolling(FVB_LEN).mean()
    sd = c.rolling(FVB_LEN).std()
    df = df.assign(
        basis=basis,
        lower=basis - FVB_MULT * sd,
        rising=basis.diff() > 0,                      # bull regime = basis rising
        prior_high=df["High"].rolling(TARGET_LOOKBACK, min_periods=20).max().shift(1),
        swing_low=df["Low"].rolling(SWING_LOOKBACK, min_periods=1).min(),
    )
    return df


def _backtest(df: pd.DataFrame, exit_model: str) -> list[dict]:
    """Return list of closed trades: {ret, bars, win}."""
    df = _signals(df).reset_index(drop=True)
    trades: list[dict] = []
    i = FVB_LEN + 2
    n = len(df)
    while i < n:
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        # ENTRY: rising regime, this bar tapped the lower band, and closed back above it
        tapped = row["Low"] <= row["lower"] * (1 + TOUCH_TOL)
        confirmed = row["Close"] > row["lower"]
        if bool(row["rising"]) and tapped and confirmed and not math.isnan(row["lower"]):
            entry = float(row["Close"])
            stop = float(row["swing_low"])
            target = float(row["prior_high"]) if not math.isnan(row["prior_high"]) else entry * 1.5
            if stop >= entry or target <= entry:   # degenerate geometry — skip
                i += 1
                continue
            # walk forward
            j = i + 1
            exit_price, bars = None, 0
            while j < n:
                b = df.iloc[j]
                bars = j - i
                if b["Low"] <= stop:                         # stop hit (both models)
                    exit_price = stop
                    break
                if exit_model == "his":
                    if b["High"] >= target:                  # target hit
                        exit_price = target
                        break
                    if bars >= MAX_HOLD:                      # time stop
                        exit_price = float(b["Close"])
                        break
                else:  # regime: hold until basis turns down
                    if not bool(b["rising"]):
                        exit_price = float(b["Close"])
                        break
                j += 1
            if exit_price is None:                           # still open at series end
                exit_price = float(df.iloc[-1]["Close"])
                bars = n - 1 - i
            ret = (exit_price - entry) / entry
            trades.append({"ret": ret, "bars": bars, "win": ret > 0})
            i = j + 1                                         # no overlapping positions
            continue
        i += 1
    return trades


def _stats(trades: list[dict]) -> dict | None:
    if not trades:
        return None
    rets = np.array([t["ret"] for t in trades])
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    gross_win = wins.sum()
    gross_loss = abs(losses.sum())
    # equity curve (sequential compounding) → max drawdown
    eq = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(eq)
    max_dd = float(((eq - peak) / peak).min()) if len(eq) else 0.0
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": float(rets.mean()),
        "total_return": float(eq[-1] - 1),
        "max_dd": max_dd,
        "avg_hold": float(np.mean([t["bars"] for t in trades])),
        "rr": (avg_win / abs(avg_loss)) if avg_loss < 0 else float("inf"),
    }


def _fmt(v, pct=False, ratio=False):
    if v == float("inf"):
        return "∞"
    if pct:
        return f"{v*100:+.1f}%"
    if ratio:
        return f"{v:.2f}"
    return f"{v:.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="")
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--exit", choices=["his", "regime"], default="his")
    ap.add_argument("--sort", choices=["pf", "expectancy", "total", "win"], default="pf")
    args = ap.parse_args()

    if args.universe:
        symbols = _load_universe()
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = ["MSFT", "NVDA", "AMD", "AAPL", "AMZN", "META", "GOOGL", "NFLX"]

    print(f"Fetching {len(symbols)} symbols (weekly, 10y)…")
    import yfinance as yf
    batch = None
    if len(symbols) > 1:
        try:
            batch = yf.download(symbols, period="10y", interval="1wk", progress=False,
                                auto_adjust=True, group_by="ticker", threads=True)
        except Exception:
            batch = None

    rows = []
    all_trades: list[dict] = []
    for sym in symbols:
        df = _weekly(sym, batch)
        if df is None:
            continue
        trades = _backtest(df, args.exit)
        st = _stats(trades)
        if st:
            st["symbol"] = sym
            rows.append(st)
            all_trades.extend(trades)

    if not rows:
        print("No results.")
        return

    key = {"pf": "profit_factor", "expectancy": "expectancy",
           "total": "total_return", "win": "win_rate"}[args.sort]
    rows.sort(key=lambda r: (r[key] if r[key] != float("inf") else 1e9), reverse=True)

    hdr = f"{'SYM':<6}{'Trades':>7}{'Win%':>7}{'PF':>7}{'AvgW':>8}{'AvgL':>8}{'Exp':>8}{'Total':>10}{'MaxDD':>8}{'Hold':>6}{'R/R':>6}"
    print(f"\n=== SMZ strategy — exit model: {args.exit.upper()} "
          f"({'swing-low stop + prior-high target' if args.exit=='his' else 'hold until regime flips red'}) ===")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['symbol']:<6}{r['trades']:>7}{r['win_rate']*100:>6.0f}%"
              f"{_fmt(r['profit_factor'], ratio=True):>7}"
              f"{_fmt(r['avg_win'], pct=True):>8}{_fmt(r['avg_loss'], pct=True):>8}"
              f"{_fmt(r['expectancy'], pct=True):>8}{_fmt(r['total_return'], pct=True):>10}"
              f"{_fmt(r['max_dd'], pct=True):>8}{r['avg_hold']:>6.0f}"
              f"{_fmt(r['rr'], ratio=True):>6}")

    # aggregate across every trade in the universe
    agg = _stats(all_trades)
    print("-" * len(hdr))
    print(f"{'ALL':<6}{agg['trades']:>7}{agg['win_rate']*100:>6.0f}%"
          f"{_fmt(agg['profit_factor'], ratio=True):>7}"
          f"{_fmt(agg['avg_win'], pct=True):>8}{_fmt(agg['avg_loss'], pct=True):>8}"
          f"{_fmt(agg['expectancy'], pct=True):>8}{'':>10}{_fmt(agg['max_dd'], pct=True):>8}"
          f"{agg['avg_hold']:>6.0f}{_fmt(agg['rr'], ratio=True):>6}")
    print(f"\nHis claim: ~65% win, ~5:1 R/R.  Measured (universe): "
          f"{agg['win_rate']*100:.0f}% win, {_fmt(agg['rr'], ratio=True)}:1 R/R, "
          f"expectancy {_fmt(agg['expectancy'], pct=True)}/trade over {agg['trades']} trades.")


if __name__ == "__main__":
    main()
