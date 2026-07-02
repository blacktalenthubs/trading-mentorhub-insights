"""Tests for the premarket signal engine — incl. the live MU example + proximity gate."""
from __future__ import annotations
import pandas as pd, numpy as np
from analytics.premarket_signals import compute_levels, evaluate

MU_LEVELS = {"cml": 1032.20, "pwl": 991.10, "pdl": 1124.66, "pwh": 1255.0,
             "pdh": 1168.68, "pml": 854.35, "w10": 887.99, "w30": 600.0}
ALL = {"cml_reclaim", "cml_held", "staged_pdl_held", "staged_pwl_held", "staged_pml_held",
       "staged_pdh_break", "staged_pwh_break", "weekly_10w_held", "weekly_30w_held"}


def test_mu_at_cml_fires_cml_reclaim_only():
    # AT the CML 1032.20 (undercut 987 premarket, reclaimed) → cml_reclaim.
    # PWL 991 is 4% below → NOT "at" it, so no pwl_held.
    sigs = evaluate(MU_LEVELS, pm_price=1032.28, pm_low=987.0, pm_high=1057.0, enabled=ALL)
    types = {s["alert_type"] for s in sigs}
    assert "cml_reclaim" in types
    assert "staged_pwl_held" not in types and "staged_pdl_held" not in types


def test_at_pwl_fires_pwl_held():
    # price sitting AT the PWL 991.10 (tagged 989, holding 992)
    sigs = evaluate(MU_LEVELS, pm_price=992.0, pm_low=989.0, pm_high=995.0, enabled=ALL)
    assert "staged_pwl_held" in {s["alert_type"] for s in sigs}


def test_proximity_gate_skips_far_past_level():
    # undercut the CML but ran 5% past it → no longer AT the level → no signal
    sigs = evaluate(MU_LEVELS, pm_price=1085.0, pm_low=987.0, pm_high=1090.0, enabled=ALL)
    assert "cml_reclaim" not in {s["alert_type"] for s in sigs}


def test_respects_enabled_types():
    sigs = evaluate(MU_LEVELS, 1032.28, 987.0, 1057.0, enabled={"cml_reclaim"})
    assert {s["alert_type"] for s in sigs} == {"cml_reclaim"}


def test_no_signal_when_no_touch():
    sigs = evaluate(MU_LEVELS, 1100.0, 1095.0, 1105.0, enabled=ALL)
    assert sigs == []


def test_compute_levels_smoke():
    idx = pd.date_range("2026-05-15", periods=40, freq="B")
    base = np.linspace(100, 120, 40)
    df = pd.DataFrame({"High": base + 1, "Low": base - 1, "Close": base}, index=idx)
    lv = compute_levels(df)
    assert "pdh" in lv and "pdl" in lv and "cml" in lv
