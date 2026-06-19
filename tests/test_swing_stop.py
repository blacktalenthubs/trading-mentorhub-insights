"""Tests for the swing prior-day-low trailing stop (Sub-spec L / #64)."""

from analytics.swing_stop import swing_trailing_stop


def test_day1_uses_morning_low():
    assert swing_trailing_stop(100.0, []) == 100.0


def test_day2_uses_prior_day_low():
    assert swing_trailing_stop(100.0, [102.0]) == 102.0


def test_tracks_most_recent_completed_day():
    assert swing_trailing_stop(100.0, [102.0, 104.0, 106.0]) == 106.0


def test_ratchet_never_lowers_the_stop():
    # prior day low dipped to 103, but current stop is already 105 → hold 105
    assert swing_trailing_stop(100.0, [103.0], current_stop=105.0) == 105.0


def test_ratchet_raises_when_prior_low_is_higher():
    assert swing_trailing_stop(100.0, [108.0], current_stop=105.0) == 108.0


def test_no_ratchet_follows_prior_low_down():
    assert swing_trailing_stop(100.0, [103.0], current_stop=105.0, ratchet=False) == 103.0
