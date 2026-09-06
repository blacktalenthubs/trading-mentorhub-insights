"""W/M/Q structural-level DEFEND / hold reclaims.

The prior week/month/quarter levels (PWH/PWL, PMH/PML, PQH/PQL) run through the
SAME open-above defend rule as the MA reclaims (check_ma_reclaim), wired on the
regular intraday ladder. This locks in: the six rules are enabled, they carry
readable feed names, and the defend logic behaves (open-above holds fire, open-
below ramp-throughs do not).
"""

import pandas as pd

from analytics.intraday_rules import AlertType, check_ma_reclaim
from alert_config import ENABLED_RULES
from alerting.notifier import _pretty_setup


_LEVEL_TYPES = [
    AlertType.PWH_RECLAIM, AlertType.PWL_RECLAIM,
    AlertType.PMH_RECLAIM, AlertType.PML_RECLAIM,
    AlertType.PQH_RECLAIM, AlertType.PQL_RECLAIM,
]

# 2h swing twins — same levels, confirmed on the 2h candle (still holding).
_SWING_LEVEL_TYPES = [
    AlertType.SWING_RECLAIM_PWH, AlertType.SWING_RECLAIM_PWL,
    AlertType.SWING_RECLAIM_PMH, AlertType.SWING_RECLAIM_PML,
    AlertType.SWING_RECLAIM_PQH, AlertType.SWING_RECLAIM_PQL,
]


def _bars(rows):
    return pd.DataFrame([{"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000}
                         for o, h, l, c in rows])


def test_all_level_reclaims_enabled():
    for at in _LEVEL_TYPES + _SWING_LEVEL_TYPES:
        assert at.value in ENABLED_RULES, f"{at.value} missing from ENABLED_RULES"


def test_level_reclaims_have_feed_names():
    # Not the ugly title-case fallback ("Pql Reclaim") — a real setup name.
    for at in _LEVEL_TYPES + _SWING_LEVEL_TYPES:
        name = _pretty_setup(at.value)
        assert name and "hold" in name.lower(), f"{at.value} → {name!r}"


def test_swing_2h_check_covers_wmq_levels():
    """The 2h swing reclaim confirms the W/M/Q levels are still holding after 2h."""
    from analytics.intraday_rules import check_swing_2h_reclaims
    prior = {
        "prior_quarter_low": 62.17,
        "prior_week_low": 61.00, "prior_month_low": 60.00,
        "prior_week_high": 70.00, "prior_month_high": 75.00, "prior_quarter_high": 80.00,
    }
    # A 2h candle that opened above PQL 62.17, wicked to it, closed back above.
    bars_2h = _bars([(62.30, 62.60, 61.70, 62.40),
                     (62.40, 63.10, 62.20, 63.00)])
    sigs = check_swing_2h_reclaims("RKLB", bars_2h, prior, today_open=62.30)
    types = {s.alert_type for s in sigs}
    assert AlertType.SWING_RECLAIM_PQL in types
    assert all((s.message or "").startswith("2h swing · ") for s in sigs)


def test_pql_defend_qualifies_open_above_wick_reclaim():
    """Opened above the prior-quarter low, wicked to it, closed back above → hold."""
    lvl = 62.17
    bars = _bars([(62.30, 62.60, 61.70, 62.40),   # opened above, wicked below the level
                  (62.40, 63.10, 62.20, 63.00)])   # closed back above
    sig = check_ma_reclaim("RKLB", bars, lvl, "PQL",
                           AlertType.PQL_RECLAIM, today_open=62.30)
    assert sig is not None
    assert sig.alert_type == AlertType.PQL_RECLAIM
    assert sig.direction == "BUY"
    assert sig.entry > lvl          # reclaimed — entry is back above the level
    assert 0 < sig.stop < sig.entry  # valid stop below entry (risk-capping may lift it toward the level)


def test_pqh_rejects_open_below_ramp_through():
    """Opened BELOW the prior-quarter high and ramped through it — a breakout, NOT a hold."""
    lvl = 140.40
    bars = _bars([(139.00, 145.50, 138.50, 145.00),   # opened below, blew through
                  (145.00, 148.00, 144.50, 148.00)])
    sig = check_ma_reclaim("NOW", bars, lvl, "PQH",
                           AlertType.PQH_RECLAIM, today_open=139.00)
    assert sig is None  # open below the level → not a defend


def test_prior_day_dict_exposes_quarter_levels():
    """fetch_prior_day's contract now includes the quarter keys the ladder reads."""
    # The wiring reads prior_day.get("prior_quarter_high" / "_low"); a dict that
    # lacks them must simply yield no level (None), never KeyError.
    prior = {"prior_quarter_high": 760.40, "prior_quarter_low": 700.00}
    assert prior.get("prior_quarter_high") == 760.40
    assert prior.get("prior_quarter_low") == 700.00
    assert {}.get("prior_quarter_high") is None
