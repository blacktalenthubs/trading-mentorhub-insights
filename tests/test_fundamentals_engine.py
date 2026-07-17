"""End-to-end Fundamentals Engine orchestrator test.

Exercises analytics/fundamentals_engine_refresh against an in-memory SQLite DB
with EDGAR monkeypatched (NO network): persistence, idempotency, and NEW-flag
detection for the alert hook.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date

import pytest

# Import the API package with a clean cwd (same guard as test_focus_list).
_HERE = os.path.dirname(os.path.abspath(__file__))
_API = os.path.join(_HERE, "..", "api")
if _API not in sys.path:
    sys.path.insert(0, _API)

_prev_cwd = os.getcwd()
os.chdir(tempfile.mkdtemp())
try:
    from app.config import get_settings
    get_settings()
    import app.models  # noqa: F401 — register models for create_all
    from app.database import Base
    from app.models.fundamentals_engine import FundFinancials, FundFlag, FundScore
    from app.models.watchlist import WatchlistItem
finally:
    os.chdir(_prev_cwd)

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from analytics import fundamentals_engine_refresh as eng  # noqa: E402
from analytics.fundamentals_metrics import PeriodFinancials  # noqa: E402


def _factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _quarters(receivables):
    """Four quarters; caller supplies the receivables series to drive DSO."""
    ends = [date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31), date(2025, 3, 31)]
    out = []
    for e, r in zip(ends, receivables):
        out.append(PeriodFinancials(
            symbol="TST", period_end=e, form="10-Q", period_days=91,
            revenue=1000.0, cost_of_revenue=600.0, gross_profit=400.0,
            receivables=r, inventory=200.0, net_income=80.0, operating_cash_flow=90.0,
            operating_income=120.0, interest_expense=-10.0, total_assets=2000.0,
            total_current_assets=800.0, total_current_liabilities=300.0, cash=200.0,
            long_term_debt=300.0, stockholders_equity=900.0, shares_diluted=1000.0,
            source_url="https://sec.gov/x", accession="0001-A",
        ))
    return out


@pytest.fixture
def factory(monkeypatch):
    monkeypatch.setattr(eng, "ticker_to_cik", lambda s: 111)
    return _factory()


def _seed_watchlist(factory, symbol="TST"):
    with factory() as s:
        s.add(WatchlistItem(user_id=1, symbol=symbol))
        s.commit()


def test_refresh_persists_financials_metrics_score(factory, monkeypatch):
    monkeypatch.setattr(eng, "load_financials", lambda sym, **k: _quarters([100, 100, 100, 100]))
    _seed_watchlist(factory)

    summary = eng.refresh_all(factory, as_of=date(2025, 4, 1), notify=False)
    assert summary["scored"] == 1
    assert summary["failures"] == 0

    with factory() as s:
        assert s.execute(select(FundFinancials).where(FundFinancials.symbol == "TST")).all()
        score = s.execute(select(FundScore).where(FundScore.symbol == "TST")).scalar_one()
        assert score.profitable is True
        assert score.latest_period_end == date(2025, 3, 31)


def test_rerun_is_idempotent(factory, monkeypatch):
    monkeypatch.setattr(eng, "load_financials", lambda sym, **k: _quarters([100, 100, 100, 100]))
    _seed_watchlist(factory)

    eng.refresh_all(factory, as_of=date(2025, 4, 1), notify=False)
    eng.refresh_all(factory, as_of=date(2025, 4, 1), notify=False)   # same day again

    with factory() as s:
        fin = s.execute(select(FundFinancials).where(FundFinancials.symbol == "TST")).all()
        assert len(fin) == 4          # 4 periods, not 8 — updated in place
        scores = s.execute(select(FundScore).where(FundScore.symbol == "TST")).all()
        assert len(scores) == 1       # one score row for the as-of date


def test_new_flag_detected_and_alerts(factory, monkeypatch):
    sent = []
    # First run: clean receivables → no DSO flag.
    monkeypatch.setattr(eng, "load_financials", lambda sym, **k: _quarters([100, 100, 100, 100]))
    _seed_watchlist(factory)
    eng.refresh_all(factory, as_of=date(2025, 4, 1), notify=False)

    # Second run, later date: rising receivables → DSO flag appears NEW → alert.
    monkeypatch.setattr(eng, "load_financials", lambda sym, **k: _quarters([80, 110, 150, 200]))
    monkeypatch.setattr(eng, "_send_telegram_maybe", None, raising=False)

    def _fake_alert(symbol, new_flags):
        sent.append((symbol, [f.code for f in new_flags]))
    monkeypatch.setattr(eng, "_alert_new_flags", _fake_alert)

    eng.refresh_all(factory, as_of=date(2025, 5, 1), notify=True)

    assert sent, "expected an alert for the newly-appeared DSO flag"
    assert "dso_rising" in sent[0][1]

    with factory() as s:
        flags = s.execute(
            select(FundFlag).where(FundFlag.symbol == "TST", FundFlag.code == "dso_rising")
        ).all()
        assert flags   # persisted


def test_no_edgar_data_marks_company_and_skips(factory, monkeypatch):
    from app.models.fundamentals_engine import FundCompany
    monkeypatch.setattr(eng, "load_financials", lambda sym, **k: [])
    _seed_watchlist(factory, "ETF")

    summary = eng.refresh_all(factory, as_of=date(2025, 4, 1), notify=False)
    assert summary["no_data"] == 1
    assert summary["scored"] == 0
    with factory() as s:
        row = s.get(FundCompany, "ETF")
        assert row is not None and row.no_edgar_data is True
