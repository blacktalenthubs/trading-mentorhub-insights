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
        assert normalize_symbol("COINBASE:ETHUSD") == "ETHUSD"
        assert normalize_symbol("NASDAQ:AAPL") == "AAPL"
        assert normalize_symbol("BINANCE:BTCUSDT") == "BTCUSDT"

    def test_no_prefix_returns_uppercase(self):
        assert normalize_symbol("ethusd") == "ETHUSD"
        assert normalize_symbol(" AAPL ") == "AAPL"

    def test_empty_raises(self):
        with pytest.raises(TVAdapterError):
            normalize_symbol("")


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
        assert sig.symbol == "ETHUSD"
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
