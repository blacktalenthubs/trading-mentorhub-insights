"""TBA breakout is ON by default (trader, 2026-10-27).

swing_tba_breakout carries default_enabled=True in the alert-type catalog, so
the per-user delivery gate (_filter_users_by_type_pref) treats it as opt-OUT —
the same semantics scanner rules already have: no pref row = ON, and only an
explicit enabled=False row (the Settings toggle) mutes it. Every other type
keeps the opt-in default (no row = OFF).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.tv_webhook import _filter_users_by_type_pref  # noqa: E402


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DB:
    """Fake async session: returns canned (user_id, alert_type, enabled) rows."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _Result(self._rows)


class _User:
    def __init__(self, id):
        self.id = id


def _kept(rows, alert_type_full, uid=3):
    users = [_User(uid)]
    out = asyncio.run(_filter_users_by_type_pref(_DB(rows), users, alert_type_full))
    return [u.id for u in out] == [uid]


def test_tba_on_by_default_no_pref_row():
    """The 2026-10-26 TSLA case: the account has NO pref row for the type at
    all — the breakout must still be delivered."""
    assert _kept([], "tv_swing_tba_breakout")


def test_tba_explicit_off_still_mutes():
    """Opt-OUT, not forced: a user who turned it off in Settings stays off."""
    assert not _kept([(3, "swing_tba_breakout", False)], "tv_swing_tba_breakout")


def test_tba_explicit_on_kept():
    assert _kept([(3, "swing_tba_breakout", True)], "tv_swing_tba_breakout")


def test_default_off_type_still_opt_in():
    """Other swing types keep the old default: no pref row = OFF."""
    assert not _kept([], "tv_swing_sma200_reclaim")
    assert _kept([(3, "swing_sma200_reclaim", True)], "tv_swing_sma200_reclaim")
    assert not _kept([(3, "swing_sma200_reclaim", False)], "tv_swing_sma200_reclaim")
