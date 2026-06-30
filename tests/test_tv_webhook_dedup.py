"""Tests for spec 67 — entry + time dedup in api/app/routers/tv_webhook.py.

The gate: a day-trade / MA re-fire on the same symbol within the cooldown, or at
a worse (higher-for-long) entry than already alerted this session, collapses to
the first/best entry. Weekly/monthly LEVEL types are exempt — they always fire.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.tv_webhook import (  # noqa: E402
    _check_entry_time_dedup,
    _entry_dedup_state,
    _is_entry_dedupable,
    _record_entry_time_fire,
)

S = "2026-06-29"


@pytest.fixture(autouse=True)
def _clear_state():
    _entry_dedup_state.clear()
    yield
    _entry_dedup_state.clear()


def _backdate(symbol: str, direction: str, minutes: float) -> None:
    """Age the last-fire timestamp to simulate elapsed time."""
    _entry_dedup_state[(symbol, direction.upper())]["last"] = (
        datetime.utcnow() - timedelta(minutes=minutes)
    )


def _fire(symbol, direction, entry, atype, elapsed=None):
    """Run the gate; if it passes, record the fire (mirrors _route_alert)."""
    if elapsed is not None:
        _backdate(symbol, direction, elapsed)
    res = _check_entry_time_dedup(symbol, direction, entry, atype, S)
    if res is None:
        _record_entry_time_fire(symbol, direction, entry, atype, S)
    return res


# ── scope: what is / isn't dedupable ──────────────────────────────────


def test_day_trade_and_ma_are_dedupable():
    assert _is_entry_dedupable("tv_rc_4h_hrec")
    assert _is_entry_dedupable("tv_rc_daily_long")
    assert _is_entry_dedupable("tv_reclaim_long")
    assert _is_entry_dedupable("tv_ma_bounce_long_v3_ema21")  # MA included
    assert _is_entry_dedupable("tv_ma_bounce_long_v3_ema200")


def test_level_and_swing_types_exempt():
    for t in ("tv_weekly_rc", "tv_monthly_rc", "tv_cml_held", "tv_pml_held",
              "tv_staged_pwl_held", "tv_monthly_box", "tv_mobo_rch",
              "tv_rsi_oversold", "tv_rsi_70", "tv_swing_rsi_30"):
        assert not _is_entry_dedupable(t), t


# ── the gate behaviour ────────────────────────────────────────────────


def test_first_fire_passes():
    assert _fire("UCTT", "BUY", 119.77, "tv_rc_4h_hrec") is None


def test_within_cooldown_dropped():
    _fire("UCTT", "BUY", 119.77, "tv_rc_4h_hrec")
    res = _fire("UCTT", "BUY", 120.82, "tv_reclaim_long", elapsed=9)
    assert res and res["reason"] == "dedup_cooldown"
    assert res["anchor"] == 119.77


def test_after_cooldown_lower_entry_fires():
    _fire("UCTT", "BUY", 119.77, "tv_rc_4h_hrec")
    # 54 min later AND a lower entry → a genuine better re-entry
    assert _fire("UCTT", "BUY", 116.34, "tv_rc_4h_long", elapsed=54) is None


def test_after_cooldown_higher_entry_is_chase():
    _fire("AMD", "BUY", 525.11, "tv_rc_daily_hrec")
    res = _fire("AMD", "BUY", 531.21, "tv_ma_bounce_long_v3_ema8", elapsed=40)
    assert res and res["reason"] == "dedup_chase"
    assert res["anchor"] == 525.11


def test_alab_three_at_same_instant_collapse_to_one():
    """ALAB fired 3 longs at 9:35:00-05 — only the first should pass."""
    assert _fire("ALAB", "BUY", 407.09, "tv_gap_up_continuation_long") is None
    assert _fire("ALAB", "BUY", 396.45, "tv_rc_4h_hrec") is not None
    assert _fire("ALAB", "BUY", 396.27, "tv_rc_daily_hrec") is not None


def test_level_type_always_fires_even_when_day_trade_in_cooldown():
    _fire("UCTT", "BUY", 119.77, "tv_rc_4h_hrec")
    # weekly_rc is exempt → fires despite the active day-trade cooldown
    assert _fire("UCTT", "BUY", 125.0, "tv_weekly_rc", elapsed=5) is None


def test_anchor_ratchets_down_to_best_entry():
    _fire("X", "BUY", 100.0, "tv_rc_4h_long")
    _fire("X", "BUY", 95.0, "tv_rc_4h_long", elapsed=40)   # lower → fires, anchor=95
    # now an entry between 95 and 100 must be a chase (>= the ratcheted 95)
    res = _fire("X", "BUY", 97.0, "tv_rc_4h_long", elapsed=40)
    assert res and res["reason"] == "dedup_chase"
    assert res["anchor"] == 95.0


def test_missing_entry_passes():
    assert _check_entry_time_dedup("Y", "BUY", None, "tv_rc_4h_long", S) is None
    assert _check_entry_time_dedup("Y", "BUY", 0.0, "tv_rc_4h_long", S) is None


def test_session_change_resets():
    _fire("Z", "BUY", 100.0, "tv_rc_4h_long")
    # same params but a new session → fresh state, fires
    assert _check_entry_time_dedup("Z", "BUY", 105.0, "tv_rc_4h_long", "2026-06-30") is None


def test_short_mirror_better_is_higher():
    """For a short, a BETTER entry is HIGHER; a lower entry is the chase."""
    _check_entry_time_dedup("SH", "SHORT", 50.0, "tv_staged_pdl_break", S)
    _record_entry_time_fire("SH", "SHORT", 50.0, "tv_staged_pdl_break", S)
    res = _check_entry_time_dedup("SH", "SHORT", 49.0, "tv_staged_pdl_break", S)
    _backdate("SH", "SHORT", 40)
    res = _check_entry_time_dedup("SH", "SHORT", 49.0, "tv_staged_pdl_break", S)
    assert res and res["reason"] == "dedup_chase"   # lower = worse for a short
