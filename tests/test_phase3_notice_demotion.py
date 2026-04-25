"""Phase 3a (2026-04-23 evening) — NOTICE-only rule demotion.

Weekly/monthly level rules still fire in evaluate_rules(), but the monitor.py
epilogue rewrites their AlertSignal so:
  - direction = "NOTICE"
  - entry / stop / target_1 / target_2 = None

These tests simulate the rewriter inline since the monitor.py loop sits inside
a long DB-bound poll function. The transformation is a small, isolated piece
of logic — easy to test as a standalone function applied to fixture signals.
"""
from __future__ import annotations

import pandas as pd

from alert_config import NOTICE_ONLY_RULES
from analytics.intraday_rules import AlertSignal, AlertType


def _apply_notice_rewrite(sig: AlertSignal, enabled: bool = True) -> AlertSignal:
    """Mirror of the rewrite in api/app/background/monitor.py epilogue.

    Kept here so we can unit-test the transformation without a DB / SQLAlchemy
    poll session. Same conditional + mutation set as the live code.
    """
    if not enabled:
        return sig
    if sig.alert_type.value in NOTICE_ONLY_RULES:
        sig.direction = "NOTICE"
        sig.entry = None
        sig.stop = None
        sig.target_1 = None
        sig.target_2 = None
    return sig


def _make_signal(alert_type: AlertType, direction: str = "BUY") -> AlertSignal:
    return AlertSignal(
        symbol="AAPL",
        alert_type=alert_type,
        direction=direction,
        price=272.50,
        entry=272.30,
        stop=271.85,
        target_1=272.80,
        target_2=274.48,
        confidence="high",
        message="weekly high broken",
        score=85,
    )


class TestNoticeOnlyRules:
    def test_weekly_high_breakout_demoted_to_notice(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.WEEKLY_HIGH_BREAKOUT))
        assert sig.direction == "NOTICE"
        assert sig.entry is None
        assert sig.stop is None
        assert sig.target_1 is None
        assert sig.target_2 is None
        # Non-actionable fields preserved (price, message, score still useful)
        assert sig.price == 272.50
        assert sig.score == 85
        assert sig.message == "weekly high broken"

    def test_weekly_level_touch_demoted(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.WEEKLY_LEVEL_TOUCH))
        assert sig.direction == "NOTICE"
        assert sig.entry is None

    def test_weekly_low_test_demoted(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.WEEKLY_LOW_TEST))
        assert sig.direction == "NOTICE"
        assert sig.entry is None

    def test_weekly_high_resistance_demoted_short(self):
        """SHORT-direction weekly resistance also rewritten to NOTICE."""
        sig = _apply_notice_rewrite(
            _make_signal(AlertType.WEEKLY_HIGH_RESISTANCE, direction="SHORT")
        )
        assert sig.direction == "NOTICE"
        assert sig.entry is None
        assert sig.stop is None

    def test_monthly_high_breakout_demoted(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.MONTHLY_HIGH_BREAKOUT))
        assert sig.direction == "NOTICE"
        assert sig.entry is None

    def test_monthly_level_touch_demoted(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.MONTHLY_LEVEL_TOUCH))
        assert sig.direction == "NOTICE"

    def test_monthly_low_test_demoted(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.MONTHLY_LOW_TEST))
        assert sig.direction == "NOTICE"

    def test_monthly_ema_touch_demoted(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.MONTHLY_EMA_TOUCH))
        assert sig.direction == "NOTICE"

    def test_monthly_high_resistance_demoted_short(self):
        sig = _apply_notice_rewrite(
            _make_signal(AlertType.MONTHLY_HIGH_RESISTANCE, direction="SHORT")
        )
        assert sig.direction == "NOTICE"
        assert sig.entry is None


class TestNonNoticeRulesUnchanged:
    """Rules NOT in NOTICE_ONLY_RULES must keep their actionable fields."""

    def test_pdh_retest_hold_keeps_buy_direction(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.PDH_RETEST_HOLD))
        assert sig.direction == "BUY"
        assert sig.entry == 272.30
        assert sig.stop == 271.85
        assert sig.target_1 == 272.80
        assert sig.target_2 == 274.48

    def test_ema_bounce_20_keeps_buy_direction(self):
        sig = _apply_notice_rewrite(_make_signal(AlertType.EMA_BOUNCE_20))
        assert sig.direction == "BUY"
        assert sig.entry == 272.30

    def test_pdh_rejection_keeps_short(self):
        sig = _apply_notice_rewrite(
            _make_signal(AlertType.PDH_REJECTION, direction="SHORT")
        )
        assert sig.direction == "SHORT"
        assert sig.entry == 272.30


class TestNoticeFlagDisabled:
    """When NOTICE_ONLY_RULES_ENABLED=false, weekly/monthly fire as normal."""

    def test_weekly_high_breakout_keeps_buy_when_disabled(self):
        sig = _apply_notice_rewrite(
            _make_signal(AlertType.WEEKLY_HIGH_BREAKOUT), enabled=False
        )
        assert sig.direction == "BUY"
        assert sig.entry == 272.30
        assert sig.target_1 == 272.80


class TestNoticeOnlyRulesSetMembership:
    """Sanity-check the set itself — exact 9 rules from the spec."""

    def test_set_contains_expected_9_rules(self):
        assert NOTICE_ONLY_RULES == {
            "weekly_level_touch",
            "weekly_high_breakout",
            "weekly_low_test",
            "weekly_high_resistance",
            "monthly_level_touch",
            "monthly_high_breakout",
            "monthly_low_test",
            "monthly_ema_touch",
            "monthly_high_resistance",
        }

    def test_set_size_is_nine(self):
        assert len(NOTICE_ONLY_RULES) == 9
