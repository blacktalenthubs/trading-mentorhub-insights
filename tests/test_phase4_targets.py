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
        """Risk $1, ATR $5 → ATR caps at 3R=$3 → T1 floor $3 above entry."""
        t1, t2 = _compute_targets(
            entry=100, stop=99, atr_daily=5, ladder=[], direction="LONG"
        )
        # ATR_CAP_RISK_MULT (3.0) limits ATR contribution: min(5, 3*1) = 3
        # T1_floor = entry + max(risk=1, capped_atr=3) = $103
        # T2_floor = entry + max(2*1, 2*3) = $106
        assert t1 == 103.0
        assert t2 == 106.0

    def test_structural_cap_kicks_in_when_resistance_below_atr_floor(self):
        """ATR=$5 caps at 3R=$3 → T1 floor $103. Ladder $103 now meets floor."""
        t1, t2 = _compute_targets(
            entry=100, stop=99, atr_daily=5,
            ladder=[(103, "EMA50"), (107, "PDH"), (115, "prior_week_high")],
            direction="LONG",
        )
        # T1 = first ladder >= floor $103 → $103 (EMA50)
        # T2 = first ladder > $103 AND >= floor $106 → $107 (PDH)
        assert t1 == 103.0
        assert t2 == 107.0

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
        """SHORT risk=$1, ATR=$5 → cap at 3R=$3 → T1 floor $97."""
        t1, t2 = _compute_targets(
            entry=100, stop=101, atr_daily=5, ladder=[], direction="SHORT"
        )
        # capped_atr = min(5, 3*1) = 3
        # T1 = entry - max(1, 3) = $97
        # T2 = entry - max(2, 6) = $94
        assert t1 == 97.0
        assert t2 == 94.0

    def test_short_structural_cap(self):
        """SHORT ATR=$5 caps at 3R=$3 → T1 floor $97.
        Ladder support at $97 now meets floor."""
        t1, t2 = _compute_targets(
            entry=100, stop=101, atr_daily=5,
            ladder=[(97, "EMA50"), (93, "PDL"), (88, "prior_week_low")],
            direction="SHORT",
        )
        # T1 = first support <= $97 → $97 (EMA50)
        # T2 = first support < $97 AND <= floor $94 → $93 (PDL)
        assert t1 == 97.0
        assert t2 == 93.0


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
        ATR ~$7. With ATR_CAP_RISK_MULT=3.0, ATR caps at 3R=$2.19.

        T1 floor = $146.61 + max($0.73, $2.19) = $148.80.
        Ladder: PDH $153.20, prior_week_high $161.47.
        T1 = first ladder >= $148.80 → PDH $153.20 (the structural sellers).
        T2 floor = $146.61 + 2*$2.19 = $151.00; first ladder > $153.20 AND
        >= $151 → prior_week_high $161.47.

        Captures $6.59 to T1 + $14.86 to T2. Today AAOI ran to $164.87 →
        both T1 and T2 hit. Matches the trader's mental model of "sellers
        at PDH first, then weekly high."
        """
        prior_day = {
            "high": 153.20,
            "prior_week_high": 161.47,
            "atr_daily": 7.0,
        }
        t1, t2 = _targets_for_long(entry=146.61, stop=145.88, prior_day=prior_day)
        assert t1 == 153.20
        assert t2 == 161.47


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


class TestAtrCapAtThreeR:
    """Phase 4a fix (2026-04-25): ATR floor capped at 3× risk.

    Without the cap, ETH 04-25 alert (risk $2.76, ATR $99.95) would push
    T1 floor to $2,419 — past every near-term level. With cap, ATR
    contribution clamps at $8.28, T1 floor lands at $2,327.72, ladder
    picks PDH around $2,337 — actionable intraday target.
    """

    def test_eth_volatile_crypto_with_tight_stop(self):
        """ETH-USD 04-25 prior_day_low_reclaim: tight stop, very high ATR.

        Without cap: T1 = $2,427 (prior-week high) — way out of range.
        With cap (3R=$8.28): T1 = PDH $2,337.27, T2 = prior-month high $2,384.47.
        """
        prior_day = {
            "high": 2337.27,
            "prior_week_high": 2427.28,
            "prior_month_high": 2384.47,
            "atr_daily": 99.95,
        }
        emas = {"EMA8": 2327.29, "EMA21": 2276.97, "EMA200": 2429.82}
        t1, t2 = _targets_for_long(
            entry=2319.44, stop=2316.68, prior_day=prior_day, emas_above=emas
        )
        # 3R cap = 3 * $2.76 = $8.28
        # T1_floor = $2319.44 + max($2.76, $8.28) = $2,327.72
        # T1 = first ladder >= $2,327.72 → EMA8 $2327.29? No, $2327.29 < $2327.72
        # → next is PDH $2,337.27
        assert t1 == 2337.27  # PDH
        # T2_floor = $2319.44 + 2*$8.28 = $2,335.99
        # T2 = first ladder > $2,337.27 AND >= $2,335.99 → prior_month_high $2,384.47
        assert t2 == 2384.47

    def test_atr_cap_inactive_when_atr_already_below_3r(self):
        """When ATR < 3R, cap doesn't kick in — behavior unchanged."""
        prior_day = {"high": 105, "prior_week_high": 110, "atr_daily": 2}
        # risk = 1, ATR = 2, 3R = 3 → ATR ($2) < cap ($3) → uncapped
        # T1_floor = 100 + max(1, 2) = 102. Ladder $105 >= floor → T1 = $105.
        t1, t2 = _targets_for_long(entry=100, stop=99, prior_day=prior_day)
        assert t1 == 105.0
        assert t2 == 110.0

    def test_atr_cap_normal_equity_unaffected(self):
        """META-style trade: risk $6.60, ATR $14.63 → 3R = $19.80.
        ATR ($14.63) < cap ($19.80), so ATR is NOT clipped.
        Same output as before the cap was added.
        """
        prior_day = {
            "high": 669.56,
            "prior_week_high": 691.52,
            "prior_month_high": 672.19,
            "atr_daily": 14.63,
        }
        t1, t2 = _targets_for_long(entry=656.38, stop=649.78, prior_day=prior_day)
        # T1 floor = entry + max(6.60, 14.63) = $671.01
        # First ladder >= $671.01 → prior_month_high $672.19
        assert t1 == 672.19
        # T2 floor = $685.64; first > $672.19 AND >= $685.64 → prior_week_high $691.52
        assert t2 == 691.52


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
