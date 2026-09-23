"""Weekly VP alert event detection — pure logic, no network/DB."""
from analytics.weekly_vp_alerts import detect

MON = "2026-09-21"


def _lv(sym, poc=100.0, vwap=None, val=None, week_open=None, prior_close=None):
    return {"symbol": sym, "poc": poc, "vwap": vwap, "val": val,
            "week_open": week_open, "prior_close": prior_close}


def test_support_when_at_level_and_opened_above():
    ev = detect([_lv("AAA", poc=100, week_open=103)], {"AAA": 100.5}, MON)
    assert len(ev) == 1 and ev[0]["event"] == "support" and ev[0]["level_name"] == "POC"
    assert ev[0]["key"] == "AAA:support:POC:2026-09-21"


def test_no_support_if_opened_below():
    # At the level but opened BELOW → not "holding support" (that'd be a test, not alerted).
    ev = detect([_lv("AAA", poc=100, week_open=98)], {"AAA": 100.4}, MON)
    assert ev == []


def test_reclaim_from_below():
    # Prior day closed below, price now just above → reclaim.
    ev = detect([_lv("BBB", poc=100, week_open=99, prior_close=98)], {"BBB": 101}, MON)
    assert len(ev) == 1 and ev[0]["event"] == "reclaim"


def test_reclaim_only_while_near():
    # Prior close below but price has run 5% above → past the reclaim band, no alert.
    ev = detect([_lv("BBB", poc=100, prior_close=98)], {"BBB": 105}, MON)
    assert ev == []


def test_loss_when_opened_above_now_below():
    ev = detect([_lv("CCC", poc=100, week_open=103)], {"CCC": 98}, MON)
    assert len(ev) == 1 and ev[0]["event"] == "loss"


def test_far_from_level_no_event():
    ev = detect([_lv("DDD", poc=100, week_open=108)], {"DDD": 110}, MON)
    assert ev == []


def test_multiple_levels_independent():
    lv = _lv("EEE", poc=100, vwap=120, val=90, week_open=101, prior_close=99)
    # price 100.5: at POC (support, opened above), far from vwap/val
    ev = detect([lv], {"EEE": 100.5}, MON)
    assert {e["level_name"] for e in ev} == {"POC"}


def test_missing_price_skipped():
    assert detect([_lv("FFF", poc=100, week_open=101)], {}, MON) == []
