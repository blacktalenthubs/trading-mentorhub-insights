"""Scanner service — wraps the analytics.signal_engine for the API."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Add project root to path so analytics package is importable
_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# The parent project's db.py reads DATABASE_URL to decide sqlite vs postgres.
# The API's .env sets DATABASE_URL to an async SQLAlchemy URL which is not a
# valid psycopg2 DSN.  Hide it so the parent db.py falls back to SQLite mode.
_saved_db_url = os.environ.pop("DATABASE_URL", None)

from analytics.signal_engine import ACTION_LABELS, SignalResult, action_label, scan_watchlist  # noqa: E402

# Force parent db.py into SQLite mode regardless of env
import db as _parent_db  # noqa: E402
_parent_db._USE_POSTGRES = False

# Restore so SQLAlchemy async engine keeps working
if _saved_db_url is not None:
    os.environ["DATABASE_URL"] = _saved_db_url


def run_scan(symbols: List[str]) -> List[dict]:
    """Run scanner on a list of symbols and return serializable dicts."""
    results: List[SignalResult] = scan_watchlist(symbols)
    return [_serialize(r) for r in results]


def _safe_round(v, decimals=2):
    """Round a value, returning None for None/NaN/Inf."""
    if v is None:
        return None
    try:
        f = float(v)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return round(f, decimals)
    except (TypeError, ValueError):
        return None


def _serialize(r: SignalResult) -> dict:
    return {
        "symbol": r.symbol,
        # Default origin; the scanner router overrides this for idea-sourced names.
        "source": "watchlist",
        "score": r.score,
        "grade": getattr(r, "score_label", ""),
        "action_label": action_label(r.support_status, r.score),
        "entry": _safe_round(r.entry),
        "stop": _safe_round(r.stop),
        "target_1": _safe_round(r.target_1),
        "target_2": _safe_round(r.target_2),
        "rr_ratio": _safe_round(r.rr_ratio),
        "support_status": r.support_status or "",
        "pattern": getattr(r, "pattern", ""),
        "direction": getattr(r, "direction", ""),
        "near_support": r.support_status == "AT SUPPORT",
        "close": _safe_round(getattr(r, "last_close", None)),
        "prior_day_low": _safe_round(getattr(r, "prior_low", None)),
        "ma20": _safe_round(getattr(r, "ma20", None)),
        "ma50": _safe_round(getattr(r, "ma50", None)),
        "prior_high": _safe_round(getattr(r, "prior_high", None)),
        "prior_low": _safe_round(getattr(r, "prior_low", None)),
        "nearest_support": _safe_round(getattr(r, "nearest_support", None)),
        "support_label": getattr(r, "support_label", ""),
        "distance_to_support": _safe_round(getattr(r, "distance_to_support", None)),
        "distance_pct": _safe_round(getattr(r, "distance_pct", None)),
        "reentry_stop": _safe_round(getattr(r, "reentry_stop", None)),
        "risk_per_share": _safe_round(getattr(r, "risk_per_share", None)),
        "bias": getattr(r, "bias", ""),
        "day_range": _safe_round(getattr(r, "day_range", None)),
        "volume_ratio": _safe_round(getattr(r, "volume_ratio", None)),
        "ref_day_high": _safe_round(getattr(r, "ref_day_high", None)),
        "ref_day_low": _safe_round(getattr(r, "ref_day_low", None)),
    }


# The action label meaning "at an actionable entry today" — AT SUPPORT with
# score >= 65. The single source of truth lives in signal_engine; reference it
# so the gate can't silently drift out of sync with the Today tab.
_ENTRY_ACTION_LABEL = ACTION_LABELS["AT SUPPORT"]["label"]  # "Potential Entry"


def meets_entry(result: dict) -> bool:
    """True when a serialized scan result clears Today's entry gate.

    This is the exact bar the Today tab already uses for watchlist names, so
    idea-sourced symbols (conviction / swing) surface only when genuinely at
    entry rather than just being "interesting".
    """
    return result.get("action_label") == _ENTRY_ACTION_LABEL


# ---------------------------------------------------------------------------
# Weekly Stage scanner (Stan Weinstein 30-week-MA) — Python port of the Pine
# indicator pine_scripts/visual/weekly_stage.pine (f_wk). READ-ONLY discovery:
# classify each symbol's weekly stage and bucket it (own / add / watch).
# ---------------------------------------------------------------------------

logger = logging.getLogger("scanner")

# Minimum weekly bars: 30 for the MA + the slope/context lookbacks (ma[-13]).
_WK_MIN_BARS = 35
_WK_SLOPE_THR = 0.5   # |4-week slope %| below this = flat (chop), per the Pine.

_STAGE_LABELS = {
    1: "Stage 1 · Basing",
    2: "Stage 2 · Advancing",
    3: "Stage 3 · Topping",
    4: "Stage 4 · Declining",
}


@dataclass
class WeeklyStageCandidate:
    symbol: str
    stage: int
    stage_label: str
    bucket: str           # "own" | "add" | "watch"
    ma: float             # the 30-week MA (rounded)
    slope_pct: float      # 4-week slope of the MA, %
    price: float          # latest weekly close
    dist_vs_ma_pct: float  # (price - ma) / ma * 100

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "stage": self.stage,
            "stage_label": self.stage_label,
            "bucket": self.bucket,
            "ma": _safe_round(self.ma),
            "slope_pct": _safe_round(self.slope_pct),
            "price": _safe_round(self.price),
            "dist_vs_ma_pct": _safe_round(self.dist_vs_ma_pct),
        }


def classify_weekly_stage(close) -> Optional[WeeklyStageCandidate]:
    """Port of weekly_stage.pine f_wk for a weekly close series → a candidate, or
    None when the series is too short or the name doesn't belong in a bucket.

    ``close`` is a pandas Series (or anything with a 30-window rolling mean and
    positional .iloc indexing). The symbol is filled in by the caller.
    """
    import pandas as pd

    s = pd.Series(close).dropna()
    if len(s) < _WK_MIN_BARS:
        return None

    ma = s.rolling(30).mean()
    if pd.isna(ma.iloc[-1]) or pd.isna(ma.iloc[-9]):
        return None

    ma_now = float(ma.iloc[-1])
    ma_4ago = float(ma.iloc[-5])   # 4 weeks ago
    ma_8ago = float(ma.iloc[-9])   # 8 weeks ago
    ma_12ago = float(ma.iloc[-13])  # 12 weeks ago
    if ma_now == 0 or ma_4ago == 0 or ma_8ago == 0:
        return None

    price = float(s.iloc[-1])
    slope = (ma_now - ma_4ago) / ma_4ago * 100.0
    slope_prior = (ma_4ago - ma_8ago) / ma_8ago * 100.0

    rising = slope > _WK_SLOPE_THR
    falling = slope < -_WK_SLOPE_THR
    above = price > ma_now

    if above and rising:
        stage = 2
    elif (not above) and falling:
        stage = 4
    elif ma_now > ma_12ago:
        stage = 3
    else:
        stage = 1

    dist = (price - ma_now) / ma_now * 100.0

    # Bucket — own (confirmed Stage 2), add (Stage 2 pullback to the rising MA),
    # watch (basing/declining but turning up near the MA). Everything else excluded.
    bucket: Optional[str] = None
    if stage == 2:
        bucket = "add" if 0.0 <= dist <= 3.0 else "own"
    elif stage in (1, 4) and -8.0 <= dist <= 8.0 and slope > slope_prior:
        bucket = "watch"

    if bucket is None:
        return None

    return WeeklyStageCandidate(
        symbol="",
        stage=stage,
        stage_label=_STAGE_LABELS.get(stage, f"Stage {stage}"),
        bucket=bucket,
        ma=ma_now,
        slope_pct=slope,
        price=price,
        dist_vs_ma_pct=dist,
    )


# Sort buckets: watch first (most improving slope), then own, then add.
_BUCKET_ORDER = {"watch": 0, "own": 1, "add": 2}


def gather_weekly_stage(universe) -> List[WeeklyStageCandidate]:
    """Fetch ~2y of WEEKLY bars per symbol, classify the 30-week-MA stage, and
    bucket. One bad symbol must NOT kill the snapshot (per-symbol try/except).

    ``universe`` is a list of analytics.screener.UniverseRow (only .symbol used).
    """
    from analytics.market_data import fetch_ohlc  # lazy, read-only

    cands: List[WeeklyStageCandidate] = []
    for u in universe:
        sym = getattr(u, "symbol", u)
        try:
            df = fetch_ohlc(sym, period="2y", interval="1wk")
            if df is None or df.empty or "Close" not in df.columns:
                continue
            c = classify_weekly_stage(df["Close"])
            if c is None:
                continue
            c.symbol = sym
            cands.append(c)
        except Exception:  # one bad symbol must not kill the snapshot
            logger.debug("weekly_stage: skipped %s", sym, exc_info=True)

    cands.sort(key=lambda c: (
        _BUCKET_ORDER.get(c.bucket, 9),
        -c.slope_pct if c.bucket == "watch" else 0.0,
    ))
    return cands
