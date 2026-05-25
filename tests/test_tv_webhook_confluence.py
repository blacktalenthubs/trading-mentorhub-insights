"""Tests for spec 58 — confluence detection and uptrend-gate enforcement
in api/app/routers/tv_webhook.py.

Two pure-function helpers (find_confluences, format_confluence_annotation) +
the gate enforcement around the TV webhook dispatch.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure api/ is on sys.path so `from app.routers...` resolves the FastAPI app.
_HERE = Path(__file__).resolve().parent
_API_ROOT = _HERE.parent / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.tv_webhook import (  # noqa: E402
    CONFLUENCE_BAND_PCT,
    FUTURES_SESSION_SYMBOLS,
    find_confluences,
    format_confluence_annotation,
    is_basing_chop,
    is_outside_session_window,
    is_uptrend_gate_rejected,
)


# ── find_confluences ───────────────────────────────────────────────────


class TestFindConfluencesBand:
    """The 1.0% band: levels within band → confluent, outside → not."""

    def test_avgo_case_pdl_confluent_with_ema21(self):
        """AVGO 2026-05-22: EMA 21 $413.02 confluent with PDL $410.50
        (spread 0.61%, inside the 1% band)."""
        entry = 413.02
        nearby = [
            {"kind": "ema21",     "value": 413.02, "label": "EMA 21"},
            {"kind": "pdl",       "value": 410.50, "label": "PDL"},
            {"kind": "mtd_avwap", "value": 420.92, "label": "MTD AVWAP"},
        ]
        result = find_confluences(entry, nearby)
        # PDL is confluent, MTD AVWAP is 1.91% away → not confluent, entry's own EMA 21 filtered out
        assert len(result) == 1
        assert result[0]["kind"] == "pdl"
        assert result[0]["value"] == 410.50

    def test_nvda_case_pm_not_confluent_with_mtd(self):
        """NVDA 2026-05-22: MTD $217.02 vs PM $205.10 — 5.6% spread, NOT confluent."""
        entry = 217.02
        nearby = [
            {"kind": "mtd_avwap", "value": 217.02, "label": "MTD May"},
            {"kind": "pm_avwap",  "value": 205.10, "label": "PM Apr"},
            {"kind": "p2m_avwap", "value": 194.02, "label": "-2M Mar"},
        ]
        result = find_confluences(entry, nearby)
        # Entry's own MTD filtered out; PM and -2M both outside 1% band
        assert result == []

    def test_entry_own_level_filtered_out(self):
        """The level matching entry's own value is never returned."""
        entry = 100.0
        nearby = [{"kind": "ema21", "value": 100.0, "label": "EMA 21"}]
        assert find_confluences(entry, nearby) == []

    def test_empty_nearby_returns_empty(self):
        assert find_confluences(100.0, []) == []

    def test_zero_entry_returns_empty(self):
        """Defensive: zero entry should not divide-by-zero or return nonsense."""
        assert find_confluences(0.0, [{"kind": "x", "value": 5.0, "label": "X"}]) == []

    def test_multi_confluence_returned(self):
        """Three levels all within 1% of $100 → all three flagged (minus the entry's own)."""
        entry = 100.0
        nearby = [
            {"kind": "ema21", "value": 100.0,  "label": "EMA 21"},  # entry's own — filtered
            {"kind": "pdl",   "value":  99.5,  "label": "PDL"},     # 0.5% below — confluent
            {"kind": "pwl",   "value": 100.5,  "label": "PWL"},     # 0.5% above — confluent
            {"kind": "pmh",   "value": 105.0,  "label": "PMH"},     # 5%   above — NOT confluent
        ]
        result = find_confluences(entry, nearby)
        assert len(result) == 2
        kinds = {r["kind"] for r in result}
        assert kinds == {"pdl", "pwl"}

    def test_band_boundary_exact(self):
        """Exactly at the band boundary counts as confluent (≤, not <)."""
        entry = 100.0
        band = entry * (CONFLUENCE_BAND_PCT / 100.0)  # 1.0
        nearby = [
            {"kind": "pdl", "value": entry - band, "label": "PDL"},
            {"kind": "pwh", "value": entry + band, "label": "PWH"},
        ]
        result = find_confluences(entry, nearby)
        assert len(result) == 2

    def test_handles_string_value_gracefully(self):
        """Pine sometimes sends numeric fields as strings; coerce defensively."""
        entry = 100.0
        nearby = [
            {"kind": "pdl", "value": "99.5", "label": "PDL"},   # str → float
            {"kind": "pwh", "value": "bogus", "label": "PWH"},  # invalid → skipped
        ]
        result = find_confluences(entry, nearby)
        assert len(result) == 1
        assert result[0]["kind"] == "pdl"


# ── format_confluence_annotation ──────────────────────────────────────


class TestFormatConfluenceAnnotation:

    def test_empty_returns_empty_string(self):
        assert format_confluence_annotation([]) == ""

    def test_single_confluence(self):
        out = format_confluence_annotation(
            [{"kind": "pdl", "value": 410.50, "label": "PDL"}]
        )
        assert out == "Confluence: PDL ($410.50)"

    def test_multi_confluence_comma_joined(self):
        out = format_confluence_annotation([
            {"kind": "pdl",       "value": 410.50, "label": "PDL"},
            {"kind": "mtd_avwap", "value": 420.92, "label": "MTD AVWAP"},
        ])
        assert out == "Confluence: PDL ($410.50), MTD AVWAP ($420.92)"

    def test_falls_back_to_kind_when_label_missing(self):
        out = format_confluence_annotation(
            [{"kind": "pdl", "value": 410.5}]
        )
        assert out == "Confluence: pdl ($410.50)"

    def test_falls_back_to_level_when_kind_and_label_missing(self):
        out = format_confluence_annotation([{"value": 100.0}])
        assert out == "Confluence: level ($100.00)"

    def test_skips_entries_with_invalid_value(self):
        out = format_confluence_annotation([
            {"kind": "pdl", "value": "bogus", "label": "PDL"},
            {"kind": "pwh", "value": 200.0,   "label": "PWH"},
        ])
        assert out == "Confluence: PWH ($200.00)"

    def test_all_invalid_returns_empty(self):
        out = format_confluence_annotation([
            {"kind": "pdl", "value": "bogus"},
            {"kind": "pwh"},
        ])
        assert out == ""

    def test_two_decimals_consistent(self):
        out = format_confluence_annotation(
            [{"kind": "x", "value": 410.5, "label": "X"}]
        )
        # 410.5 → "410.50" (two decimals)
        assert "$410.50" in out


# ── Adapter — spec-58 payload field parsing ─────────────────────────


class TestAdapterSpec58Fields:
    """Verify analytics.tv_signal_adapter.payload_to_alert_signal correctly
    attaches the four new spec-58 fields onto the signal object as the
    `_tv_*` attributes the webhook reads."""

    def _base_payload(self, **overrides) -> dict:
        """Minimal valid TV payload — enough for the adapter to build an
        AlertSignal. Spec-58 fields layered on top via overrides."""
        base = {
            "symbol": "AAOI",
            "exchange": "NASDAQ",
            "interval": "1D",
            "price": "181.49",
            "high": "182.46",
            "low": "166.66",
            "volume": "10253114",
            "entry": "171.47",
            "stop": "166.66",
            "target_1": "177.96",
            "target_2": "200.11",
            "rule": "ma_bounce_long_v3",
            "direction": "BUY",
            "ma_tag": "ema21",
            "pdh": "182.18",
            "pdl": "163.66",
        }
        base.update(overrides)
        return base

    def test_uptrend_pass_true(self):
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(self._base_payload(uptrend_pass="true"))
        assert sig._tv_uptrend_pass is True

    def test_uptrend_pass_false(self):
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(self._base_payload(uptrend_pass="false"))
        assert sig._tv_uptrend_pass is False

    def test_uptrend_pass_missing_defaults_none(self):
        """Legacy Pine alerts (pre-spec-58) don't send the field — adapter
        treats as None so the webhook lets them through (backward-compat)."""
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(self._base_payload())
        assert sig._tv_uptrend_pass is None

    def test_overhead_mas_csv_parsed(self):
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(
            self._base_payload(overhead_mas="EMA 100, EMA 200, SMA 200")
        )
        assert sig._tv_overhead_mas == ["EMA 100", "EMA 200", "SMA 200"]

    def test_overhead_mas_empty(self):
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(self._base_payload(overhead_mas=""))
        assert sig._tv_overhead_mas == []

    def test_nearby_levels_csv_parsed_with_pipes(self):
        """The wire format from Pine: pipe between fields, comma between entries.
        Pine: array.join of "kind|value|label" strings."""
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(self._base_payload(
            nearby_levels="ema21|171.47|EMA 21,pdl|410.50|PDL,mtd_avwap|180.28|MTD AVWAP"
        ))
        assert len(sig._tv_nearby_levels) == 3
        assert sig._tv_nearby_levels[0] == {"kind": "ema21", "value": 171.47, "label": "EMA 21"}
        assert sig._tv_nearby_levels[1] == {"kind": "pdl", "value": 410.50, "label": "PDL"}
        assert sig._tv_nearby_levels[2] == {"kind": "mtd_avwap", "value": 180.28, "label": "MTD AVWAP"}

    def test_nearby_levels_skips_malformed_entries(self):
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(self._base_payload(
            nearby_levels="ema21|171.47|EMA 21,bogus,pwl|notanumber|PWL,mtd|180.28"
        ))
        # Valid: ema21 (full), mtd (no label, falls back to kind)
        # Skipped: "bogus" (no separator), "pwl|notanumber|PWL" (not float)
        kinds = [lvl["kind"] for lvl in sig._tv_nearby_levels]
        assert kinds == ["ema21", "mtd"]

    def test_nearby_levels_native_list_preserved(self):
        """Future-compat: if Pine ever sends a proper JSON list of dicts."""
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(self._base_payload(
            nearby_levels=[
                {"kind": "ema21", "value": 171.47, "label": "EMA 21"},
                {"kind": "pdl",   "value": 410.50, "label": "PDL"},
            ]
        ))
        assert len(sig._tv_nearby_levels) == 2
        assert sig._tv_nearby_levels[0]["kind"] == "ema21"

    def test_mtd_avwap_parsed(self):
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig = payload_to_alert_signal(self._base_payload(mtd_avwap="180.28"))
        assert sig._tv_mtd_avwap == 180.28

    def test_mtd_avwap_missing_or_empty(self):
        from analytics.tv_signal_adapter import payload_to_alert_signal
        sig_missing = payload_to_alert_signal(self._base_payload())
        assert sig_missing._tv_mtd_avwap is None
        sig_empty = payload_to_alert_signal(self._base_payload(mtd_avwap=""))
        assert sig_empty._tv_mtd_avwap is None


# ── Uptrend gate predicate (refined 2026-05-23) ─────────────────────


class TestUptrendGateRefined:
    """Spec 58 FR-003 refined: only MA-based BUY entries (`tv_ma_*`)
    are gated by uptrend_pass=False. Level-based BUYs (PDH/PDL/PWH/PWL/
    PMH/PML reclaim or hold) pass through regardless of MA stack — in
    downtrend regimes, the trader plays the levels with overhead MAs as
    targets / resistance, not as entry blockers."""

    # ── MA-based: gated (the noise cut spec 58 was built for) ───────

    def test_ma_bounce_buy_downtrend_rejected(self):
        """The PLTR/META/MSFT case from 2026-05-22 — still correctly blocked."""
        assert is_uptrend_gate_rejected("tv_ma_bounce_long_v3_ema21", "BUY", False) is True

    def test_ma_bounce_all_per_ma_variants_rejected(self):
        for suffix in ("ema8", "ema21", "ema50", "ema100", "ema200", "sma50", "sma100", "sma200"):
            assert is_uptrend_gate_rejected(
                f"tv_ma_bounce_long_v3_{suffix}", "BUY", False
            ) is True, suffix

    # ── Level-based BUYs: ALL pass through in downtrends (the refinement) ──

    def test_pdl_reclaim_downtrend_passes(self):
        """SWMR/PLTR case — pdl_reclaim is a valid level play on downtrend stocks."""
        assert is_uptrend_gate_rejected("tv_staged_pdl_reclaim", "BUY", False) is False

    def test_pwl_reclaim_downtrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_pwl_reclaim", "BUY", False) is False

    def test_pml_reclaim_downtrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_pml_reclaim", "BUY", False) is False

    def test_pdh_held_downtrend_passes(self):
        """Reversal play: stock briefly above prior high, holds it — valid even
        if MA stack is bearish (e.g., SWMR holding WH 38.06 — 2026-05-22)."""
        assert is_uptrend_gate_rejected("tv_staged_pdh_held", "BUY", False) is False

    def test_pwh_held_downtrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_pwh_held", "BUY", False) is False

    def test_pmh_held_downtrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_pmh_held", "BUY", False) is False

    # ── Spec 58 (2026-05-23) — symmetric low-held types ─────────────

    def test_pdl_held_downtrend_passes(self):
        """ETH 2026-05-23 case: wicked PML, bounced. New `pml_held` alert
        type fires regardless of MA stack (level play, not MA-based)."""
        assert is_uptrend_gate_rejected("tv_staged_pdl_held", "BUY", False) is False

    def test_pwl_held_downtrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_pwl_held", "BUY", False) is False

    def test_pml_held_downtrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_pml_held", "BUY", False) is False

    # ── Spec 58 (2026-05-23 evening) — monthly AVWAP defense types ──

    def test_mtd_avwap_held_downtrend_passes(self):
        """ETH 2026-05-23: stalled exactly at MTD Apr AVWAP $2,246.15 — the
        live validation case. Level-based alert, fires in any regime."""
        assert is_uptrend_gate_rejected("tv_staged_mtd_avwap_held", "BUY", False) is False

    def test_pm_avwap_held_downtrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_pm_avwap_held", "BUY", False) is False

    def test_p2m_avwap_held_downtrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_p2m_avwap_held", "BUY", False) is False


# ── Basing-chop filter (spec 58, 2026-05-24) ────────────────────────


class TestBasingChopFilter:
    """Suppress level-based BUYs in pure basing chop. BOTH signals
    (stage='BASING', |vwap_slope_pct|<0.3) must agree before the gate
    triggers. Refined 2026-05-24 — dropped inside_day requirement (too
    common a flag; real PDL/PWL holds happen on inside days too)."""

    STAGE_BASING = "STAGE 1: BASING — inside range + VWAP flat — WAIT — sweeps only"

    def test_btc_2026_05_23_case_suppressed(self):
        """The exact BTC payload from 2026-05-23 — both signals say wait."""
        assert is_basing_chop(self.STAGE_BASING, 0.04) is True

    def test_clean_uptrend_passes(self):
        """STAGE 2 ADVANCING + rising VWAP → not basing."""
        assert is_basing_chop("STAGE 2: ADVANCING — above PDH + VWAP rising", 0.8) is False

    def test_basing_but_strong_vwap_slope_passes(self):
        """Basing classifier but VWAP slope material → directional bias →
        let through. Stage can lag — VWAP slope is the live signal."""
        assert is_basing_chop(self.STAGE_BASING, 0.8) is False

    def test_basing_with_inside_day_no_longer_blocks(self):
        """Refinement 2026-05-24 — inside_day is NOT a filter input anymore.
        A PDL hold on an inside day with flat VWAP still gets suppressed
        (basing + flat VWAP); but with material VWAP slope, it fires."""
        # Flat VWAP — suppressed
        assert is_basing_chop(self.STAGE_BASING, 0.04) is True
        # Material slope — let through (was previously blocked when inside_day=true)
        assert is_basing_chop(self.STAGE_BASING, 0.5) is False

    def test_vwap_slope_at_threshold_passes(self):
        """Exactly 0.3% slope is the boundary — passes through (>=0.3)."""
        assert is_basing_chop(self.STAGE_BASING, 0.3) is False

    def test_vwap_slope_just_under_threshold_suppressed(self):
        assert is_basing_chop(self.STAGE_BASING, 0.29) is True

    def test_negative_vwap_slope_uses_abs(self):
        """Falling VWAP at -0.04 is still flat-ish — counts as basing."""
        assert is_basing_chop(self.STAGE_BASING, -0.04) is True

    def test_negative_vwap_slope_steep_passes(self):
        """-0.8 is materially falling — not basing, alerts still flow."""
        assert is_basing_chop(self.STAGE_BASING, -0.8) is False

    def test_missing_stage_passes(self):
        """Legacy Pine sends no stage field → let through (backward-compat)."""
        assert is_basing_chop("", 0.04) is False
        assert is_basing_chop(None, 0.04) is False

    def test_missing_vwap_slope_passes(self):
        """Defensive — if vwap_slope is None, no suppression."""
        assert is_basing_chop(self.STAGE_BASING, None) is False

    def test_stage2_passes(self):
        assert is_basing_chop("STAGE 2: ADVANCING", 0.04) is False

    def test_transitioning_passes(self):
        """TRANSITIONING isn't BASING — let through."""
        assert is_basing_chop("TRANSITIONING\nno clean regime", 0.04) is False

    # ── Uptrend regime: nothing is gated ────────────────────────────

    def test_ma_bounce_uptrend_passes(self):
        assert is_uptrend_gate_rejected("tv_ma_bounce_long_v3_ema21", "BUY", True) is False

    def test_level_alert_uptrend_passes(self):
        assert is_uptrend_gate_rejected("tv_staged_pdl_reclaim", "BUY", True) is False

    # ── Backward-compat: legacy Pine sending no uptrend_pass ────────

    def test_legacy_no_uptrend_field_passes_ma(self):
        """uptrend_pass=None means legacy Pine — let through (rollback safety)."""
        assert is_uptrend_gate_rejected("tv_ma_bounce_long_v3_ema21", "BUY", None) is False

    def test_legacy_no_uptrend_field_passes_level(self):
        assert is_uptrend_gate_rejected("tv_staged_pdl_reclaim", "BUY", None) is False

    # ── Direction edge cases ────────────────────────────────────────

    def test_short_never_gated(self):
        """SHORT direction is out of spec-58 scope — gate doesn't apply."""
        assert is_uptrend_gate_rejected("tv_ma_rejection_short_v3_ema21", "SHORT", False) is False

    def test_notice_never_gated(self):
        assert is_uptrend_gate_rejected("tv_ma_proximity_long_v3_ema21", "NOTICE", False) is False

    def test_none_direction_not_gated(self):
        assert is_uptrend_gate_rejected("tv_ma_bounce_long_v3_ema21", None, False) is False


# ── is_outside_session_window (futures filter) ─────────────────────────
class TestFuturesSessionWindow:
    """Spec 2026-05-24 — suppress /ES /NQ alerts outside 04:00-16:00 ET Mon-Fri."""

    def _et(self, year, month, day, hour, minute=0):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/New_York"))

    # ── Symbol scope: only futures gated ────────────────────────────

    def test_non_futures_symbol_always_passes(self):
        """Stocks + crypto unaffected by the futures window — return False at any time."""
        # 3 AM ET Sunday — would be "outside" for futures, but stocks pass
        sunday_3am = self._et(2026, 5, 24, 3, 0)
        assert is_outside_session_window("AAPL", sunday_3am) is False
        assert is_outside_session_window("BTC-USD", sunday_3am) is False
        assert is_outside_session_window("ETH-USD", sunday_3am) is False
        assert is_outside_session_window("IREN", sunday_3am) is False

    def test_futures_symbols_in_scope(self):
        """The frozenset includes ES1!, NQ1!, MES1!, MNQ1! — nothing else."""
        assert "ES1!" in FUTURES_SESSION_SYMBOLS
        assert "NQ1!" in FUTURES_SESSION_SYMBOLS
        assert "MES1!" in FUTURES_SESSION_SYMBOLS
        assert "MNQ1!" in FUTURES_SESSION_SYMBOLS
        # Verify scope is narrow — not accidentally including crypto/stocks
        assert "BTC-USD" not in FUTURES_SESSION_SYMBOLS
        assert "AAPL" not in FUTURES_SESSION_SYMBOLS

    # ── Inside window: should pass (return False) ───────────────────

    def test_es_passes_during_premarket(self):
        """5 AM ET Tuesday = US pre-market, futures actively trading → pass."""
        tuesday_5am = self._et(2026, 5, 26, 5, 0)
        assert is_outside_session_window("ES1!", tuesday_5am) is False

    def test_es_passes_during_rth(self):
        """10 AM ET Wednesday = US RTH → pass."""
        wed_10am = self._et(2026, 5, 27, 10, 0)
        assert is_outside_session_window("ES1!", wed_10am) is False

    def test_es_passes_at_3_30pm(self):
        """3:30 PM ET = inside the 4 PM close cutoff → pass."""
        thurs_3_30pm = self._et(2026, 5, 28, 15, 30)
        assert is_outside_session_window("ES1!", thurs_3_30pm) is False

    def test_es_passes_at_exactly_4am(self):
        """4:00 AM ET sharp = first minute of window → pass."""
        mon_4am = self._et(2026, 5, 25, 4, 0)
        assert is_outside_session_window("ES1!", mon_4am) is False

    # ── Outside window: should suppress (return True) ───────────────

    def test_es_suppressed_at_3am(self):
        """3 AM ET Tuesday = before 4 AM window → suppress."""
        tues_3am = self._et(2026, 5, 26, 3, 0)
        assert is_outside_session_window("ES1!", tues_3am) is True

    def test_es_suppressed_at_4pm(self):
        """4 PM ET sharp = first minute past close → suppress."""
        wed_4pm = self._et(2026, 5, 27, 16, 0)
        assert is_outside_session_window("ES1!", wed_4pm) is True

    def test_es_suppressed_at_9pm(self):
        """9 PM ET = Asian session = noise → suppress."""
        thurs_9pm = self._et(2026, 5, 28, 21, 0)
        assert is_outside_session_window("ES1!", thurs_9pm) is True

    def test_es_suppressed_at_midnight(self):
        """Midnight ET = deep overnight → suppress."""
        fri_midnight = self._et(2026, 5, 29, 0, 0)
        assert is_outside_session_window("ES1!", fri_midnight) is True

    # ── Weekend: always outside ─────────────────────────────────────

    def test_es_suppressed_saturday(self):
        """Saturday at any time → suppress (futures partially closed anyway)."""
        sat_noon = self._et(2026, 5, 23, 12, 0)
        assert is_outside_session_window("ES1!", sat_noon) is True

    def test_es_suppressed_sunday_evening(self):
        """Sunday 7 PM ET = Globex reopens but outside our practical window."""
        sun_7pm = self._et(2026, 5, 24, 19, 0)
        assert is_outside_session_window("ES1!", sun_7pm) is True

    # ── Other futures symbols use same rules ────────────────────────

    def test_nq_uses_same_window(self):
        """NQ1! follows the same window as ES1!."""
        tues_3am = self._et(2026, 5, 26, 3, 0)
        tues_10am = self._et(2026, 5, 26, 10, 0)
        assert is_outside_session_window("NQ1!", tues_3am) is True
        assert is_outside_session_window("NQ1!", tues_10am) is False

    def test_micros_use_same_window(self):
        """MES1! and MNQ1! follow the same window."""
        tues_2am = self._et(2026, 5, 26, 2, 0)
        tues_11am = self._et(2026, 5, 26, 11, 0)
        assert is_outside_session_window("MES1!", tues_2am) is True
        assert is_outside_session_window("MES1!", tues_11am) is False
        assert is_outside_session_window("MNQ1!", tues_2am) is True
        assert is_outside_session_window("MNQ1!", tues_11am) is False

    # ── Timezone-naive datetime support ─────────────────────────────

    def test_naive_datetime_interpreted_as_et(self):
        """If caller passes a naive datetime (no tzinfo), treat it as ET."""
        from datetime import datetime
        # 3 AM 'local' (assumed ET) on a Tuesday → suppress
        naive_3am = datetime(2026, 5, 26, 3, 0)
        assert is_outside_session_window("ES1!", naive_3am) is True
