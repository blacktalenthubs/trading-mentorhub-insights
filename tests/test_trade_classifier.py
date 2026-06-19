"""Tests for the day/swing trade classifier (Sub-spec L / #64)."""

from analytics.trade_classifier import classify_trade


def test_slow_ema_bounce_is_swing():
    assert classify_trade("tv_ma_bounce_long_v3_ema50")[0] == "swing"
    assert classify_trade("tv_ma_bounce_long_v3_ema21")[0] == "swing"
    assert classify_trade("tv_ma_bounce_long_v3_ema200")[0] == "swing"
    assert classify_trade("tv_ma_bounce_long_v3_sma50")[0] == "swing"


def test_fast_8ema_bounce_is_day():
    assert classify_trade("tv_ma_bounce_long_v3_ema8")[0] == "day"


def test_momentum_and_weekly_types_are_swing():
    for t in ("tv_rsi_oversold", "tv_ema_5_20_cross", "tv_weekly_rc", "tv_rsi_70"):
        assert classify_trade(t)[0] == "swing"


def test_core_level_entries_are_day():
    for t in ("tv_staged_pdl_held", "tv_staged_pwh_held", "tv_rc_4h",
              "tv_staged_orl_held", "tv_gap_up_continuation_long"):
        assert classify_trade(t)[0] == "day"


def test_day_trade_above_70_rsi_is_swing_eligible():
    tt, elig = classify_trade("tv_staged_pwh_held", rsi=70.93)
    assert tt == "day"
    assert elig is True


def test_day_trade_below_70_not_swing_eligible():
    tt, elig = classify_trade("tv_staged_pwh_held", rsi=55.0)
    assert tt == "day"
    assert elig is False


def test_swing_never_flags_swing_eligible():
    # swing_eligible only annotates DAY trades
    _, elig = classify_trade("tv_ma_bounce_long_v3_ema50", rsi=72.0)
    assert elig is False


def test_unknown_type_defaults_day():
    assert classify_trade("tv_something_new")[0] == "day"
    assert classify_trade(None)[0] == "day"
