"""Shared daily-bar indicator columns.

The repo historically grew one private ``_sma`` / ``_rsi`` / ``_atr`` per scanner.
This module is the one place that derives the columns the pattern scanner
(``patterns/``) needs, so the pattern modules stay free of indicator math and
future scanners can reuse the same definitions.

Input contract: a DataFrame with Title-case ``Open, High, Low, Close, Volume``
columns — the shape ``analytics.market_data.fetch_ohlc`` / ``fetch_daily_history``
return. Output: the same frame with lowercase derived columns appended.

Derived columns
---------------
sma20, sma50, sma200   simple moving averages of Close
sma50_slope            percent change of sma50 over the last ``slope_bars`` bars
sma200_slope           percent change of sma200 over the last ``slope_bars`` bars
avg_vol_50             50-bar simple average of Volume
rvol                   Volume / avg_vol_50
atr14                  Wilder ATR (matches intraday_data's fetch_prior_day ATR14)
rsi14                  Wilder RSI (same math as intraday_data.compute_rsi_wilder,
                       but as a full Series instead of a single float)
high_52w, low_52w      rolling 252-bar max High / min Low
"""

from __future__ import annotations

import numpy as np
import pandas as pd

OHLCV = ("Open", "High", "Low", "Close", "Volume")


def sma(series: pd.Series, n: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(n, min_periods=n).mean()


def pct_slope(series: pd.Series, bars: int) -> pd.Series:
    """Percent change of a series over the last ``bars`` bars (as a fraction).

    ``+0.02`` means the MA is 2% higher than it was ``bars`` bars ago — rising.
    """
    prev = series.shift(bars)
    return (series - prev) / prev.replace(0, np.nan)


def true_range(df: pd.DataFrame) -> pd.Series:
    """True range per bar: max(H-L, |H-prevC|, |L-prevC|)."""
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr_wilder(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder-smoothed ATR."""
    return true_range(df).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI as a Series (0-100)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    # All-gain windows → avg_loss 0 → rs inf → rsi 100
    rsi = rsi.where(~(avg_loss == 0), 100.0)
    return rsi


def add_derived_columns(
    df: pd.DataFrame,
    *,
    slope_bars: int = 10,
    vol_window: int = 50,
    atr_period: int = 14,
    rsi_period: int = 14,
    year_bars: int = 252,
) -> pd.DataFrame:
    """Return a copy of ``df`` with the derived columns listed in the module docstring.

    Never raises on short history — columns are simply NaN where undefined.
    Callers decide the minimum-bar rule (the pattern scanner requires 400).
    """
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"add_derived_columns: missing columns {missing}")

    out = df.copy()
    for c in OHLCV:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)

    close, vol = out["Close"], out["Volume"]
    out["sma20"] = sma(close, 20)
    out["sma50"] = sma(close, 50)
    out["sma200"] = sma(close, 200)
    out["sma50_slope"] = pct_slope(out["sma50"], slope_bars)
    out["sma200_slope"] = pct_slope(out["sma200"], slope_bars)
    out["avg_vol_50"] = sma(vol, vol_window)
    out["rvol"] = vol / out["avg_vol_50"].replace(0, np.nan)
    out["atr14"] = atr_wilder(out, atr_period)
    out["rsi14"] = rsi_wilder(close, rsi_period)
    out["high_52w"] = out["High"].rolling(year_bars, min_periods=year_bars).max()
    out["low_52w"] = out["Low"].rolling(year_bars, min_periods=year_bars).min()
    return out
