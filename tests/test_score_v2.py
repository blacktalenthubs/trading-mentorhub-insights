"""Tests for Score v2 — signal-type-aware alert scoring.

v2 treats bounce/dip-buy signals differently from breakout signals:
- MA/EMA bounce types get full 25 pts for MA position (the MA *is* the level)
- Other bounce types get 10 pts when below both MAs (not 0)
- Below VWAP = 15 pts for bounces (neutral/expected), not 10
- R:R bonus of +5 when T1/risk >= 1.5
- Breakout signals score identically to v1
"""

from __future__ import annotations

import pytest

from analytics.intraday_rules import AlertSignal, AlertType, _score_alert, _score_alert_v2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(
    alert_type: AlertType = AlertType.MA_BOUNCE_20,
    direction: str = "BUY",
    confidence: str = "medium",
    vwap_position: str = "below VWAP",
    entry: float | None = 185.00,
    stop: float | None = 184.00,
    target_1: float | None = 187.00,
    target_2: float | None = 189.00,
    **kwargs,
) -> AlertSignal:
    return AlertSignal(
        symbol=kwargs.pop("symbol", "TEST"),
        alert_type=alert_type,
        direction=direction,
        price=kwargs.pop("price", entry or 185.00),
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence=confidence,
        vwap_position=vwap_position,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# TestScoreV2MaBounce — MA/EMA bounce types
# ---------------------------------------------------------------------------

class TestScoreV2MaBounce:
    """MA/EMA bounce types should get full 25pts MA position in v2."""

    @pytest.mark.parametrize("alert_type", [
        AlertType.MA_BOUNCE_20,
        AlertType.MA_BOUNCE_50,
        AlertType.MA_BOUNCE_100,
        AlertType.MA_BOUNCE_200,
        AlertType.EMA_BOUNCE_20,
        AlertType.EMA_BOUNCE_50,
        AlertType.EMA_BOUNCE_100,
    ])
    def test_ma_bounce_gets_full_ma_position(self, alert_type):
        """MA bounce below both MAs: v1=0, v2=25 for MA position factor."""
        sig = _make_signal(alert_type=alert_type, confidence="medium", vwap_position="below VWAP")
        # close below both MAs
        v1 = _score_alert(sig, ma20=190.0, ma50=195.0, close=185.0, vol_ratio=0.9)
        v2 = _score_alert_v2(sig, ma20=190.0, ma50=195.0, close=185.0, vol_ratio=0.9)
        # v1 gives 0 for MA position; v2 gives 25
        assert v2 > v1
        assert v2 >= v1 + 25  # at least 25 more from MA position

    def test_ma_bounce_above_both_mas(self):
        """When above both MAs, v1 and v2 MA position should both be 25."""
        sig = _make_signal(alert_type=AlertType.MA_BOUNCE_20)
        v1 = _score_alert(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.0)
        v2 = _score_alert_v2(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.0)
        # Both get 25 for MA position — so v2 may still be slightly higher from VWAP/RR
        assert v2 >= v1


# ---------------------------------------------------------------------------
# TestScoreV2NonMaBounce — other bounce types (PDL, support, etc.)
# ---------------------------------------------------------------------------

class TestScoreV2NonMaBounce:
    """Non-MA bounce types get 10 (not 0) when below both MAs."""

    @pytest.mark.parametrize("alert_type", [
        AlertType.PRIOR_DAY_LOW_RECLAIM,
        AlertType.WEEKLY_LEVEL_TOUCH,
    ])
    def test_non_ma_bounce_below_both_gets_10(self, alert_type):
        """Below both MAs: v1=0, v2=10 for MA position."""
        sig = _make_signal(alert_type=alert_type)
        v1 = _score_alert(sig, ma20=190.0, ma50=195.0, close=185.0, vol_ratio=0.9)
        v2 = _score_alert_v2(sig, ma20=190.0, ma50=195.0, close=185.0, vol_ratio=0.9)
        assert v2 > v1
        # v2 should be at least 10 more (MA position 0→10, plus VWAP 10→15)
        assert v2 >= v1 + 10

    def test_non_ma_bounce_vwap_below_is_neutral(self):
        """Below VWAP for bounce: v2 gives 15 (neutral) vs v1's 10."""
        sig = _make_signal(
            alert_type=AlertType.PRIOR_DAY_LOW_RECLAIM,
            vwap_position="below VWAP",
        )
        v1 = _score_alert(sig, ma20=190.0, ma50=195.0, close=185.0, vol_ratio=1.0)
        v2 = _score_alert_v2(sig, ma20=190.0, ma50=195.0, close=185.0, vol_ratio=1.0)
        assert v2 > v1


# ---------------------------------------------------------------------------
# TestScoreV2Breakout — breakout signals identical to v1
# ---------------------------------------------------------------------------

class TestScoreV2Breakout:
    """Breakout/non-bounce signals should score identically in v1 and v2."""

    @pytest.mark.parametrize("alert_type", [
        AlertType.PRIOR_DAY_HIGH_BREAKOUT,
        AlertType.WEEKLY_HIGH_BREAKOUT,
        AlertType.INSIDE_DAY_BREAKOUT,
        AlertType.OPENING_RANGE_BREAKOUT,
        AlertType.OUTSIDE_DAY_BREAKOUT,
    ])
    def test_breakout_scores_identical(self, alert_type):
        """Non-bounce signals: v1 == v2 (no R:R bonus on these fixtures)."""
        sig = _make_signal(
            alert_type=alert_type,
            vwap_position="above VWAP",
            confidence="high",
            entry=185.00,
            stop=184.00,
            target_1=186.00,  # R:R = 1.0, no bonus
        )
        v1 = _score_alert(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        v2 = _score_alert_v2(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        assert v2 == v1

    def test_breakout_with_rr_bonus(self):
        """Breakout with R:R >= 1.5 gets +5 bonus in v2."""
        sig = _make_signal(
            alert_type=AlertType.PRIOR_DAY_HIGH_BREAKOUT,
            vwap_position="above VWAP",
            confidence="medium",  # medium so base < 100, leaving room for bonus
            entry=185.00,
            stop=184.00,
            target_1=186.50,  # R:R = 1.5, qualifies
        )
        v1 = _score_alert(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        v2 = _score_alert_v2(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        assert v1 < 100, f"v1 must be < 100 to test bonus (was {v1})"
        assert v2 == v1 + 5


# ---------------------------------------------------------------------------
# TestMarch5Fixtures — real scenarios from March 5, 2026
# ---------------------------------------------------------------------------

class TestMarch5Fixtures:
    """Reproduce the March 5 scoring gap where good bounces scored B/C."""

    def test_googl_ma_bounce(self):
        """GOOGL MA bounce: v1~30 (C grade), v2 should be >= 60."""
        sig = _make_signal(
            symbol="GOOGL",
            alert_type=AlertType.MA_BOUNCE_50,
            confidence="medium",
            vwap_position="below VWAP",
            entry=171.50,
            stop=170.50,
            target_1=173.50,  # R:R = 2.0
            target_2=175.00,
        )
        v1 = _score_alert(sig, ma20=173.0, ma50=172.0, close=171.50, vol_ratio=0.6)
        v2 = _score_alert_v2(sig, ma20=173.0, ma50=172.0, close=171.50, vol_ratio=0.6)
        assert v1 <= 40, f"v1 should be low (was {v1})"
        assert v2 >= 60, f"v2 should be >= 60 (was {v2})"

    def test_spy_ma_bounce(self):
        """SPY MA bounce: v1 penalises below-VWAP; v2 significantly higher."""
        sig = _make_signal(
            symbol="SPY",
            alert_type=AlertType.MA_BOUNCE_20,
            confidence="high",
            vwap_position="below VWAP",
            entry=590.00,
            stop=588.50,
            target_1=592.50,  # R:R = 1.67
            target_2=595.00,
        )
        # close below 20MA but above 50MA → v1 gives 15 for MA position
        v1 = _score_alert(sig, ma20=590.50, ma50=588.00, close=590.00, vol_ratio=1.0)
        v2 = _score_alert_v2(sig, ma20=590.50, ma50=588.00, close=590.00, vol_ratio=1.0)
        assert v2 > v1, f"v2 ({v2}) should exceed v1 ({v1})"
        assert v2 >= 70, f"v2 should be >= 70 (was {v2})"

    def test_pltr_ema_bounce(self):
        """PLTR EMA bounce: v2 significantly higher than v1."""
        sig = _make_signal(
            symbol="PLTR",
            alert_type=AlertType.EMA_BOUNCE_20,
            confidence="high",
            vwap_position="below VWAP",
            entry=88.00,
            stop=87.00,
            target_1=90.00,  # R:R = 2.0
            target_2=92.00,
        )
        # close below 20MA but above 50MA → v1 gives 15 for MA position
        v1 = _score_alert(sig, ma20=89.0, ma50=87.0, close=88.0, vol_ratio=0.9)
        v2 = _score_alert_v2(sig, ma20=89.0, ma50=87.0, close=88.0, vol_ratio=0.9)
        assert v2 > v1, f"v2 ({v2}) should exceed v1 ({v1})"
        assert v2 >= 65, f"v2 should be >= 65 (was {v2})"


# ---------------------------------------------------------------------------
# TestScoreV2EdgeCases
# ---------------------------------------------------------------------------

class TestScoreV2EdgeCases:
    """Edge cases: None entry/stop, zero risk, score cap."""

    def test_none_entry_no_crash(self):
        """No entry price: R:R bonus should not crash."""
        sig = _make_signal(entry=None, stop=None, target_1=None)
        score = _score_alert_v2(sig, ma20=190.0, ma50=195.0, close=185.0, vol_ratio=1.0)
        assert 0 <= score <= 100

    def test_zero_risk_no_div_by_zero(self):
        """Entry == stop: R:R is undefined, should not crash."""
        sig = _make_signal(entry=185.0, stop=185.0, target_1=187.0)
        score = _score_alert_v2(sig, ma20=190.0, ma50=195.0, close=185.0, vol_ratio=1.0)
        assert 0 <= score <= 100

    def test_score_capped_at_100(self):
        """Score should never exceed 100 even with all bonuses."""
        sig = _make_signal(
            alert_type=AlertType.MA_BOUNCE_20,
            confidence="high",
            vwap_position="above VWAP",
            entry=185.0,
            stop=184.0,
            target_1=187.0,  # R:R = 2.0
        )
        score = _score_alert_v2(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=2.0)
        assert score <= 100

    def test_sell_signal_unchanged(self):
        """SELL signals should score the same in v1 and v2."""
        sig = _make_signal(
            alert_type=AlertType.RESISTANCE_PRIOR_HIGH,
            direction="SELL",
            vwap_position="above VWAP",
            confidence="high",
            entry=None,
            stop=None,
            target_1=None,
            target_2=None,
        )
        v1 = _score_alert(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        v2 = _score_alert_v2(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        assert v2 == v1


# ---------------------------------------------------------------------------
# TestScoreV2RRBonus
# ---------------------------------------------------------------------------

class TestScoreV2RRBonus:
    """R:R bonus: +5 when T1/risk >= 1.5."""

    def test_rr_below_threshold_no_bonus(self):
        """R:R = 1.0 → no bonus, scores differ only by signal-type factors."""
        sig = _make_signal(
            alert_type=AlertType.PRIOR_DAY_HIGH_BREAKOUT,
            vwap_position="above VWAP",
            confidence="high",
            entry=185.0,
            stop=184.0,
            target_1=186.0,  # R:R = 1.0
        )
        v1 = _score_alert(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        v2 = _score_alert_v2(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        assert v2 == v1  # no signal-type diff and no R:R bonus

    def test_rr_at_threshold_gets_bonus(self):
        """R:R = 1.5 → +5 bonus."""
        sig = _make_signal(
            alert_type=AlertType.PRIOR_DAY_HIGH_BREAKOUT,
            vwap_position="above VWAP",
            confidence="medium",  # medium keeps base < 100
            entry=185.0,
            stop=184.0,
            target_1=186.50,  # R:R = 1.5
        )
        v1 = _score_alert(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        v2 = _score_alert_v2(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        assert v1 < 100, f"v1 must be < 100 to test bonus (was {v1})"
        assert v2 == v1 + 5

    def test_rr_above_threshold_gets_bonus(self):
        """R:R = 3.0 → still +5 (no scaling)."""
        sig = _make_signal(
            alert_type=AlertType.PRIOR_DAY_HIGH_BREAKOUT,
            vwap_position="above VWAP",
            confidence="medium",  # medium keeps base < 100
            entry=185.0,
            stop=184.0,
            target_1=188.0,  # R:R = 3.0
        )
        v1 = _score_alert(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        v2 = _score_alert_v2(sig, ma20=180.0, ma50=175.0, close=185.0, vol_ratio=1.3)
        assert v1 < 100, f"v1 must be < 100 to test bonus (was {v1})"
        assert v2 == v1 + 5
