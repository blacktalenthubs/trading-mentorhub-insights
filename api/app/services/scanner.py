"""Scanner service — wraps the analytics.signal_engine for the API."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

# Add project root to path so analytics package is importable
_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from analytics.signal_engine import SignalResult, action_label, scan_watchlist  # noqa: E402


def run_scan(symbols: List[str]) -> List[dict]:
    """Run scanner on a list of symbols and return serializable dicts."""
    results: List[SignalResult] = scan_watchlist(symbols)
    return [_serialize(r) for r in results]


def _serialize(r: SignalResult) -> dict:
    return {
        "symbol": r.symbol,
        "score": r.score,
        "grade": r.score_label,
        "action_label": action_label(r.support_status, r.score),
        "entry": round(r.entry, 2),
        "stop": round(r.stop, 2),
        "target_1": round(r.target_1, 2),
        "target_2": round(r.target_2, 2),
        "rr_ratio": round(r.rr_ratio, 2),
        "support_status": r.support_status,
        "pattern": r.pattern,
        "direction": r.direction,
        "near_support": r.support_status == "AT SUPPORT",
        "close": round(r.last_close, 2),
        "prior_day_low": round(r.prior_low, 2),
        "ma20": round(r.ma20, 2) if r.ma20 else None,
        "ma50": round(r.ma50, 2) if r.ma50 else None,
        "prior_high": round(r.prior_high, 2),
        "prior_low": round(r.prior_low, 2),
        "nearest_support": round(r.nearest_support, 2),
        "support_label": r.support_label,
        "distance_to_support": round(r.distance_to_support, 2),
        "distance_pct": round(r.distance_pct, 2),
        "reentry_stop": round(r.reentry_stop, 2),
        "risk_per_share": round(r.risk_per_share, 2),
        "bias": r.bias,
        "day_range": round(r.day_range, 2),
        "volume_ratio": round(r.volume_ratio, 2),
    }
