"""Unit tests for the fundamentals scoring & flag layer (config-driven, pure)."""

from datetime import date

from analytics.fundamentals_metrics import PeriodFinancials, compute_metrics
from analytics.fundamentals_scoring import CRITICAL, WARN, score_company
from fundamentals_config import get_config


def _q(period_end, **kw):
    base = dict(symbol="TST", period_end=period_end, form="10-Q", period_days=91)
    base.update(kw)
    return PeriodFinancials(**base)


def _four_quarters(**overrides):
    ends = [date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31)]
    out = []
    for e in ends:
        kw = dict(revenue=1000.0, cost_of_revenue=600.0, gross_profit=400.0,
                  receivables=100.0, inventory=200.0, net_income=80.0,
                  operating_cash_flow=90.0, operating_income=120.0,
                  interest_expense=-10.0, total_assets=2000.0,
                  total_current_assets=800.0, total_current_liabilities=300.0,
                  cash=200.0, long_term_debt=300.0, stockholders_equity=900.0,
                  shares_diluted=1000.0)
        kw.update(overrides)
        out.append(_q(e, **kw))
    return out


def test_healthy_company_scores_well_low_risk():
    ms = compute_metrics(_four_quarters(), market_cap=3000.0, price=1.0)
    res = score_company(ms)
    assert res.profitable is True
    assert res.risk_score < 30            # clean trends
    assert res.quality_score > 0
    codes = {f.code for f in res.flags}
    assert "profitable" in codes


def test_dso_rising_raises_warn_flag():
    ps = _four_quarters()
    for p, r in zip(ps, [80.0, 110.0, 150.0, 200.0]):   # rising receivables → DSO
        p.receivables = r
    ms = compute_metrics(ps, market_cap=3000.0, price=1.0)
    res = score_company(ms)
    codes = {f.code for f in res.flags}
    assert "dso_rising" in codes
    assert res.risk_score > 0


def test_earnings_cashflow_divergence_is_critical():
    ps = _four_quarters()
    ni = [50.0, 60.0, 70.0, 90.0]      # up
    cfo = [90.0, 60.0, 30.0, 10.0]     # down
    for p, n, c in zip(ps, ni, cfo):
        p.net_income, p.operating_cash_flow = n, c
    ms = compute_metrics(ps, market_cap=3000.0, price=1.0)
    res = score_company(ms)
    div = [f for f in res.flags if f.code == "cfo_divergence"]
    assert div and div[0].severity == CRITICAL


def test_unprofitable_flagged():
    ps = _four_quarters(net_income=-40.0)
    ms = compute_metrics(ps, market_cap=3000.0, price=1.0)
    res = score_company(ms)
    assert res.profitable is False
    assert any(f.code == "unprofitable" for f in res.flags)


def test_heavy_dilution_flag():
    ps = _four_quarters()
    for p, s in zip(ps, [1000.0, 1050.0, 1120.0, 1200.0]):   # +20% dilution
        p.shares_diluted = s
    ms = compute_metrics(ps, market_cap=3000.0, price=1.0)
    res = score_company(ms)
    dil = [f for f in res.flags if f.code == "dilution_heavy"]
    assert dil and dil[0].severity == CRITICAL


def test_thresholds_are_config_driven(monkeypatch):
    # Tighten the DSO streak requirement to 4 via env → a 3-quarter rise no
    # longer flags, proving thresholds aren't hardcoded.
    ps = _four_quarters()
    for p, r in zip(ps, [80.0, 110.0, 150.0, 200.0]):
        p.receivables = r
    ms = compute_metrics(ps, market_cap=3000.0, price=1.0)

    monkeypatch.setenv("FUND_DSO_RISING_QUARTERS", "4")
    cfg = get_config()
    res = score_company(ms, cfg)
    assert not any(f.code == "dso_rising" for f in res.flags)


def test_coverage_reported_for_sparse_data():
    # Only revenue/NI present → low coverage, no crash.
    ps = [_q(date(2025, 3, 31), revenue=1000.0, net_income=50.0)]
    ms = compute_metrics(ps, market_cap=None, price=None)
    res = score_company(ms)
    assert 0.0 <= res.quality_coverage <= 1.0
    assert 0.0 <= res.risk_coverage <= 1.0


def test_flags_sorted_critical_first():
    ps = _four_quarters()
    # induce dilution (critical) + margin compression (warn)
    for p, s, gp in zip(ps, [1000.0, 1100.0, 1150.0, 1200.0], [420.0, 400.0, 380.0, 360.0]):
        p.shares_diluted = s
        p.gross_profit = gp
    ms = compute_metrics(ps, market_cap=3000.0, price=1.0)
    res = score_company(ms)
    severities = [f.severity for f in res.flags]
    # first non-info flag should be critical before any warn
    non_info = [s for s in severities if s != "info"]
    if CRITICAL in non_info and WARN in non_info:
        assert non_info.index(CRITICAL) < non_info.index(WARN)
