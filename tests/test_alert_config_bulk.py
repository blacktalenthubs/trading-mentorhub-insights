"""Bulk alert-type toggle endpoint (Settings 'Check all' / per-group 'Enable all').

As of 2026-06-20 the toggles are PER-USER (user_alert_type_prefs), not the global
alert_type_config — so one account's bulk action only writes that user's rows and
never affects another user. These drive the router with a fake AsyncSession.
"""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _alias_app(monkeypatch):
    """api/ is the import root in production, so `app` resolves to the api
    package. Under pytest the top-level streamlit app.py would shadow it — alias
    it. Also force a clean Settings (no .env) so app.database imports cleanly."""
    import importlib
    import sys
    import api.app as _api_app
    monkeypatch.setitem(sys.modules, "app", _api_app)
    _cfg_mod = importlib.import_module("app.config")
    _clean = _cfg_mod.Settings(_env_file=None)  # type: ignore[call-arg]
    monkeypatch.setattr(_cfg_mod, "get_settings", lambda: _clean)


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return _FakeScalars(self._rows)

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    """First execute() = the catalog query (returns the alert_type keys); every
    later execute() = _set_pref's existence check (None → a new pref is added)."""

    def __init__(self, types):
        self._types = types
        self._first = True
        self.added = []

    async def execute(self, _stmt):
        if self._first:
            self._first = False
            return _FakeResult(rows=self._types)
        return _FakeResult(scalar=None)

    def add(self, obj):
        self.added.append(obj)


class _FakeUser:
    id = 42


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _call(types, enabled: bool):
    from app.routers.alert_config import AlertConfigBulkUpdate, set_all_alert_config
    sess = _FakeSession(types)
    result = _run(
        set_all_alert_config(
            AlertConfigBulkUpdate(enabled=enabled), user=_FakeUser(), db=sess
        )
    )
    return result, sess


def test_bulk_writes_per_user_prefs_only():
    result, sess = _call(["staged_pdl_held", "rc_4h", "weekly_ma_held"], enabled=True)
    assert result["updated"] == 3
    assert result["enabled"] is True
    # The fix: it writes PER-USER pref rows scoped to THIS user — never a global row.
    assert len(sess.added) == 3
    assert all(p.user_id == 42 for p in sess.added)
    assert all(p.enabled is True for p in sess.added)
    assert {p.alert_type for p in sess.added} == {"staged_pdl_held", "rc_4h", "weekly_ma_held"}


def test_bulk_uncheck_writes_disabled_prefs():
    result, sess = _call(["rc_4h"], enabled=False)
    assert result["updated"] == 1
    assert sess.added[0].user_id == 42
    assert sess.added[0].enabled is False


def test_bulk_empty_is_a_noop():
    result, sess = _call([], enabled=False)
    assert result["updated"] == 0
    assert sess.added == []
