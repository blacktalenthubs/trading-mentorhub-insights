"""Exit-plan engine — one simple target/exit per trade style (backend-owned)."""

from analytics.exit_plan import trade_style, build_exit_plan


def test_style_mapping():
    assert trade_style("tv_rc_4h") == "Day"
    assert trade_style("tv_staged_pdl_reclaim") == "Day"
    assert trade_style("tv_staged_orl_held") == "Day"
    assert trade_style("tv_gap_up_continuation_long") == "Gap-and-go"
    assert trade_style("tv_rsi_oversold") == "Swing"
    assert trade_style("tv_ema_5_20_cross") == "Swing"
    assert trade_style("tv_ma_bounce_long_v3_ema50") == "Swing"
    assert trade_style("tv_weekly_ma_held") == "Long hold"
    assert trade_style("tv_ma_bounce_long_v3_sma200") == "Long hold"


def test_day_uses_next_resistance():
    p = build_exit_plan("tv_rc_4h", "BUY", entry=100.0, stop=98.0, next_resistance=105.0)
    assert p["style"] == "day"
    assert p["label"] == "Day trade"
    assert p["target"] == 105.0
    assert "next resistance" in p["exit"]


def test_gap_and_go_rsi75_morning_low():
    p = build_exit_plan("tv_gap_up_continuation_long", "BUY", entry=100.0, stop=99.0,
                        rsi=62, morning_low=97.5)
    assert p["style"] == "gap"
    assert p["target"] == "RSI 75+"
    assert p["stop"] == 97.5  # morning low overrides the raw stop
    assert "RSI 75+" in p["exit"] and "morning low" in p["exit"]


def test_swing_rsi70_trail_pdl():
    p = build_exit_plan("tv_rsi_oversold", "BUY", entry=50.0, stop=48.0, rsi=33)
    assert p["style"] == "swing"
    assert p["target"] == "RSI 70"
    assert "RSI 70" in p["exit"] and "PDL" in p["exit"]
    assert "now 33" in p["exit"]


def test_long_hold_rsi70_or_5w_ema():
    p = build_exit_plan("tv_weekly_ma_held", "BUY", entry=200.0, stop=185.0, weekly_rsi=55)
    assert p["style"] == "long"
    assert "RSI 70" in p["exit"] and "5-week EMA" in p["exit"]
    assert "now 55" in p["exit"]
