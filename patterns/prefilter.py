"""Pre-filter applied to every symbol before any pattern logic runs.

Every rule is a liquidity or trend gate. The scanner logs how many names each
gate removes so the funnel is visible. Order matters for those counts: a name
is charged to the FIRST gate it fails.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from patterns.config import PrefilterConfig

FILTER_ORDER = (
    "liquidity",        # close > min_close and avg_vol_50 > min_avg_vol_50
    "above_sma200",     # close > sma200
    "sma200_rising",    # sma200_slope > 0
    "near_52w_high",    # close within max_pct_below_52w_high of the 52-week high
    "off_52w_low",      # close at least min_pct_above_52w_low above the 52-week low
)


def prefilter(df: pd.DataFrame, cfg: PrefilterConfig) -> Optional[str]:
    """Return the name of the first failing gate, or ``None`` if the symbol passes.

    Expects the derived columns from ``analytics.indicators.add_derived_columns``.
    NaN in any input counts as a failure of that gate (never crashes).
    """
    last = df.iloc[-1]
    close = float(last["Close"])
    avg_vol = last.get("avg_vol_50")
    sma200 = last.get("sma200")
    slope200 = last.get("sma200_slope")
    hi52 = last.get("high_52w")
    lo52 = last.get("low_52w")

    if pd.isna(avg_vol) or close <= cfg.min_close or float(avg_vol) <= cfg.min_avg_vol_50:
        return "liquidity"
    if cfg.require_close_above_sma200 and (pd.isna(sma200) or close <= float(sma200)):
        return "above_sma200"
    if cfg.require_sma200_rising and (pd.isna(slope200) or float(slope200) <= 0):
        return "sma200_rising"
    if pd.isna(hi52) or close < float(hi52) * (1.0 - cfg.max_pct_below_52w_high):
        return "near_52w_high"
    if pd.isna(lo52) or close < float(lo52) * (1.0 + cfg.min_pct_above_52w_low):
        return "off_52w_low"
    return None


def empty_funnel() -> dict[str, int]:
    """A zeroed funnel counter keyed by gate name (plus the pass count)."""
    counts = {name: 0 for name in FILTER_ORDER}
    counts["passed"] = 0
    return counts
