"""Pine TBA port (patterns/pine_tba.py) + the Task-B enablement set (2026-11-18).

The port is the TBA Patterns Pine's pattern engine (repo main v2026.10.29.2) on daily
bars: pattern LOCKED from completed bars, breakout = price crossing the locked TBA,
fired by analytics.breakout_alerts as the registered `swing_tba_breakout` type.
Fixtures mirror tests/test_patterns.py's synthetic shapes."""
import numpy as np
import pandas as pd

from patterns.pine_tba import detect_locked
from analytics.breakout_alerts import detect_pine_tba


def _to_df(close, vol=None):
    c = np.asarray(close, float)
    n = len(c)
    hi = c * 1.004
    lo = c * 0.996
    op = np.concatenate([[c[0]], c[:-1]])
    v = np.asarray(vol, float) if vol is not None else np.full(n, 1_000_000.0)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"Open": op, "High": np.maximum(hi, np.maximum(op, c)),
                         "Low": np.minimum(lo, np.minimum(op, c)),
                         "Close": c, "Volume": v}, index=idx)


def _ease(a, b, n):
    t = np.arange(n)
    return a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * t / max(1, n - 1)))


def _triangle():
    seg = []
    for lo in [93, 95, 97, 99]:
        seg += list(_ease(lo, 100.0, 6)) + list(_ease(100.0, lo + 1.5, 5))
    return np.concatenate([np.linspace(40, 92, 120), np.array(seg)])


def test_pine_ascending_triangle():
    hit = detect_locked(_to_df(_triangle()))
    assert hit is not None and hit["pattern"] == "Ascending Triangle"
    assert abs(hit["tba"] - 100.4) < 0.5
    assert hit["stop"] < hit["tba"]


def test_pine_bull_flag():
    pole = np.linspace(80, 100, 9)                       # +25% pole in 8 bars
    flag = np.array([99.0, 98.2, 98.8, 98.0, 98.5])      # tight drift, <50% retrace
    hit = detect_locked(_to_df(np.concatenate([np.linspace(60, 80, 60), pole, flag])))
    assert hit is not None and hit["pattern"] == "Bull Flag"
    assert hit["stop"] < hit["tba"]


def test_pine_downtrend_rejected():
    assert detect_locked(_to_df(np.linspace(150, 60, 150))) is None


def _locked_below_tba():
    """Triangle pattern with the last completed bar pulled back below the TBA —
    the locked state the morning of a breakout day."""
    df = _to_df(_triangle())
    df.iloc[-1, df.columns.get_loc("Close")] = 99.0
    df.iloc[-1, df.columns.get_loc("High")] = 99.4
    df.iloc[-1, df.columns.get_loc("Low")] = 98.6
    return df


def test_pine_tba_cross_fires_on_locked_level():
    locked = _locked_below_tba()
    hit = detect_locked(locked)
    assert hit is not None
    tba = hit["tba"]
    # Append today's forming bar: opens below the TBA, crosses and closes above it.
    today = pd.DataFrame(
        {"Open": [tba * 0.995], "High": [tba * 1.035], "Low": [tba * 0.99],
         "Close": [tba * 1.03], "Volume": [2_000_000.0]},
        index=[locked.index[-1] + pd.tseries.offsets.BDay(1)])
    df = pd.concat([locked, today])
    events = detect_pine_tba(df)
    assert len(events) == 1
    ev = events[0]
    assert ev["buy_point"] == tba
    assert ev["stop"] < ev["buy_point"]
    assert ev["risk_pct"] <= 8.0


def test_pine_tba_no_cross_no_fire():
    locked = _locked_below_tba()
    today = pd.DataFrame(
        {"Open": [99.0], "High": [99.8], "Low": [98.5], "Close": [99.2],
         "Volume": [1_000_000.0]},
        index=[locked.index[-1] + pd.tseries.offsets.BDay(1)])
    assert detect_pine_tba(pd.concat([locked, today])) == []


# ── Task B (2026-11-18): the trader's ON set, scanner side ────────────────────
def test_task_b_rules_enabled():
    from alert_config import ENABLED_RULES
    for rule in ("prior_day_high_breakout",      # PDH break
                 "prior_day_low_reclaim",        # PDL reclaim
                 "pwh_breakout_retest",          # PWH break (scanner form: breakout + retest)
                 "pwl_reclaim",                  # PWL reclaim
                 "ma20_support_1h",              # SMA 1h support/reclaim set
                 "ma50_support_1h",              # re-enabled 2026-11-18
                 "ma200_support_1h"):
        assert rule in ENABLED_RULES, rule


def test_swing_tba_breakout_registered():
    # Load the catalog module directly (the app package __init__ pulls web deps
    # the sandbox lacks; CI runs the full catalog suite in test_alert_type_catalog.py).
    import importlib.util
    import pathlib
    import sys
    import types
    from sqlalchemy.orm import declarative_base
    app_stub = types.ModuleType("app")
    db_stub = types.ModuleType("app.database")
    db_stub.Base = declarative_base()
    sys.modules.setdefault("app", app_stub)
    sys.modules["app.database"] = db_stub
    path = pathlib.Path(__file__).resolve().parents[1] / "api/app/models/alert_type_config.py"
    spec = importlib.util.spec_from_file_location("alert_type_config_direct", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["alert_type_config_direct"] = mod   # SQLAlchemy Mapped[] resolution needs it
    spec.loader.exec_module(mod)
    rows = {r[0]: r for r in mod.ALERT_TYPE_CATALOG}
    assert "swing_tba_breakout" in rows
    assert rows["swing_tba_breakout"][3] is True   # catalog default (documentation; per-user toggle is the real gate)
