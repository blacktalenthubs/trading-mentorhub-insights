"""Tests for the premarket signal engine — incl. the live MU example."""
from __future__ import annotations
import pandas as pd, numpy as np
from analytics.premarket_signals import compute_levels, evaluate

# MU premarket 07-02: undercut PWL 991.10, reclaiming toward CML 1032.20.
MU_LEVELS = {"cml": 1032.20, "pwl": 991.10, "pdl": 1124.66, "pwh": 1255.0,
             "pdh": 1168.68, "pml": 854.35, "w10": 887.99, "w30": 600.0}
ALL = {"cml_reclaim", "cml_held", "staged_pdl_held", "staged_pwl_held", "staged_pml_held",
       "staged_pdh_break", "staged_pwh_break", "weekly_10w_held", "weekly_30w_held"}


def test_mu_fires_cml_reclaim_and_pwl_held():
    sigs = evaluate(MU_LEVELS, pm_price=1032.28, pm_low=991.0, pm_high=1154.0, enabled=ALL)
    types = {s["alert_type"] for s in sigs}
    assert "cml_reclaim" in types      # undercut & reclaimed the current-month low
    assert "staged_pwl_held" in types  # tagged & held the prior-week low
    # should NOT fire far-away levels
    assert "staged_pdl_held" not in types and "staged_pdh_break" not in types


def test_respects_enabled_types():
    sigs = evaluate(MU_LEVELS, 1032.28, 991.0, 1154.0, enabled={"cml_reclaim"})
    assert {s["alert_type"] for s in sigs} == {"cml_reclaim"}


def test_no_signal_when_no_touch():
    # price hovering well above the CML, low never near any level → nothing
    sigs = evaluate(MU_LEVELS, 1100.0, 1095.0, 1105.0, enabled=ALL)
    assert sigs == []


def test_compute_levels_smoke():
    idx = pd.date_range("2026-05-15", periods=40, freq="B")
    base = np.linspace(100, 120, 40)
    df = pd.DataFrame({"High": base + 1, "Low": base - 1, "Close": base}, index=idx)
    lv = compute_levels(df)
    assert "pdh" in lv and "pdl" in lv and "cml" in lv
    assert lv["pdh"] >= lv["pdl"]
