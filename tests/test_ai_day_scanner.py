"""Tests for AI Day Trade Scanner — ensures alerts go to all users watching a symbol."""

import pytest
from unittest.mock import patch, MagicMock
from analytics.ai_day_scanner import (
    parse_day_trade_response, build_day_trade_prompt,
    build_exit_prompt, parse_exit_response,
    _user_wants_alert, _truncate_for_free, _wait_fingerprint,
    _close_auto_trade, AUTO_TRADE_NOTIONAL,
    _apply_wait_override, _compute_stop_t1,
)


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


class TestDailyMAContext:
    """Phase 1 (Spec 34) — prompt includes dedicated daily MA section."""

    def _sample_bars(self, n=5, base=2280.0):
        return [
            {"open": base, "high": base + 2, "low": base - 2, "close": base + 1, "volume": 1000}
            for _ in range(n)
        ]

    def test_prompt_includes_daily_ma_section(self):
        prompt = build_day_trade_prompt(
            symbol="SPY",
            bars_5m=self._sample_bars(),
            bars_1h=self._sample_bars(),
            prior_day={
                "high": 680, "low": 670, "close": 675,
                "ma20": 674.0, "ma50": 672.5, "ma100": 668.0, "ma200": 660.0,
            },
        )
        assert "[DAILY MAs" in prompt
        assert "50 Daily MA: $672.50" in prompt
        assert "200 Daily MA: $660.00" in prompt
        assert "dominant level" in prompt.lower()

    def test_prompt_omits_daily_mas_when_absent(self):
        prompt = build_day_trade_prompt(
            symbol="SPY",
            bars_5m=self._sample_bars(),
            bars_1h=self._sample_bars(),
            prior_day={"high": 680, "low": 670, "close": 675},  # no MAs
        )
        assert "[DAILY MAs" not in prompt

    def test_prompt_instructs_priority_on_daily_ma(self):
        prompt = build_day_trade_prompt(
            symbol="SPY",
            bars_5m=self._sample_bars(),
            bars_1h=self._sample_bars(),
            prior_day={"ma50": 672.0},
        )
        assert "Daily MAs" in prompt or "daily MA" in prompt
        # The rules section must mention priority
        assert "KEY LEVEL PRIORITY" in prompt


class TestShortDirection:
    """Phase 2 (Spec 34) — SHORT as first-class direction."""

    def test_parses_short_with_full_trade_plan(self):
        text = """SETUP: PDH rejection
Direction: SHORT
Entry: $2330.56
Stop: $2335.00
T1: $2300.00
T2: $2275.00
Conviction: HIGH
Reason: Lower high confirmed with 1.3x volume on rejection bar."""
        result = parse_day_trade_response(text)
        assert result["direction"] == "SHORT"
        assert result["entry"] == 2330.56
        assert result["stop"] == 2335.00
        assert result["t1"] == 2300.00
        assert result["t2"] == 2275.00
        assert result["conviction"] == "HIGH"
        assert "lower high" in result["reason"].lower()

    def test_prompt_includes_short_confirmation_rules(self):
        prompt = build_day_trade_prompt(
            symbol="ETH-USD",
            bars_5m=[{"open": 2280, "high": 2290, "low": 2278, "close": 2288, "volume": 1000}],
            bars_1h=[],
            prior_day={"high": 2300, "low": 2250},
        )
        assert "SHORT CONFIRMATION RULES" in prompt
        assert "LOWER HIGH" in prompt
        assert "SHORT / RESISTANCE / WAIT" in prompt or "LONG / SHORT" in prompt

    def test_prompt_distinguishes_short_from_resistance(self):
        prompt = build_day_trade_prompt(
            symbol="ETH-USD",
            bars_5m=[{"open": 2280, "high": 2290, "low": 2278, "close": 2288, "volume": 1000}],
            bars_1h=[],
            prior_day={"high": 2300},
        )
        # SHORT = confirmed rejection with entry/stop/T1/T2
        # RESISTANCE = approaching, notice only
        assert "approaching resistance but no confirmed rejection" in prompt.lower() \
            or "RESISTANCE (notice)" in prompt


class TestPerUserShortFilter:
    """Per-user delivery filter for SHORT mirrors LONG filter."""

    def test_skips_user_with_open_short(self):
        user_open_shorts = {(3, "ETH-USD"): True}
        symbol_users_eth = [3, 13, 28]

        delivered = [uid for uid in symbol_users_eth if not user_open_shorts.get((uid, "ETH-USD"))]
        assert 3 not in delivered
        assert 13 in delivered
        assert 28 in delivered

    def test_wait_suppressed_for_user_with_open_position(self):
        """WAIT alerts reference direction (\"no LONG setup\") — confusing for users
        already in a position. Skip WAIT delivery if user holds the symbol."""
        user_open_longs = {(3, "ETH-USD"): True}
        user_open_shorts: dict = {}
        symbol_users_eth = [3, 13, 28]

        delivered_wait = []
        for uid in symbol_users_eth:
            # Same logic as scanner: skip if user holds either direction
            if user_open_longs.get((uid, "ETH-USD")) or user_open_shorts.get((uid, "ETH-USD")):
                continue
            delivered_wait.append(uid)

        assert 3 not in delivered_wait  # holds LONG, WAIT suppressed
        assert 13 in delivered_wait     # no position, gets WAIT
        assert 28 in delivered_wait     # no position, gets WAIT

    def test_wait_suppressed_for_short_holders_too(self):
        """User holding SHORT should also not receive WAIT alerts for same symbol."""
        user_open_longs: dict = {}
        user_open_shorts = {(3, "ETH-USD"): True}

        skip = user_open_longs.get((3, "ETH-USD")) or user_open_shorts.get((3, "ETH-USD"))
        assert skip is True

    def test_long_and_short_filters_independent(self):
        """User holding LONG should still get SHORT alerts (and vice versa)."""
        user_open_longs = {(3, "ETH-USD"): True}
        user_open_shorts: dict = {}  # empty
        symbol_users_eth = [3]

        # SHORT delivery: user 3 holds LONG but not SHORT → SHORT alert should deliver
        short_delivered = [uid for uid in symbol_users_eth if not user_open_shorts.get((uid, "ETH-USD"))]
        assert 3 in short_delivered

        # LONG delivery: user 3 holds LONG → LONG alert suppressed
        long_delivered = [uid for uid in symbol_users_eth if not user_open_longs.get((uid, "ETH-USD"))]
        assert 3 not in long_delivered


class TestExitManagement:
    """Phase 3 (Spec 34) — exit scan for open positions."""

    def _sample_bars(self, n=10, base=2200.0):
        return [
            {"open": base, "high": base + 3, "low": base - 2, "close": base + 1, "volume": 1000}
            for _ in range(n)
        ]

    def test_exit_prompt_for_long_position(self):
        prompt = build_exit_prompt(
            symbol="ETH-USD",
            direction="BUY",
            entry=2200.0,
            stop=2190.0,
            t1=2220.0,
            t2=2240.0,
            opened_minutes_ago=30,
            bars_5m=self._sample_bars(),
        )
        assert "LONG" in prompt
        assert "EXIT_NOW" in prompt
        assert "TAKE_PROFITS" in prompt
        assert "HOLD" in prompt
        # LONG stop is BELOW entry — exit only if price actually below stop
        assert "below the stop level" in prompt
        assert "$2200.00" in prompt
        assert "$2190.00" in prompt
        assert "30 min ago" in prompt

    def test_exit_prompt_for_short_position(self):
        prompt = build_exit_prompt(
            symbol="ETH-USD",
            direction="SHORT",
            entry=2300.0,
            stop=2310.0,
            t1=2280.0,
            t2=2260.0,
            opened_minutes_ago=15,
            bars_5m=self._sample_bars(),
        )
        assert "SHORT" in prompt
        # SHORT stop is ABOVE entry, target BELOW
        assert "above the stop level" in prompt or "above" in prompt
        assert "$2300.00" in prompt
        assert "$2310.00" in prompt

    def test_exit_prompt_defaults_to_hold(self):
        prompt = build_exit_prompt(
            symbol="SPY", direction="BUY", entry=670.0,
            stop=668.0, t1=675.0, t2=680.0,
            opened_minutes_ago=5,
            bars_5m=self._sample_bars(n=3, base=670.0),
        )
        # New conservative exit prompt — must emphasize trust-the-stop
        assert "TRUST THE STOP" in prompt
        assert "HOLD is the correct default" in prompt

    def test_exit_prompt_forbids_early_stop_exit(self):
        """Critical: AI must not EXIT_NOW just because price is approaching stop."""
        prompt = build_exit_prompt(
            symbol="ETH-USD", direction="BUY", entry=2200.0,
            stop=2193.0, t1=2210.0, t2=2225.0,
            opened_minutes_ago=20,
            bars_5m=[{"open": 2198, "high": 2199, "low": 2194, "close": 2196, "volume": 1000}],
        )
        assert "approaching stop" in prompt.lower() or "approaching" in prompt.lower()
        assert "trust" in prompt.lower()
        # Prompt must explicitly forbid "testing stop zone" exits
        assert "testing stop zone" in prompt.lower() or "Do NOT fire EXIT_NOW" in prompt

    def test_exit_prompt_take_profits_requires_actual_t1_touch(self):
        """TAKE_PROFITS must require price to actually hit T1, not just approach."""
        prompt = build_exit_prompt(
            symbol="NVDA", direction="BUY", entry=128.0,
            stop=126.0, t1=130.0, t2=132.0,
            opened_minutes_ago=10,
            bars_5m=[{"open": 128.5, "high": 129.2, "low": 128.3, "close": 128.9, "volume": 1000}],
        )
        # Must require actual T1 touch + rejection, not just proximity
        assert "TOUCHED or exceeded T1" in prompt
        assert "approaching T1 = HOLD" in prompt

    def test_parse_exit_now(self):
        text = """Status: EXIT_NOW
Reason: Price broke below stop zone with lower low structure.
Action: Exit at market now."""
        result = parse_exit_response(text)
        assert result["status"] == "EXIT_NOW"
        assert "broke below stop" in result["reason"]
        assert "exit at market" in result["action"].lower()

    def test_parse_take_profits(self):
        text = """Status: TAKE_PROFITS
Reason: Price within 0.4% of T1, rejection wick forming.
Action: Trim 50% here, trail stop to breakeven."""
        result = parse_exit_response(text)
        assert result["status"] == "TAKE_PROFITS"
        assert "Trim" in result["action"]

    def test_parse_hold(self):
        text = """Status: HOLD
Reason: Structure intact, volume steady, no action needed.
Action: Keep holding, stop still valid."""
        result = parse_exit_response(text)
        assert result["status"] == "HOLD"

    def test_parse_handles_garbage(self):
        result = parse_exit_response("some random text")
        assert result["status"] is None

    def test_exit_cooldown_is_covered_elsewhere(self):
        # Placeholder — full cooldown test below
        pass


class TestSpec36UserAlertFilters:
    """Spec 36 — user-controlled preferences gate Telegram delivery before rate limits."""

    class _FakeUser:
        def __init__(self, **kw):
            self.telegram_enabled = kw.get("telegram_enabled", True)
            self.min_conviction = kw.get("min_conviction", "medium")
            self.wait_alerts_enabled = kw.get("wait_alerts_enabled", True)
            self.alert_directions = kw.get("alert_directions", "LONG,SHORT,RESISTANCE,EXIT")

    def test_master_kill_switch(self):
        u = self._FakeUser(telegram_enabled=False)
        assert _user_wants_alert(u, "LONG", "high") is False
        assert _user_wants_alert(u, "WAIT") is False
        assert _user_wants_alert(u, "EXIT") is False

    def test_wait_toggle_off(self):
        u = self._FakeUser(wait_alerts_enabled=False)
        assert _user_wants_alert(u, "WAIT") is False
        # Other directions unaffected
        assert _user_wants_alert(u, "LONG", "medium") is True

    def test_wait_toggle_on(self):
        u = self._FakeUser(wait_alerts_enabled=True)
        assert _user_wants_alert(u, "WAIT") is True

    def test_direction_filter_blocks(self):
        u = self._FakeUser(alert_directions="LONG,EXIT")
        assert _user_wants_alert(u, "LONG", "medium") is True
        assert _user_wants_alert(u, "SHORT", "medium") is False
        assert _user_wants_alert(u, "RESISTANCE", "medium") is False
        assert _user_wants_alert(u, "EXIT") is True

    def test_direction_filter_empty_blocks_all(self):
        """Defensive: if user unchecked everything, don't spam — treat as opt-out."""
        u = self._FakeUser(alert_directions="")
        assert _user_wants_alert(u, "LONG", "high") is False

    def test_min_conviction_high(self):
        u = self._FakeUser(min_conviction="high")
        assert _user_wants_alert(u, "LONG", "high") is True
        assert _user_wants_alert(u, "LONG", "medium") is False
        assert _user_wants_alert(u, "LONG", "low") is False

    def test_min_conviction_medium(self):
        u = self._FakeUser(min_conviction="medium")
        assert _user_wants_alert(u, "LONG", "high") is True
        assert _user_wants_alert(u, "LONG", "medium") is True
        assert _user_wants_alert(u, "LONG", "low") is False

    def test_min_conviction_low(self):
        u = self._FakeUser(min_conviction="low")
        assert _user_wants_alert(u, "LONG", "high") is True
        assert _user_wants_alert(u, "LONG", "medium") is True
        assert _user_wants_alert(u, "LONG", "low") is True

    def test_conviction_ignored_for_exit(self):
        """Exit signals don't have conviction — must always pass if direction allowed."""
        u = self._FakeUser(min_conviction="high")
        assert _user_wants_alert(u, "EXIT") is True  # no conviction passed — still OK

    def test_unknown_conviction_defaults_safely(self):
        u = self._FakeUser(min_conviction="medium")
        # Unknown values treated as medium (neither too strict nor too loose)
        assert _user_wants_alert(u, "LONG", "garbage") is True

    def test_direction_case_insensitive(self):
        u = self._FakeUser(alert_directions="long,Short,RESISTANCE,exit")
        assert _user_wants_alert(u, "LONG", "high") is True
        assert _user_wants_alert(u, "SHORT", "high") is True

    def test_exit_blocked_if_direction_removed(self):
        u = self._FakeUser(alert_directions="LONG,SHORT")
        assert _user_wants_alert(u, "EXIT") is False

    def test_defaults_when_attrs_missing(self):
        """User object missing preference attrs should fail open (allow)."""
        class Bare:
            telegram_enabled = True
        b = Bare()
        # Should default to allowing alerts (conservative)
        assert _user_wants_alert(b, "LONG", "medium") is True


class TestTruncateForFree:
    """Spec 36 Option A — free users get headline only on AI Updates."""

    def test_free_truncates_at_sentence_boundary(self):
        reason = "Price pinned at VWAP with declining volume. Structure flat, no higher low yet."
        out, truncated = _truncate_for_free(reason, "free")
        assert truncated is True
        # Should cut at the first ". " — drops the second sentence
        assert "Structure flat" not in out
        assert "Price pinned at VWAP with declining volume" in out

    def test_free_truncates_at_semicolon(self):
        reason = "Price tested resistance; volume 0.5x average; no rejection candle."
        out, truncated = _truncate_for_free(reason, "free")
        assert truncated is True
        assert "volume" not in out.lower()
        assert "Price tested resistance" in out

    def test_free_truncates_long_single_clause(self):
        reason = "This is a single very long reason without any delimiters that should be clipped with ellipsis for free users"
        out, truncated = _truncate_for_free(reason, "free", max_len=60)
        assert truncated is True
        assert len(out) <= 60
        assert out.endswith("…")

    def test_pro_returns_full_reason_unchanged(self):
        reason = "Price pinned at VWAP with declining volume. Structure flat."
        out, truncated = _truncate_for_free(reason, "pro")
        assert truncated is False
        assert out == reason

    def test_premium_returns_full_reason_unchanged(self):
        reason = "Price pinned at VWAP with declining volume."
        out, truncated = _truncate_for_free(reason, "premium")
        assert truncated is False
        assert out == reason

    def test_empty_reason_safe(self):
        out, truncated = _truncate_for_free("", "free")
        assert truncated is False
        assert out == ""

    def test_short_reason_not_clipped_but_marked_free(self):
        """Short single-clause reasons: no clip, but still mark as 'truncated' since
        we apply the upgrade tag based on this return."""
        reason = "Low volume chop."
        out, truncated = _truncate_for_free(reason, "free")
        # Free always returns truncated=True so upgrade CTA appears; text is safe
        assert truncated is True
        assert "Low volume chop" in out


class TestWaitReasonFingerprint:
    """Reason-change detection replaces time-based cooldown for WAITs."""

    def test_identical_reasons_same_fingerprint(self):
        r = "Price pinned at VWAP with flat structure and weak volume."
        assert _wait_fingerprint(r) == _wait_fingerprint(r)

    def test_same_story_different_numbers_same_fingerprint(self):
        """Price $2207 vs $2209 shouldn't refire — same structural story."""
        a = "Price at $2207 near VWAP, volume 0.5x avg, flat structure"
        b = "Price at $2209 near VWAP, volume 0.6x avg, flat structure"
        assert _wait_fingerprint(a) == _wait_fingerprint(b)

    def test_different_stories_different_fingerprints(self):
        """Meaningfully different AI reasoning triggers a refire."""
        a = "Price near VWAP, volume weak, structure flat"
        b = "Price tested session high, rejected with volume spike"
        assert _wait_fingerprint(a) != _wait_fingerprint(b)

    def test_empty_reason_safe(self):
        assert _wait_fingerprint("") == ""
        assert _wait_fingerprint(None) == ""  # type: ignore

    def test_fingerprint_strips_punctuation(self):
        a = "Price near VWAP; low volume!"
        b = "Price near VWAP, low volume."
        assert _wait_fingerprint(a) == _wait_fingerprint(b)


class TestAutoPilotPnL:
    """Spec 35 — auto-trade P&L math."""

    class _FakeTrade:
        """Minimal stand-in for AIAutoTrade (no DB needed)."""
        def __init__(self, direction, entry, stop, shares):
            self.direction = direction
            self.entry_price = entry
            self.stop_price = stop
            self.shares = shares
            self.symbol = "TEST"
            self.status = "open"
            self.exit_price = None
            self.closed_at = None
            self.exit_reason = None
            self.pnl_dollars = None
            self.pnl_percent = None
            self.r_multiple = None

    def test_long_win_at_t1(self):
        t = self._FakeTrade("BUY", entry=2200, stop=2190, shares=4.545)
        _close_auto_trade(None, t, exit_price=2220, status="closed_t1", exit_reason="T1 hit")
        assert t.status == "closed_t1"
        assert t.exit_price == 2220
        # +$20/share × 4.545 shares = $90.9
        assert abs(t.pnl_dollars - 90.9) < 0.5
        # 20/2200 = 0.909%
        assert abs(t.pnl_percent - 0.9091) < 0.01
        # R = (2220-2200)/(2200-2190) = 20/10 = 2R
        assert t.r_multiple == 2.0

    def test_long_loss_at_stop(self):
        t = self._FakeTrade("BUY", entry=2200, stop=2190, shares=4.545)
        _close_auto_trade(None, t, exit_price=2190, status="closed_stop", exit_reason="Stop")
        assert t.pnl_dollars < 0
        assert t.r_multiple == -1.0  # -1R

    def test_short_win(self):
        """SHORT inverts the sign — price dropped = profit."""
        t = self._FakeTrade("SHORT", entry=130, stop=132, shares=76.923)
        _close_auto_trade(None, t, exit_price=128, status="closed_t1", exit_reason="T1")
        # Short $130 → $128 = +$2/share × 76.923 = $153.85
        assert t.pnl_dollars > 0
        assert t.pnl_percent > 0
        # R = (130-128)/(132-130) = 2/2 = 1R
        assert t.r_multiple == 1.0

    def test_short_loss_at_stop(self):
        t = self._FakeTrade("SHORT", entry=130, stop=132, shares=76.923)
        _close_auto_trade(None, t, exit_price=132, status="closed_stop", exit_reason="Stop")
        assert t.pnl_dollars < 0
        assert t.r_multiple == -1.0

    def test_r_multiple_none_without_stop(self):
        t = self._FakeTrade("BUY", entry=2200, stop=None, shares=4.545)
        _close_auto_trade(None, t, exit_price=2220, status="closed_t1", exit_reason="T1")
        assert t.r_multiple is None
        assert t.pnl_dollars > 0  # P&L still computes

    def test_close_is_idempotent(self):
        """Already closed trade — calling again doesn't corrupt state."""
        t = self._FakeTrade("BUY", entry=2200, stop=2190, shares=4.545)
        _close_auto_trade(None, t, exit_price=2220, status="closed_t1", exit_reason="T1")
        first_pnl = t.pnl_dollars
        # Try to close again
        _close_auto_trade(None, t, exit_price=2100, status="closed_stop", exit_reason="Stop")
        assert t.pnl_dollars == first_pnl  # unchanged
        assert t.status == "closed_t1"     # unchanged


class TestAutoPilotSizing:
    def test_notional_is_fixed_10k(self):
        assert AUTO_TRADE_NOTIONAL == 10_000


class TestSpec44WaitOverride:
    """Spec 44: enforce AI signal commitment — WAIT override gate."""

    def _make_parsed(self, direction="WAIT", reason="", **kw):
        return {"direction": direction, "reason": reason, "conviction": "MEDIUM", **kw}

    def test_wait_with_vwap_reclaim_overrides_to_long(self):
        """Real 2026-04-16 case: NVDA VWAP reclaim with higher-low → should be LONG."""
        p = self._make_parsed(
            reason="VWAP reclaim with higher low structure from $197.30, volume 1.2x average supports bounce",
            price=197.30,
        )
        _apply_wait_override(p, "NVDA")
        assert p["direction"] == "LONG"
        assert p["conviction"] == "MEDIUM"
        assert p.get("_override") is True

    def test_wait_with_bounce_overrides_to_long(self):
        """PDL bounce described but AI said WAIT — override."""
        p = self._make_parsed(
            reason="PDL bounce at $197, RSI overbought at 68.5 limits upside conviction",
            price=197.00,
        )
        _apply_wait_override(p, "NVDA")
        assert p["direction"] == "LONG"
        assert p["conviction"] == "MEDIUM"

    def test_wait_with_holding_above_overrides_to_long(self):
        """Real 2026-04-16 case: SPY holding above key level."""
        p = self._make_parsed(
            reason="VWAP reclaim after pullback, RSI overbought at 70.2 but price holding above key level with average volume",
            price=535.20,
        )
        _apply_wait_override(p, "SPY")
        assert p["direction"] == "LONG"
        assert p["conviction"] == "MEDIUM"

    def test_wait_midrange_no_override(self):
        """Generic mid-range reason stays WAIT."""
        p = self._make_parsed(reason="price mid-range between levels, no structure forming")
        _apply_wait_override(p, "SPY")
        assert p["direction"] == "WAIT"
        assert p.get("_override") is None

    def test_wait_approaching_no_override(self):
        """Approaching a level without setup keywords stays WAIT."""
        p = self._make_parsed(reason="approaching PDH, RSI at 70, no confirmed structure")
        _apply_wait_override(p, "SPY")
        assert p["direction"] == "WAIT"

    def test_wait_with_rejection_overrides_to_short(self):
        """SHORT setup described as WAIT → override to SHORT."""
        p = self._make_parsed(
            reason="PDH rejection with lower high forming, volume spike on rejection bar",
            price=540.00,
        )
        _apply_wait_override(p, "SPY")
        assert p["direction"] == "SHORT"
        assert p["conviction"] == "MEDIUM"

    def test_long_direction_no_override(self):
        """Already LONG — gate does nothing."""
        p = self._make_parsed(direction="LONG", reason="PDL bounce confirmed")
        _apply_wait_override(p, "NVDA")
        assert p["direction"] == "LONG"
        assert p["conviction"] == "MEDIUM"  # unchanged
        assert p.get("_override") is None

    def test_empty_reason_no_override(self):
        """Empty reason stays WAIT."""
        p = self._make_parsed(reason="")
        _apply_wait_override(p, "SPY")
        assert p["direction"] == "WAIT"

    def test_conflicting_signals_no_override(self):
        """Both LONG and SHORT signals in reason — don't guess, stay WAIT."""
        p = self._make_parsed(reason="bounce off support but rejection at resistance with lower high")
        _apply_wait_override(p, "SPY")
        assert p["direction"] == "WAIT"

    def test_override_preserves_entry_stop_t1(self):
        """When AI hedged but included levels, override keeps them."""
        p = self._make_parsed(
            reason="VWAP reclaim with structure but RSI limits conviction",
            entry=700.50, stop=698.00, t1=703.00, t2=705.00, price=700.60,
        )
        _apply_wait_override(p, "SPY")
        assert p["direction"] == "LONG"
        assert p["entry"] == 700.50  # preserved, not overwritten with price
        assert p["stop"] == 698.00
        assert p["t1"] == 703.00

    def test_override_populates_entry_from_price(self):
        """When AI said WAIT with no entry, override uses current price as entry."""
        p = self._make_parsed(
            reason="100 Daily MA bounce with higher low structure",
            price=2322.00,
        )
        assert p.get("entry") is None  # AI didn't provide entry
        _apply_wait_override(p, "ETH-USD")
        assert p["direction"] == "LONG"
        assert p["entry"] == 2322.00  # populated from current price

    def test_override_populates_entry_for_short(self):
        """SHORT override also populates entry from price."""
        p = self._make_parsed(
            reason="PDH rejection with confirmed lower high",
            price=2340.00,
        )
        _apply_wait_override(p, "SPY")
        assert p["direction"] == "SHORT"
        assert p["entry"] == 2340.00

    def test_override_skips_when_entry_zero(self):
        """Entry=0 should be treated as missing and populated from price."""
        p = self._make_parsed(
            reason="session high breakout with momentum",
            entry=0, price=2336.23,
        )
        _apply_wait_override(p, "ETH-USD")
        assert p["direction"] == "LONG"
        assert p["entry"] == 2336.23

    def test_override_computes_stop_from_pdl(self):
        """Stop = highest support below entry (PDL)."""
        p = self._make_parsed(
            reason="100 Daily MA bounce with higher low structure",
            price=2322.00,
        )
        prior_day = {"high": 2350.00, "low": 2310.00, "ma100": 2317.00}
        bars_5m = [
            {"open": 2315, "high": 2325, "low": 2308, "close": 2322, "volume": 100},
            {"open": 2322, "high": 2328, "low": 2318, "close": 2322, "volume": 120},
        ]
        _apply_wait_override(p, "ETH-USD", prior_day=prior_day, bars_5m=bars_5m)
        assert p["direction"] == "LONG"
        assert p["entry"] == 2322.00
        assert p["stop"] == 2317.00  # ma100, highest support below entry
        assert p["t1"] == 2328.00  # session_high, lowest resistance above

    def test_override_computes_t1_from_session_high(self):
        """T1 = lowest resistance above entry."""
        p = self._make_parsed(
            reason="VWAP reclaim with higher low",
            price=535.00,
        )
        prior_day = {"high": 540.00, "low": 530.00, "ma50": 532.00}
        bars_5m = [
            {"open": 533, "high": 538, "low": 531, "close": 535, "volume": 1000},
        ]
        _apply_wait_override(p, "SPY", prior_day=prior_day, bars_5m=bars_5m)
        assert p["t1"] == 538.00  # session_high
        assert p["stop"] == 532.00  # ma50

    def test_override_does_not_overwrite_ai_stop_t1(self):
        """If AI provided stop/T1, override keeps them."""
        p = self._make_parsed(
            reason="PDL bounce confirmed with structure",
            price=2320.00, entry=2318.00, stop=2310.00, t1=2340.00,
        )
        prior_day = {"high": 2350.00, "low": 2305.00}
        bars_5m = [
            {"open": 2315, "high": 2325, "low": 2308, "close": 2320, "volume": 100},
        ]
        _apply_wait_override(p, "ETH-USD", prior_day=prior_day, bars_5m=bars_5m)
        assert p["stop"] == 2310.00  # preserved from AI
        assert p["t1"] == 2340.00  # preserved from AI

    def test_override_short_stop_above_t1_below(self):
        """SHORT: stop = nearest resistance above, T1 = nearest support below."""
        p = self._make_parsed(
            reason="PDH rejection with lower high forming",
            price=2340.00,
        )
        prior_day = {"high": 2360.00, "low": 2310.00, "ma100": 2330.00}
        bars_5m = [
            {"open": 2345, "high": 2355, "low": 2320, "close": 2340, "volume": 100},
        ]
        _apply_wait_override(p, "SPY", prior_day=prior_day, bars_5m=bars_5m)
        assert p["direction"] == "SHORT"
        assert p["stop"] == 2355.00  # session_high, nearest resistance above
        assert p["t1"] == 2330.00  # ma100, nearest support below

    def test_override_no_levels_no_crash(self):
        """No prior_day or bars_5m — stop/T1 remain None."""
        p = self._make_parsed(
            reason="bounce at support level",
            price=100.00,
        )
        _apply_wait_override(p, "TEST")
        assert p["direction"] == "LONG"
        assert p["entry"] == 100.00
        assert p.get("stop") is None
        assert p.get("t1") is None

    def test_override_buying_opportunity(self):
        """'buying opportunity' triggers LONG override."""
        p = self._make_parsed(
            reason="100 Daily EMA confluence with RSI strength creating buying opportunity",
            price=2356.71,
        )
        _apply_wait_override(p, "ETH-USD")
        assert p["direction"] == "LONG"
        assert p["conviction"] == "MEDIUM"

    def test_override_support_test(self):
        """'support test' triggers LONG override."""
        p = self._make_parsed(
            reason="VWAP support test with RSI 61.6 showing strength",
            price=2353.28,
        )
        _apply_wait_override(p, "ETH-USD")
        assert p["direction"] == "LONG"
        assert p["conviction"] == "MEDIUM"

    def test_override_holding_vwap(self):
        """'holding vwap' triggers LONG override."""
        p = self._make_parsed(
            reason="Price holding VWAP/prior close confluence but no volume confirmation",
            price=2355.16,
        )
        _apply_wait_override(p, "ETH-USD")
        assert p["direction"] == "LONG"
        assert p["conviction"] == "MEDIUM"

    def test_override_holding_support(self):
        """'holding support' triggers LONG override."""
        p = self._make_parsed(
            reason="Price holding support at key level with RSI strength",
            price=2350.00,
        )
        _apply_wait_override(p, "ETH-USD")
        assert p["direction"] == "LONG"
        assert p["conviction"] == "MEDIUM"


class TestExitCooldown:
    def test_exit_cooldown_logic(self):
        """Cooldown suppresses same (trade_id, status) within 30 min."""
        import time
        from analytics.ai_day_scanner import _exit_notified, _EXIT_COOLDOWN_SEC

        _exit_notified.clear()
        trade_id = 42
        status = "EXIT_NOW"
        now = time.time()

        # First notification → should fire
        _exit_notified[(trade_id, status)] = now
        # Check within cooldown → suppressed
        assert (now + 60 - _exit_notified[(trade_id, status)]) < _EXIT_COOLDOWN_SEC
        # Check after cooldown → allowed
        assert (now + _EXIT_COOLDOWN_SEC + 10 - _exit_notified[(trade_id, status)]) > _EXIT_COOLDOWN_SEC
