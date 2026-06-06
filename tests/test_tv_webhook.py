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
from api.app.routers.tv_webhook import (
    CRYPTO_REGIME_ALLOWLIST,
    INDEX_REGIME_ALLOWLIST,
    crypto_pdl_blocks_buy,
    resolve_spy_above_pdl,
    spy_pdl_blocks_buy,
)


class TestCryptoPdlBlocksBuy:
    # BTC is the crypto 'index': gates ETH/alt buys, exempt itself.
    def test_blocks_eth_buy_when_btc_below_pdl(self):
        assert crypto_pdl_blocks_buy(False, "BUY", "ETH-USD") is True
        assert crypto_pdl_blocks_buy(False, "BUY", "SOL-USD") is True

    def test_exempts_btc_itself(self):
        assert "BTC-USD" in CRYPTO_REGIME_ALLOWLIST
        assert crypto_pdl_blocks_buy(False, "BUY", "BTC-USD") is False

    def test_never_touches_stocks(self):
        # Stocks are gated by the SPY gate, not BTC — crypto gate ignores them.
        assert crypto_pdl_blocks_buy(False, "BUY", "AAPL") is False

    def test_fail_open_and_above_pdl(self):
        assert crypto_pdl_blocks_buy(None, "BUY", "ETH-USD") is False
        assert crypto_pdl_blocks_buy(True, "BUY", "ETH-USD") is False

    def test_never_blocks_shorts(self):
        assert crypto_pdl_blocks_buy(False, "SHORT", "ETH-USD") is False


class TestResolveSpyAbovePdl:
    # Backend's own below-PDL reading (same as the banner) is authoritative for
    # routing; the Pine field is only a fallback when backend data is missing.
    def test_backend_is_authoritative(self):
        assert resolve_spy_above_pdl(True, None) is False   # below → block
        assert resolve_spy_above_pdl(True, True) is False    # backend overrides pine
        assert resolve_spy_above_pdl(False, None) is True    # not below → deliver
        assert resolve_spy_above_pdl(False, False) is True   # backend overrides pine

    def test_falls_back_to_pine_when_backend_unavailable(self):
        assert resolve_spy_above_pdl(None, False) is False
        assert resolve_spy_above_pdl(None, True) is True
        assert resolve_spy_above_pdl(None, None) is None


# -----------------------------------------------------------------------------
# Spec 61 — SPY-below-PDL gate decision (proven exhaustively, not assumed)
# -----------------------------------------------------------------------------


class TestSpyPdlBlocksBuy:
    def test_blocks_non_index_buy_when_below_pdl(self):
        # THE live-failing case: a normal equity BUY while SPY is under its PDL.
        assert spy_pdl_blocks_buy(False, "BUY", "AAPL") is True
        assert spy_pdl_blocks_buy(False, "BUY", "AAOI") is True

    def test_exempts_index_allowlist(self):
        for sym in ("SPY", "QQQ", "IWM", "DRAM"):
            assert sym in INDEX_REGIME_ALLOWLIST
            assert spy_pdl_blocks_buy(False, "BUY", sym) is False

    def test_never_blocks_shorts_or_notices(self):
        assert spy_pdl_blocks_buy(False, "SHORT", "AAPL") is False
        assert spy_pdl_blocks_buy(False, "SELL", "AAPL") is False
        assert spy_pdl_blocks_buy(False, "NOTICE", "AAPL") is False

    def test_fail_open_when_field_absent(self):
        # None = Pine didn't stamp spy_above_pdl (e.g. an alert still running the
        # OLD compiled script) → NEVER block. This is exactly why a BUY can still
        # deliver with SPY under PDL: the field never arrived, so the gate can't
        # fire. The fix is on the Pine/alert side, not here.
        assert spy_pdl_blocks_buy(None, "BUY", "AAPL") is False

    def test_no_block_when_spy_above_pdl(self):
        assert spy_pdl_blocks_buy(True, "BUY", "AAPL") is False

    def test_case_insensitive(self):
        assert spy_pdl_blocks_buy(False, "buy", "aapl") is True
        assert spy_pdl_blocks_buy(False, "buy", "spy") is False

    def test_custom_allowlist_exempts(self):
        # Admin adds AAPL to the exempt list (live, via Settings) → not blocked.
        custom = frozenset({"SPY", "QQQ", "IWM", "DRAM", "AAPL"})
        assert spy_pdl_blocks_buy(False, "BUY", "AAPL", custom) is False
        # A name NOT in the custom list is still blocked.
        assert spy_pdl_blocks_buy(False, "BUY", "NVDA", custom) is True


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

    def test_spy_above_pdl_parsed(self):
        # Spec 61 — SPY-below-PDL hard regime block. The webhook reads
        # _tv_spy_above_pdl to suppress every buy when the broad tape breaks
        # its prior-day low. true→True, false→False, absent→None (let through).
        assert getattr(
            payload_to_alert_signal(self._base_payload(spy_above_pdl="true")),
            "_tv_spy_above_pdl",
        ) is True
        assert getattr(
            payload_to_alert_signal(self._base_payload(spy_above_pdl="false")),
            "_tv_spy_above_pdl",
        ) is False
        assert getattr(
            payload_to_alert_signal(self._base_payload()),
            "_tv_spy_above_pdl",
        ) is None

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
        # Public-access launch (a827423): alerts fan out to ALL active users via
        # select(User), no longer the per-watchlist join. Guard against the old
        # broken User.watchlist attribute regression, and confirm the grade-gate
        # fix (eager-load the subscription) is still present.
        assert "select(User)" in src
        assert "selectinload(User.subscription)" in src
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
    """Smoke test: with all gates passing, route returns 200 FAST and queues
    the heavy pipeline as a background task (2026-05-20 fast-response change).

    We monkeypatch the dispatcher to avoid yfinance / DB / Telegram calls.
    """

    def test_accepts_valid_payload_returns_queued(self, monkeypatch, base_payload):
        """Handler returns 200 immediately with {accepted, queued} — the real
        work is deferred to a BackgroundTask, not awaited inline."""
        app, mod = _make_app(monkeypatch, enabled=True)

        dispatched = {"called": False}

        async def fake_dispatch(sig):
            dispatched["called"] = True

        monkeypatch.setattr(mod, "_dispatch_signal", fake_dispatch)

        client = TestClient(app)
        response = client.post("/tv/webhook", json=base_payload)
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] is True
        assert body["queued"] is True
        # TestClient runs background tasks after the response — so by the time
        # .post() returns, the background dispatch has executed.
        assert dispatched["called"] is True

    def test_background_dispatch_error_does_not_break_response(self, monkeypatch, base_payload):
        """A dispatch error in the background task must not affect the already-
        sent 200 response — _dispatch_background swallows + logs it."""
        app, mod = _make_app(monkeypatch, enabled=True)

        async def boom(sig):
            raise RuntimeError("intentional failure")

        monkeypatch.setattr(mod, "_dispatch_signal", boom)

        client = TestClient(app)
        # Should not raise even though the background task throws.
        response = client.post("/tv/webhook", json=base_payload)
        assert response.status_code == 200
        assert response.json()["accepted"] is True


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
    """SHORT gate — non-SPY shorts dropped always; SPY shorts ACTION only
    on the 3 structural PDH/PDL rules. NOTE: _route_alert is downstream of
    the allow-list filter, so it never sees non-PDH/PDL types in practice.
    The tests below use only allow-listed types where relevant."""

    def test_buy_passes_unchanged(self):
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("AAPL", "BUY", "staged_pdh_break")
        deliver, downgrade = _run(_route_alert(sig))
        assert deliver is True
        assert downgrade is None

    def test_notice_passes_unchanged(self):
        """NOTICE direction always passes through — allow-list filter is
        upstream so _route_alert never gets a non-allowlisted NOTICE."""
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("SPY", "NOTICE", "staged_pdl_reclaim")
        deliver, downgrade = _run(_route_alert(sig))
        assert deliver is True
        assert downgrade is None

    def test_non_index_short_always_dropped(self):
        """Single-name equity shorts are noise — hard-drop. Only the index set
        (SPY/QQQ/IWM) may short (spec 61)."""
        from api.app.routers.tv_webhook import _route_alert
        for symbol in ("NVDA", "AAPL", "AMD", "GOOGL", "TSLA"):
            sig = _FakeSig(symbol, "SHORT", "staged_pdl_break")
            deliver, downgrade = _run(_route_alert(sig))
            assert deliver is False, f"{symbol} SHORT should drop"
            assert downgrade is None

    def test_index_short_whitelisted_rules_action(self):
        """SPY/QQQ/IWM shorts on the structural rules pass through (spec 61)."""
        from api.app.routers.tv_webhook import _route_alert
        for symbol in ("SPY", "QQQ", "IWM"):
            for rule in ("staged_pdl_break", "staged_pdh_rejection"):
                sig = _FakeSig(symbol, "SHORT", rule)
                deliver, _ = _run(_route_alert(sig))
                assert deliver is True, f"{symbol} {rule} SHORT should deliver"

    def test_spy_short_whitelisted_rules_action(self):
        """The 3 structural SPY SHORT rules pass through as ACTION."""
        from api.app.routers.tv_webhook import _route_alert
        for rule in (
            "staged_pdh_rejection",
            "staged_pdh_failed_short",
            "staged_pdl_break",
        ):
            sig = _FakeSig("SPY", "SHORT", rule)
            deliver, downgrade = _run(_route_alert(sig))
            assert deliver is True, f"{rule} should pass through"
            assert downgrade is None, f"{rule} should not downgrade"

    def test_spy_short_vwap_dropped(self):
        """tv_vwap_reject_short was removed from the SPY SHORT whitelist
        2026-05-19 — VWAP isn't in the PDH/PDL allow-list anyway, but the
        whitelist itself shouldn't include it as a defensive measure."""
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("SPY", "SHORT", "vwap_reject_short")
        deliver, _ = _run(_route_alert(sig))
        assert deliver is False

    def test_spy_short_accepts_tv_prefixed_rule(self):
        """Defensive — if a caller passes already-prefixed rule it still works."""
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("SPY", "SHORT", "tv_staged_pdl_break")
        deliver, _ = _run(_route_alert(sig))
        assert deliver is True

    def test_unknown_direction_passes_through(self):
        """Defensive — unknown directions shouldn't trip the SHORT gate.
        (Allow-list filter is upstream so they wouldn't reach here in
        practice for non-allowlisted types.)"""
        from api.app.routers.tv_webhook import _route_alert
        sig = _FakeSig("AAPL", "FLAT", "staged_pdh_break")
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


class TestAllowList:
    """Allow-list (2026-05-19) — PDH/PDL exact + MA/EMA prefix only.
    Everything else (VWAP, open-line, weekly/monthly HTF, proximity NOTICEs)
    drops at the webhook level regardless of what Pine fires.
    """

    def test_allow_list_exact_match_set(self):
        """Static fallback set: 5 daily + 10 weekly/monthly staged + 2 HTF +
        pullback + 4 open-line types (re-added 2026-05-21). This is only the
        DB-read-failure fallback — per-type gating is alert_type_config."""
        from api.app.routers.tv_webhook import _ALLOWED_ALERT_TYPES
        assert _ALLOWED_ALERT_TYPES == {
            "tv_staged_pdh_break",
            "tv_staged_pdh_rejection",
            "tv_staged_pdh_failed_short",
            "tv_staged_pdl_break",
            "tv_staged_pdl_reclaim",
            "tv_staged_pwh_break",
            "tv_staged_pwh_rejection",
            "tv_staged_pwh_failed_short",
            "tv_staged_pwl_break",
            "tv_staged_pwl_reclaim",
            "tv_staged_pmh_break",
            "tv_staged_pmh_rejection",
            "tv_staged_pmh_failed_short",
            "tv_staged_pml_break",
            "tv_staged_pml_reclaim",
            "tv_htf_support_held",
            "tv_htf_proximity",
            "tv_pullback_long",
            "tv_open_reclaimed",
            "tv_open_held",
            "tv_open_wick_reclaim",
            "tv_open_lost",
        }

    def test_pullback_long_allowed(self):
        """Uptrend pullback continuation alert (2026-05-20) passes the allow-list."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        assert _is_allowed_alert_type("tv_pullback_long")

    def test_weekly_monthly_staged_allowed(self):
        """W/M staged types (S1 item 2) pass the allow-list."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        for t in (
            "tv_staged_pwh_break", "tv_staged_pwl_reclaim",
            "tv_staged_pmh_rejection", "tv_staged_pml_break",
        ):
            assert _is_allowed_alert_type(t), f"{t} should be allowed"

    def test_collapsed_htf_types_allowed(self):
        """S1 collapsed HTF alerts pass the allow-list."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        assert _is_allowed_alert_type("tv_htf_support_held")
        assert _is_allowed_alert_type("tv_htf_proximity")

    def test_old_per_level_htf_types_still_dropped(self):
        """The OLD per-level HTF alerts (pre-collapse) must NOT pass — if a
        stale chart fires tv_pwh_held etc., the allow-list drops them."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        for t in (
            "tv_pwh_held", "tv_pwl_held", "tv_pmh_held", "tv_pml_held",
            "tv_pwh_wick_reclaim", "tv_htf_proximity_pwh",
        ):
            assert not _is_allowed_alert_type(t), f"{t} should still drop"

    def test_allow_list_prefixes_for_ma_family(self):
        """Prefix set: MA bounce + rejection + proximity families (any MA tag)."""
        from api.app.routers.tv_webhook import _ALLOWED_ALERT_TYPE_PREFIXES
        assert "tv_ma_bounce_long_v3" in _ALLOWED_ALERT_TYPE_PREFIXES
        assert "tv_ma_rejection_short_v3" in _ALLOWED_ALERT_TYPE_PREFIXES
        assert "tv_ma_proximity_long_v3" in _ALLOWED_ALERT_TYPE_PREFIXES
        assert "tv_ma_proximity_short_v3" in _ALLOWED_ALERT_TYPE_PREFIXES

    def test_ma_proximity_variants_allowed(self):
        """MA proximity NOTICE alerts (S3, 2026-05-20) pass the allow-list."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        for t in (
            "tv_ma_proximity_long_v3",
            "tv_ma_proximity_long_v3_ema8",
            "tv_ma_proximity_long_v3_ema50_ema100",
            "tv_ma_proximity_short_v3",
            "tv_ma_proximity_short_v3_sma200",
        ):
            assert _is_allowed_alert_type(t), f"{t} should be allowed"

    def test_pdh_pdl_types_allowed(self):
        """All 5 PDH/PDL exact-match types pass _is_allowed_alert_type."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        for t in (
            "tv_staged_pdh_break",
            "tv_staged_pdh_rejection",
            "tv_staged_pdh_failed_short",
            "tv_staged_pdl_break",
            "tv_staged_pdl_reclaim",
        ):
            assert _is_allowed_alert_type(t), f"{t} should be allowed"

    def test_ma_bounce_variants_allowed(self):
        """MA bounce with any MA-tag suffix passes via prefix match."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        for t in (
            "tv_ma_bounce_long_v3",              # no MA tag
            "tv_ma_bounce_long_v3_ema5",
            "tv_ma_bounce_long_v3_ema50",
            "tv_ma_bounce_long_v3_ema200",
            "tv_ma_bounce_long_v3_sma100",
            "tv_ma_bounce_long_v3_ema8_ema21",   # confluence — multiple MAs same bar
        ):
            assert _is_allowed_alert_type(t), f"{t} should be allowed"

    def test_ma_rejection_variants_allowed(self):
        """MA rejection (SHORT side) with any MA-tag suffix is also on
        the allow-list. Note: SHORT gate still filters non-SPY shorts
        downstream — that's separate from the allow-list."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        for t in (
            "tv_ma_rejection_short_v3",
            "tv_ma_rejection_short_v3_ema10",
            "tv_ma_rejection_short_v3_sma200",
            "tv_ma_rejection_short_v3_ema50_ema100",
        ):
            assert _is_allowed_alert_type(t), f"{t} should be allowed"

    def test_non_allowed_types_dropped(self):
        """Sanity checks — types that should NOT pass the allow-list."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        for t in (
            "tv_vwap_reclaim_long",
            "tv_vwap_reject_short",
            "tv_vwap_support_hold",
            "tv_pwh_held",
            "tv_pwl_held",
            "tv_pmh_held",
            "tv_pml_held",
            "tv_pwh_wick_reclaim",
            "tv_htf_proximity_pwh",               # old per-level — collapsed to tv_htf_proximity
            "tv_intraday_ema_rejection_short",    # intraday EMA — not v3 daily
            "tv_hourly_resistance_rejection_short",
            "tv_unknown_rule",
        ):
            assert not _is_allowed_alert_type(t), f"{t} should be dropped"


    def test_spy_short_whitelist_subset_of_allow_list(self):
        """Every SPY SHORT whitelisted rule must also pass the allow-list.
        Otherwise SHORT alerts would be dropped upstream before
        _route_alert can ACTION them."""
        from api.app.routers.tv_webhook import (
            _SPY_SHORT_ACTION_RULES,
            _is_allowed_alert_type,
        )
        for t in _SPY_SHORT_ACTION_RULES:
            assert _is_allowed_alert_type(t), f"SPY SHORT rule {t} blocked by allow-list"

    def test_spy_short_whitelist_is_9_structural_rules(self):
        """Post-2026-05-20 (S1 item 2): SPY SHORT whitelist = the 9 structural
        rejection/break rules across daily + weekly + monthly levels. MA
        rejection is NOT included (per user: 'leave ema for nw could be
        noisy there lots of chops')."""
        from api.app.routers.tv_webhook import _SPY_SHORT_ACTION_RULES
        assert _SPY_SHORT_ACTION_RULES == {
            "tv_staged_pdh_rejection",
            "tv_staged_pdh_failed_short",
            "tv_staged_pdl_break",
            "tv_staged_pwh_rejection",
            "tv_staged_pwh_failed_short",
            "tv_staged_pwl_break",
            "tv_staged_pmh_rejection",
            "tv_staged_pmh_failed_short",
            "tv_staged_pml_break",
        }

    def test_dispatch_drops_non_allowed_types(self):
        """The dispatch path must short-circuit on non-allow-listed types.
        Source-level check since end-to-end DB mocking is heavy."""
        import inspect
        from api.app.routers import tv_webhook
        src = inspect.getsource(tv_webhook._dispatch_signal)
        assert "_is_allowed_alert_type" in src, "_dispatch_signal must call _is_allowed_alert_type"
        # Non-routed known types are recorded for review; unknown types dropped.
        assert "_persist_unrouted" in src, "non-routed types must take the record-only path"
        assert "unknown_type" in src, "unknown types must be dropped"


class TestPerTypeEnablement:
    """Per-alert-type gating via the alert_type_config enabled set (2026-05-21)."""

    def test_open_line_types_pass_static_fallback(self):
        # enabled=None -> static allow-list. Open-line types are now included
        # so a DB-read failure never silently drops them.
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        for t in ("tv_open_reclaimed", "tv_open_held",
                  "tv_open_wick_reclaim", "tv_open_lost"):
            assert _is_allowed_alert_type(t), f"{t} should pass the static fallback"

    def test_enabled_set_is_authoritative(self):
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        enabled = {"open_reclaimed", "open_held"}
        assert _is_allowed_alert_type("tv_open_reclaimed", enabled)
        assert _is_allowed_alert_type("tv_open_held", enabled)
        # known types not in the enabled set are dropped
        assert not _is_allowed_alert_type("tv_open_wick_reclaim", enabled)
        assert not _is_allowed_alert_type("tv_staged_pdh_break", enabled)

    def test_ma_per_ma_gating(self):
        """MA families gate per moving average; a confluence alert routes if
        ANY of its MAs is enabled; all SMAs share one grouped key."""
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        enabled = {"ma_bounce_long_v3_ema8", "ma_bounce_long_v3_sma"}
        # exact EMA match routes
        assert _is_allowed_alert_type("tv_ma_bounce_long_v3_ema8", enabled)
        # a different EMA does NOT route
        assert not _is_allowed_alert_type("tv_ma_bounce_long_v3_ema50", enabled)
        # confluence routes if any constituent MA is enabled
        assert _is_allowed_alert_type("tv_ma_bounce_long_v3_ema8_ema50", enabled)
        # every SMA maps to the shared grouped key
        assert _is_allowed_alert_type("tv_ma_bounce_long_v3_sma200", enabled)
        # a different family is untouched
        assert not _is_allowed_alert_type("tv_ma_rejection_short_v3_ema8", enabled)

    def test_empty_enabled_set_drops_everything(self):
        from api.app.routers.tv_webhook import _is_allowed_alert_type
        assert not _is_allowed_alert_type("tv_open_reclaimed", set())
        assert not _is_allowed_alert_type("tv_staged_pdh_break", set())


class TestSpyShortSessionDedup:
    """Session-level dedup config — SPY SHORT rules must be exempt from
    symbol-direction-session dedup (so each type can fire once
    independently) AND have a 16h identity-dedup window (so each TYPE
    caps at once per session)."""

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
        ):
            assert rule in src, f"{rule} must be in SESSION_DEDUP_EXEMPT_TYPES"

    def test_spy_short_rules_have_session_length_dedup_window(self):
        """Each SPY SHORT rule should have a 16h identity dedup window —
        caps each TYPE at once per session."""
        import inspect
        from api.app.routers import tv_webhook
        src = inspect.getsource(tv_webhook._dispatch_signal)
        assert "timedelta(hours=16)" in src, "16h window override must exist"
        for rule in (
            "tv_staged_pdh_rejection",
            "tv_staged_pdh_failed_short",
            "tv_staged_pdl_break",
        ):
            # rule appears twice (exempt + window override) — both required.
            assert src.count(rule) >= 2, f"{rule} needs entries in both dicts"


class TestIsChopRefire:
    """R-distance price-band check (pure helper used by _alert_already_fired).

    Level alerts re-firing within 1R of the prior entry = chop (True, suppress).
    Beyond 1R = price genuinely moved (False, allow fresh re-test).
    """

    def test_level_within_1r_is_chop(self):
        """AAPL today: prior 296.56/295.89 (R=$0.67), new 297.06.
        Distance $0.50 < R $0.67 → chop, suppress."""
        from api.app.routers.tv_webhook import _is_chop_refire
        assert _is_chop_refire(
            "tv_staged_pdl_reclaim",
            new_entry=297.06, prior_entry=296.56, prior_stop=295.89,
        ) is True

    def test_level_beyond_1r_is_fresh(self):
        """Same setup but new entry $298.00 → distance $1.44 > R $0.67 →
        price moved more than 1R, fresh re-test."""
        from api.app.routers.tv_webhook import _is_chop_refire
        assert _is_chop_refire(
            "tv_staged_pdl_reclaim",
            new_entry=298.00, prior_entry=296.56, prior_stop=295.89,
        ) is False

    def test_nflx_same_price_is_chop(self):
        """NFLX today: PDH break 14:50 @ 89.68, again 20:00 @ 89.68 (0%
        spread). Distance $0 < R $0.32 → chop."""
        from api.app.routers.tv_webhook import _is_chop_refire
        assert _is_chop_refire(
            "tv_staged_pdh_break",
            new_entry=89.68, prior_entry=89.68, prior_stop=89.36,
        ) is True

    def test_meta_pdl_reclaim_is_chop(self):
        """META today: 15:00 @ 609.32 stop 607.37 (R=$1.95), re-fire 16:20
        @ 610.00 distance $0.68 < R $1.95 → chop."""
        from api.app.routers.tv_webhook import _is_chop_refire
        assert _is_chop_refire(
            "tv_staged_pdl_reclaim",
            new_entry=610.00, prior_entry=609.32, prior_stop=607.37,
        ) is True

    def test_non_level_alert_returns_true(self):
        """MA bounce isn't in the level scope — the band check doesn't apply.
        Helper returns True so the caller falls back to time-window dedup."""
        from api.app.routers.tv_webhook import _is_chop_refire
        # Even with new entry $50 away from prior (way beyond 1R), a non-level
        # alert type returns True (defer to time dedup).
        assert _is_chop_refire(
            "tv_ma_bounce_v3_ema50",
            new_entry=150.0, prior_entry=100.0, prior_stop=99.0,
        ) is True

    def test_missing_new_entry_returns_true(self):
        """No new_entry → can't compute band, return True (time-dedup only)."""
        from api.app.routers.tv_webhook import _is_chop_refire
        assert _is_chop_refire(
            "tv_staged_pdl_reclaim",
            new_entry=None, prior_entry=100.0, prior_stop=99.0,
        ) is True

    def test_missing_prior_data_returns_true(self):
        """Prior entry or stop is None → can't compute R, return True."""
        from api.app.routers.tv_webhook import _is_chop_refire
        assert _is_chop_refire(
            "tv_staged_pdl_reclaim",
            new_entry=100.0, prior_entry=None, prior_stop=99.0,
        ) is True
        assert _is_chop_refire(
            "tv_staged_pdl_reclaim",
            new_entry=100.0, prior_entry=100.0, prior_stop=None,
        ) is True

    def test_zero_r_returns_true(self):
        """Prior entry == prior stop → R=0 → can't band-check, return True."""
        from api.app.routers.tv_webhook import _is_chop_refire
        assert _is_chop_refire(
            "tv_staged_pdl_reclaim",
            new_entry=100.5, prior_entry=100.0, prior_stop=100.0,
        ) is True

    def test_all_level_types_covered(self):
        """The level whitelist matches the alert types we want band-checked."""
        from api.app.routers.tv_webhook import _LEVEL_ALERT_TYPES_FOR_PRICE_BAND
        for t in (
            "tv_staged_pdh_break", "tv_staged_pdh_rejection",
            "tv_staged_pdh_failed_short", "tv_staged_pdl_break",
            "tv_staged_pdl_reclaim",
            "tv_staged_pwh_break", "tv_staged_pwl_reclaim",
            "tv_staged_pmh_break", "tv_staged_pml_reclaim",
        ):
            assert t in _LEVEL_ALERT_TYPES_FOR_PRICE_BAND, f"{t} missing"
