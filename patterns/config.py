"""Every tunable number for the breakout pattern scanner lives here.

Pattern modules never hardcode thresholds — they read from these frozen
dataclasses. Change a default here to retune; or build a custom
``ScannerConfig(...)`` and pass it to ``patterns.screener.run_scan``.

All fractions are expressed as fractions (0.15 == 15%), never percents.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DataConfig:
    """History + derived-column parameters."""

    min_bars: int = 400              # tickers with less daily history are skipped (logged)
    fetch_period: str = "2y"         # yfinance period string (~504 bars)
    slope_bars: int = 10             # MA slope = pct change over this many bars
    vol_window: int = 50             # avg_vol_50
    atr_period: int = 14
    rsi_period: int = 14
    year_bars: int = 252             # 52-week high/low window


@dataclass(frozen=True)
class PrefilterConfig:
    """Liquidity + trend gate applied before any pattern logic."""

    min_close: float = 10.0
    min_avg_vol_50: float = 500_000
    require_close_above_sma200: bool = True
    require_sma200_rising: bool = True      # sma200_slope > 0
    max_pct_below_52w_high: float = 0.25    # close >= 0.75 * high_52w
    min_pct_above_52w_low: float = 0.30     # close >= 1.30 * low_52w


@dataclass(frozen=True)
class BreakoutConfig:
    """Shared breakout confirmation on the most recent bar."""

    min_rvol: float = 1.8               # breakout-bar volume vs avg_vol_50
    min_close_range_pos: float = 0.5    # (close-low)/(high-low) — no big upper wick
    require_close_above_open: bool = True
    # A close more than this far above the buy point is extended, not a setup —
    # rejected whether or not the volume confirmed. Tighten rather than chase.
    max_extension_pct: float = 0.05


@dataclass(frozen=True)
class CupHandleConfig:
    lookback_bars: int = 200
    rim_neighborhood: int = 20          # rim high = max of this many bars each side
    min_depth: float = 0.15
    max_depth: float = 0.35
    recovery_tolerance: float = 0.05    # "recovered" = close within 5% of rim
    min_cup_bars: int = 35              # rim → recovery
    low_position_min: float = 0.25      # lowest bar must sit in the middle 50% of the cup
    low_position_max: float = 0.75
    handle_min_bars: int = 5
    handle_max_bars: int = 15
    handle_min_depth: float = 0.05
    handle_max_depth: float = 0.15
    handle_low_min_cup_fraction: float = 0.5   # handle_low > cup_low + 0.5*(rim-cup_low)
    handle_max_over_rim: float = 0.05           # handle high may poke at most 5% over the rim
    require_handle_volume_dryup: bool = True    # handle avg vol < cup right-side avg vol


@dataclass(frozen=True)
class FlatBaseConfig:
    min_bars: int = 25
    max_bars: int = 60
    max_depth: float = 0.15
    prior_advance_bars: int = 60
    min_prior_advance: float = 0.20     # +20% in the 60 bars before the base
    # The base starts when price first tags its top: one of the first N bars must
    # print a high within this tolerance of base_high. Stops the window from
    # swallowing the tail of the prior advance (which would loosen the stop).
    start_touch_bars: int = 3
    start_touch_tol: float = 0.03
    require_tightening: bool = True     # 2nd-half range <= 1st-half range
    require_volume_contraction: bool = True
    require_closes_above_sma50: bool = True


@dataclass(frozen=True)
class AscendingTriangleConfig:
    min_bars: int = 20
    max_bars: int = 60
    peak_distance: int = 4              # scipy.signal.find_peaks distance
    min_ceiling_touches: int = 3
    ceiling_tolerance: float = 0.02     # touches within 2% of each other
    max_high_over_ceiling: float = 0.02 # nothing in the window may exceed the ceiling by more
    require_touches_span: bool = True   # touches must fall in both halves of the window
    max_first_touch_pos: float = 0.3    # first ceiling touch within the first 30% of the window
    min_swing_lows: int = 2
    min_lows_r2: float = 0.6
    max_last_low_gap: float = 0.10      # last swing low within 10% of ceiling
    require_volume_decline: bool = True


@dataclass(frozen=True)
class BullFlagConfig:
    lookback_bars: int = 40
    pole_min_bars: int = 4
    pole_max_bars: int = 15
    pole_min_gain: float = 0.15
    pole_min_avg_rvol: float = 1.3
    pole_end_tolerance: float = 0.02    # the pole's last bar must be within 2% of the pole high
    flag_min_bars: int = 3
    flag_max_bars: int = 12
    max_retracement: float = 0.5
    max_flag_slope_per_bar: float = 0.0     # regression slope of close, as fraction of mean close
    max_flag_range_vs_pole: float = 0.40
    max_flag_avg_rvol: float = 0.8


@dataclass(frozen=True)
class ScoreWeights:
    """Composite 0-100 score. See ``patterns.scoring`` for how each part is measured.

    volume_dryup  — how much volume contracted through the base/handle/flag
    tightness     — how shallow/tight the consolidation is vs its allowed maximum
    duration      — base length vs the pattern's maximum span (longer = more built)
    trend         — strength of the long-term trend filter (200 SMA slope, distance
                    above the 200 SMA, 50 > 200, proximity to the 52-week high)
    """

    volume_dryup: float = 30.0
    tightness: float = 30.0
    duration: float = 20.0
    trend: float = 20.0


@dataclass(frozen=True)
class ScannerConfig:
    data: DataConfig = field(default_factory=DataConfig)
    prefilter: PrefilterConfig = field(default_factory=PrefilterConfig)
    breakout: BreakoutConfig = field(default_factory=BreakoutConfig)
    cup_handle: CupHandleConfig = field(default_factory=CupHandleConfig)
    flat_base: FlatBaseConfig = field(default_factory=FlatBaseConfig)
    ascending_triangle: AscendingTriangleConfig = field(default_factory=AscendingTriangleConfig)
    bull_flag: BullFlagConfig = field(default_factory=BullFlagConfig)
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    earnings_window_days: int = 10      # --earnings-filter drops names reporting within N days


DEFAULT_CONFIG = ScannerConfig()
