"""Tests for analytics/strategy_analysis — classification + aggregation.

Pure logic, no DB/network.
"""

from __future__ import annotations

from analytics.strategy_analysis import aggregate_patterns, classify_pattern


class TestClassifyPattern:
    def test_swing(self):
        # EOW avg beats EOD avg by >= 0.5 with healthy EOW win → Swing, promote.
        r = classify_pattern(avg_eod=0.3, win_eod=55, avg_eow=1.5, win_eow=65, n=20, n_eow=20)
        assert r["classification"] == "Swing"
        assert r["confidence"] == "ok"
        assert r["recommendation"] == "promote"

    def test_day(self):
        # Strong EOD, fades by EOW, moderate win → Day, keep.
        r = classify_pattern(avg_eod=1.0, win_eod=55, avg_eow=0.4, win_eow=48, n=20, n_eow=20)
        assert r["classification"] == "Day"
        assert r["recommendation"] == "keep"

    def test_avoid(self):
        r = classify_pattern(avg_eod=-0.5, win_eod=40, avg_eow=-0.2, win_eow=45, n=20, n_eow=20)
        assert r["classification"] == "Avoid"
        assert r["recommendation"] == "stop"

    def test_low_confidence_blocks_promote(self):
        # Great numbers but tiny sample → low confidence, never promote.
        r = classify_pattern(avg_eod=2.0, win_eod=80, avg_eow=0.5, win_eow=80, n=3, n_eow=3)
        assert r["confidence"] == "low"
        assert r["recommendation"] == "keep"

    def test_swing_boundary(self):
        # diff exactly SWING_EDGE_PCT (0.5) and win exactly 50 → Swing.
        r = classify_pattern(avg_eod=0.2, win_eod=50, avg_eow=0.7, win_eow=50, n=12, n_eow=12)
        assert r["classification"] == "Swing"

    def test_no_eow_data_uses_eod(self):
        # No matured EOW yet → classify from EOD only.
        r = classify_pattern(avg_eod=1.2, win_eod=70, avg_eow=None, win_eow=None, n=15, n_eow=0)
        assert r["classification"] == "Day"


class TestAggregatePatterns:
    def test_groups_and_ranks(self):
        rows = [
            # winner: strong EOW
            {"alert_type": "p_swing", "ret_eod_pct": 0.2, "ret_eow_pct": 2.0},
            {"alert_type": "p_swing", "ret_eod_pct": 0.4, "ret_eow_pct": 1.0},
            # loser
            {"alert_type": "p_bad", "ret_eod_pct": -1.0, "ret_eow_pct": -0.5},
            {"alert_type": "p_bad", "ret_eod_pct": -0.5, "ret_eow_pct": -1.5},
        ]
        out = aggregate_patterns(rows, label_map={"p_swing": "Swinger"})
        # Ranked by avg EOW return desc → swing pattern first.
        assert out[0]["alert_type"] == "p_swing"
        assert out[0]["label"] == "Swinger"
        assert out[0]["n"] == 2
        assert out[0]["avg_ret_eow"] == 1.5
        assert out[0]["win_eow_pct"] == 100.0
        assert out[-1]["alert_type"] == "p_bad"
        assert out[-1]["classification"] == "Avoid"
        assert out[-1]["recommendation"] == "stop"

    def test_eow_null_only_eod(self):
        rows = [
            {"alert_type": "p", "ret_eod_pct": 1.0, "ret_eow_pct": None},
            {"alert_type": "p", "ret_eod_pct": -1.0, "ret_eow_pct": None},
        ]
        out = aggregate_patterns(rows)
        assert out[0]["n"] == 2
        assert out[0]["n_eow"] == 0
        assert out[0]["avg_ret_eow"] is None
        assert out[0]["win_eod_pct"] == 50.0
