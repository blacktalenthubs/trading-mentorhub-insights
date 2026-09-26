"""Every tunable threshold for the breakout pattern scanner — nothing hardcoded in the
detection code. Change a number here, not in a pattern module.

Defaults are the build spec's. The whole config is one frozen dataclass; `CONFIG` is the
shared instance. Pass a custom `PatternConfig(...)` into the screener to A/B a rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PatternConfig:
    # ── History / data ───────────────────────────────────────────────────────
    min_bars: int = 400              # skip a ticker with less daily history (logged, never crash)
    slope_lookback: int = 10         # bars for sma50_slope / sma200_slope (% change over N)
    avg_vol_window: int = 50         # avg_vol_50
    atr_len: int = 14
    rsi_len: int = 14

    # ── Pre-filter (every pattern) ───────────────────────────────────────────
    min_close: float = 10.0
    min_avg_vol: float = 500_000.0
    require_above_sma200: bool = True
    require_rising_sma200: bool = True          # sma200_slope > 0
    max_pct_below_52w_high: float = 0.25        # close within 25% of the 52w high
    min_pct_above_52w_low: float = 0.30         # close ≥ 30% above the 52w low

    # ── Breakout confirmation (shared) ───────────────────────────────────────
    breakout_rvol: float = 1.8                  # rvol on the breakout bar
    breakout_close_upper_frac: float = 0.5      # close in the upper 50% of the bar range

    # ── Actionability (shared) — used to LABEL "actionable now" vs "watch", not to drop ──
    max_pct_to_trigger: float = 6.0             # actionable only if price is within this % below the trigger
    max_setup_risk_pct: float = 8.0             # actionable only if entry→stop risk ≤ this % (tight, not loose)

    # ── Zanger informational context (NEVER filters — just labels to guide the read) ──────
    tight_stop_pct: float = 0.06                # a tight "Zanger" stop = this % under the trigger (shown alongside the structural stop)
    big_day_pct: float = 15.0                   # a breakout-day move ≥ this % is flagged "extended" (his climax-fail caution)
    near_highs_pct: float = 70.0                # close in the top (100-this)% of the day's range = "near highs" (his best breakouts)

    # ── Cup and handle ───────────────────────────────────────────────────────
    ch_search_bars: int = 200
    ch_rim_side_bars: int = 20                  # a rim = local high, max of 20 bars each side
    ch_depth_min: float = 0.15
    ch_depth_max: float = 0.35
    ch_recover_pct: float = 0.05                # "recovered" = within 5% of the rim
    ch_min_cup_days: int = 35
    ch_low_exclude_edge_frac: float = 0.25      # cup low must not be in first/last 25% of span
    ch_handle_min_days: int = 5
    ch_handle_max_days: int = 15
    ch_handle_depth_min: float = 0.05
    ch_handle_depth_max: float = 0.15
    ch_handle_upper_half_frac: float = 0.5      # handle low > cup_low + 0.5*(rim-cup_low)

    # ── Flat base ────────────────────────────────────────────────────────────
    fb_min_bars: int = 25
    fb_max_bars: int = 60
    fb_depth_max: float = 0.15
    fb_prior_advance: float = 0.20              # ≥20% run in the 60 bars before the base
    fb_prior_advance_bars: int = 60

    # ── Ascending triangle ───────────────────────────────────────────────────
    at_min_bars: int = 20
    at_max_bars: int = 60
    at_peak_distance: int = 4                   # find_peaks distance
    at_ceiling_tol: float = 0.02                # ≥3 highs within 2% of each other
    at_min_ceiling_touches: int = 3
    at_min_low_touches: int = 2
    at_lows_r2_min: float = 0.6                 # R² of the rising-lows fit
    at_converge_pct: float = 0.10               # last low within 10% of the ceiling

    # ── Bull flag ────────────────────────────────────────────────────────────
    bf_search_bars: int = 40
    bf_pole_min_bars: int = 4
    bf_pole_max_bars: int = 15
    bf_pole_gain: float = 0.15                  # ≥15% pole run
    bf_pole_rvol: float = 1.3                   # avg rvol over the pole
    bf_flag_min_bars: int = 3
    bf_flag_max_bars: int = 12
    bf_flag_retrace_max: float = 0.5            # ≤50% of the pole given back
    bf_flag_range_frac: float = 0.40            # flag range ≤ 40% of pole range
    bf_flag_rvol_max: float = 0.8               # the quiet is the signal

    # ── Horizontal resistance / TBA (Zanger — AMD-style flat-ceiling break) ──
    ht_min_bars: int = 20
    ht_max_bars: int = 90
    ht_peak_distance: int = 4
    ht_level_tol: float = 0.015                 # highs within 1.5% of each other = one ceiling
    ht_min_touches: int = 3
    ht_max_level_dist: float = 0.08             # the ceiling must sit within 8% of price (near, actionable)

    # ── Descending trendline break (Zanger — QQQ-style) ──────────────────────
    tl_min_bars: int = 30
    tl_max_bars: int = 150
    tl_peak_distance: int = 5
    tl_min_highs: int = 3
    tl_r2_min: float = 0.6                       # the fitted line must be a real trendline
    tl_max_dist_above: float = 0.06             # a FRESH break: close within 6% above the projected line

    # ── Earnings filter (opt-in) ─────────────────────────────────────────────
    earnings_block_days: int = 10               # drop a name reporting within N days

    # ── Score weights (0-100 composite) — documented so you can tune ──────────
    # score = 100 * (w_volume·volume_dryup + w_tight·tightness + w_dur·duration + w_trend·trend)
    # each sub-score is 0..1:
    #   volume_dryup — how far base/flag volume fell below the prior/cup-side volume (bigger = better)
    #   tightness    — how far inside the max allowed depth the consolidation is (tighter = better)
    #   duration     — base length scaled into a healthy band (longer bases score higher, capped)
    #   trend        — 200-SMA slope + distance above it, and RSI in a constructive band
    w_volume: float = 0.35
    w_tight: float = 0.25
    w_duration: float = 0.15
    w_trend: float = 0.25
    duration_full_days: int = 45                # a base this long (days) maxes the duration sub-score

    patterns_enabled: tuple[str, ...] = field(
        default_factory=lambda: ("cup_handle", "flat_base", "ascending_triangle", "bull_flag",
                                 "horizontal_tba", "trendline_break"))


CONFIG = PatternConfig()
