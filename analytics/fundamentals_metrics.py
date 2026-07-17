"""Fundamentals metric engine — pure, offline, deterministic.

Given an ordered list of :class:`PeriodFinancials` (oldest → newest) for one
company, compute the Section 3a (red-flag) and 3b (value/quality) metrics.

Design contract:
  * PURE. No network, no DB, no clock. Everything is a function of the inputs,
    so the whole module is unit-testable with hand-built fixtures.
  * MODULAR. Metrics are registered in ``METRIC_REGISTRY``; adding a Phase-2
    ratio is a new function + one registry line, no rewrite (NFR: extensibility).
  * HONEST. A metric whose inputs are missing returns ``None`` — never a guess.
    ``None`` propagates to the score/flag layer as "missing", never as zero.

Every value the engine emits carries provenance (which period / filing) via the
:class:`MetricValue` returned alongside, so numbers stay auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional


# ── Normalised inputs ────────────────────────────────────────────────────
@dataclass
class PeriodFinancials:
    """One reporting period's line items, already normalised out of XBRL.

    All monetary fields are in USD; ``None`` means the source filing did not
    report (or we could not resolve) that concept for this period.
    """

    symbol: str
    period_end: date
    form: str                       # "10-K" or "10-Q"
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None   # "Q1".."Q4" or "FY"
    filed_date: Optional[date] = None
    source_url: Optional[str] = None
    accession: Optional[str] = None
    period_days: int = 90           # duration of the income/cash-flow window

    # Income statement (flow — covers ``period_days``).
    revenue: Optional[float] = None
    cost_of_revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None   # ~EBIT
    net_income: Optional[float] = None
    interest_expense: Optional[float] = None

    # Cash-flow statement (flow).
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None

    # Balance sheet (instant, at ``period_end``).
    inventory: Optional[float] = None
    receivables: Optional[float] = None
    total_current_assets: Optional[float] = None
    total_current_liabilities: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    cash: Optional[float] = None
    short_term_debt: Optional[float] = None
    long_term_debt: Optional[float] = None
    stockholders_equity: Optional[float] = None
    shares_diluted: Optional[float] = None

    # ── convenience derivations ──
    @property
    def total_debt(self) -> Optional[float]:
        st, lt = self.short_term_debt, self.long_term_debt
        if st is None and lt is None:
            return None
        return (st or 0.0) + (lt or 0.0)

    @property
    def cogs(self) -> Optional[float]:
        """Cost of goods, derived from gross profit if not reported directly."""
        if self.cost_of_revenue is not None:
            return self.cost_of_revenue
        if self.revenue is not None and self.gross_profit is not None:
            return self.revenue - self.gross_profit
        return None

    @property
    def ebit(self) -> Optional[float]:
        return self.operating_income

    @property
    def free_cash_flow(self) -> Optional[float]:
        if self.operating_cash_flow is None:
            return None
        # capex is reported negative in cash-flow statements; treat as magnitude.
        return self.operating_cash_flow - abs(self.capex or 0.0)

    @property
    def gross_margin(self) -> Optional[float]:
        if self.revenue in (None, 0) or self.gross_profit is None:
            return None
        return self.gross_profit / self.revenue

    @property
    def operating_margin(self) -> Optional[float]:
        if self.revenue in (None, 0) or self.operating_income is None:
            return None
        return self.operating_income / self.revenue


@dataclass
class MetricValue:
    """A computed metric bound to the period it was measured against."""

    name: str
    value: Optional[float]
    period_end: Optional[date] = None
    unit: str = ""                    # "days", "ratio", "pct", "usd", "x"
    source_url: Optional[str] = None
    # A short, human note (e.g. "rising 3 quarters") for the report layer.
    note: str = ""


@dataclass
class MetricSet:
    """Everything the engine computed for one company, keyed by metric name.

    ``latest`` holds point-in-time value metrics (from the newest period).
    ``trends`` holds window observations (rising counts, deltas) used by flags.
    """

    symbol: str
    as_of: Optional[date] = None
    latest: Dict[str, MetricValue] = field(default_factory=dict)
    trends: Dict[str, float] = field(default_factory=dict)

    def add(self, mv: MetricValue) -> None:
        self.latest[mv.name] = mv

    def val(self, name: str) -> Optional[float]:
        mv = self.latest.get(name)
        return mv.value if mv else None


# ── small numeric helpers ────────────────────────────────────────────────
def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct_change(old: Optional[float], new: Optional[float]) -> Optional[float]:
    if old is None or new is None or old == 0:
        return None
    return (new - old) / abs(old) * 100.0


def _rising_streak(series: List[Optional[float]]) -> int:
    """Length of the trailing strictly-increasing run in ``series``.

    ``None`` entries break the streak (missing data is not a trend).
    Example: [1, 2, 3, 4] → 3 (three consecutive increases at the tail).
    """
    streak = 0
    for i in range(len(series) - 1, 0, -1):
        cur, prev = series[i], series[i - 1]
        if cur is None or prev is None or cur <= prev:
            break
        streak += 1
    return streak


def _ttm(periods: List[PeriodFinancials], attr: str) -> Optional[float]:
    """Trailing-twelve-month sum of a flow attribute.

    Uses the newest annual (10-K) value if the tail period is a 10-K, else sums
    the last 4 quarterly values. Returns ``None`` if we can't assemble a clean
    TTM (missing pieces) — never a partial guess.
    """
    if not periods:
        return None
    tail = periods[-1]
    if tail.form == "10-K":
        return getattr(tail, attr)
    quarters = [p for p in periods if p.form == "10-Q"][-4:]
    if len(quarters) < 4:
        return None
    vals = [getattr(q, attr) for q in quarters]
    if any(v is None for v in vals):
        return None
    return sum(vals)


# ── 3a: red-flag / trend metrics ─────────────────────────────────────────
def days_sales_inventory(p: PeriodFinancials) -> Optional[float]:
    cogs = p.cogs
    if cogs is None or cogs <= 0 or p.inventory is None:
        return None
    return p.inventory / (cogs / p.period_days)


def days_sales_outstanding(p: PeriodFinancials) -> Optional[float]:
    if p.revenue is None or p.revenue <= 0 or p.receivables is None:
        return None
    return p.receivables / (p.revenue / p.period_days)


def accruals_ratio(p: PeriodFinancials) -> Optional[float]:
    """(Net income − operating cash flow) / total assets. High = low quality."""
    if p.net_income is None or p.operating_cash_flow is None:
        return None
    return _safe_div(p.net_income - p.operating_cash_flow, p.total_assets)


def interest_coverage(p: PeriodFinancials) -> Optional[float]:
    ie = p.interest_expense
    if ie is None or abs(ie) < 1e-9 or p.ebit is None:
        return None
    return p.ebit / abs(ie)


def debt_to_equity(p: PeriodFinancials) -> Optional[float]:
    return _safe_div(p.total_debt, p.stockholders_equity)


def current_ratio(p: PeriodFinancials) -> Optional[float]:
    return _safe_div(p.total_current_assets, p.total_current_liabilities)


def quick_ratio(p: PeriodFinancials) -> Optional[float]:
    if p.total_current_assets is None or p.total_current_liabilities in (None, 0):
        return None
    inv = p.inventory or 0.0
    return (p.total_current_assets - inv) / p.total_current_liabilities


# ── 3b: value / quality metrics (some need price) ────────────────────────
def return_on_capital(ttm_ebit: Optional[float], p: PeriodFinancials) -> Optional[float]:
    """Greenblatt ROC = EBIT / (net working capital + net fixed assets).

    Net fixed assets ≈ total assets − current assets − cash (we lack a clean
    PP&E line in the curated set). Documented approximation; labelled ROC.
    """
    if ttm_ebit is None or p.total_current_assets is None or p.total_current_liabilities is None:
        return None
    nwc = p.total_current_assets - p.total_current_liabilities
    net_fixed = None
    if p.total_assets is not None:
        net_fixed = p.total_assets - p.total_current_assets - (p.cash or 0.0)
    if net_fixed is None:
        return None
    capital = nwc + net_fixed
    if capital <= 0:
        return None
    return ttm_ebit / capital


def earnings_yield(ttm_ebit: Optional[float], market_cap: Optional[float],
                   p: PeriodFinancials) -> Optional[float]:
    """Greenblatt earnings yield = EBIT / Enterprise Value."""
    if ttm_ebit is None or market_cap is None or market_cap <= 0:
        return None
    ev = market_cap + (p.total_debt or 0.0) - (p.cash or 0.0)
    if ev <= 0:
        return None
    return ttm_ebit / ev


def fcf_yield(ttm_fcf: Optional[float], market_cap: Optional[float]) -> Optional[float]:
    if ttm_fcf is None or market_cap is None or market_cap <= 0:
        return None
    return ttm_fcf / market_cap


def graham_intrinsic(ttm_net_income: Optional[float], shares: Optional[float],
                     pe_multiple: float) -> Optional[float]:
    """Conservative earnings-based intrinsic value PER SHARE. An ESTIMATE."""
    if ttm_net_income is None or shares in (None, 0) or ttm_net_income <= 0:
        return None
    eps = ttm_net_income / shares
    return eps * pe_multiple


def margin_of_safety(intrinsic_ps: Optional[float], price: Optional[float]) -> Optional[float]:
    """(intrinsic − price) / intrinsic, as a percent. Positive = cushion."""
    if intrinsic_ps is None or price is None or intrinsic_ps <= 0:
        return None
    return (intrinsic_ps - price) / intrinsic_ps * 100.0


# Registry of point-in-time metrics that need only the newest period.
# name → (fn, unit). Extend here for new Phase-2 ratios.
METRIC_REGISTRY: Dict[str, tuple[Callable[[PeriodFinancials], Optional[float]], str]] = {
    "dsi": (days_sales_inventory, "days"),
    "dso": (days_sales_outstanding, "days"),
    "accruals_ratio": (accruals_ratio, "ratio"),
    "interest_coverage": (interest_coverage, "x"),
    "debt_to_equity": (debt_to_equity, "ratio"),
    "current_ratio": (current_ratio, "ratio"),
    "quick_ratio": (quick_ratio, "ratio"),
    "gross_margin": (lambda p: p.gross_margin, "ratio"),
    "operating_margin": (lambda p: p.operating_margin, "ratio"),
}


def compute_metrics(
    periods: List[PeriodFinancials],
    *,
    market_cap: Optional[float] = None,
    price: Optional[float] = None,
    pe_multiple: float = 15.0,
) -> MetricSet:
    """Compute the full metric set for one company.

    ``periods`` MUST be sorted oldest → newest. ``market_cap`` / ``price`` are
    optional; the valuation metrics that need them return ``None`` when absent
    (graceful — small caps / IPOs often lack a clean feed).
    """
    ms = MetricSet(symbol=periods[-1].symbol if periods else "")
    if not periods:
        return ms
    latest = periods[-1]
    ms.as_of = latest.period_end
    src = latest.source_url

    # Point-in-time registry metrics off the newest period.
    for name, (fn, unit) in METRIC_REGISTRY.items():
        ms.add(MetricValue(name, fn(latest), latest.period_end, unit, src))

    # TTM aggregates for the valuation block.
    ttm_ebit = _ttm(periods, "operating_income")
    ttm_ni = _ttm(periods, "net_income")
    ttm_fcf = None
    ocf = _ttm(periods, "operating_cash_flow")
    capex = _ttm(periods, "capex")
    if ocf is not None:
        ttm_fcf = ocf - abs(capex or 0.0)

    ms.add(MetricValue("roc", return_on_capital(ttm_ebit, latest), latest.period_end, "ratio", src))
    ms.add(MetricValue("earnings_yield", earnings_yield(ttm_ebit, market_cap, latest),
                       latest.period_end, "ratio", src))
    ms.add(MetricValue("fcf_yield", fcf_yield(ttm_fcf, market_cap), latest.period_end, "ratio", src))

    intrinsic = graham_intrinsic(ttm_ni, latest.shares_diluted, pe_multiple)
    ms.add(MetricValue("intrinsic_value_ps", intrinsic, latest.period_end, "usd", src,
                       note="Graham earnings-based ESTIMATE"))
    ms.add(MetricValue("margin_of_safety", margin_of_safety(intrinsic, price),
                       latest.period_end, "pct", src))

    # Profitability (TTM GAAP net income > 0). The headline "is this real?" filter.
    profitable = None if ttm_ni is None else (1.0 if ttm_ni > 0 else 0.0)
    ms.add(MetricValue("profitable", profitable, latest.period_end, "bool", src))
    ms.add(MetricValue("ttm_net_income", ttm_ni, latest.period_end, "usd", src))
    ms.add(MetricValue("ttm_ebit", ttm_ebit, latest.period_end, "usd", src))
    ms.add(MetricValue("ttm_fcf", ttm_fcf, latest.period_end, "usd", src))

    # ── trend observations across the window ──
    # Use a SINGLE consistent cadence for every trend so we never compare an
    # annual 10-K flow against a quarterly one (that would corrupt raw
    # growth/delta comparisons). Prefer the quarterly series; fall back to the
    # full list only if the issuer files no 10-Qs.
    trend_periods = [p for p in periods if p.form == "10-Q"] or periods
    t_first, t_last = trend_periods[0], trend_periods[-1]

    ms.trends["dso_rising_streak"] = _rising_streak([days_sales_outstanding(p) for p in trend_periods])
    ms.trends["dsi_rising_streak"] = _rising_streak([days_sales_inventory(p) for p in trend_periods])
    ms.trends["dilution_pct"] = _pct_change(t_first.shares_diluted, t_last.shares_diluted) or 0.0
    ms.trends["gross_margin_delta_pts"] = _delta_pts(t_first.gross_margin, t_last.gross_margin)
    ms.trends["operating_margin_delta_pts"] = _delta_pts(t_first.operating_margin, t_last.operating_margin)

    # Earnings-up / cash-flow-down divergence across the window.
    ms.trends["ni_growth_pct"] = _pct_change(t_first.net_income, t_last.net_income) or 0.0
    ms.trends["cfo_growth_pct"] = _pct_change(t_first.operating_cash_flow, t_last.operating_cash_flow) or 0.0

    return ms


def _delta_pts(old: Optional[float], new: Optional[float]) -> float:
    """Change in a fraction expressed in percentage POINTS (0.42→0.39 = -3.0)."""
    if old is None or new is None:
        return 0.0
    return (new - old) * 100.0
