"""Tests for reproject_after_stop() in analytics/signal_engine.py."""

from __future__ import annotations

import pytest


class TestReprojectAfterStop:
    """Tests for reproject_after_stop()."""

    def test_finds_next_support_below_broken_stop(self):
        """When 20 MA breaks, projects to 50 MA."""
        from analytics.signal_engine import reproject_after_stop

        result = reproject_after_stop(
            current_price=178.0,
            broken_stop=180.0,
            prior_low=174.0,
            ma20=181.0,     # above broken stop — skipped
            ma50=175.0,     # below broken stop — used
        )
        assert result is not None
        assert result["support"] == 175.0
        assert result["support_label"] == "50 SMA"

    def test_uses_ema_when_sma_above_broken(self):
        """Falls back to EMAs when SMAs are above broken stop."""
        from analytics.signal_engine import reproject_after_stop

        result = reproject_after_stop(
            current_price=178.0,
            broken_stop=180.0,
            prior_low=170.0,
            ma20=182.0,     # above
            ma50=185.0,     # above
            ema20=179.5,    # below — nearest to current price
            ema50=176.0,    # below
        )
        assert result is not None
        assert result["support_label"] == "20 EMA"
        assert result["support"] == 179.5

    def test_returns_none_when_no_support_below(self):
        """All supports above broken stop -> None."""
        from analytics.signal_engine import reproject_after_stop

        result = reproject_after_stop(
            current_price=170.0,
            broken_stop=165.0,
            prior_low=168.0,    # above broken stop
            ma20=172.0,         # above
            ma50=175.0,         # above
        )
        assert result is None

    def test_prior_low_as_next_support(self):
        """Prior day low used when it's the nearest below."""
        from analytics.signal_engine import reproject_after_stop

        result = reproject_after_stop(
            current_price=178.0,
            broken_stop=180.0,
            prior_low=177.0,    # closest below
            ma20=182.0,         # above
            ma50=170.0,         # below but further
        )
        assert result is not None
        assert result["support"] == 177.0
        assert result["support_label"] == "Prior Day Low"

    def test_entry_stop_target_structure(self):
        """Output has entry, stop, target_1, target_2, support, support_label."""
        from analytics.signal_engine import reproject_after_stop

        result = reproject_after_stop(
            current_price=178.0,
            broken_stop=180.0,
            prior_low=174.0,
            ma20=181.0,
            ma50=175.0,
            prior_high=185.0,
        )
        assert result is not None
        required_keys = {
            "entry", "stop", "target_1", "target_2",
            "risk_per_share", "rr_ratio", "support", "support_label",
        }
        assert required_keys.issubset(result.keys())
        assert result["entry"] > 0
        assert result["stop"] > 0
        assert result["target_1"] > 0
        assert result["target_2"] > result["target_1"]

    def test_excludes_broken_stop_level(self):
        """Support == broken_stop is skipped (strictly below)."""
        from analytics.signal_engine import reproject_after_stop

        result = reproject_after_stop(
            current_price=180.0,
            broken_stop=175.0,
            prior_low=175.0,    # exactly at broken stop — should skip
            ma20=180.0,         # above
            ma50=170.0,         # below — should be used
        )
        assert result is not None
        assert result["support"] == 170.0
        assert result["support_label"] == "50 SMA"

    def test_rr_ratio_positive(self):
        """R:R is calculated correctly and positive."""
        from analytics.signal_engine import reproject_after_stop

        result = reproject_after_stop(
            current_price=178.0,
            broken_stop=180.0,
            prior_low=174.0,
            ma20=181.0,
            ma50=175.0,
            prior_high=185.0,
        )
        assert result is not None
        assert result["rr_ratio"] > 0
