#!/usr/bin/env python3
"""
Prior-Quarter (PQ) pattern backtest — does a DAILY-CLOSE event on the prior
completed quarter's High / Close / Low have swing edge, across a wide universe?

Patterns tested (all LONG, daily-close-gated — the founder's rule):
  • PQ Low reclaim   — daily close crosses back ABOVE the prior-quarter LOW   (spring / bottom)
  • PQ Close reclaim — daily close crosses back ABOVE the prior-quarter CLOSE (value acceptance)
  • PQ High break    — daily close crosses ABOVE the prior-quarter HIGH        (leader breakout)

Trade sim (uniform, honest):
  entry  = signal-day close
  stop   = a later daily CLOSE back below the level  → invalidation (founder rule)
  target = the next PQ level up (Low→Close, Close→High, High→High+range)
  timeout= ~1 quarter (63 trading days)
  exit at whichever comes first; return = (exit-entry)/entry.

Reports per-pattern: N, win%, avg/median return, avg R (level as stop), avg hold.
Prints limitations honestly. Uses yfinance (works locally).
"""
import sys
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    sys.exit("pip install yfinance")

UNIVERSE = [
    # megacap / semi / AI leaders
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AMD","AVGO","MU","ORCL","QCOM",
    "INTC","TSM","ASML","LRCX","KLAC","MRVL","ON","MCHP","ARM","SMCI",
    # software
    "CRM","ADBE","NFLX","SNOW","CRWD","PLTR","PANW","NET","DDOG","MDB","SHOP","UBER","ABNB",
    # energy / nuclear / infra
    "CEG","NRG","VRT","ETN","POWL","GEV","SMR","OKLO","BWXT",
    # high-beta / turnaround
    "COIN","HOOD","SOFI","RIVN","ROKU","DKNG","AFRM","U",
    # indices
    "SPY","QQQ",
]

YEARS = 5
MAX_HOLD = 189         # up to ~3 quarters — bottom bounces run for months (INOD/BTC)
STOP_BUFFER = 0.015    # exit only on a daily close this far BELOW the level (not the exact tick)


def prior_quarter_levels(daily: pd.DataFrame) -> pd.DataFrame:
    """For each daily bar, attach the prior COMPLETED quarter's high/close/low.
    No lookahead: each bar uses its OWN quarter's PRIOR quarter (always completed)."""
    q = daily.resample("Q").agg(high=("High", "max"), low=("Low", "min"), close=("Close", "last"))
    q.index = q.index.to_period("Q")
    q_prev = q.shift(1)                     # prior quarter's values, indexed by quarter period
    mh, mc, ml = q_prev["high"].to_dict(), q_prev["close"].to_dict(), q_prev["low"].to_dict()
    qp = daily.index.to_period("Q")
    out = daily.copy()
    out["pqh"] = [mh.get(p, np.nan) for p in qp]
    out["pqc"] = [mc.get(p, np.nan) for p in qp]
    out["pql"] = [ml.get(p, np.nan) for p in qp]
    return out


def simulate(df: pd.DataFrame, level_col: str, target_fn, trend_only: bool = False):
    """Yield (return_pct, R, hold_days, won) for each daily-close cross ABOVE the level.
    trend_only=True: take the entry ONLY when price is above its 200-day SMA (real uptrend)."""
    c = df["Close"].values
    h = df["High"].values
    lv = df[level_col].values
    sma200 = df["Close"].rolling(200).mean().values
    n = len(df)
    trades = []
    i = 1
    while i < n - 1:
        if np.isnan(lv[i]) or np.isnan(lv[i - 1]):
            i += 1
            continue
        # daily-close cross UP through the level
        if c[i - 1] <= lv[i - 1] and c[i] > lv[i] and (not trend_only or (not np.isnan(sma200[i]) and c[i] > sma200[i])):
            entry = c[i]
            level = lv[i]
            stop_lv = level * (1 - STOP_BUFFER)            # buffered stop, not the exact tick
            tgt = target_fn(df, i)
            risk = max(entry - stop_lv, entry * 0.002)
            exit_px, hold = None, 0
            for j in range(i + 1, min(i + 1 + MAX_HOLD, n)):
                if not np.isnan(tgt) and h[j] >= tgt:      # target hit intrabar
                    exit_px, hold = tgt, j - i
                    break
                if c[j] < stop_lv:                          # daily close BELOW the buffered level → stop
                    exit_px, hold = c[j], j - i
                    break
            if exit_px is None:                             # timeout
                jj = min(i + MAX_HOLD, n - 1)
                exit_px, hold = c[jj], jj - i
            ret = (exit_px - entry) / entry
            R = (exit_px - entry) / risk
            trades.append((ret, R, hold, ret > 0))
            i = i + hold + 1                                # no overlapping trades on same level
        else:
            i += 1
    return trades


def tgt_low(df, i):    # PQ Low bounce → aim for the WHOLE range (PQ High), the real target (INOD 34→125)
    return df["pqh"].values[i]
def tgt_close(df, i):  # PQ Close reclaim → aim for PQ High
    return df["pqh"].values[i]
def tgt_high(df, i):   # PQ High break → measured move (PQ High + 0.5*PQ range)
    v = df.iloc[i]
    return v["pqh"] + 0.5 * (v["pqh"] - v["pql"])


def summarize(name, trades):
    if not trades:
        print(f"  {name:18s}  N=0")
        return None
    arr = np.array([[t[0], t[1], t[2], t[3]] for t in trades], float)
    n = len(arr)
    win = arr[:, 3].mean() * 100
    avg = arr[:, 0].mean() * 100
    wins = arr[arr[:, 3] == 1, 0]
    losses = arr[arr[:, 3] == 0, 0]
    avgW = wins.mean() * 100 if len(wins) else 0.0
    avgL = losses.mean() * 100 if len(losses) else 0.0
    rr = abs(avgW / avgL) if avgL else float("inf")
    hold = arr[:, 2].mean()
    print(f"  {name:18s}  N={n:4d}  win={win:5.1f}%  avg={avg:+6.2f}%  avgWIN={avgW:+6.1f}%  avgLOSS={avgL:+6.1f}%  R:R={rr:4.1f}  hold={hold:5.1f}d")
    return (n, win, avg, avgW, avgL, hold)


def main():
    print(f"Downloading {len(UNIVERSE)} symbols, {YEARS}y daily …")
    data = yf.download(UNIVERSE, period=f"{YEARS}y", interval="1d",
                       auto_adjust=True, progress=False, group_by="ticker")
    raw = {"PQ Low reclaim": [], "PQ Close reclaim": [], "PQ High break": []}
    trend = {"PQ Low reclaim": [], "PQ Close reclaim": [], "PQ High break": []}
    n_syms = 0
    for sym in UNIVERSE:
        try:
            d = data[sym].dropna()
        except Exception:
            continue
        if len(d) < 300:
            continue
        d = prior_quarter_levels(d)
        n_syms += 1
        raw["PQ Low reclaim"]     += simulate(d, "pql", tgt_low)
        raw["PQ Close reclaim"]   += simulate(d, "pqc", tgt_close)
        raw["PQ High break"]      += simulate(d, "pqh", tgt_high)
        trend["PQ Low reclaim"]   += simulate(d, "pql", tgt_low,   trend_only=True)
        trend["PQ Close reclaim"] += simulate(d, "pqc", tgt_close, trend_only=True)
        trend["PQ High break"]    += simulate(d, "pqh", tgt_high,  trend_only=True)

    print(f"\n=== PQ pattern edge — {n_syms} symbols, {YEARS}y, daily-close-gated (stop buffer {STOP_BUFFER*100:.1f}%) ===")
    print(f"(entry=signal close · stop=daily close below buffered level · target=next PQ level · timeout {MAX_HOLD}d)")
    for tag, buckets in (("ALL crosses", raw), ("UPTREND only (price > 200-day)", trend)):
        print(f"\n-- {tag} --")
        all_t = []
        for name, tr in buckets.items():
            summarize(name, tr)
            all_t += tr
        summarize("ALL", all_t)
    print("\nCaveats: survivorship (current universe, not point-in-time); auto-adjusted prices;")
    print("no slippage/fees; overlapping-trade guard is per-pattern; a coin-flip long book in a")
    print("5y bull tape runs ~55% — judge each pattern vs that baseline, not vs 50%.")


if __name__ == "__main__":
    main()
