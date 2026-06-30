"""Morning-window gate — the 4h high break (rc_4h_hrec) only fires in the first
~3h of RTH (≤ 12:30 ET, equities), muted after to avoid chasing into the close."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_API_ROOT = Path(__file__).resolve().parent.parent / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.tv_webhook import _is_after_morning_window  # noqa: E402

ET = ZoneInfo("America/New_York")


def _at(h, m=0):
    return datetime(2026, 6, 30, h, m, tzinfo=ET)   # a Tuesday


def test_4h_break_allowed_in_morning_bar():
    # the morning 4h bar runs 09:30–13:30 — breaks vs YESTERDAY's high, all fire
    assert not _is_after_morning_window("AAPL", "tv_rc_4h_hrec", _at(9, 35))
    assert not _is_after_morning_window("AAPL", "tv_rc_4h_hrec", _at(11, 0))
    assert not _is_after_morning_window("AAPL", "tv_rc_4h_hrec", _at(12, 45))  # was wrongly cut at 12:30
    assert not _is_after_morning_window("AAPL", "tv_rc_4h_hrec", _at(13, 25))  # still the morning bar


def test_4h_break_muted_in_afternoon_bar():
    # at/after 13:30 the morning bar has CLOSED — breaks only re-test the morning high
    assert _is_after_morning_window("AAPL", "tv_rc_4h_hrec", _at(13, 30))   # afternoon 4h bar opens
    assert _is_after_morning_window("AAPL", "tv_rc_4h_hrec", _at(13, 35))   # the dud cluster
    assert _is_after_morning_window("AAPL", "tv_rc_4h_hrec", _at(15, 55))


def test_only_4h_break_is_gated():
    # other types are never morning-gated, even in the afternoon
    for t in ("tv_rc_4h_long", "tv_rc_daily_hrec", "tv_weekly_rc", "tv_staged_pdh_break"):
        assert not _is_after_morning_window("AAPL", t, _at(14, 0)), t


def test_crypto_is_exempt():
    # 24/7 — no "open", so the 4h break is never morning-gated for crypto
    assert not _is_after_morning_window("BTC-USD", "tv_rc_4h_hrec", _at(14, 0))
    assert not _is_after_morning_window("ETH-USD", "tv_rc_4h_hrec", _at(2, 0))
