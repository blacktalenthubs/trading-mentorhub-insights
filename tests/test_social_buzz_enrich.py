"""Tests for the Social-feed value-add pure helpers.

Buzz-trend / earnings enrichment (analytics/social_trend) and the per-user
watchlist-buzz trigger (analytics/social_watchlist_alert._qualifies). No DB.
"""

from __future__ import annotations

from datetime import date, timedelta

from analytics.social_trend import (
    earnings_in_days, is_accelerating, mentions_series,
)
from analytics.social_watchlist_alert import _qualifies


class TestEarningsInDays:
    def test_none(self):
        assert earnings_in_days(None, date(2026, 6, 1)) is None

    def test_today(self):
        assert earnings_in_days(date(2026, 6, 1), date(2026, 6, 1)) == 0

    def test_week_out(self):
        assert earnings_in_days(date(2026, 6, 8), date(2026, 6, 1)) == 7

    def test_past_is_negative(self):
        assert earnings_in_days(date(2026, 5, 30), date(2026, 6, 1)) == -2


class TestMentionsSeries:
    def test_orders_oldest_to_newest_plus_current(self):
        # prior is newest-first: [newest=10, older=8] → series 8,10 + current 12.
        prior = [[{"symbol": "AAA", "mentions": 10}], [{"symbol": "AAA", "mentions": 8}]]
        assert mentions_series("AAA", prior, 12) == [8, 10, 12]

    def test_skips_snapshots_missing_the_symbol(self):
        prior = [
            [{"symbol": "AAA", "mentions": 10}],
            [{"symbol": "BBB", "mentions": 99}],   # AAA absent — skipped
            [{"symbol": "AAA", "mentions": 6}],
        ]
        # oldest→newest of present: 6, 10, then current 14.
        assert mentions_series("AAA", prior, 14) == [6, 10, 14]

    def test_new_symbol_only_current(self):
        assert mentions_series("ZZZ", [], 5) == [5]


class TestIsAccelerating:
    def test_recent_step(self):
        assert is_accelerating([10, 12, 30]) is True

    def test_window_growth_only(self):
        # last step small (5%), but window 10->20 = +100%.
        assert is_accelerating([10, 15, 19, 20]) is True

    def test_flat(self):
        assert is_accelerating([30, 30, 30]) is False

    def test_falling(self):
        assert is_accelerating([30, 20, 10]) is False

    def test_too_few_points(self):
        assert is_accelerating([10]) is False
        assert is_accelerating([]) is False


class TestQualifies:
    def test_accelerating_wins(self):
        assert _qualifies({"accelerating": True}, rank=99) == "buzz accelerating"

    def test_growth_spike(self):
        assert _qualifies({"growth_pct": 80}, rank=99) == "+80% mentions today"

    def test_top_n_rank(self):
        assert _qualifies({"growth_pct": 5}, rank=5) == "#5 most-talked-about"

    def test_none(self):
        assert _qualifies({"growth_pct": 10}, rank=20) is None
