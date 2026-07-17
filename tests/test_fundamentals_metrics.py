"""Unit tests for the pure fundamentals metric engine (no network/DB)."""

from datetime import date

import pytest

from analytics.fundamentals_metrics import (
    PeriodFinancials,
    compute_metrics,
    days_sales_inventory,
    days_sales_outstanding,
    accruals_ratio,
    interest_coverage,
    debt_to_equity,
    current_ratio,
    quick_ratio,
    return_on_capital,
    earnings_yield,
    margin_of_safety,
    _rising_streak,
    _ttm,
)


def _q(period_end, **kw):
    base = dict(symbol="TST", period_end=period_end, form="10-Q", period_days=91)
    base.update(kw)
    return PeriodFinancials(**base)


def test_dsi_dso_basic():
    p = _q(date(2025, 3, 31), cost_of_revenue=910.0, inventory=910.0,
           revenue=1820.0, receivables=910.0)
    # inventory / (cogs/91) = 910 / (910/91) = 91 days
    assert days_sales_inventory(p) == pytest.approx(91.0)
    # receivables / (rev/91) = 910 / (1820/91) = 45.5 days
    assert days_sales_outstanding(p) == pytest.approx(45.5)


def test_metrics_return_none_when_inputs_missing():
    p = _q(date(2025, 3, 31))  # nothing populated
    assert days_sales_inventory(p) is None
    assert days_sales_outstanding(p) is None
    assert accruals_ratio(p) is None
    assert interest_coverage(p) is None
    assert debt_to_equity(p) is None


def test_cogs_derived_from_gross_profit():
    p = _q(date(2025, 3, 31), revenue=1000.0, gross_profit=400.0, inventory=150.0)
    # cogs = 1000 - 400 = 600 ; dsi = 150 / (600/91) = 22.75
    assert p.cogs == pytest.approx(600.0)
    assert days_sales_inventory(p) == pytest.approx(150 / (600 / 91))


def test_accruals_ratio_sign():
    # NI above CFO → positive accruals (lower quality).
    p = _q(date(2025, 3, 31), net_income=200.0, operating_cash_flow=50.0, total_assets=1500.0)
    assert accruals_ratio(p) == pytest.approx((200 - 50) / 1500)


def test_interest_coverage_and_leverage():
    p = _q(date(2025, 3, 31), operating_income=300.0, interest_expense=-100.0,
           short_term_debt=200.0, long_term_debt=800.0, stockholders_equity=500.0)
    assert interest_coverage(p) == pytest.approx(3.0)      # 300 / |−100|
    assert debt_to_equity(p) == pytest.approx(2.0)         # 1000 / 500


def test_current_and_quick_ratio():
    p = _q(date(2025, 3, 31), total_current_assets=500.0,
           total_current_liabilities=250.0, inventory=100.0)
    assert current_ratio(p) == pytest.approx(2.0)
    assert quick_ratio(p) == pytest.approx((500 - 100) / 250)


def test_free_cash_flow_treats_capex_as_magnitude():
    p = _q(date(2025, 3, 31), operating_cash_flow=500.0, capex=-120.0)
    assert p.free_cash_flow == pytest.approx(380.0)


def test_rising_streak_helper():
    assert _rising_streak([1, 2, 3, 4]) == 3
    assert _rising_streak([4, 3, 2, 1]) == 0
    assert _rising_streak([1, 2, None, 4]) == 0   # None right before tail → can't confirm a rise
    assert _rising_streak([5, 5, 6]) == 1          # equal is not "rising"


def test_ttm_sums_four_quarters():
    ps = [_q(date(2024, 6, 30), net_income=10.0),
          _q(date(2024, 9, 30), net_income=20.0),
          _q(date(2024, 12, 31), net_income=30.0),
          _q(date(2025, 3, 31), net_income=40.0)]
    assert _ttm(ps, "net_income") == pytest.approx(100.0)


def test_ttm_uses_annual_when_tail_is_10k():
    ps = [_q(date(2024, 3, 31), net_income=5.0),
          PeriodFinancials(symbol="TST", period_end=date(2024, 12, 31),
                           form="10-K", period_days=365, net_income=99.0)]
    assert _ttm(ps, "net_income") == pytest.approx(99.0)


def test_ttm_none_when_incomplete():
    ps = [_q(date(2024, 12, 31), net_income=30.0),
          _q(date(2025, 3, 31), net_income=40.0)]
    assert _ttm(ps, "net_income") is None   # only 2 quarters


def test_greenblatt_roc_and_earnings_yield():
    p = _q(date(2025, 3, 31), total_current_assets=400.0, total_current_liabilities=200.0,
           total_assets=1000.0, cash=100.0, short_term_debt=0.0, long_term_debt=300.0)
    ttm_ebit = 200.0
    # nwc = 200 ; net_fixed = 1000 - 400 - 100 = 500 ; capital = 700 ; roc = 200/700
    assert return_on_capital(ttm_ebit, p) == pytest.approx(200 / 700)
    # ev = mktcap 1000 + debt 300 - cash 100 = 1200 ; ey = 200/1200
    assert earnings_yield(ttm_ebit, 1000.0, p) == pytest.approx(200 / 1200)


def test_margin_of_safety():
    # intrinsic 100, price 70 → 30% cushion
    assert margin_of_safety(100.0, 70.0) == pytest.approx(30.0)
    # price above intrinsic → negative
    assert margin_of_safety(100.0, 130.0) == pytest.approx(-30.0)
    assert margin_of_safety(None, 70.0) is None


def test_compute_metrics_end_to_end_trends():
    # Four quarters with steadily rising DSO and net income up but CFO down.
    ps = []
    receivables = [100.0, 130.0, 170.0, 220.0]  # rising DSO
    ni = [50.0, 60.0, 70.0, 80.0]               # earnings up
    cfo = [60.0, 40.0, 20.0, 5.0]               # cash flow down
    ends = [date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31)]
    for i, e in enumerate(ends):
        ps.append(_q(e, revenue=1000.0, cost_of_revenue=600.0, receivables=receivables[i],
                     inventory=200.0, net_income=ni[i], operating_cash_flow=cfo[i],
                     operating_income=120.0, total_assets=2000.0, shares_diluted=1000.0))
    ms = compute_metrics(ps, market_cap=5000.0, price=1.0)
    assert ms.trends["dso_rising_streak"] == 3
    assert ms.trends["ni_growth_pct"] > 0
    assert ms.trends["cfo_growth_pct"] < 0
    assert ms.val("profitable") == 1.0   # ttm NI = 260 > 0
    assert ms.val("dso") is not None
