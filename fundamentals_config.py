"""Fundamentals Engine — tunable thresholds & scoring weights.

Same philosophy as ``alert_config.py``: every threshold and weight lives here
and is env-overridable, so the value/short-selling methodology can be tuned
WITHOUT a redeploy. Nothing in the metric or scoring engine hardcodes a
number — it reads from the dataclasses below.

Red-flag methodology (Staley / short-selling) and value screening (Greenblatt /
Graham) both draw their thresholds from here.

Override any value at runtime with an env var, e.g.::

    FUND_DSO_RISING_QUARTERS=4      # need 4 rising quarters, not 3, to flag
    FUND_ACCRUALS_RATIO_WARN=0.12
    FUND_WEIGHT_PROFITABLE=25

Weights are relative; the engine normalises each score to 0-100.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Dict


def _f(name: str, default: float) -> float:
    """Read a float env override, falling back to the default."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


# ── Trend / red-flag thresholds ──────────────────────────────────────────
@dataclass(frozen=True)
class RedFlagThresholds:
    """When does a metric's trend become a red flag?"""

    # How many trailing quarters we look across for a trend.
    trend_lookback_quarters: int = field(default_factory=lambda: _i("FUND_TREND_LOOKBACK_Q", 8))

    # A metric "rising" this many consecutive quarters is adverse (DSI/DSO).
    dso_rising_quarters: int = field(default_factory=lambda: _i("FUND_DSO_RISING_QUARTERS", 3))
    dsi_rising_quarters: int = field(default_factory=lambda: _i("FUND_DSI_RISING_QUARTERS", 3))

    # Accruals ratio (NI - CFO) / total assets. Large positive = low earnings quality.
    accruals_ratio_warn: float = field(default_factory=lambda: _f("FUND_ACCRUALS_RATIO_WARN", 0.10))
    accruals_ratio_critical: float = field(default_factory=lambda: _f("FUND_ACCRUALS_RATIO_CRIT", 0.20))

    # Earnings up while operating cash flow down over the window = divergence.
    # Minimum % move required on each leg to call it a real divergence.
    divergence_min_ni_growth_pct: float = field(default_factory=lambda: _f("FUND_DIVERGENCE_NI_PCT", 5.0))
    divergence_min_cfo_drop_pct: float = field(default_factory=lambda: _f("FUND_DIVERGENCE_CFO_PCT", 5.0))

    # Margin compression: gross/operating margin falling at least this many
    # points from window start to end.
    margin_compression_pts: float = field(default_factory=lambda: _f("FUND_MARGIN_COMPRESSION_PTS", 3.0))

    # Interest coverage (EBIT / interest expense) below this = leverage risk.
    interest_coverage_warn: float = field(default_factory=lambda: _f("FUND_INTEREST_COVERAGE_WARN", 3.0))
    interest_coverage_critical: float = field(default_factory=lambda: _f("FUND_INTEREST_COVERAGE_CRIT", 1.5))

    # Debt/equity above this is elevated leverage.
    debt_equity_warn: float = field(default_factory=lambda: _f("FUND_DEBT_EQUITY_WARN", 1.5))
    debt_equity_critical: float = field(default_factory=lambda: _f("FUND_DEBT_EQUITY_CRIT", 3.0))

    # Diluted share count growth over the window (%). Heavy dilution above this.
    dilution_warn_pct: float = field(default_factory=lambda: _f("FUND_DILUTION_WARN_PCT", 5.0))
    dilution_critical_pct: float = field(default_factory=lambda: _f("FUND_DILUTION_CRIT_PCT", 15.0))


# ── Value / quality thresholds ───────────────────────────────────────────
@dataclass(frozen=True)
class ValueThresholds:
    """Greenblatt / Graham cheapness + quality bars."""

    # Greenblatt Return on Capital — good business above this (as a fraction, 0.25 = 25%).
    roc_good: float = field(default_factory=lambda: _f("FUND_ROC_GOOD", 0.20))
    roc_excellent: float = field(default_factory=lambda: _f("FUND_ROC_EXCELLENT", 0.35))

    # Greenblatt Earnings Yield (EBIT / EV) — cheap above this.
    earnings_yield_cheap: float = field(default_factory=lambda: _f("FUND_EARNINGS_YIELD_CHEAP", 0.08))
    earnings_yield_very_cheap: float = field(default_factory=lambda: _f("FUND_EARNINGS_YIELD_VCHEAP", 0.12))

    # Free-cash-flow yield (FCF / market cap) — healthy above this.
    fcf_yield_good: float = field(default_factory=lambda: _f("FUND_FCF_YIELD_GOOD", 0.05))

    # Graham balance-sheet health.
    current_ratio_min: float = field(default_factory=lambda: _f("FUND_CURRENT_RATIO_MIN", 1.5))
    quick_ratio_min: float = field(default_factory=lambda: _f("FUND_QUICK_RATIO_MIN", 1.0))
    debt_equity_max: float = field(default_factory=lambda: _f("FUND_GRAHAM_DEBT_EQUITY_MAX", 1.0))

    # Margin of safety (intrinsic vs price) considered adequate above this (%).
    margin_of_safety_min_pct: float = field(default_factory=lambda: _f("FUND_MOS_MIN_PCT", 25.0))

    # Graham-style intrinsic estimate: normalized EPS * this multiple.
    # Deliberately conservative; documented as an ESTIMATE, never presented as fact.
    intrinsic_pe_multiple: float = field(default_factory=lambda: _f("FUND_INTRINSIC_PE", 15.0))


# ── Scoring weights ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class QualityWeights:
    """Positive contributors to the 0-100 quality score. Start equal-weight;
    tune later. Each sub-signal contributes its weight when the bar is met."""

    profitable: float = field(default_factory=lambda: _f("FUND_WEIGHT_PROFITABLE", 20.0))
    roc: float = field(default_factory=lambda: _f("FUND_WEIGHT_ROC", 20.0))
    earnings_yield: float = field(default_factory=lambda: _f("FUND_WEIGHT_EARNINGS_YIELD", 15.0))
    fcf_yield: float = field(default_factory=lambda: _f("FUND_WEIGHT_FCF_YIELD", 15.0))
    balance_sheet: float = field(default_factory=lambda: _f("FUND_WEIGHT_BALANCE_SHEET", 15.0))
    margin_of_safety: float = field(default_factory=lambda: _f("FUND_WEIGHT_MOS", 15.0))


@dataclass(frozen=True)
class RiskWeights:
    """Contributors to the 0-100 risk score (higher = more red flags)."""

    dso_rising: float = field(default_factory=lambda: _f("FUND_RWEIGHT_DSO", 15.0))
    dsi_rising: float = field(default_factory=lambda: _f("FUND_RWEIGHT_DSI", 15.0))
    accruals: float = field(default_factory=lambda: _f("FUND_RWEIGHT_ACCRUALS", 20.0))
    cfo_divergence: float = field(default_factory=lambda: _f("FUND_RWEIGHT_DIVERGENCE", 20.0))
    margin_compression: float = field(default_factory=lambda: _f("FUND_RWEIGHT_MARGIN", 10.0))
    interest_coverage: float = field(default_factory=lambda: _f("FUND_RWEIGHT_COVERAGE", 10.0))
    dilution: float = field(default_factory=lambda: _f("FUND_RWEIGHT_DILUTION", 10.0))


@dataclass(frozen=True)
class FundamentalsConfig:
    red_flags: RedFlagThresholds = field(default_factory=RedFlagThresholds)
    value: ValueThresholds = field(default_factory=ValueThresholds)
    quality_weights: QualityWeights = field(default_factory=QualityWeights)
    risk_weights: RiskWeights = field(default_factory=RiskWeights)

    def as_dict(self) -> Dict[str, Dict[str, float]]:
        """Flatten for the API / admin UI (provenance + tuning surface)."""
        out: Dict[str, Dict[str, float]] = {}
        for f in fields(self):
            section = getattr(self, f.name)
            out[f.name] = {sf.name: getattr(section, sf.name) for sf in fields(section)}
        return out


# EDGAR politeness — SEC requires a declared User-Agent and caps request rate.
SEC_USER_AGENT = os.environ.get(
    "SEC_EDGAR_USER_AGENT",
    "BusyTradersDesk fundamentals-engine (mentorhubnetworks@gmail.com)",
)
# SEC allows ~10 req/s; stay well under to be a good citizen.
SEC_RATE_PER_MIN = _i("SEC_RATE_PER_MIN", 300)
# How long a cached companyfacts payload is considered fresh (hours).
# Fundamentals only change on new filings, so a long TTL is fine.
SEC_CACHE_TTL_HOURS = _i("SEC_CACHE_TTL_HOURS", 20)


def get_config() -> FundamentalsConfig:
    """Build a fresh config from the current environment.

    Not memoised on purpose — reading env each call means an admin can change a
    threshold and the next nightly run picks it up without a process restart,
    the same tunable-gate contract the Pine/webhook config uses.
    """
    return FundamentalsConfig()
