"""Tests for the EDGAR XBRL normaliser (offline — synthetic companyfacts)."""

from datetime import date

from analytics import edgar_client
from analytics.edgar_client import get_period_financials


def _fact(start, end, val, form, filed, accn="0000-00-000000"):
    d = {"end": end, "val": val, "form": form, "filed": filed, "accn": accn,
         "fy": int(end[:4]), "fp": "Q2"}
    if start is not None:
        d["start"] = start
    return d


def _companyfacts():
    """Two quarters (Q1 & Q2 2025) of a minimal filer, plus a restatement of Q1
    net income (later 'filed' must win)."""
    def dur(tag, unit, facts):
        return {tag: {"units": {unit: facts}}}

    gaap = {}
    # Net income (anchor) — quarterly durations ~91 days.
    gaap.update(dur("NetIncomeLoss", "USD", [
        _fact("2025-01-01", "2025-03-31", 100.0, "10-Q", "2025-04-20", "0001-A"),
        _fact("2025-01-01", "2025-03-31", 111.0, "10-Q", "2025-07-25", "0001-B"),  # restated, newer
        _fact("2025-04-01", "2025-06-30", 120.0, "10-Q", "2025-07-25", "0002-A"),
        # a full-year duration that must be IGNORED for a quarter anchor
        _fact("2024-01-01", "2024-12-31", 500.0, "10-K", "2025-02-15", "0000-A"),
    ]))
    gaap.update(dur("Revenues", "USD", [
        _fact("2025-01-01", "2025-03-31", 1000.0, "10-Q", "2025-04-20", "0001-A"),
        _fact("2025-04-01", "2025-06-30", 1100.0, "10-Q", "2025-07-25", "0002-A"),
    ]))
    # Instant balance-sheet concept (no 'start').
    gaap.update(dur("Assets", "USD", [
        _fact(None, "2025-03-31", 5000.0, "10-Q", "2025-04-20", "0001-A"),
        _fact(None, "2025-06-30", 5200.0, "10-Q", "2025-07-25", "0002-A"),
    ]))
    gaap.update(dur("InventoryNet", "USD", [
        _fact(None, "2025-03-31", 300.0, "10-Q", "2025-04-20", "0001-A"),
        _fact(None, "2025-06-30", 320.0, "10-Q", "2025-07-25", "0002-A"),
    ]))
    return {"cik": 1234567, "facts": {"us-gaap": gaap}}


def _find(periods, end, form):
    return next(p for p in periods if p.period_end == end and p.form == form)


def test_normalises_all_periods_oldest_first():
    periods = get_period_financials(_companyfacts(), "TST", max_periods=12)
    # One 10-K (FY2024) + two 10-Qs, sorted oldest → newest.
    assert [(p.period_end, p.form) for p in periods] == [
        (date(2024, 12, 31), "10-K"),
        (date(2025, 3, 31), "10-Q"),
        (date(2025, 6, 30), "10-Q"),
    ]


def test_restatement_latest_filed_wins():
    q1 = _find(get_period_financials(_companyfacts(), "TST"), date(2025, 3, 31), "10-Q")
    assert q1.net_income == 111.0   # restated value (filed 2025-07-25) beats 100.0


def test_flow_vs_instant_concepts_attached():
    q1 = _find(get_period_financials(_companyfacts(), "TST"), date(2025, 3, 31), "10-Q")
    assert q1.revenue == 1000.0        # duration flow matched by end+quarter length
    assert q1.total_assets == 5000.0   # instant matched by end
    assert q1.inventory == 300.0


def test_provenance_url_built():
    periods = get_period_financials(_companyfacts(), "TST")
    assert periods[0].source_url and "edgar/data/1234567" in periods[0].source_url


def test_no_anchor_returns_empty():
    assert get_period_financials({"cik": 1, "facts": {"us-gaap": {}}}, "TST") == []


def test_annual_flow_stays_on_the_10k_not_a_quarter():
    # The full-year NetIncomeLoss (500) belongs to the 10-K period only — no
    # 10-Q may carry it (annual duration must never match a quarter context).
    periods = get_period_financials(_companyfacts(), "TST")
    k = _find(periods, date(2024, 12, 31), "10-K")
    assert k.net_income == 500.0
    assert all(p.net_income != 500.0 for p in periods if p.form == "10-Q")


def test_ticker_to_cik_uses_map(monkeypatch):
    monkeypatch.setattr(edgar_client, "_cik_map", {"AAPL": 320193})
    assert edgar_client.ticker_to_cik("aapl") == 320193
    assert edgar_client.ticker_to_cik("NOPE") is None
