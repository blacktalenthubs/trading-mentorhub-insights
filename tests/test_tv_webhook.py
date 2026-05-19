"""Phase 5a (2026-04-25) — TradingView webhook ingest.

Two test groups:

1. **Adapter unit tests** — `analytics/tv_signal_adapter.py` parsing logic
   (interval map, symbol normalization, ISO date parse, direction
   validation, numeric coercion).

2. **Endpoint unit tests** — FastAPI route shape (Pydantic validation,
   feature flag enforcement, IP allowlist). The full dispatch pipeline
   (HTF gate, structural targets, DB persist, notifier) is exercised at
   integration-test level — kept as smoke tests using monkeypatch to
   avoid hitting yfinance / DB / Telegram in unit tests.

Live network is NOT required for these tests.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from analytics.intraday_rules import AlertType
from analytics.tv_signal_adapter import (
    INTERVAL_MAP,
    TVAdapterError,
    normalize_direction,
    normalize_interval,
    normalize_symbol,
    parse_fired_at,
    payload_to_alert_signal,
)


# -----------------------------------------------------------------------------
# Adapter — small helpers
# -----------------------------------------------------------------------------


class TestNormalizeSymbol:
    def test_strips_exchange_prefix(self):
        # Equity symbols stay as-is after stripping exchange
        assert normalize_symbol("NASDAQ:AAPL") == "AAPL"
        assert normalize_symbol("NYSE:GME") == "GME"

    def test_crypto_tv_format_maps_to_internal_hyphenated(self):
        """Live bug fix (2026-04-25): TV sends ETHUSD, our system needs
        ETH-USD for yfinance / Coinbase lookups. Without this mapping,
        fetch_prior_day('ETHUSD') 404'd in production."""
        assert normalize_symbol("ETHUSD") == "ETH-USD"
        assert normalize_symbol("COINBASE:ETHUSD") == "ETH-USD"
        assert normalize_symbol("BTCUSD") == "BTC-USD"
        assert normalize_symbol("BINANCE:BTCUSDT") == "BTC-USD"
        assert normalize_symbol("ETHUSDT") == "ETH-USD"
        assert normalize_symbol("ETHUSDC") == "ETH-USD"
        assert normalize_symbol("SOLUSD") == "SOL-USD"
        assert normalize_symbol("DOGEUSDT") == "DOGE-USD"

    def test_no_prefix_returns_uppercase(self):
        assert normalize_symbol("aapl") == "AAPL"
        assert normalize_symbol(" GOOG ") == "GOOG"

    def test_empty_raises(self):
        with pytest.raises(TVAdapterError):
            normalize_symbol("")

    def test_unknown_symbol_passes_through(self):
        # Unknown crypto / non-mapped pair: passthrough uppercased
        assert normalize_symbol("FOOBAR") == "FOOBAR"


class TestNormalizeInterval:
    @pytest.mark.parametrize("tv_value,expected", [
        ("D", "1d"),
        ("1D", "1d"),
        ("W", "1w"),
        ("M", "1mo"),
        ("240", "4h"),
        ("60", "1h"),
        ("30", "30m"),
        ("15", "15m"),
        ("5", "5m"),
        ("1", "1m"),
    ])
    def test_known_codes_map_correctly(self, tv_value, expected):
        assert normalize_interval(tv_value) == expected

    def test_unknown_code_lowercased_passthrough(self):
        # Defensive: unknown intervals fall through lowercased so we don't lose data
        assert normalize_interval("FOO") == "foo"

    def test_empty_returns_empty(self):
        assert normalize_interval("") == ""

    def test_interval_map_has_all_common_values(self):
        for k in ["1", "5", "15", "30", "60", "240", "D", "W", "M"]:
            assert k in INTERVAL_MAP


class TestParseFiredAt:
    def test_iso_with_z_suffix(self):
        # TV's actual format: 2026-04-25T18:05:14Z
        result = parse_fired_at("2026-04-25T18:05:14Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 25
        assert result.hour == 18
        assert result.tzinfo == timezone.utc

    def test_invalid_returns_none(self):
        assert parse_fired_at("not-a-date") is None
        assert parse_fired_at("") is None
        assert parse_fired_at(None) is None  # type: ignore


class TestNormalizeDirection:
    @pytest.mark.parametrize("input_val,expected", [
        ("BUY", "BUY"),
        ("buy", "BUY"),
        ("LONG", "BUY"),  # canonicalize LONG → BUY
        ("SHORT", "SHORT"),
        ("SELL", "SHORT"),  # canonicalize SELL → SHORT
        ("NOTICE", "NOTICE"),
        (" Buy ", "BUY"),
    ])
    def test_canonicalizes(self, input_val, expected):
        assert normalize_direction(input_val) == expected

    def test_invalid_falls_back_to_notice(self):
        # Per design: bad direction defaults to NOTICE so a misconfigured
        # Pine Script can't silently fire as LONG/SHORT
        assert normalize_direction("invalid") == "NOTICE"
        assert normalize_direction("") == "NOTICE"
        assert normalize_direction(None) == "NOTICE"  # type: ignore


# -----------------------------------------------------------------------------
# Adapter — payload conversion
# -----------------------------------------------------------------------------


class TestPayloadToAlertSignal:
    def _base_payload(self, **overrides):
        payload = {
            "symbol": "ETHUSD",
            "exchange": "COINBASE",
            "interval": "D",
            "price": "2311.30",
            "high": "2323.79",
            "low": "2301.18",
            "volume": "21065.37478612",
            "rule": "rsi_below_57_71",
            "direction": "BUY",
            "fired_at": "2026-04-25T18:05:14Z",
        }
        payload.update(overrides)
        return payload

    def test_full_payload_converts_correctly(self):
        sig = payload_to_alert_signal(self._base_payload())
        # Live fix: TV's "ETHUSD" maps to internal "ETH-USD" for yfinance compat
        assert sig.symbol == "ETH-USD"
        assert sig.alert_type == AlertType.TV_WEBHOOK
        assert sig.direction == "BUY"
        assert sig.price == 2311.30
        assert sig.entry == 2311.30  # entry defaults to price when missing for BUY
        # TV metadata stashed on the signal
        assert getattr(sig, "_tv_rule") == "rsi_below_57_71"
        assert getattr(sig, "_tv_high") == 2323.79
        assert getattr(sig, "_tv_low") == 2301.18
        assert getattr(sig, "_tv_interval") == "1d"
        assert getattr(sig, "_source") == "tradingview"

    def test_missing_symbol_raises(self):
        with pytest.raises(TVAdapterError, match="symbol"):
            payload_to_alert_signal({"price": "100", "rule": "test"})

    def test_missing_rule_raises(self):
        with pytest.raises(TVAdapterError, match="rule"):
            payload_to_alert_signal({"symbol": "BTCUSD", "price": "100"})

    def test_missing_price_raises(self):
        with pytest.raises(TVAdapterError, match="price"):
            payload_to_alert_signal({"symbol": "BTCUSD", "rule": "test"})

    def test_invalid_price_raises(self):
        with pytest.raises(TVAdapterError, match="price"):
            payload_to_alert_signal({"symbol": "BTCUSD", "rule": "test", "price": "abc"})

    def test_missing_direction_defaults_to_notice(self):
        sig = payload_to_alert_signal({
            "symbol": "BTCUSD", "price": "50000", "rule": "test",
        })
        assert sig.direction == "NOTICE"
        # NOTICE direction → entry NOT auto-set from price
        assert sig.entry is None

    def test_short_direction_sets_entry_from_price(self):
        sig = payload_to_alert_signal(self._base_payload(direction="SHORT"))
        assert sig.direction == "SHORT"
        assert sig.entry == 2311.30

    def test_explicit_entry_stop_targets_preserved(self):
        sig = payload_to_alert_signal(self._base_payload(
            entry="2310.00", stop="2305.00", target_1="2330.00", target_2="2350.00",
        ))
        assert sig.entry == 2310.00
        assert sig.stop == 2305.00
        assert sig.target_1 == 2330.00
        assert sig.target_2 == 2350.00

    def test_message_includes_rule_and_interval(self):
        sig = payload_to_alert_signal(self._base_payload())
        assert "[TV]" in sig.message
        assert "rsi_below_57_71" in sig.message
        assert "1d" in sig.message

    def test_notice_message_marks_heads_up(self):
        sig = payload_to_alert_signal({
            "symbol": "ETHUSD", "price": "2311", "rule": "weekly_high_test",
            "direction": "NOTICE",
        })
        assert "heads-up" in sig.message.lower()

    def test_optional_volume_handled(self):
        sig = payload_to_alert_signal(self._base_payload(volume=""))
        assert getattr(sig, "_tv_volume") is None

    def test_payload_must_be_dict(self):
        with pytest.raises(TVAdapterError):
            payload_to_alert_signal("not a dict")  # type: ignore


# -----------------------------------------------------------------------------
# Endpoint — feature flag + IP allowlist + Pydantic validation
# -----------------------------------------------------------------------------


def _make_app(monkeypatch, enabled: bool = True, allowed_ips: str = ""):
    """Build a fresh FastAPI app with the TV router under controlled flags."""
    monkeypatch.setattr(
        "alert_config.TV_WEBHOOK_ENABLED",
        enabled,
        raising=False,
    )
    monkeypatch.setattr(
        "alert_config.TV_WEBHOOK_ALLOWED_IPS",
        allowed_ips,
        raising=False,
    )
    # Reload the router module so it picks up the new flag values.
    import importlib

    import api.app.routers.tv_webhook as mod
    importlib.reload(mod)

    app = FastAPI()
    app.include_router(mod.router, prefix="/tv")
    return app, mod


@pytest.fixture
def base_payload():
    return {
        "symbol": "ETHUSD",
        "exchange": "COINBASE",
        "interval": "D",
        "price": "2311.30",
        "rule": "rsi_below_57_71",
        "direction": "BUY",
        "fired_at": "2026-04-25T18:05:14Z",
    }


class TestEndpointFeatureFlag:
    def test_503_when_disabled(self, monkeypatch, base_payload):
        app, _ = _make_app(monkeypatch, enabled=False)
        client = TestClient(app)
        response = client.post("/tv/webhook", json=base_payload)
        assert response.status_code == 503
        assert "disabled" in response.json()["detail"].lower()


class TestEndpointIpAllowlist:
    def test_403_when_ip_not_allowed(self, monkeypatch, base_payload):
        app, _ = _make_app(monkeypatch, enabled=True, allowed_ips="1.2.3.4,5.6.7.8")
        client = TestClient(app)
        # TestClient defaults to 127.0.0.1 / "testclient" → not on allowlist
        response = client.post("/tv/webhook", json=base_payload)
        assert response.status_code == 403


class TestEndpointPydanticValidation:
    def test_422_on_missing_required_field(self, monkeypatch):
        app, _ = _make_app(monkeypatch, enabled=True)
        client = TestClient(app)
        response = client.post("/tv/webhook", json={"symbol": "ETHUSD"})
        # Pydantic V2 returns 422 for validation errors
        assert response.status_code in (400, 422)

    def test_400_on_invalid_payload_logic(self, monkeypatch, base_payload):
        """When the adapter rejects the payload (e.g. bad price), expect 400."""
        app, mod = _make_app(monkeypatch, enabled=True)

        # Force the dispatch path to error in the adapter rather than through
        # network calls — invalid price triggers TVAdapterError.
        bad = dict(base_payload)
        bad["price"] = "not-a-number"
        client = TestClient(app)
        response = client.post("/tv/webhook", json=bad)
        # Either Pydantic catches it (422) or the adapter raises (400)
        assert response.status_code in (400, 422)


class TestWatchlistQuery:
    """Live bug fix (2026-04-25): _users_watching used `User.watchlist.contains`
    but watchlist is a separate `WatchlistItem` table, not a User column.

    These tests verify the JOIN-based query references the right model
    classes — they don't run the query (that needs a real DB session) but
    catch attribute typos that broke production.
    """

    def test_users_watching_imports_resolve(self):
        """Smoke: the function imports the right model classes without error."""
        import api.app.routers.tv_webhook as mod
        # Calling the function with a fake db will fail — but we only care
        # about whether the model imports/lookups succeed up to the point
        # of execution. Use inspect.
        import inspect
        src = inspect.getsource(mod._users_watching)
        # Confirm the fix landed: should reference WatchlistItem table, not
        # the broken User.watchlist attribute.
        assert "WatchlistItem" in src
        assert "User.watchlist.contains" not in src

    def test_watchlist_model_file_has_required_columns(self):
        """Schema sanity: read the file directly (avoid Streamlit import side-effects)."""
        with open("api/app/models/watchlist.py") as f:
            src = f.read()
        assert 'class WatchlistItem' in src
        assert '__tablename__ = "watchlist"' in src
        assert 'user_id' in src
        assert 'symbol' in src


class TestEndpointAcceptsValidPayload:
    """Smoke test: with all gates passing and dispatch mocked, route returns 200.

    We monkeypatch the dispatcher to avoid yfinance / DB / Telegram calls.
    """

    def test_accepts_valid_payload(self, monkeypatch, base_payload):
        app, mod = _make_app(monkeypatch, enabled=True)

        async def fake_dispatch(sig, request):
            return {"dispatched": True, "persisted": 0, "notified": 0}

        monkeypatch.setattr(mod, "_dispatch_signal", fake_dispatch)

        client = TestClient(app)
        response = client.post("/tv/webhook", json=base_payload)
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] is True
        assert body["dispatched"] is True

    def test_dispatch_error_swallowed_returns_200(self, monkeypatch, base_payload):
        """TV retries on 5xx — dispatch errors must be swallowed to avoid spam."""
        app, mod = _make_app(monkeypatch, enabled=True)

        async def boom(sig, request):
            raise RuntimeError("intentional failure")

        monkeypatch.setattr(mod, "_dispatch_signal", boom)

        client = TestClient(app)
        response = client.post("/tv/webhook", json=base_payload)
        assert response.status_code == 200
        assert response.json()["dispatched"] is False


# -----------------------------------------------------------------------------
# Identity dedup (2026-05-03) — replaces price-band dedup.
# MA-tag suffix unit tests live here (no DB / no async). Behavioral dedup
# tests are in api/tests/test_tv_webhook_dedup.py because they need
# pytest-asyncio + the async SQLAlchemy stack which only the api package
# is configured for.
# -----------------------------------------------------------------------------


class TestMaTagToSuffix:
    """Pine ma_tag → alert_type suffix conversion."""

    def test_single_ema(self):
        from api.app.routers.tv_webhook import _ma_tag_to_suffix
        assert _ma_tag_to_suffix("100E") == "_ema100"
        assert _ma_tag_to_suffix("8E") == "_ema8"
        assert _ma_tag_to_suffix("21E") == "_ema21"

    def test_single_sma(self):
        from api.app.routers.tv_webhook import _ma_tag_to_suffix
        assert _ma_tag_to_suffix("50S") == "_sma50"
        assert _ma_tag_to_suffix("200S") == "_sma200"

    def test_confluence_combined(self):
        """Pine concatenates tags when multiple MAs fire same bar."""
        from api.app.routers.tv_webhook import _ma_tag_to_suffix
        assert _ma_tag_to_suffix("8E21E") == "_ema8_ema21"
        assert _ma_tag_to_suffix("50E100E") == "_ema50_ema100"
        assert _ma_tag_to_suffix("50S200S") == "_sma50_sma200"

    def test_empty_or_unparseable(self):
        """Rules without MA (VWAP reclaim, PDH break) should produce no suffix."""
        from api.app.routers.tv_webhook import _ma_tag_to_suffix
        assert _ma_tag_to_suffix("") == ""
        assert _ma_tag_to_suffix("garbage") == ""
        assert _ma_tag_to_suffix(None or "") == ""


# -----------------------------------------------------------------------------
# Routing logic — SPY-only SHORT gate (2026-05-18 simplification).
# All non-SPY SHORTs are dropped unconditionally. SPY SHORTs fire only on
# the 4 structural rules; everything else (incl. MA/EMA rejections) drops.
# -----------------------------------------------------------------------------


class _FakeSig:
    """Minimal stand-in for AlertSignal — only fields _route_alert reads.

    Note: production sets _tv_rule to the BARE name (e.g. "staged_pdl_break")
    via tv_signal_adapter line 221. _route_alert handles both bare and
    "tv_"-prefixed forms; tests below use the bare form to match production.
    """

    def __init__(self, symbol: str, direction: str, rule: str = ""):
        self.symbol = symbol
        self.direction = direction
        self._tv_rule = rule


def _run(coro):
    """Run an async coroutine to completion in a sync test."""
    import asyncio
    return asyncio.run(coro)


class TestRoutingLogic:
    """Non-SPY shorts dropped always. SPY shorts ACTION only on the 4
    structural rules; non-whitelisted SPY shorts also dropped."""

    def test_buy_passes_unchanged(self):
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("AAPL", "BUY", "staged_pdh_break")
        deliver, downgrade = _run(_route_alert(sig))
        assert deliver is True
        assert downgrade is None

    def test_notice_passes_unchanged(self):
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("AAPL", "NOTICE", "vwap_reclaim_long")
        deliver, downgrade = _run(_route_alert(sig))
        assert deliver is True
        assert downgrade is None

    def test_non_spy_short_always_dropped(self):
        """Equity shorts are noise regardless of regime — hard-drop."""
        from api.app.routers.tv_webhook import _route_alert
        for symbol in ("NVDA", "AAPL", "AMD", "GOOGL", "QQQ", "TSLA"):
            sig = _FakeSig(symbol, "SHORT", "staged_pdl_break")
            deliver, downgrade = _run(_route_alert(sig))
            assert deliver is False, f"{symbol} SHORT should drop"
            assert downgrade is None

    def test_spy_short_whitelisted_rules_action(self):
        """The 4 structural SPY SHORT rules pass through as ACTION."""
        from api.app.routers.tv_webhook import _route_alert
        for rule in (
            "staged_pdh_rejection",
            "staged_pdh_failed_short",
            "staged_pdl_break",
            "vwap_reject_short",
        ):
            sig = _FakeSig("SPY", "SHORT", rule)
            deliver, downgrade = _run(_route_alert(sig))
            assert deliver is True, f"{rule} should pass through"
            assert downgrade is None, f"{rule} should not downgrade"

    def test_spy_short_non_whitelisted_dropped(self):
        """SPY shorts NOT in the structural whitelist (e.g. MA rejections)
        drop entirely — no NOTICE downgrade. Keeps chop noise out."""
        from api.app.routers.tv_webhook import _route_alert
        for rule in (
            "ma_rejection_short_v3_ema50",
            "ma_rejection_short_v3_ema100",
            "ma_rejection_short_v3_sma200",
            "ema_rejection_short",
            "open_lost",
        ):
            sig = _FakeSig("SPY", "SHORT", rule)
            deliver, downgrade = _run(_route_alert(sig))
            assert deliver is False, f"SPY {rule} should drop"

    def test_spy_short_accepts_tv_prefixed_rule(self):
        """Defensive — if a caller passes already-prefixed rule it still works."""
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("SPY", "SHORT", "tv_staged_pdl_break")
        deliver, _ = _run(_route_alert(sig))
        assert deliver is True

    def test_unknown_direction_passes_through(self):
        """Defensive — unknown directions shouldn't trip the gate."""
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("AAPL", "FLAT", "unknown")
        deliver, downgrade = _run(_route_alert(sig))
        assert deliver is True
        assert downgrade is None

    def test_short_lowercase_normalized(self):
        """Direction 'short' (lowercase) must hit the same gate as 'SHORT'."""
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("NVDA", "short", "staged_pdl_break")
        deliver, _ = _run(_route_alert(sig))
        assert deliver is False

    def test_sell_treated_as_short(self):
        """SELL direction (synonym for SHORT) hits the same gate."""
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("NVDA", "SELL", "staged_pdl_break")
        deliver, _ = _run(_route_alert(sig))
        assert deliver is False


class TestSpyShortSessionDedup:
    """Session-level dedup config — the 4 SPY SHORT rules must be exempt
    from symbol-direction-session dedup (so each type can fire once
    independently) AND have a 16h identity-dedup window (so each TYPE caps
    at once per session)."""

    def test_spy_short_rules_in_session_dedup_exempt(self):
        """SPY SHORT structural rules bypass SYMBOL_SESSION_DEDUP — otherwise
        PDH rejection at 10:00 would block PDL break at 14:00."""
        import inspect
        from api.app.routers import tv_webhook
        src = inspect.getsource(tv_webhook._dispatch_signal)
        for rule in (
            "tv_staged_pdh_rejection",
            "tv_staged_pdh_failed_short",
            "tv_staged_pdl_break",
            "tv_vwap_reject_short",
        ):
            assert rule in src, f"{rule} must be in SESSION_DEDUP_EXEMPT_TYPES"

    def test_spy_short_rules_have_session_length_dedup_window(self):
        """Each of the 4 SPY SHORT rules should have a 16h identity dedup
        window — caps each TYPE at once per session."""
        import inspect
        from api.app.routers import tv_webhook
        src = inspect.getsource(tv_webhook._dispatch_signal)
        # We just check the override block mentions hours=16 for each rule.
        assert "timedelta(hours=16)" in src, "16h window override must exist"
        for rule in (
            "tv_staged_pdh_rejection",
            "tv_staged_pdh_failed_short",
            "tv_staged_pdl_break",
            "tv_vwap_reject_short",
        ):
            # rule appears twice (exempt + window override) — both required.
            assert src.count(rule) >= 2, f"{rule} needs entries in both dicts"


