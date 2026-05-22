"""Tests for the swing scanner's per-MA alert-type routing (spec 56)."""

from __future__ import annotations

from analytics.swing_scanner import _alert_type_for


def test_alert_type_for_ema_levels():
    assert _alert_type_for("EMA 21") == "swing_bounce_ema21"
    assert _alert_type_for("EMA 50") == "swing_bounce_ema50"
    assert _alert_type_for("EMA 100") == "swing_bounce_ema100"
    assert _alert_type_for("EMA 200") == "swing_bounce_ema200"


def test_alert_type_for_sma_levels():
    assert _alert_type_for("SMA 50") == "swing_bounce_sma50"
    assert _alert_type_for("SMA 100") == "swing_bounce_sma100"
    assert _alert_type_for("SMA 200") == "swing_bounce_sma200"


def test_alert_type_for_rsi():
    assert _alert_type_for("RSI 30") == "swing_rsi_30"
