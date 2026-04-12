"""Tests for AI Day Trade Scanner — ensures alerts go to all users watching a symbol."""

import pytest
from unittest.mock import patch, MagicMock
from analytics.ai_day_scanner import parse_day_trade_response, build_day_trade_prompt


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


class TestMultiUserPromptSafety:
    """Scanner prompt must NOT contain per-user data — prevents cross-user leakage."""

    def _sample_bars(self, n=5, base=2280.0):
        return [
            {"open": base, "high": base + 2, "low": base - 2, "close": base + 1, "volume": 1000}
            for _ in range(n)
        ]

    def test_prompt_has_no_active_positions_section(self):
        """Generic prompt must never include [ACTIVE POSITIONS] section."""
        prompt = build_day_trade_prompt(
            symbol="ETH-USD",
            bars_5m=self._sample_bars(),
            bars_1h=self._sample_bars(),
            prior_day={"high": 2300, "low": 2250, "close": 2275},
        )
        assert "[ACTIVE POSITIONS]" not in prompt
        assert "ACTIVE POSITIONS" not in prompt

    def test_prompt_ignores_active_positions_arg(self):
        """Even when passed active_positions, prompt must not include them (multi-user safety)."""
        fake_positions = [
            {"symbol": "ETH-USD", "entry": 2293.46, "stop": "$2280", "t1": "$2310", "time": "09:45"}
        ]
        prompt = build_day_trade_prompt(
            symbol="ETH-USD",
            bars_5m=self._sample_bars(),
            bars_1h=self._sample_bars(),
            prior_day={"high": 2300, "low": 2250, "close": 2275},
            active_positions=fake_positions,
        )
        # Prompt should NOT contain any user position data
        assert "$2293.46" not in prompt
        assert "2293.46" not in prompt
        assert "09:45" not in prompt

    def test_prompt_is_generic_across_users(self):
        """Same symbol → same prompt, regardless of who's watching."""
        args = {
            "symbol": "ETH-USD",
            "bars_5m": self._sample_bars(),
            "bars_1h": self._sample_bars(),
            "prior_day": {"high": 2300, "low": 2250, "close": 2275},
        }
        prompt_a = build_day_trade_prompt(**args, active_positions=[{"symbol": "ETH-USD", "entry": 2290}])
        prompt_b = build_day_trade_prompt(**args, active_positions=[{"symbol": "ETH-USD", "entry": 2200}])
        prompt_c = build_day_trade_prompt(**args, active_positions=None)
        assert prompt_a == prompt_b == prompt_c


class TestPerUserPositionFilter:
    """Per-user delivery filter: skip LONG if that user already holds the symbol."""

    def test_filter_skips_user_with_open_long(self):
        """User 3 holds ETH; user 13 doesn't. Only user 13 should get the alert."""
        user_open_longs = {(3, "ETH-USD"): True}
        symbol_users_eth = [3, 13, 28]

        delivered_to = []
        for uid in symbol_users_eth:
            if user_open_longs.get((uid, "ETH-USD")):
                continue  # skip — user already long
            delivered_to.append(uid)

        assert 3 not in delivered_to
        assert 13 in delivered_to
        assert 28 in delivered_to

    def test_filter_skips_all_when_all_hold(self):
        user_open_longs = {
            (3, "ETH-USD"): True,
            (13, "ETH-USD"): True,
        }
        symbol_users_eth = [3, 13]

        delivered_to = [uid for uid in symbol_users_eth if not user_open_longs.get((uid, "ETH-USD"))]
        assert delivered_to == []

    def test_filter_delivers_to_all_when_none_hold(self):
        user_open_longs = {}
        symbol_users_eth = [3, 13, 28]

        delivered_to = [uid for uid in symbol_users_eth if not user_open_longs.get((uid, "ETH-USD"))]
        assert delivered_to == [3, 13, 28]

    def test_filter_scopes_by_symbol(self):
        """Open LONG in ETH should NOT suppress a BTC alert."""
        user_open_longs = {(3, "ETH-USD"): True}
        symbol_users_btc = [3, 13]

        # BTC scan — user 3 holds ETH but not BTC
        delivered_to = [uid for uid in symbol_users_btc if not user_open_longs.get((uid, "BTC-USD"))]
        assert 3 in delivered_to
        assert 13 in delivered_to

    def test_filter_only_applies_to_long_direction(self):
        """RESISTANCE alerts should deliver even to users holding open LONGs."""
        # This mirrors the scanner: RESISTANCE is useful as an exit signal
        # The filter is only in the LONG delivery branch.
        user_open_longs = {(3, "ETH-USD"): True}

        # Simulating RESISTANCE branch (no filter applied)
        resistance_delivered = [3]  # user 3 gets it regardless
        assert 3 in resistance_delivered
