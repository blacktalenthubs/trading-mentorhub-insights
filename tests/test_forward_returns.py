"""Tests for analytics/forward_returns — pure date math + return computation.

No DB/network: exercises the pure helpers that take a {date: close} map.
"""

from __future__ import annotations

from datetime import date

from analytics.forward_returns import (
    forward_pct,
    is_eow_matured,
    pick_close_on_or_before,
    week_friday,
)


class TestWeekFriday:
    def test_monday(self):
        # Mon 2026-06-01 → Fri 2026-06-05
        assert week_friday(date(2026, 6, 1)) == date(2026, 6, 5)

    def test_wednesday(self):
        assert week_friday(date(2026, 6, 3)) == date(2026, 6, 5)

    def test_friday_is_itself(self):
        assert week_friday(date(2026, 6, 5)) == date(2026, 6, 5)


class TestEowMatured:
    def test_not_matured_on_friday(self):
        # The Friday bar isn't closed yet on Friday.
        assert is_eow_matured(date(2026, 6, 3), today=date(2026, 6, 5)) is False

    def test_matured_after_friday(self):
        assert is_eow_matured(date(2026, 6, 3), today=date(2026, 6, 6)) is True

    def test_midweek_alert_before_friday(self):
        assert is_eow_matured(date(2026, 6, 3), today=date(2026, 6, 4)) is False


class TestPickCloseOnOrBefore:
    def test_exact_date(self):
        closes = {date(2026, 6, 5): 13.0}
        assert pick_close_on_or_before(closes, date(2026, 6, 5)) == 13.0

    def test_holiday_falls_back_to_prior_day(self):
        # Friday is a holiday (no bar) → use Thursday's close.
        closes = {date(2026, 6, 4): 12.0}  # Thursday
        assert pick_close_on_or_before(closes, date(2026, 6, 5)) == 12.0

    def test_none_when_no_bar_in_window(self):
        closes = {date(2026, 1, 1): 99.0}  # far away
        assert pick_close_on_or_before(closes, date(2026, 6, 5)) is None

    def test_respects_floor(self):
        # Only a bar before the floor exists → None (don't borrow a pre-alert close).
        closes = {date(2026, 6, 1): 10.0}
        assert pick_close_on_or_before(closes, date(2026, 6, 5), floor=date(2026, 6, 3)) is None


class TestForwardPct:
    def test_gain(self):
        assert forward_pct(100.0, 105.0) == 5.0

    def test_loss(self):
        assert forward_pct(100.0, 95.0) == -5.0

    def test_flat(self):
        assert forward_pct(100.0, 100.0) == 0.0

    def test_zero_fire_price_is_none(self):
        assert forward_pct(0.0, 105.0) is None

    def test_none_close_is_none(self):
        assert forward_pct(100.0, None) is None
