"""Premarket signal engine — evaluate the level-based alert rules on PREMARKET price.

The TV pines are RTH-anchored and don't run premarket, so premarket signals come
from here: given a symbol's daily/weekly history + its live premarket price (and the
premarket low/high so far), compute the same key levels the pines use and report
which rules TRIGGER — filtered to the user's ENABLED alert types.

Pure over price data — no app/DB deps — so it's unit-testable and reusable by the
triage premarket job. Delivery (push + feed, focus-scoping) is layered on top.

Rules (level + price-position, the premarket-computable subset):
  cml_reclaim / cml_held   — current-month low: undercut & reclaimed / tagged & held
  staged_pdl_held / _pwl_held / _pml_held — prior day/week/month low tagged & held
  staged_pdh_break / _pwh_break           — prior day/week high broken
  weekly_10w_held / weekly_30w_held       — tagged & held a weekly MA
"""

from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd

TOL_PCT = 0.3    # how close the premarket low must tag a level to count (%)
PROX_PCT = 1.5   # price must be AT the level now (within this % above it) — not 5% past it


def compute_levels(daily: pd.DataFrame, weekly: Optional[pd.DataFrame] = None) -> dict:
    """Key levels from daily (+ optional weekly) bars. `daily` needs a DatetimeIndex
    and High/Low/Close columns; the LAST row is the most recent completed session."""
    if daily is None or len(daily) < 25:
        return {}
    h, l, c = daily["High"], daily["Low"], daily["Close"]
    idx = daily.index
    lv: dict = {
        "prior_close": float(c.iloc[-1]),
        "pdh": float(h.iloc[-1]),
        "pdl": float(l.iloc[-1]),
    }
    # current-month low/high (month of the last bar)
    last = idx[-1]
    cur_month = (idx.year == last.year) & (idx.month == last.month)
    if cur_month.any():
        lv["cml"] = float(l[cur_month].min())
    # prior week high/low (the ISO-week before the last bar's week)
    wk = idx.isocalendar()
    last_wk = (wk.year.iloc[-1], wk.week.iloc[-1])
    prior_wk_mask = ~((wk.year == last_wk[0]) & (wk.week == last_wk[1])).values
    if prior_wk_mask.any():
        recent = daily[prior_wk_mask].tail(5)   # last full week before this one
        lv["pwh"] = float(recent["High"].max())
        lv["pwl"] = float(recent["Low"].min())
    # prior month low (the month before the last bar's month)
    prior_month = (idx.year * 12 + idx.month) == (last.year * 12 + last.month - 1)
    if prior_month.any():
        lv["pml"] = float(l[prior_month].min())
    # weekly MAs (10w / 30w) off weekly closes
    if weekly is not None and len(weekly) >= 30:
        wc = weekly["Close"]
        lv["w10"] = float(wc.rolling(10).mean().iloc[-1])
        lv["w30"] = float(wc.rolling(30).mean().iloc[-1])
    return lv


def _held(price: float, low: float, level: float, tol: float) -> bool:
    """Tagged from above and holding, AT the level now: price in [level, level+PROX%],
    low dipped to within tol. The proximity cap stops it firing 5% past the level."""
    return level > 0 and level <= price <= level * (1 + PROX_PCT / 100.0) and low <= level * (1 + tol / 100.0)


def _reclaim(price: float, low: float, level: float, tol: float) -> bool:
    """Undercut & reclaimed, AT the level now: low broke below, price back just above it."""
    return level > 0 and low < level * (1 - tol / 100.0) and level <= price <= level * (1 + PROX_PCT / 100.0)


def evaluate(levels: dict, pm_price: float, pm_low: float, pm_high: float,
             enabled: Iterable[str], tol: float = TOL_PCT) -> list[dict]:
    """Return the triggered signals (filtered to `enabled` alert types)."""
    en = set(enabled or [])
    out: list[dict] = []

    def emit(atype: str, level: float, why: str):
        if atype in en:
            out.append({
                "alert_type": atype, "direction": "BUY",
                "entry": round(pm_price, 2), "level": round(level, 2),
                "stop": round(level * 0.997, 2), "note": why,
            })

    cml = levels.get("cml")
    if cml:
        if _reclaim(pm_price, pm_low, cml, tol):
            emit("cml_reclaim", cml, "undercut & reclaimed the current-month low premarket")
        elif _held(pm_price, pm_low, cml, tol):
            emit("cml_held", cml, "tagged & held the current-month low premarket")
    for lvl_key, atype, label in (
        ("pdl", "staged_pdl_held", "prior-day low"),
        ("pwl", "staged_pwl_held", "prior-week low"),
        ("pml", "staged_pml_held", "prior-month low"),
        ("w10", "weekly_10w_held", "10-week MA"),
        ("w30", "weekly_30w_held", "30-week MA"),
    ):
        lvl = levels.get(lvl_key)
        if lvl and _held(pm_price, pm_low, lvl, tol):
            emit(atype, lvl, f"tagged & held the {label} premarket")
    for lvl_key, atype, label in (
        ("pdh", "staged_pdh_break", "prior-day high"),
        ("pwh", "staged_pwh_break", "prior-week high"),
    ):
        lvl = levels.get(lvl_key)
        if lvl and lvl < pm_price <= lvl * (1 + PROX_PCT / 100.0) and pm_low <= lvl:  # just broke, at it
            emit(atype, lvl, f"broke the {label} premarket")
    return out
