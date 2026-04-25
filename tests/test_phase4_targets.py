"""Phase 4a (2026-04-24) — structural / ATR hybrid targets.

Helpers under test:
- `_resistance_ladder`  → ordered structural levels above/below entry
- `_compute_targets`    → hybrid T1/T2 (ATR floor + structural cap)
- `_targets_for_long`   → convenience wrapper, ladder + targets (LONG)
- `_targets_for_short`  → mirror for SHORT

Approach: pure unit tests against fixture inputs. No yfinance, no mocks.
Historical replay tests live in tests/test_phase4_replay.py.
"""
from __future__ import annotations

import pytest

from analytics.intraday_rules import (
    _compute_targets,
    _resistance_ladder,
    _targets_for_long,
    _targets_for_short,
)


# -----------------------------------------------------------------------------
# _resistance_ladder
# -----------------------------------------------------------------------------


class TestResistanceLadderLong:
    def test_orders_levels_ascending_nearest_first(self):
        prior_day = {"high": 105, "prior_week_high": 110, "prior_month_high": 108}
        ladder = _resistance_ladder(prior_day, current_price=100.0, direction="LONG")
        assert ladder == [(105.0, "PDH"), (108.0, "prior_month_high"), (110.0, "prior_week_high")]

    def test_drops_levels_below_entry(self):
        prior_day = {"high": 95, "prior_week_high": 110}  # PDH is BELOW entry
        ladder = _resistance_ladder(prior_day, current_price=100.0, direction="LONG")
        assert (95.0, "PDH") not in ladder
        assert any(label == "prior_week_high" for _, label in ladder)

    def test_dedupes_levels_within_03_pct(self):
        # PDH 105.00 and prior_week_high 105.20 → 0.19% apart, dedupe to PDH only
        prior_day = {"high": 105.00, "prior_week_high": 105.20, "prior_month_high": 110}
        ladder = _resistance_ladder(prior_day, current_price=100.0, direction="LONG")
        prices = [p for p, _ in ladder]
        assert 105.00 in prices
        assert 105.20 not in prices
        assert 110.00 in prices

    def test_includes_emas_above_entry(self):
        prior_day = {"high": 110}
        emas = {"EMA50": 102, "EMA100": 95, "EMA200": 115}  # EMA100 below entry → excluded
        ladder = _resistance_ladder(prior_day, current_price=100.0, emas=emas, direction="LONG")
        labels = [label for _, label in ladder]
        assert "EMA50" in labels
        assert "EMA200" in labels
        assert "EMA100" not in labels

    def test_includes_session_high_only_when_breakout_triggered(self):
        prior_day = {"high": 110}
        ladder_no_breakout = _resistance_ladder(
            prior_day, current_price=100.0, direction="LONG",
            session_high=120, breakout_triggered=False,
        )
        labels_a = [label for _, label in ladder_no_breakout]
        assert "session_high" not in labels_a

        ladder_breakout = _resistance_ladder(
            prior_day, current_price=100.0, direction="LONG",
            session_high=120, breakout_triggered=True,
        )
        labels_b = [label for _, label in ladder_breakout]
        assert "session_high" in labels_b

    def test_caps_at_4_levels(self):
        prior_day = {"high": 105, "prior_week_high": 130, "prior_month_high": 115}
        emas = {"EMA50": 110, "EMA100": 120, "EMA200": 125}
        ladder = _resistance_ladder(prior_day, current_price=100.0, emas=emas, direction="LONG")
        assert len(ladder) <= 4

    def test_empty_prior_day_returns_empty_list(self):
        assert _resistance_ladder(None, current_price=100.0) == []
        assert _resistance_ladder({}, current_price=100.0) == []


class TestResistanceLadderShort:
    def test_short_returns_supports_descending(self):
        prior_day = {"low": 95, "prior_week_low": 90, "prior_month_low": 92}
        ladder = _resistance_ladder(prior_day, current_price=100.0, direction="SHORT")
        # Nearest first → 95, 92, 90
        assert ladder == [(95.0, "PDL"), (92.0, "prior_month_low"), (90.0, "prior_week_low")]

    def test_short_drops_levels_above_entry(self):
        prior_day = {"low": 105, "prior_week_low": 90}  # PDL is ABOVE entry → invalid for SHORT
        ladder = _resistance_ladder(prior_day, current_price=100.0, direction="SHORT")
        prices = [p for p, _ in ladder]
        assert 105 not in prices
        assert 90 in prices


# -----------------------------------------------------------------------------
# _compute_targets
# -----------------------------------------------------------------------------


class TestComputeTargetsLong:
    def test_atr_floor_when_ladder_far_below_atr(self):
        """Risk $1, ATR $5, no ladder → T1 floor $5 above entry."""
        t1, t2 = _compute_targets(
            entry=100, stop=99, atr_daily=5, ladder=[], direction="LONG"
        )
        assert t1 == 105.0  # entry + max(1*1, 1*5)
        assert t2 == 110.0

    def test_structural_cap_kicks_in_when_resistance_below_atr_floor(self):
        """ATR floor $5; ladder has $103 (under floor) and $107 (over floor).
        T1 takes nearest >= floor → $107. NOT $103."""
        t1, t2 = _compute_targets(
            entry=100, stop=99, atr_daily=5,
            ladder=[(103, "EMA50"), (107, "PDH"), (115, "prior_week_high")],
            direction="LONG",
        )
        assert t1 == 107.0  # PDH cap
        assert t2 == 115.0  # prior_week_high cap

    def test_structural_cap_takes_nearest_when_above_floor(self):
        """ATR floor $1; ladder has $103 (over floor) and $115."""
        t1, t2 = _compute_targets(
            entry=100, stop=99, atr_daily=1,
            ladder=[(103, "PDH"), (115, "prior_week_high")],
            direction="LONG",
        )
        assert t1 == 103.0
        assert t2 == 115.0

    def test_atr_none_falls_back_to_risk(self):
        """No ATR → atr defaults to risk → T1 = entry + 1R = $101."""
        t1, t2 = _compute_targets(
            entry=100, stop=99, atr_daily=None, ladder=[], direction="LONG"
        )
        assert t1 == 101.0
        assert t2 == 102.0

    def test_min_gap_between_t1_and_t2(self):
        """When T1 caps and T2 candidate is too close, force min gap."""
        # Risk $2, ATR $1, ladder PDH at $101.50 (between T1 floor $102 and T2 floor $104)
        # Actually T1 floor = entry + max(2,1) = $102, no level >= $102 below T2 floor
        # So T1 = T1_floor = $102. T2 needs to be > T1 AND >= T2_floor $104.
        # No level in that range → T2 = T2_floor $104. Gap is $2 = 1.0R, well above 0.5R.
        # Test explicit min-gap clamp:
        t1, t2 = _compute_targets(
            entry=100, stop=98, atr_daily=1,
            ladder=[(102.5, "PDH"), (102.6, "prior_week_high")],  # too close
            direction="LONG",
        )
        # T1 = $102.5 (PDH meets floor $102), T2 candidate = $102.6 but too close
        # T2 should snap to T1 + 0.5R = $102.5 + $1 = $103.5
        assert t1 == 102.5
        assert t2 >= t1 + 0.5 * 2  # min_gap = 0.5R = $1, T2 >= $103.5

    def test_zero_risk_returns_entry_entry(self):
        t1, t2 = _compute_targets(
            entry=100, stop=100, atr_daily=5, ladder=[], direction="LONG"
        )
        assert t1 == t2 == 100.0


class TestComputeTargetsShort:
    def test_short_atr_floor_below_entry(self):
        t1, t2 = _compute_targets(
            entry=100, stop=101, atr_daily=5, ladder=[], direction="SHORT"
        )
        assert t1 == 95.0
        assert t2 == 90.0

    def test_short_structural_cap(self):
        """SHORT entry $100. ATR $5 → T1 floor $95.
        Ladder has support at $97 (below floor — too close), $93 (good)."""
        t1, t2 = _compute_targets(
            entry=100, stop=101, atr_daily=5,
            ladder=[(97, "EMA50"), (93, "PDL"), (88, "prior_week_low")],
            direction="SHORT",
        )
        # First support <= 95 = $93 (skipping $97 which is above floor)
        assert t1 == 93.0
        # Next support < $93 AND <= T2 floor $90 = $88
        assert t2 == 88.0


# -----------------------------------------------------------------------------
# _targets_for_long / _targets_for_short — wrappers
# -----------------------------------------------------------------------------


class TestTargetsForLongWrapper:
    def test_falls_back_to_pct_when_prior_day_none(self):
        t1, t2 = _targets_for_long(entry=100, stop=99, prior_day=None)
        assert t1 == 101.0  # entry + 1R
        assert t2 == 102.0  # entry + 2R

    def test_uses_structural_when_prior_day_supplied(self):
        prior_day = {"high": 105, "prior_week_high": 110, "atr_daily": 5}
        t1, t2 = _targets_for_long(entry=100, stop=99, prior_day=prior_day)
        assert t1 == 105.0  # PDH cap
        assert t2 == 110.0

    def test_meta_pdl_bounce_today(self):
        """Reproduce META 04-24 09:30 PDL bounce target capture.

        Entry $656.38 (close), stop $649.78 (PDL × 0.995), ATR $14.63.
        Risk = $6.60, T1 floor = $656.38 + max($6.60, $14.63) = $671.01.

        Ladder: PDH $669.56, prior_month_high $672.19, prior_week_high $691.52.
        PDH ($669.56) sits BELOW the ATR-driven floor ($671.01) — algorithm
        correctly skips it (don't quote a target tighter than 1×ATR).
        T1 = prior_month_high $672.19, T2 = prior_week_high $691.52.
        Captures ~$15.81 to T1 + holds T2 open. Today's high was $680.67
        → T1 hit, T2 stayed valid for next session.
        """
        prior_day = {
            "high": 669.56,
            "prior_week_high": 691.52,
            "prior_month_high": 672.19,
            "atr_daily": 14.63,
        }
        t1, t2 = _targets_for_long(entry=656.38, stop=649.78, prior_day=prior_day)
        assert t1 == 672.19
        assert t2 == 691.52

    def test_aaoi_ema8_today(self):
        """AAOI 04-24 ema_bounce_8: entry $146.61, stop $145.88 (risk $0.73).
        ATR ~$7. T1 floor = $146.61 + max($0.73, $7) = $153.61.

        Ladder: PDH $153.20, prior_week_high $161.47. PDH ($153.20) is JUST
        below floor ($153.61) — skipped. T1 = prior_week_high $161.47.
        No level above $161.47 in ladder; T2 falls back to floor + min-gap
        clamp ($161.47 + 0.5*$0.73 ≈ $161.84).

        Today AAOI ran to $164.87 high → T1 captured $14.86.
        """
        prior_day = {
            "high": 153.20,
            "prior_week_high": 161.47,
            "atr_daily": 7.0,
        }
        t1, t2 = _targets_for_long(entry=146.61, stop=145.88, prior_day=prior_day)
        assert t1 == 161.47
        # T2 = T1 + min_gap = $161.47 + 0.5*$0.73 = $161.84
        assert t2 > t1
        assert t2 == pytest.approx(161.84, abs=0.01)


class TestTargetsForShortWrapper:
    def test_falls_back_to_pct_when_prior_day_none(self):
        t1, t2 = _targets_for_short(entry=100, stop=101, prior_day=None)
        assert t1 == 99.0
        assert t2 == 98.0

    def test_uses_support_ladder_when_prior_day_supplied(self):
        prior_day = {"low": 95, "prior_week_low": 90, "atr_daily": 5}
        t1, t2 = _targets_for_short(entry=100, stop=101, prior_day=prior_day)
        assert t1 == 95.0
        assert t2 == 90.0


class TestStructuralTargetsFlagDisabled:
    """When STRUCTURAL_TARGETS_ENABLED=false, wrappers fall back to %-based.

    Patches the module-level flag to False to verify the fallback path.
    """

    def test_long_falls_back_when_flag_false(self, monkeypatch):
        import analytics.intraday_rules as rules
        monkeypatch.setattr(rules, "STRUCTURAL_TARGETS_ENABLED", False)
        prior_day = {"high": 105, "prior_week_high": 110, "atr_daily": 5}
        t1, t2 = rules._targets_for_long(entry=100, stop=99, prior_day=prior_day)
        # Falls back to %-based: T1 = 100+1 = $101, T2 = 100+2 = $102
        assert t1 == 101.0
        assert t2 == 102.0

    def test_short_falls_back_when_flag_false(self, monkeypatch):
        import analytics.intraday_rules as rules
        monkeypatch.setattr(rules, "STRUCTURAL_TARGETS_ENABLED", False)
        prior_day = {"low": 95, "prior_week_low": 90, "atr_daily": 5}
        t1, t2 = rules._targets_for_short(entry=100, stop=101, prior_day=prior_day)
        assert t1 == 99.0
        assert t2 == 98.0
