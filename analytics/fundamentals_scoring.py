"""Fundamentals scoring & flag derivation — pure, config-driven.

Turns a :class:`MetricSet` into:
  * a 0-100 quality score (Greenblatt/Graham cheapness + quality),
  * a 0-100 risk score (Staley red flags),
  * a list of :class:`Flag` labels (the scannable "DSO rising 3 quarters ⚠️").

All thresholds/weights come from :mod:`fundamentals_config`, so tuning the
methodology is a config/env change, never a code change (mirrors the tunable
Pine/webhook gates). No network, no DB, no clock → fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from analytics.fundamentals_metrics import MetricSet
from fundamentals_config import FundamentalsConfig, get_config

INFO = "info"
WARN = "warn"
CRITICAL = "critical"


@dataclass
class Flag:
    code: str            # stable machine key, e.g. "dso_rising"
    severity: str        # info | warn | critical
    label: str           # scannable, e.g. "DSO rising 3 quarters"
    detail: str = ""     # one-line context with the number
    metric: str = ""     # which metric drove it (provenance)


@dataclass
class ScoreResult:
    symbol: str
    quality_score: float          # 0-100 (higher = better business & cheaper)
    risk_score: float             # 0-100 (higher = more red flags)
    profitable: Optional[bool]    # TTM GAAP profitable? None = unknown
    flags: List[Flag]
    # Fraction of the score's inputs we actually had data for (0-1). Low
    # coverage = treat the score with caution (small caps / IPOs).
    quality_coverage: float
    risk_coverage: float


def score_company(ms: MetricSet, cfg: Optional[FundamentalsConfig] = None) -> ScoreResult:
    cfg = cfg or get_config()
    flags: List[Flag] = []

    quality, q_have, q_total = _quality_score(ms, cfg, flags)
    risk, r_have, r_total = _risk_score(ms, cfg, flags)

    prof = ms.val("profitable")
    profitable = None if prof is None else bool(prof >= 1.0)
    if profitable is True:
        flags.append(Flag("profitable", INFO, "PROFITABLE", "TTM GAAP net income positive", "profitable"))
    elif profitable is False:
        flags.append(Flag("unprofitable", WARN, "NOT PROFITABLE",
                          "TTM GAAP net income negative", "profitable"))

    # Severity-ranked so the report shows the scariest first.
    order = {CRITICAL: 0, WARN: 1, INFO: 2}
    flags.sort(key=lambda f: order.get(f.severity, 3))

    return ScoreResult(
        symbol=ms.symbol,
        quality_score=round(quality, 1),
        risk_score=round(risk, 1),
        profitable=profitable,
        flags=flags,
        quality_coverage=round(q_have / q_total, 2) if q_total else 0.0,
        risk_coverage=round(r_have / r_total, 2) if r_total else 0.0,
    )


# ── quality (positive) ───────────────────────────────────────────────────
def _quality_score(ms: MetricSet, cfg: FundamentalsConfig, flags: List[Flag]):
    w = cfg.quality_weights
    v = cfg.value
    earned = 0.0            # weighted points earned
    available = 0.0         # weighted points whose inputs existed
    have = 0
    total = 6

    prof = ms.val("profitable")
    if prof is not None:
        available += w.profitable
        have += 1
        if prof >= 1.0:
            earned += w.profitable

    roc = ms.val("roc")
    if roc is not None:
        available += w.roc
        have += 1
        if roc >= v.roc_excellent:
            earned += w.roc
        elif roc >= v.roc_good:
            earned += w.roc * 0.6
        if roc >= v.roc_good:
            flags.append(Flag("high_roc", INFO, "High return on capital",
                              f"ROC {roc*100:.0f}%", "roc"))

    ey = ms.val("earnings_yield")
    if ey is not None:
        available += w.earnings_yield
        have += 1
        if ey >= v.earnings_yield_very_cheap:
            earned += w.earnings_yield
        elif ey >= v.earnings_yield_cheap:
            earned += w.earnings_yield * 0.6
        if ey >= v.earnings_yield_cheap:
            flags.append(Flag("cheap_earnings_yield", INFO, "Cheap on earnings yield",
                              f"Earnings yield {ey*100:.0f}%", "earnings_yield"))

    fcy = ms.val("fcf_yield")
    if fcy is not None:
        available += w.fcf_yield
        have += 1
        if fcy >= v.fcf_yield_good:
            earned += w.fcf_yield

    # Balance-sheet health (Graham): current ratio + debt/equity together.
    cr = ms.val("current_ratio")
    de = ms.val("debt_to_equity")
    if cr is not None or de is not None:
        available += w.balance_sheet
        have += 1
        sub = 0.0
        checks = 0
        if cr is not None:
            checks += 1
            if cr >= v.current_ratio_min:
                sub += 1
        if de is not None:
            checks += 1
            if de <= v.debt_equity_max:
                sub += 1
        if checks:
            earned += w.balance_sheet * (sub / checks)

    mos = ms.val("margin_of_safety")
    if mos is not None:
        available += w.margin_of_safety
        have += 1
        if mos >= v.margin_of_safety_min_pct:
            earned += w.margin_of_safety
            flags.append(Flag("margin_of_safety", INFO, "Trades below intrinsic estimate",
                              f"~{mos:.0f}% margin of safety (estimate)", "margin_of_safety"))

    # Normalise to 0-100 over the weight that actually had data (so a small cap
    # with 3/6 inputs still gets a fair score, just lower coverage).
    score = (earned / available * 100.0) if available > 0 else 0.0
    return score, have, total


# ── risk (red flags) ─────────────────────────────────────────────────────
def _risk_score(ms: MetricSet, cfg: FundamentalsConfig, flags: List[Flag]):
    rw = cfg.risk_weights
    t = cfg.red_flags
    earned = 0.0
    available = 0.0
    have = 0
    total = 7

    # DSO rising streak.
    dso_streak = ms.trends.get("dso_rising_streak")
    if dso_streak is not None:
        available += rw.dso_rising
        have += 1
        if dso_streak >= t.dso_rising_quarters:
            earned += rw.dso_rising
            flags.append(Flag("dso_rising", WARN, f"DSO rising {int(dso_streak)} quarters",
                              "Receivables building vs sales", "dso"))

    dsi_streak = ms.trends.get("dsi_rising_streak")
    if dsi_streak is not None:
        available += rw.dsi_rising
        have += 1
        if dsi_streak >= t.dsi_rising_quarters:
            earned += rw.dsi_rising
            flags.append(Flag("dsi_rising", WARN, f"DSI rising {int(dsi_streak)} quarters",
                              "Inventory building vs cost of sales", "dsi"))

    accr = ms.val("accruals_ratio")
    if accr is not None:
        available += rw.accruals
        have += 1
        if accr >= t.accruals_ratio_critical:
            earned += rw.accruals
            flags.append(Flag("accruals_high", CRITICAL, "Large accruals gap",
                              f"Accruals ratio {accr:.2f} — earnings well above cash", "accruals_ratio"))
        elif accr >= t.accruals_ratio_warn:
            earned += rw.accruals * 0.5
            flags.append(Flag("accruals_elevated", WARN, "Elevated accruals",
                              f"Accruals ratio {accr:.2f}", "accruals_ratio"))

    # Earnings up while operating cash flow down = quality-of-earnings divergence.
    ni_g = ms.trends.get("ni_growth_pct")
    cfo_g = ms.trends.get("cfo_growth_pct")
    if ni_g is not None and cfo_g is not None:
        available += rw.cfo_divergence
        have += 1
        if ni_g >= t.divergence_min_ni_growth_pct and cfo_g <= -t.divergence_min_cfo_drop_pct:
            earned += rw.cfo_divergence
            flags.append(Flag("cfo_divergence", CRITICAL, "Earnings / cash-flow divergence",
                              f"Net income {ni_g:+.0f}% while op cash flow {cfo_g:+.0f}%", "operating_cash_flow"))

    # Margin compression (use the worse of gross/operating).
    gm_d = ms.trends.get("gross_margin_delta_pts")
    om_d = ms.trends.get("operating_margin_delta_pts")
    worst = None
    for d in (gm_d, om_d):
        if d is not None and (worst is None or d < worst):
            worst = d
    if worst is not None:
        available += rw.margin_compression
        have += 1
        if worst <= -t.margin_compression_pts:
            earned += rw.margin_compression
            flags.append(Flag("margin_compression", WARN, "Margins compressing",
                              f"Margin down {abs(worst):.1f} pts over window", "operating_margin"))

    cov = ms.val("interest_coverage")
    if cov is not None:
        available += rw.interest_coverage
        have += 1
        if cov <= t.interest_coverage_critical:
            earned += rw.interest_coverage
            flags.append(Flag("interest_coverage_low", CRITICAL, "Thin interest coverage",
                              f"EBIT covers interest {cov:.1f}x", "interest_coverage"))
        elif cov <= t.interest_coverage_warn:
            earned += rw.interest_coverage * 0.5
            flags.append(Flag("interest_coverage_warn", WARN, "Low interest coverage",
                              f"EBIT covers interest {cov:.1f}x", "interest_coverage"))

    dilution = ms.trends.get("dilution_pct")
    if dilution is not None:
        available += rw.dilution
        have += 1
        if dilution >= t.dilution_critical_pct:
            earned += rw.dilution
            flags.append(Flag("dilution_heavy", CRITICAL, "Heavy dilution",
                              f"Diluted shares +{dilution:.0f}% over window", "shares_diluted"))
        elif dilution >= t.dilution_warn_pct:
            earned += rw.dilution * 0.5
            flags.append(Flag("dilution", WARN, "Share dilution",
                              f"Diluted shares +{dilution:.0f}% over window", "shares_diluted"))

    score = (earned / available * 100.0) if available > 0 else 0.0
    return score, have, total
