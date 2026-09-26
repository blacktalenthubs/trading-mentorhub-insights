"""Derived columns for the pattern scanner. There's no central indicator layer in the repo
(each scanner rolls its own), so this is the shared one for `patterns/` — the detectors read
these columns and never compute their own. Reuses support_signals._rsi (the project RSI)."""
from __future__ import annotations

import pandas as pd

from patterns.config import CONFIG, PatternConfig


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    try:
        from analytics.support_signals import _rsi as _proj_rsi   # the project's Wilder RSI
        return _proj_rsi(close, n)
    except Exception:
        d = close.diff()
        up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
        dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
        return 100 - 100 / (1 + up / dn.replace(0, 1e-9))


def add_indicators(df: pd.DataFrame, cfg: PatternConfig = CONFIG) -> pd.DataFrame:
    """Return a copy of `df` with the scanner's derived columns. Assumes Open/High/Low/
    Close/Volume (the project's fetch_ohlc shape). Slopes are % change of the MA over the
    last `slope_lookback` bars (a rising vs falling MA test)."""
    out = df.copy()
    c, v = out["Close"], out["Volume"]
    out["sma20"] = c.rolling(20).mean()
    out["sma50"] = c.rolling(50).mean()
    out["sma200"] = c.rolling(200).mean()
    k = cfg.slope_lookback
    out["sma50_slope"] = (out["sma50"] - out["sma50"].shift(k)) / out["sma50"].shift(k) * 100.0
    out["sma200_slope"] = (out["sma200"] - out["sma200"].shift(k)) / out["sma200"].shift(k) * 100.0
    out["avg_vol_50"] = v.rolling(cfg.avg_vol_window).mean()
    out["rvol"] = v / out["avg_vol_50"]
    out["atr14"] = _atr(out, cfg.atr_len)
    out["rsi14"] = _rsi(c, cfg.rsi_len)
    # 52-week window (~252 trading days). min_periods so early bars still get a value.
    out["hi_52w"] = out["High"].rolling(252, min_periods=60).max()
    out["lo_52w"] = out["Low"].rolling(252, min_periods=60).min()
    return out
