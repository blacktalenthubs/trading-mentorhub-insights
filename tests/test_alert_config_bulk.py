"""Bulk alert-type toggle endpoint (Settings > Alert Types 'Uncheck all' /
'Check all'). Drives the router function directly with a fake AsyncSession —
same lightweight style as the other api-router unit tests."""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _alias_app(monkeypatch):
    """api/ is the import root in production, so `app` resolves to the api
    package (its modules use `from app.* ...`). Under pytest the top-level
    streamlit app.py would shadow it — alias it for the duration of the test.
    Also force a clean Settings (no .env) so app.database imports cleanly: the
    repo-root .env holds streamlit keys that api's Settings rejects."""
    import importlib
    import sys
    import api.app as _api_app
    monkeypatch.setitem(sys.modules, "app", _api_app)
    _cfg_mod = importlib.import_module("app.config")
    _clean = _cfg_mod.Settings(_env_file=None)  # type: ignore[call-arg]
    monkeypatch.setattr(_cfg_mod, "get_settings", lambda: _clean)


class _FakeRow:
    def __init__(self, enabled: bool):
        self.enabled = enabled


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    """Returns the same row set on every execute() — the bulk endpoint issues
    a single select(AlertTypeConfig)."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _call(rows, enabled: bool):
    from app.routers.alert_config import AlertConfigBulkUpdate, set_all_alert_config
    return _run(
        set_all_alert_config(
            AlertConfigBulkUpdate(enabled=enabled), user=object(), db=_FakeSession(rows)
        )
    )


def test_uncheck_all_disables_every_row():
    rows = [_FakeRow(True), _FakeRow(True), _FakeRow(False)]
    result = _call(rows, enabled=False)
    assert result == {"updated": 3, "enabled": False}
    assert all(r.enabled is False for r in rows)


def test_check_all_enables_every_row():
    rows = [_FakeRow(False), _FakeRow(True), _FakeRow(False)]
    result = _call(rows, enabled=True)
    assert result == {"updated": 3, "enabled": True}
    assert all(r.enabled is True for r in rows)


def test_empty_table_is_a_noop():
    result = _call([], enabled=False)
    assert result == {"updated": 0, "enabled": False}
