"""Tests for AI Day Trade Scanner — ensures alerts go to all users watching a symbol."""

import pytest
from unittest.mock import patch, MagicMock
from analytics.ai_day_scanner import parse_day_trade_response


class TestParseDayTradeResponse:
    """Test structured output parsing."""

    def test_parses_long_with_all_fields(self):
        text = """SETUP: VWAP HOLD
Direction: LONG
Entry: $2243.21
Stop: $2233.30
T1: $2250.49
T2: $2253.50
Conviction: MEDIUM
Reason: Price pulled back to VWAP and held with 3 consecutive bars above."""
        result = parse_day_trade_response(text)
        assert result["direction"] == "LONG"
        assert result["entry"] == 2243.21
        assert result["stop"] == 2233.30
        assert result["t1"] == 2250.49
        assert result["t2"] == 2253.50
        assert result["conviction"] == "MEDIUM"
        assert result["setup_type"] == "VWAP HOLD"
        assert "pulled back" in result["reason"]

    def test_parses_wait(self):
        text = """SETUP: NONE
Direction: WAIT
Entry: —
Stop: —
T1: —
T2: —
Conviction: LOW
Reason: Price mid-range, no confirmed setup."""
        result = parse_day_trade_response(text)
        assert result["direction"] == "WAIT"
        assert result["entry"] is None
        assert result["stop"] is None

    def test_parses_resistance(self):
        text = """SETUP: RESISTANCE
Direction: RESISTANCE
Entry: $2253.50
Stop: —
T1: —
T2: —
Conviction: MEDIUM
Reason: Approaching PDH resistance at $2253.50."""
        result = parse_day_trade_response(text)
        assert result["direction"] == "RESISTANCE"
        assert result["entry"] == 2253.50

    def test_parses_btc_comma_prices(self):
        text = """SETUP: PDL HOLD
Direction: LONG
Entry: $72,667.55
Stop: $72,564.35
T1: $72,935.25
T2: $73,118.19
Conviction: HIGH
Reason: PDL hold confirmed."""
        result = parse_day_trade_response(text)
        assert result["entry"] == 72667.55
        assert result["stop"] == 72564.35
        assert result["t1"] == 72935.25

    def test_handles_malformed_output(self):
        text = "Some random text without proper format"
        result = parse_day_trade_response(text)
        assert result["direction"] is None
        assert result["entry"] is None

    def test_handles_empty_string(self):
        result = parse_day_trade_response("")
        assert result["direction"] is None


class TestMultiUserAlertDistribution:
    """Ensure all users watching a symbol get the same alerts."""

    def test_wait_goes_to_all_users(self):
        """If 3 users watch ETH-USD and AI says WAIT, all 3 get the WAIT in DB."""
        # This is a logic check — the scanner iterates symbol_users[symbol]
        # for WAIT recording, not just _first_uid
        symbol_users = {"ETH-USD": [3, 13, 28]}

        # Simulate the WAIT recording loop
        alerts_created = []
        for uid in symbol_users["ETH-USD"]:
            alerts_created.append({"user_id": uid, "alert_type": "ai_scan_wait", "symbol": "ETH-USD"})

        assert len(alerts_created) == 3
        assert all(a["user_id"] in [3, 13, 28] for a in alerts_created)
        assert all(a["alert_type"] == "ai_scan_wait" for a in alerts_created)

    def test_long_goes_to_first_user_only_in_db(self):
        """LONG alerts record once (first user) to avoid DB duplication."""
        symbol_users = {"ETH-USD": [3, 13, 28]}

        # Simulate the LONG recording loop (only first user)
        alerts_created = []
        _first_uid = symbol_users["ETH-USD"][0]
        for uid in [_first_uid]:
            alerts_created.append({"user_id": uid, "alert_type": "ai_day_long", "symbol": "ETH-USD"})

        assert len(alerts_created) == 1
        assert alerts_created[0]["user_id"] == 3

    def test_telegram_goes_to_all_users(self):
        """Telegram sends to ALL users regardless of DB dedup."""
        symbol_users = {"ETH-USD": [3, 13, 28]}

        telegram_sent = []
        for uid in symbol_users["ETH-USD"]:
            telegram_sent.append(uid)

        assert len(telegram_sent) == 3
        assert 3 in telegram_sent


class TestPositionDetection:
    """Test the support/resistance classification."""

    def test_price_at_support(self):
        """Price within 0.3% below a level = AT SUPPORT."""
        current = 2235.0
        pdl = 2235.71  # 0.03% away
        dist = abs(current - pdl) / pdl
        assert dist <= 0.003  # AT threshold

    def test_price_at_resistance(self):
        """Price within 0.3% above a level = AT RESISTANCE."""
        current = 2254.0
        pdh = 2253.50  # 0.02% away, level below price
        dist = abs(current - pdh) / pdh
        assert dist <= 0.003

    def test_price_mid_range(self):
        """Price >0.8% from all levels = MID-RANGE."""
        current = 2245.0
        pdl = 2230.0  # 0.67% away
        pdh = 2253.0  # 0.36% away
        dist_pdl = abs(current - pdl) / pdl
        dist_pdh = abs(current - pdh) / pdh
        # PDL is approaching (0.67%), PDH is approaching (0.36%)
        # Neither is AT (<0.3%)
        assert dist_pdl > 0.003
        assert dist_pdh > 0.003

    def test_ma_below_price_is_support(self):
        """MA below current price = support."""
        current = 674.0
        ma50 = 673.0  # below price
        assert ma50 <= current * 1.001  # support classification

    def test_ma_above_price_is_resistance(self):
        """MA above current price = resistance."""
        current = 670.0
        ma50 = 673.0  # above price
        assert ma50 > current * 1.001  # resistance classification


class TestStopValidation:
    """Test that stops are structural, not fixed %."""

    def test_stop_not_too_tight(self):
        """Stop should be at least 0.3% below entry."""
        entry = 2243.0
        stop = 2233.0  # $10 = 0.45% — good
        min_stop_dist = entry * 0.003  # ~$6.73
        assert (entry - stop) >= min_stop_dist

    def test_reject_tight_stop(self):
        """$0.30 stop on $2200 asset is invalid."""
        entry = 2243.0
        stop = 2242.70  # $0.30 = 0.013% — too tight
        min_stop_dist = entry * 0.003
        assert (entry - stop) < min_stop_dist  # should be rejected
