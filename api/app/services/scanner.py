"""Scanner service — wraps the analytics.signal_engine for the API."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

# Add project root to path so analytics package is importable
_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# The parent project's db.py reads DATABASE_URL to decide sqlite vs postgres.
# The API's .env sets DATABASE_URL to an async SQLAlchemy URL which is not a
# valid psycopg2 DSN.  Hide it so the parent db.py falls back to SQLite mode.
_saved_db_url = os.environ.pop("DATABASE_URL", None)

from analytics.signal_engine import SignalResult, action_label, scan_watchlist  # noqa: E402

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
