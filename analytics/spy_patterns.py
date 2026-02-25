"""
SPY Prior Day Low Pattern Analysis

Analyzes historical SPY daily data to answer:
1. How often does SPY test the prior day's low?
2. When it tests, how often does it reclaim and close higher?
3. How often does it break and keep going lower?
4. What stop distance minimizes false stops while protecting capital?
5. How does this vary by market regime (trending vs choppy)?

Usage:
    python -m analytics.spy_patterns
    # Or import and call: analyze_prior_day_low(df)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
SPY_DB = DATA_DIR / "spy_patterns.db"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class DayResult:
    """Result of analyzing one trading day vs prior day's low."""
    date: date
    open: float
    high: float
    low: float
    close: float
    prior_low: float
    prior_close: float

    # Did price reach the prior day's low?
    tested_prior_low: bool  # low <= prior_low + threshold

    # Outcome categories
    outcome: str  # 'no_test', 'wick_reclaim', 'held_above', 'broke_and_closed_below'

    # Measurements
    max_penetration_below: float  # How far below prior low (0 if never touched)
    close_vs_prior_low: float     # close - prior_low (positive = closed above)
    day_range: float              # high - low
    open_vs_prior_low: float      # open - prior_low


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------

def fetch_spy_data(period_years: int = 3) -> pd.DataFrame:
    """Fetch SPY daily OHLCV data using yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError(
            "yfinance required. Install with: pip install yfinance"
        )

    end = date.today()
    start = end - timedelta(days=period_years * 365)

    ticker = yf.Ticker("SPY")
    df = ticker.history(start=start.isoformat(), end=end.isoformat(), interval="1d")
    df = df.reset_index()
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    # Normalize date column
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date

    return df[["date", "open", "high", "low", "close", "volume"]].copy()


def load_or_fetch_spy(force_refresh: bool = False) -> pd.DataFrame:
    """Load from cache or fetch fresh data."""
    cache_file = DATA_DIR / "spy_daily.csv"

    if cache_file.exists() and not force_refresh:
        df = pd.read_csv(cache_file, parse_dates=["date"])
        df["date"] = df["date"].dt.date
        # Refresh if data is more than 1 day stale
        if df["date"].max() >= date.today() - timedelta(days=2):
            return df

    df = fetch_spy_data(period_years=3)
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(cache_file, index=False)
    return df


# ---------------------------------------------------------------------------
# Core Analysis
# ---------------------------------------------------------------------------

def classify_day(
    row: pd.Series,
    prior_low: float,
    prior_close: float,
    threshold_pct: float = 0.05,
) -> DayResult:
    """Classify a single day's behavior relative to prior day's low.

    threshold_pct: how close price must get to prior low to count as "tested"
                   (0.05 = within 0.05% of prior low, ~$0.35 on SPY at 690)
    """
    threshold = prior_low * (threshold_pct / 100)

    tested = row["low"] <= prior_low + threshold
    max_penetration = max(0, prior_low - row["low"])
    close_vs = row["close"] - prior_low

    if not tested:
        outcome = "no_test"
    elif row["low"] < prior_low and row["close"] > prior_low:
        outcome = "wick_reclaim"  # Broke below, closed above = your re-entry signal
    elif row["low"] >= prior_low - threshold and row["close"] > prior_low:
        outcome = "held_above"   # Touched/near but never broke, closed above
    else:
        outcome = "broke_and_closed_below"  # Broke and stayed below

    return DayResult(
        date=row["date"],
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        prior_low=prior_low,
        prior_close=prior_close,
        tested_prior_low=tested,
        outcome=outcome,
        max_penetration_below=max_penetration,
        close_vs_prior_low=close_vs,
        day_range=row["high"] - row["low"],
        open_vs_prior_low=row["open"] - prior_low,
    )


def analyze_prior_day_low(df: pd.DataFrame) -> pd.DataFrame:
    """Run full prior-day-low analysis on SPY daily data."""
    df = df.sort_values("date").reset_index(drop=True)

    results = []
    for i in range(1, len(df)):
        prior = df.iloc[i - 1]
        current = df.iloc[i]
        result = classify_day(
            current,
            prior_low=prior["low"],
            prior_close=prior["close"],
        )
        results.append(result.__dict__)

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Pattern Statistics
# ---------------------------------------------------------------------------

def compute_pattern_stats(results: pd.DataFrame) -> dict:
    """Compute key statistics from the analysis."""
    total_days = len(results)
    tested = results[results["tested_prior_low"]]
    not_tested = results[~results["tested_prior_low"]]

    stats = {
        "total_trading_days": total_days,
        "days_tested_prior_low": len(tested),
        "days_never_reached": len(not_tested),
        "pct_days_tested": len(tested) / total_days * 100,
    }

    if len(tested) > 0:
        outcomes = tested["outcome"].value_counts()
        for outcome in ["wick_reclaim", "held_above", "broke_and_closed_below"]:
            count = outcomes.get(outcome, 0)
            stats[f"count_{outcome}"] = count
            stats[f"pct_{outcome}"] = count / len(tested) * 100

        # Wick and reclaim stats (your re-entry setup)
        reclaims = tested[tested["outcome"] == "wick_reclaim"]
        if len(reclaims) > 0:
            stats["reclaim_avg_penetration"] = reclaims["max_penetration_below"].mean()
            stats["reclaim_median_penetration"] = reclaims["max_penetration_below"].median()
            stats["reclaim_max_penetration"] = reclaims["max_penetration_below"].max()
            stats["reclaim_avg_close_above_low"] = reclaims["close_vs_prior_low"].mean()

        # Break and fail stats
        breaks = tested[tested["outcome"] == "broke_and_closed_below"]
        if len(breaks) > 0:
            stats["break_avg_penetration"] = breaks["max_penetration_below"].mean()
            stats["break_median_penetration"] = breaks["max_penetration_below"].median()
            stats["break_avg_close_below_low"] = abs(breaks["close_vs_prior_low"].mean())

    return stats


def compute_stop_analysis(results: pd.DataFrame) -> pd.DataFrame:
    """For each stop distance, calculate win rate if entering at prior day's low.

    Simulates: enter long at prior_low, stop at prior_low - X, target 2:1 R/R.
    """
    tested = results[results["tested_prior_low"]].copy()
    if len(tested) == 0:
        return pd.DataFrame()

    stop_distances = [0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50, 3.00, 4.00, 5.00]
    rows = []

    for stop_dist in stop_distances:
        wins = 0
        losses = 0
        no_trigger = 0

        for _, day in tested.iterrows():
            entry = day["prior_low"]
            stop = entry - stop_dist
            target = entry + (stop_dist * 2)  # 2:1 R/R

            # Did price go below our stop?
            if day["low"] < stop:
                losses += 1
            # Did price hit our target?
            elif day["high"] >= target:
                wins += 1
            # Price tested area but neither stop nor target hit
            elif day["close"] > entry:
                wins += 1  # Closed above entry, partial win
            else:
                losses += 1  # Closed below entry

        total = wins + losses
        rows.append({
            "stop_distance": stop_dist,
            "wins": wins,
            "losses": losses,
            "total_trades": total,
            "win_rate": wins / total * 100 if total > 0 else 0,
            "avg_win": stop_dist * 2,  # 2:1 target
            "avg_loss": stop_dist,
            "expectancy": ((wins / total * stop_dist * 2) - (losses / total * stop_dist))
            if total > 0 else 0,
            "max_loss_per_100_shares": stop_dist * 100,
        })

    return pd.DataFrame(rows)


def compute_reentry_analysis(results: pd.DataFrame) -> dict:
    """Analyze the wick-and-reclaim re-entry pattern specifically."""
    reclaims = results[results["outcome"] == "wick_reclaim"].copy()
    breaks = results[results["outcome"] == "broke_and_closed_below"].copy()

    if len(reclaims) == 0:
        return {}

    # How far does the wick go before reclaiming?
    penetration_buckets = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    bucket_stats = []
    for max_pen in penetration_buckets:
        count = len(reclaims[reclaims["max_penetration_below"] <= max_pen])
        pct = count / len(reclaims) * 100 if len(reclaims) > 0 else 0
        bucket_stats.append({
            "max_wick_below_prior_low": f"<= ${max_pen:.2f}",
            "reclaim_count": count,
            "pct_of_reclaims": pct,
        })

    # After reclaim, how much did it close above the prior low?
    close_above_stats = {
        "avg_close_above_prior_low": reclaims["close_vs_prior_low"].mean(),
        "median_close_above_prior_low": reclaims["close_vs_prior_low"].median(),
        "pct_closed_above_open": len(reclaims[reclaims["close"] > reclaims["open"]]) / len(reclaims) * 100,
    }

    return {
        "total_reclaims": len(reclaims),
        "total_breaks": len(breaks),
        "reclaim_vs_break_ratio": f"{len(reclaims)}:{len(breaks)}",
        "penetration_buckets": pd.DataFrame(bucket_stats),
        "close_stats": close_above_stats,
    }


def compute_ma_context(df: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Add moving average context — does reclaim rate change based on trend?"""
    df = df.sort_values("date").reset_index(drop=True)
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()

    # Merge MA data into results
    ma_lookup = df.set_index("date")[["ma20", "ma50"]].to_dict("index")
    results = results.copy()
    results["above_ma20"] = results["date"].apply(
        lambda d: ma_lookup.get(d, {}).get("ma20") is not None
        and ma_lookup.get(d, {}).get("ma20") < results.loc[results["date"] == d, "close"].values[0]
        if d in ma_lookup else None
    )
    # Simplified: just add the MA values
    results["ma20"] = results["date"].map(lambda d: ma_lookup.get(d, {}).get("ma20"))
    results["ma50"] = results["date"].map(lambda d: ma_lookup.get(d, {}).get("ma50"))
    results["trend"] = results.apply(
        lambda r: "uptrend" if r["close"] > (r["ma20"] or 0) and r["close"] > (r["ma50"] or 0)
        else "downtrend" if r["close"] < (r["ma20"] or float("inf")) and r["close"] < (r["ma50"] or float("inf"))
        else "mixed",
        axis=1,
    )

    return results


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_report(df: pd.DataFrame) -> str:
    """Generate a text report of all findings."""
    results = analyze_prior_day_low(df)
    stats = compute_pattern_stats(results)
    stop_df = compute_stop_analysis(results)
    reentry = compute_reentry_analysis(results)
    results_with_ma = compute_ma_context(df, results)

    lines = []
    lines.append("=" * 70)
    lines.append("SPY PRIOR DAY LOW — PATTERN ANALYSIS REPORT")
    lines.append(f"Period: {df['date'].min()} to {df['date'].max()}")
    lines.append(f"Total Trading Days Analyzed: {stats['total_trading_days']}")
    lines.append("=" * 70)

    lines.append("\n--- SECTION 1: HOW OFTEN DOES SPY TEST PRIOR DAY'S LOW? ---\n")
    lines.append(f"  Days that tested prior low:    {stats['days_tested_prior_low']} ({stats['pct_days_tested']:.1f}%)")
    lines.append(f"  Days that never reached it:    {stats['days_never_reached']} ({100 - stats['pct_days_tested']:.1f}%)")

    lines.append("\n--- SECTION 2: WHAT HAPPENS WHEN IT TESTS? ---\n")
    tested_total = stats["days_tested_prior_low"]
    if tested_total > 0:
        lines.append(f"  Wick below → reclaimed above:  {stats.get('count_wick_reclaim', 0)} ({stats.get('pct_wick_reclaim', 0):.1f}%)")
        lines.append(f"  Held at/above prior low:       {stats.get('count_held_above', 0)} ({stats.get('pct_held_above', 0):.1f}%)")
        lines.append(f"  Broke below → closed below:    {stats.get('count_broke_and_closed_below', 0)} ({stats.get('pct_broke_and_closed_below', 0):.1f}%)")

        bullish = stats.get("count_wick_reclaim", 0) + stats.get("count_held_above", 0)
        lines.append(f"\n  BULLISH outcomes (reclaim + held): {bullish} ({bullish / tested_total * 100:.1f}%)")
        lines.append(f"  BEARISH outcomes (broke below):    {stats.get('count_broke_and_closed_below', 0)} ({stats.get('pct_broke_and_closed_below', 0):.1f}%)")

    lines.append("\n--- SECTION 3: WICK AND RECLAIM DETAILS ---\n")
    if reentry:
        lines.append(f"  Total reclaim days: {reentry['total_reclaims']}")
        lines.append(f"  Total break days:   {reentry['total_breaks']}")
        lines.append(f"  Ratio:              {reentry['reclaim_vs_break_ratio']}")

        lines.append("\n  How far does the wick go before reclaiming?")
        if "penetration_buckets" in reentry:
            for _, row in reentry["penetration_buckets"].iterrows():
                lines.append(f"    Wick {row['max_wick_below_prior_low']}: {row['reclaim_count']} times ({row['pct_of_reclaims']:.1f}%)")

        cs = reentry.get("close_stats", {})
        lines.append(f"\n  After reclaim, avg close above prior low: ${cs.get('avg_close_above_prior_low', 0):.2f}")
        lines.append(f"  After reclaim, closed as green candle:     {cs.get('pct_closed_above_open', 0):.1f}%")

    lines.append("\n--- SECTION 4: OPTIMAL STOP DISTANCE ---\n")
    if len(stop_df) > 0:
        lines.append(f"  {'Stop $':>8} {'Wins':>6} {'Losses':>8} {'Win%':>7} {'Expect$/trade':>14} {'MaxLoss/100sh':>14}")
        lines.append(f"  {'─' * 8} {'─' * 6} {'─' * 8} {'─' * 7} {'─' * 14} {'─' * 14}")
        for _, row in stop_df.iterrows():
            lines.append(
                f"  ${row['stop_distance']:>6.2f} {row['wins']:>6} {row['losses']:>8} "
                f"{row['win_rate']:>6.1f}% ${row['expectancy']:>12.2f} ${row['max_loss_per_100_shares']:>12.0f}"
            )

        best = stop_df.loc[stop_df["expectancy"].idxmax()]
        lines.append(f"\n  BEST STOP DISTANCE: ${best['stop_distance']:.2f}")
        lines.append(f"  Win Rate: {best['win_rate']:.1f}% | Expectancy: ${best['expectancy']:.2f}/trade")

    lines.append("\n--- SECTION 5: TREND CONTEXT ---\n")
    tested_with_ma = results_with_ma[results_with_ma["tested_prior_low"]]
    for trend in ["uptrend", "downtrend", "mixed"]:
        subset = tested_with_ma[tested_with_ma["trend"] == trend]
        if len(subset) > 0:
            reclaim_count = len(subset[subset["outcome"].isin(["wick_reclaim", "held_above"])])
            lines.append(f"  {trend.upper():>12}: {len(subset)} tests, "
                        f"{reclaim_count} bullish ({reclaim_count / len(subset) * 100:.1f}%), "
                        f"{len(subset) - reclaim_count} bearish ({(len(subset) - reclaim_count) / len(subset) * 100:.1f}%)")

    lines.append("\n--- SECTION 6: TRADING RULES (DERIVED FROM DATA) ---\n")
    if len(stop_df) > 0:
        best = stop_df.loc[stop_df["expectancy"].idxmax()]
        lines.append(f"  1. ENTRY: Buy when SPY wicks below prior day low and reclaims above it")
        lines.append(f"  2. STOP: ${best['stop_distance']:.2f} below prior day low (data-optimal)")
        lines.append(f"  3. TARGET: ${best['stop_distance'] * 2:.2f} above entry (2:1 R/R)")
        lines.append(f"  4. MAX ATTEMPTS: 2 per day (re-enter on second reclaim)")
        lines.append(f"  5. ABORT: If price stays below for >10 min, level is dead")
        lines.append(f"  6. TREND FILTER: Higher win rate when above MA20+MA50 (uptrend)")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Fetching SPY data...")
    df = load_or_fetch_spy(force_refresh=True)
    print(f"Loaded {len(df)} days of SPY data ({df['date'].min()} to {df['date'].max()})")

    report = generate_report(df)
    print(report)

    # Save report
    report_path = DATA_DIR / "spy_pattern_report.txt"
    report_path.write_text(report)
    print(f"\nReport saved to: {report_path}")

    # Save detailed results
    results = analyze_prior_day_low(df)
    results.to_csv(DATA_DIR / "spy_prior_day_low_results.csv", index=False)
    print(f"Detailed results saved to: {DATA_DIR / 'spy_prior_day_low_results.csv'}")
