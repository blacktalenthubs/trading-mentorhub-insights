"""Regime inside-day classification (_regime_dict) — locks in why today's bars
must be RTH-filtered before the regime read. An extended-hours print poking
outside the prior RTH range flips inside_day off and mis-reads an inside day as
NEUTRAL; the RTH-only slice keeps it correct. See _spy_regime_fresh."""

import asyncio  # noqa: F401  (keeps import style consistent with sibling tests)

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _alias_app(monkeypatch):
    """api/ is the import root in prod (`from app.* ...`); under pytest the
    top-level streamlit app.py shadows it. Alias it + force clean Settings so
    app.routers.market imports without the repo-root .env collision."""
    import importlib
    import sys
    import api.app as _api_app
    monkeypatch.setitem(sys.modules, "app", _api_app)
    _cfg = importlib.import_module("app.config")
    _clean = _cfg.Settings(_env_file=None)  # type: ignore[call-arg]
    monkeypatch.setattr(_cfg, "get_settings", lambda: _clean)


def _bars(rows):
    """rows = list of (ts 'HH:MM', open, high, low, close). 1k volume each."""
    idx = pd.DatetimeIndex([pd.Timestamp(f"2026-06-08 {t}") for t, *_ in rows])
    data = {
        "Open": [r[1] for r in rows],
        "High": [r[2] for r in rows],
        "Low": [r[3] for r in rows],
        "Close": [r[4] for r in rows],
        "Volume": [1000 for _ in rows],
    }
    return pd.DataFrame(data, index=idx)


# Prior-day RTH range used by all cases: PDH 110, PDL 100.
PDH, PDL = 110.0, 100.0

# RTH session that stays entirely inside the prior range [100, 110].
_RTH = [
    ("09:30", 104, 106, 103, 105),
    ("10:00", 105, 108, 104, 107),
    ("15:55", 107, 108, 102, 106),
]
# Same RTH session but with a thin premarket print that pokes to 112 (above PDH).
_PREMARKET = ("09:00", 111, 112, 111, 111)


def _regime(rows):
    from app.routers.market import _regime_dict
    return _regime_dict(_bars(rows), PDH, PDL, "test", "SPY", rsi=None)


def test_rth_only_session_reads_inside_day():
    out = _regime(_RTH)
    assert out["status"] == "ok"
    assert out["inside_day"] is True
    assert out["bias"] == "WAIT"  # inside day → wait for a break, not NEUTRAL


def test_premarket_poke_breaks_inside_day_classification():
    """The bug: include an extended-hours bar above PDH and the SAME inside RTH
    session no longer reads as inside_day → falls through to NEUTRAL. This is
    exactly what RTH-filtering in _spy_regime_fresh prevents."""
    out = _regime([_PREMARKET, *_RTH])
    assert out["inside_day"] is False
    assert out["bias"] != "WAIT"


def test_genuine_break_above_pdh_is_not_inside():
    rows = [*_RTH, ("15:30", 109, 111, 109, 110.5)]  # RTH high 111 > PDH 110
    out = _regime(rows)
    assert out["inside_day"] is False
