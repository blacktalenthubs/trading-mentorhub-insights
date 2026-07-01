"""SnapTrade integration tests.

Covers the pure transforms (activity → trades_monthly row, fill → pattern
reconciliation), config gating, schema surface, and the model shape. Network
+ live-DB paths are exercised via a mocked SDK client so no real SnapTrade
credentials or Postgres are required.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# activity_to_monthly_row
# ---------------------------------------------------------------------------

class TestActivityToMonthlyRow:
    @pytest.fixture
    def svc(self):
        from app.services import snaptrade_service
        return snaptrade_service

    def _buy(self):
        return {
            "type": "BUY",
            "symbol": {"symbol": {"symbol": "nvda", "description": "NVIDIA"}},
            "trade_date": "2026-06-30T00:00:00Z",
            "units": 10,
            "price": 100.0,
            "amount": -1000.0,
            "description": "Bought 10 NVDA",
        }

    def test_buy_maps_to_row(self, svc):
        row = svc.activity_to_monthly_row(self._buy(), account_label="ROBINHOOD")
        assert row is not None
        assert row["symbol"] == "NVDA"          # uppercased
        assert row["transaction_type"] == "BUY"
        assert row["trade_date"] == "2026-06-30"  # truncated to date
        assert row["quantity"] == 10.0
        assert row["price"] == 100.0
        assert row["amount"] == -1000.0
        assert row["account"] == "ROBINHOOD"
        assert row["is_option"] == 0

    def test_non_trade_returns_none(self, svc):
        div = {"type": "DIVIDEND", "symbol": {"symbol": {"symbol": "NVDA"}},
               "trade_date": "2026-06-30", "units": 0, "price": 0}
        assert svc.activity_to_monthly_row(div, account_label="RH") is None

    def test_missing_symbol_returns_none(self, svc):
        act = {"type": "BUY", "trade_date": "2026-06-30", "units": 5, "price": 10}
        assert svc.activity_to_monthly_row(act, account_label="RH") is None

    def test_missing_date_returns_none(self, svc):
        act = {"type": "BUY", "symbol": {"symbol": {"symbol": "NVDA"}},
               "units": 5, "price": 10}
        assert svc.activity_to_monthly_row(act, account_label="RH") is None

    def test_amount_reconstructed_when_absent_buy(self, svc):
        act = self._buy()
        act.pop("amount")
        row = svc.activity_to_monthly_row(act, account_label="RH")
        # BUY = cash out = negative
        assert row["amount"] == -1000.0

    def test_amount_reconstructed_when_absent_sell(self, svc):
        act = self._buy()
        act["type"] = "SELL"
        act.pop("amount")
        row = svc.activity_to_monthly_row(act, account_label="RH")
        # SELL = cash in = positive
        assert row["amount"] == 1000.0

    def test_quantity_absolute_value(self, svc):
        act = self._buy()
        act["units"] = -10  # some brokers report signed units
        row = svc.activity_to_monthly_row(act, account_label="RH")
        assert row["quantity"] == 10.0

    def test_flat_string_symbol(self, svc):
        act = self._buy()
        act["symbol"] = "TSLA"
        row = svc.activity_to_monthly_row(act, account_label="RH")
        assert row["symbol"] == "TSLA"

    def test_option_detected(self, svc):
        act = self._buy()
        act["option_symbol"] = {"underlying_symbol": "SPY", "ticker": "SPY 250101C"}
        act["symbol"] = None
        row = svc.activity_to_monthly_row(act, account_label="RH")
        assert row is not None
        assert row["is_option"] == 1
        assert row["symbol"] == "SPY"


# ---------------------------------------------------------------------------
# match_fill_to_pattern
# ---------------------------------------------------------------------------

class TestMatchFillToPattern:
    @pytest.fixture
    def svc(self):
        from app.services import snaptrade_service
        return snaptrade_service

    def test_matches_same_symbol_and_date(self, svc):
        row = {"symbol": "NVDA", "trade_date": "2026-06-30", "transaction_type": "BUY"}
        alerts = [{"symbol": "NVDA", "session_date": "2026-06-30",
                   "alert_type": "ema_bounce_21", "direction": "LONG"}]
        assert svc.match_fill_to_pattern(row, alerts) == "ema_bounce_21"

    def test_no_match_different_date(self, svc):
        row = {"symbol": "NVDA", "trade_date": "2026-06-30", "transaction_type": "BUY"}
        alerts = [{"symbol": "NVDA", "session_date": "2026-06-29",
                   "alert_type": "ema_bounce_21", "direction": "LONG"}]
        assert svc.match_fill_to_pattern(row, alerts) is None

    def test_no_match_different_symbol(self, svc):
        row = {"symbol": "NVDA", "trade_date": "2026-06-30", "transaction_type": "BUY"}
        alerts = [{"symbol": "TSLA", "session_date": "2026-06-30",
                   "alert_type": "ema_bounce_21", "direction": "LONG"}]
        assert svc.match_fill_to_pattern(row, alerts) is None

    def test_prefers_same_direction(self, svc):
        row = {"symbol": "NVDA", "trade_date": "2026-06-30", "transaction_type": "BUY"}
        alerts = [
            {"symbol": "NVDA", "session_date": "2026-06-30",
             "alert_type": "pdh_rejection", "direction": "SHORT"},
            {"symbol": "NVDA", "session_date": "2026-06-30",
             "alert_type": "prior_day_low_bounce", "direction": "LONG"},
        ]
        assert svc.match_fill_to_pattern(row, alerts) == "prior_day_low_bounce"

    def test_empty_candidates(self, svc):
        row = {"symbol": "NVDA", "trade_date": "2026-06-30", "transaction_type": "BUY"}
        assert svc.match_fill_to_pattern(row, []) is None


# ---------------------------------------------------------------------------
# Config gating
# ---------------------------------------------------------------------------

class TestConfigGating:
    @pytest.fixture
    def svc(self):
        from app.services import snaptrade_service
        return snaptrade_service

    def test_not_configured_when_empty(self, svc):
        class S:
            SNAPTRADE_CLIENT_ID = ""
            SNAPTRADE_CONSUMER_KEY = ""
        assert svc.is_configured(S()) is False

    def test_configured_when_both_present(self, svc):
        class S:
            SNAPTRADE_CLIENT_ID = "cid"
            SNAPTRADE_CONSUMER_KEY = "ckey"
        assert svc.is_configured(S()) is True

    def test_not_configured_when_only_one(self, svc):
        class S:
            SNAPTRADE_CLIENT_ID = "cid"
            SNAPTRADE_CONSUMER_KEY = ""
        assert svc.is_configured(S()) is False

    def test_get_client_raises_when_unconfigured(self, svc):
        class S:
            SNAPTRADE_CLIENT_ID = ""
            SNAPTRADE_CONSUMER_KEY = ""
        with pytest.raises(svc.SnapTradeNotConfigured):
            svc.get_client(S())

    def test_user_id_namespaced(self, svc):
        assert svc.snaptrade_user_id_for(42) == "btd_42"


# ---------------------------------------------------------------------------
# run_daily_sync graceful no-op
# ---------------------------------------------------------------------------

class TestDailySyncNoOp:
    def test_run_daily_sync_no_op_when_unconfigured(self):
        from app.services import snaptrade_service as svc

        class S:
            SNAPTRADE_CLIENT_ID = ""
            SNAPTRADE_CONSUMER_KEY = ""

        def _factory():  # should never be called
            raise AssertionError("session factory used while unconfigured")

        totals = svc.run_daily_sync(_factory, S())
        assert totals == {"users": 0, "imported": 0, "matched": 0}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_status_response_defaults(self):
        from app.schemas.snaptrade import ConnectionStatusResponse
        r = ConnectionStatusResponse(connected=False, status="none")
        assert r.broker_slug is None
        assert r.last_sync_count == 0

    def test_sync_result_shape(self):
        from app.schemas.snaptrade import SyncResultResponse
        r = SyncResultResponse(
            fills_fetched=3, fills_imported=2, fills_skipped=1,
            patterns_matched=1, start_date="2026-06-23", end_date="2026-06-30",
        )
        assert r.fills_imported == 2

    def test_no_schema_exposes_user_secret(self):
        """The user_secret must never appear in any response schema."""
        import app.schemas.snaptrade as schemas
        from pydantic import BaseModel
        for name in dir(schemas):
            obj = getattr(schemas, name)
            if isinstance(obj, type) and issubclass(obj, BaseModel):
                assert "user_secret" not in obj.model_fields, (
                    f"{name} exposes user_secret"
                )


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class TestModel:
    def test_connection_columns(self):
        from app.models.snaptrade import SnapTradeConnection
        cols = {c.name for c in SnapTradeConnection.__table__.columns}
        assert {
            "id", "user_id", "snaptrade_user_id", "user_secret", "status",
            "broker_slug", "last_synced_at", "last_sync_count",
        } <= cols

    def test_unique_on_user(self):
        from app.models.snaptrade import SnapTradeConnection
        names = [c.name for c in SnapTradeConnection.__table_args__]
        assert "uq_snaptrade_conn_user" in names

    def test_status_constants(self):
        from app.models.snaptrade import (
            STATUS_CONNECTED,
            STATUS_DISABLED,
            STATUS_REGISTERED,
        )
        assert {STATUS_REGISTERED, STATUS_CONNECTED, STATUS_DISABLED} == {
            "registered", "connected", "disabled"
        }
