"""Tests for analytics/intel_hub.py — win rates, S/R levels, fundamentals, weekly bars."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Create a temp SQLite DB with alerts table and patch get_db."""
    db_path = str(tmp_path / "test.db")

    def _get_connection():
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _get_db():
        conn = _get_connection()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    conn = _get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            price REAL NOT NULL,
            entry REAL,
            stop REAL,
            target_1 REAL,
            target_2 REAL,
            confidence TEXT,
            message TEXT,
            narrative TEXT DEFAULT '',
            score INTEGER DEFAULT 0,
            score_v2 INTEGER DEFAULT 0,
            notified_email INTEGER DEFAULT 0,
            notified_sms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_date TEXT NOT NULL,
            user_id INTEGER
        );
    """)
    conn.close()

    with patch("db.get_db", _get_db):
        yield _get_db


def _insert_alert(get_db, symbol, alert_type, direction, session_date,
                  price=100.0, created_at=None):
    """Insert a test alert row."""
    ts = created_at or "2026-03-01 10:30:00"
    with get_db() as conn:
        conn.execute(
            "INSERT INTO alerts (symbol, alert_type, direction, price, "
            "session_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (symbol, alert_type, direction, price, session_date, ts),
        )


# ---------------------------------------------------------------------------
# Win rate tests
# ---------------------------------------------------------------------------

class TestGetAlertWinRates:
    """Tests for get_alert_win_rates()."""

    def test_empty_db_returns_zero(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        result = get_alert_win_rates(days=90)
        assert result["overall"]["total"] == 0
        assert result["overall"]["win_rate"] == 0.0
        assert result["by_symbol"] == {}

    def test_entry_with_target_hit_is_win(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        session = date.today().isoformat()
        _insert_alert(tmp_db, "AAPL", "ma_bounce", "BUY", session,
                      created_at=f"{session} 10:00:00")
        _insert_alert(tmp_db, "AAPL", "target_1_hit", "SELL", session,
                      created_at=f"{session} 11:00:00")

        result = get_alert_win_rates(days=30)
        assert result["overall"]["wins"] == 1
        assert result["overall"]["losses"] == 0
        assert result["overall"]["win_rate"] == 100.0
        assert "AAPL" in result["by_symbol"]
        assert result["by_symbol"]["AAPL"]["win_rate"] == 100.0

    def test_entry_with_stop_out_is_loss(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        session = date.today().isoformat()
        _insert_alert(tmp_db, "MSFT", "support_bounce", "BUY", session)
        _insert_alert(tmp_db, "MSFT", "stop_loss_hit", "SELL", session)

        result = get_alert_win_rates(days=30)
        assert result["overall"]["losses"] == 1
        assert result["overall"]["win_rate"] == 0.0

    def test_entry_without_outcome_is_unknown(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        session = date.today().isoformat()
        _insert_alert(tmp_db, "TSLA", "ma_bounce", "BUY", session)

        result = get_alert_win_rates(days=30)
        assert result["overall"]["unknown"] == 1
        assert result["overall"]["win_rate"] == 0.0

    def test_multiple_symbols_grouped(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        session = date.today().isoformat()
        # AAPL wins
        _insert_alert(tmp_db, "AAPL", "ma_bounce", "BUY", session)
        _insert_alert(tmp_db, "AAPL", "target_1_hit", "SELL", session)
        # MSFT loses
        _insert_alert(tmp_db, "MSFT", "support_bounce", "BUY", session)
        _insert_alert(tmp_db, "MSFT", "stop_loss_hit", "SELL", session)

        result = get_alert_win_rates(days=30)
        assert result["overall"]["total"] == 2
        assert result["overall"]["win_rate"] == 50.0
        assert result["by_symbol"]["AAPL"]["win_rate"] == 100.0
        assert result["by_symbol"]["MSFT"]["win_rate"] == 0.0

    def test_by_alert_type(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        session = date.today().isoformat()
        _insert_alert(tmp_db, "AAPL", "ma_bounce", "BUY", session)
        _insert_alert(tmp_db, "AAPL", "target_1_hit", "SELL", session)
        _insert_alert(tmp_db, "NVDA", "gap_fill", "BUY", session)
        _insert_alert(tmp_db, "NVDA", "stop_loss_hit", "SELL", session)

        result = get_alert_win_rates(days=30)
        assert "ma_bounce" in result["by_alert_type"]
        assert result["by_alert_type"]["ma_bounce"]["win_rate"] == 100.0
        assert result["by_alert_type"]["gap_fill"]["win_rate"] == 0.0

    def test_by_hour(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        session = date.today().isoformat()
        _insert_alert(tmp_db, "AAPL", "ma_bounce", "BUY", session,
                      created_at=f"{session} 10:30:00")
        _insert_alert(tmp_db, "AAPL", "target_1_hit", "SELL", session)

        result = get_alert_win_rates(days=30)
        assert 10 in result["by_hour"]
        assert result["by_hour"][10]["win_rate"] == 100.0

    def test_lookback_respects_days(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        old_session = (date.today() - timedelta(days=100)).isoformat()
        _insert_alert(tmp_db, "AAPL", "ma_bounce", "BUY", old_session)
        _insert_alert(tmp_db, "AAPL", "target_1_hit", "SELL", old_session)

        result = get_alert_win_rates(days=30)
        assert result["overall"]["total"] == 0

    def test_outcome_types_not_counted_as_entries(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        session = date.today().isoformat()
        # Only outcome alerts, no entry alerts
        _insert_alert(tmp_db, "AAPL", "target_1_hit", "SELL", session)
        _insert_alert(tmp_db, "AAPL", "stop_loss_hit", "SELL", session)

        result = get_alert_win_rates(days=30)
        assert result["overall"]["total"] == 0

    def test_notice_direction_excluded(self, tmp_db):
        from analytics.intel_hub import get_alert_win_rates

        session = date.today().isoformat()
        _insert_alert(tmp_db, "SPY", "regime_change", "NOTICE", session)

        result = get_alert_win_rates(days=30)
        assert result["overall"]["total"] == 0


# ---------------------------------------------------------------------------
# S/R levels tests
# ---------------------------------------------------------------------------

class TestGetSrLevels:
    """Tests for get_sr_levels()."""

    @patch("analytics.intraday_data.fetch_hourly_bars")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    def test_levels_from_prior_day(self, mock_prior, mock_intra, mock_hourly):
        from analytics.intel_hub import get_sr_levels

        mock_prior.return_value = {
            "close": 150.0, "high": 155.0, "low": 145.0,
            "ma20": 148.0, "ma50": 146.0, "ma100": 140.0, "ma200": 130.0,
            "ema20": 149.0, "ema50": 147.0, "ema100": 142.0,
            "prior_week_high": 157.0, "prior_week_low": 143.0,
        }
        intra_df = pd.DataFrame({"Close": [152.0]})
        mock_intra.return_value = intra_df
        mock_hourly.return_value = pd.DataFrame()

        levels = get_sr_levels("AAPL")
        assert len(levels) > 0

        # Check that levels are sorted by proximity
        distances = [abs(l["distance_pct"]) for l in levels]
        assert distances == sorted(distances)

        # Check that MA levels are included
        labels = [l["label"] for l in levels]
        assert "20 SMA" in labels
        assert "50 SMA" in labels
        assert "Prior Day High" in labels
        assert "Prior Day Low" in labels

    @patch("analytics.intraday_data.fetch_hourly_bars")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    def test_no_prior_day_returns_empty(self, mock_prior, mock_intra, mock_hourly):
        from analytics.intel_hub import get_sr_levels

        mock_prior.return_value = None
        levels = get_sr_levels("FAKE")
        assert levels == []

    @patch("analytics.intraday_data.fetch_hourly_bars")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    def test_level_type_classification(self, mock_prior, mock_intra, mock_hourly):
        from analytics.intel_hub import get_sr_levels

        # Price at 150, MA20 at 148 (below = support), MA50 at 160 (above = resistance)
        mock_prior.return_value = {
            "close": 150.0, "high": 155.0, "low": 145.0,
            "ma20": 148.0, "ma50": 160.0, "ma100": None, "ma200": None,
            "ema20": None, "ema50": None, "ema100": None,
            "prior_week_high": None, "prior_week_low": None,
        }
        intra_df = pd.DataFrame({"Close": [150.0]})
        mock_intra.return_value = intra_df
        mock_hourly.return_value = pd.DataFrame()

        levels = get_sr_levels("AAPL")
        level_map = {l["label"]: l for l in levels}
        assert level_map["20 SMA"]["type"] == "support"
        assert level_map["50 SMA"]["type"] == "resistance"

    @patch("analytics.intraday_data.fetch_hourly_bars")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    def test_hourly_swing_levels_included(self, mock_prior, mock_intra, mock_hourly):
        from analytics.intel_hub import get_sr_levels

        mock_prior.return_value = {
            "close": 150.0, "high": 155.0, "low": 145.0,
            "ma20": None, "ma50": None, "ma100": None, "ma200": None,
            "ema20": None, "ema50": None, "ema100": None,
            "prior_week_high": None, "prior_week_low": None,
        }
        intra_df = pd.DataFrame({"Close": [150.0]})
        mock_intra.return_value = intra_df

        # Create hourly bars with swing highs and lows
        idx = pd.date_range("2026-03-06 10:00", periods=10, freq="1h")
        bars = pd.DataFrame({
            "Open":  [149, 150, 152, 151, 149, 148, 150, 151, 153, 152],
            "High":  [150, 152, 154, 153, 150, 149, 152, 153, 155, 153],
            "Low":   [148, 149, 151, 150, 148, 147, 149, 150, 152, 151],
            "Close": [150, 151, 153, 150, 149, 148, 151, 152, 154, 152],
            "Volume": [1000] * 10,
        }, index=idx)
        mock_hourly.return_value = bars

        levels = get_sr_levels("AAPL")
        sources = {l["source"] for l in levels}
        assert "hourly" in sources


# ---------------------------------------------------------------------------
# Fundamentals tests
# ---------------------------------------------------------------------------

class TestGetFundamentals:
    """Tests for get_fundamentals()."""

    @patch("yfinance.Ticker")
    def test_basic_fundamentals(self, mock_ticker_cls):
        from analytics.intel_hub import get_fundamentals

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "trailingPE": 25.5,
            "forwardPE": 22.0,
            "marketCap": 2_500_000_000_000,
            "fiftyTwoWeekHigh": 200.0,
            "fiftyTwoWeekLow": 120.0,
            "sector": "Technology",
            "industry": "Semiconductors",
            "beta": 1.5,
            "dividendYield": 0.005,
            "shortRatio": 2.3,
            "shortName": "NVIDIA Corp",
        }
        mock_ticker.calendar = None
        mock_ticker_cls.return_value = mock_ticker

        result = get_fundamentals("NVDA")
        assert result is not None
        assert result["pe"] == 25.5
        assert result["forward_pe"] == 22.0
        assert result["market_cap_fmt"] == "$2.5T"
        assert result["sector"] == "Technology"
        assert result["beta"] == 1.5
        assert result["name"] == "NVIDIA Corp"

    @patch("yfinance.Ticker")
    def test_missing_fields_default_none(self, mock_ticker_cls):
        from analytics.intel_hub import get_fundamentals

        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.calendar = None
        mock_ticker_cls.return_value = mock_ticker

        result = get_fundamentals("FAKE")
        assert result is not None
        assert result["pe"] is None
        assert result["sector"] is None
        assert result["market_cap_fmt"] == "N/A"

    @patch("yfinance.Ticker")
    def test_exception_returns_none(self, mock_ticker_cls):
        from analytics.intel_hub import get_fundamentals

        mock_ticker_cls.side_effect = Exception("API error")
        result = get_fundamentals("FAIL")
        assert result is None


# ---------------------------------------------------------------------------
# Market cap formatting
# ---------------------------------------------------------------------------

class TestFormatMarketCap:
    def test_trillion(self):
        from analytics.intel_hub import _format_market_cap
        assert _format_market_cap(2_500_000_000_000) == "$2.5T"

    def test_billion(self):
        from analytics.intel_hub import _format_market_cap
        assert _format_market_cap(500_000_000_000) == "$500.0B"

    def test_million(self):
        from analytics.intel_hub import _format_market_cap
        assert _format_market_cap(12_300_000) == "$12.3M"

    def test_none(self):
        from analytics.intel_hub import _format_market_cap
        assert _format_market_cap(None) == "N/A"

    def test_small_value(self):
        from analytics.intel_hub import _format_market_cap
        assert _format_market_cap(50000) == "$50,000"


# ---------------------------------------------------------------------------
# Weekly bars tests
# ---------------------------------------------------------------------------

class TestGetWeeklyBars:
    """Tests for get_weekly_bars()."""

    @patch("yfinance.Ticker")
    def test_weekly_resampling(self, mock_ticker_cls):
        from analytics.intel_hub import get_weekly_bars

        # Create 60 days of daily data
        idx = pd.bdate_range("2025-12-01", periods=60)
        daily = pd.DataFrame({
            "Open": [100 + i * 0.5 for i in range(60)],
            "High": [101 + i * 0.5 for i in range(60)],
            "Low": [99 + i * 0.5 for i in range(60)],
            "Close": [100.5 + i * 0.5 for i in range(60)],
            "Volume": [1_000_000] * 60,
        }, index=idx)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = daily
        mock_ticker_cls.return_value = mock_ticker

        weekly_df, wmas = get_weekly_bars("AAPL")
        assert not weekly_df.empty
        assert len(weekly_df) < len(daily)  # Resampled = fewer rows
        assert "wma10" in wmas
        assert isinstance(wmas["wma10"], float)

    @patch("yfinance.Ticker")
    def test_empty_history(self, mock_ticker_cls):
        from analytics.intel_hub import get_weekly_bars

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        weekly_df, wmas = get_weekly_bars("FAKE")
        assert weekly_df.empty
        assert wmas == {}


# ---------------------------------------------------------------------------
# Hub context assembly
# ---------------------------------------------------------------------------

class TestAssembleHubContext:
    """Tests for assemble_hub_context()."""

    @patch("analytics.intel_hub.get_alert_win_rates")
    @patch("analytics.intel_hub.get_weekly_bars")
    @patch("analytics.intel_hub.get_sr_levels")
    @patch("analytics.intel_hub.get_fundamentals")
    def test_assembles_all_sections(self, mock_fund, mock_sr,
                                    mock_weekly, mock_wr):
        from analytics.intel_hub import assemble_hub_context

        mock_fund.return_value = {"pe": 25.0, "sector": "Tech"}
        mock_sr.return_value = [
            {"level": 150.0, "label": "50 SMA", "type": "support",
             "source": "daily_ma", "distance_pct": -1.5}
        ]
        weekly_df = pd.DataFrame({
            "Open": [100.0], "High": [105.0],
            "Low": [98.0], "Close": [103.0], "Volume": [5_000_000],
        })
        mock_weekly.return_value = (weekly_df, {"wma10": 101.0})
        mock_wr.return_value = {
            "by_symbol": {"AAPL": {"wins": 5, "losses": 2, "win_rate": 71.4}},
            "overall": {"wins": 20, "losses": 10, "win_rate": 66.7, "total": 30},
        }

        result = assemble_hub_context("AAPL")
        assert result["symbol"] == "AAPL"
        assert result["fundamentals"]["pe"] == 25.0
        assert len(result["sr_levels"]) == 1
        assert result["weekly_trend"]["direction"] == "up"
        assert "overall" in result["win_rates"]

    @patch("analytics.intel_hub.get_alert_win_rates", side_effect=Exception)
    @patch("analytics.intel_hub.get_weekly_bars", side_effect=Exception)
    @patch("analytics.intel_hub.get_sr_levels", side_effect=Exception)
    @patch("analytics.intel_hub.get_fundamentals", side_effect=Exception)
    def test_graceful_failure(self, mock_fund, mock_sr,
                              mock_weekly, mock_wr):
        from analytics.intel_hub import assemble_hub_context

        result = assemble_hub_context("FAIL")
        assert result["symbol"] == "FAIL"
        assert result["fundamentals"] is None
        assert result["sr_levels"] == []
        assert result["weekly_trend"] == {}
        assert result["win_rates"] == {}


# ---------------------------------------------------------------------------
# compute_scanner_rank tests
# ---------------------------------------------------------------------------

class TestComputeScannerRank:
    """Tests for compute_scanner_rank()."""

    def test_uptrending_near_20ema_scores_high(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "AAPL",
            "intraday": {"current_price": 182.50},
            "prior_day": {
                "close": 182.00, "ma20": 181.50, "ma50": 175.00,
                "ema20": 182.00, "ema50": 176.00, "rsi14": 42.0,
                "pattern": "inside", "direction": "up",
            },
            "alerts_today": [{"direction": "BUY"}],
        }
        result = compute_scanner_rank(blob)
        assert result["rank_score"] >= 70
        assert result["rank_label"] in ("A+", "A")
        assert result["trend_pts"] == 30  # above both 50 MAs
        assert result["proximity_pts"] >= 28  # within 0.5% of 20 EMA
        assert result["setup_pts"] == 15  # inside + up + BUY alert

    def test_downtrending_scores_low(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "FAKE",
            "intraday": {"current_price": 90.0},
            "prior_day": {
                "close": 90.0, "ma20": 95.0, "ma50": 100.0,
                "ema20": 96.0, "ema50": 101.0, "rsi14": 55.0,
                "pattern": None, "direction": "down",
            },
            "alerts_today": [],
        }
        result = compute_scanner_rank(blob)
        assert result["trend_pts"] == 0  # below both 50 MAs
        assert result["rank_label"] in ("C", "B")

    def test_mega_cap_rsi_30_gets_boost(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "NVDA",  # mega cap
            "intraday": {"current_price": 800.0},
            "prior_day": {
                "close": 800.0, "ma20": 810.0, "ma50": 790.0,
                "ema20": 805.0, "ema50": 795.0, "rsi14": 30.0,
                "pattern": None, "direction": None,
            },
            "alerts_today": [],
        }
        result = compute_scanner_rank(blob)
        assert result["rsi_pts"] == 20  # mega cap RSI 28-35 boost

    def test_inside_day_adds_setup_points(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "TEST",
            "intraday": {"current_price": 100.0},
            "prior_day": {
                "close": 100.0, "ma20": 99.0, "ma50": 95.0,
                "ema20": 99.5, "ema50": 96.0, "rsi14": 50.0,
                "pattern": "inside", "direction": None,
            },
            "alerts_today": [],
        }
        result = compute_scanner_rank(blob)
        assert result["setup_pts"] >= 5  # inside day

    def test_buy_alerts_add_setup_points(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "TEST",
            "intraday": {"current_price": 100.0},
            "prior_day": {
                "close": 100.0, "ma20": 99.0, "ma50": 95.0,
                "ema20": 99.5, "ema50": 96.0, "rsi14": 50.0,
                "pattern": None, "direction": None,
            },
            "alerts_today": [{"direction": "BUY"}],
        }
        result = compute_scanner_rank(blob)
        assert result["setup_pts"] >= 5  # BUY alert

    def test_no_data_returns_minimal_score(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "EMPTY",
            "intraday": {},
            "prior_day": {},
            "alerts_today": [],
        }
        result = compute_scanner_rank(blob)
        assert result["rank_score"] == 0
        assert result["rank_label"] == "C"
        assert result["edge"] == "No price data"


# ---------------------------------------------------------------------------
# assemble_scanner_context tests
# ---------------------------------------------------------------------------

class TestAssembleScannerContext:
    """Tests for assemble_scanner_context()."""

    @patch("analytics.intel_hub.get_sr_levels")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    @patch("alerting.alert_store.get_alerts_today")
    @patch("db.get_all_daily_plans")
    def test_assembles_context_for_symbols(
        self, mock_plans, mock_alerts, mock_prior, mock_intra, mock_sr
    ):
        from analytics.intel_hub import assemble_scanner_context

        mock_plans.return_value = [
            {"symbol": "AAPL", "score": 85, "score_label": "A",
             "entry": 182.50, "stop": 180.00, "target_1": 185.00,
             "target_2": 188.00, "pattern": "bull_flag"},
        ]
        mock_alerts.return_value = [
            {"symbol": "AAPL", "direction": "BUY", "alert_type": "ma_bounce"},
        ]
        mock_prior.return_value = {
            "close": 182.00, "high": 183.50, "low": 181.00,
            "ma20": 181.00, "ma50": 178.00, "ema20": 181.50,
            "ema50": 179.00,
            "rsi14": 58.0, "pattern": "inside", "direction": "up",
        }
        intra_df = pd.DataFrame({
            "Open": [182.0], "High": [183.2], "Low": [181.8],
            "Close": [182.75], "Volume": [1000],
        }, index=pd.to_datetime(["2026-03-07 10:00"]))
        mock_intra.return_value = intra_df
        mock_sr.return_value = [
            {"level": 181.0, "label": "20 SMA", "type": "support",
             "source": "daily_ma", "distance_pct": -0.96},
        ]

        result = assemble_scanner_context(["AAPL"])
        assert len(result) == 1
        blob = result[0]
        assert blob["symbol"] == "AAPL"
        assert blob["is_crypto"] is False
        assert blob["plan"]["score"] == 85
        assert blob["intraday"]["current_price"] == 182.75
        assert blob["prior_day"]["rsi14"] == 58.0
        assert blob["prior_day"]["ema50"] == 179.00
        assert len(blob["sr_levels"]) == 1
        assert len(blob["alerts_today"]) == 1

    @patch("analytics.intel_hub.get_sr_levels")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    @patch("alerting.alert_store.get_alerts_today")
    @patch("db.get_all_daily_plans")
    def test_skips_symbol_without_prior_day(
        self, mock_plans, mock_alerts, mock_prior, mock_intra, mock_sr
    ):
        from analytics.intel_hub import assemble_scanner_context

        mock_plans.return_value = []
        mock_alerts.return_value = []
        mock_prior.return_value = None  # No prior day data

        result = assemble_scanner_context(["FAKE"])
        assert result == []

    @patch("analytics.intel_hub.get_sr_levels")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    @patch("alerting.alert_store.get_alerts_today")
    @patch("db.get_all_daily_plans")
    def test_handles_empty_intraday(
        self, mock_plans, mock_alerts, mock_prior, mock_intra, mock_sr
    ):
        from analytics.intel_hub import assemble_scanner_context

        mock_plans.return_value = []
        mock_alerts.return_value = []
        mock_prior.return_value = {
            "close": 100.0, "high": 101.0, "low": 99.0,
            "ma20": 99.5, "ma50": 98.0, "ema20": 99.8,
            "ema50": 97.5,
            "rsi14": 50.0, "pattern": None, "direction": None,
        }
        mock_intra.return_value = pd.DataFrame()  # Empty intraday
        mock_sr.return_value = []

        result = assemble_scanner_context(["SPY"])
        assert len(result) == 1
        assert result[0]["intraday"] == {}

    @patch("analytics.intel_hub.get_sr_levels")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    @patch("alerting.alert_store.get_alerts_today")
    @patch("db.get_all_daily_plans")
    def test_crypto_symbol_tagged(
        self, mock_plans, mock_alerts, mock_prior, mock_intra, mock_sr
    ):
        from analytics.intel_hub import assemble_scanner_context

        mock_plans.return_value = []
        mock_alerts.return_value = []
        mock_prior.return_value = {
            "close": 60000.0, "high": 61000.0, "low": 59000.0,
            "ma20": 58000.0, "ma50": 55000.0, "ema20": 59000.0,
            "ema50": 56000.0,
            "rsi14": 65.0, "pattern": None, "direction": "up",
        }
        mock_intra.return_value = pd.DataFrame()
        mock_sr.return_value = []

        result = assemble_scanner_context(["BTC-USD"])
        assert len(result) == 1
        assert result[0]["is_crypto"] is True

    @patch("analytics.intel_hub.get_sr_levels")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    @patch("alerting.alert_store.get_alerts_today")
    @patch("db.get_all_daily_plans")
    def test_stop_hit_sets_invalidated_flag(
        self, mock_plans, mock_alerts, mock_prior, mock_intra, mock_sr
    ):
        from analytics.intel_hub import assemble_scanner_context

        mock_plans.return_value = [
            {"symbol": "AAPL", "entry": 182.0, "stop": 180.0,
             "target_1": 185.0, "target_2": 188.0, "score": 80,
             "score_label": "A", "pattern": "normal"},
        ]
        mock_alerts.return_value = [
            {"symbol": "AAPL", "direction": "SELL",
             "alert_type": "stop_loss_hit"},
        ]
        mock_prior.return_value = {
            "close": 179.0, "high": 183.0, "low": 178.0,
            "ma20": 181.0, "ma50": 175.0, "ema20": 180.5,
            "ema50": 176.0, "rsi14": 35.0, "pattern": None,
            "direction": "down",
        }
        intra_df = pd.DataFrame({
            "Open": [180.0], "High": [180.5], "Low": [178.0],
            "Close": [178.5], "Volume": [1000],
        }, index=pd.to_datetime(["2026-03-07 10:00"]))
        mock_intra.return_value = intra_df
        mock_sr.return_value = []

        result = assemble_scanner_context(["AAPL"])
        assert len(result) == 1
        assert result[0]["invalidated"] is True

    @patch("analytics.intel_hub.get_sr_levels")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    @patch("alerting.alert_store.get_alerts_today")
    @patch("db.get_all_daily_plans")
    def test_no_stop_hit_not_invalidated(
        self, mock_plans, mock_alerts, mock_prior, mock_intra, mock_sr
    ):
        from analytics.intel_hub import assemble_scanner_context

        mock_plans.return_value = []
        mock_alerts.return_value = [
            {"symbol": "AAPL", "direction": "BUY",
             "alert_type": "ma_bounce"},
        ]
        mock_prior.return_value = {
            "close": 182.0, "high": 183.0, "low": 181.0,
            "ma20": 181.0, "ma50": 178.0, "ema20": 181.5,
            "ema50": 179.0, "rsi14": 50.0, "pattern": None,
            "direction": "up",
        }
        mock_intra.return_value = pd.DataFrame()
        mock_sr.return_value = []

        result = assemble_scanner_context(["AAPL"])
        assert len(result) == 1
        assert result[0]["invalidated"] is False

    @patch("analytics.intel_hub.get_sr_levels")
    @patch("analytics.intraday_data.fetch_intraday")
    @patch("analytics.intraday_data.fetch_prior_day")
    @patch("alerting.alert_store.get_alerts_today")
    @patch("db.get_all_daily_plans")
    def test_reprojected_plan_attached(
        self, mock_plans, mock_alerts, mock_prior, mock_intra, mock_sr
    ):
        from analytics.intel_hub import assemble_scanner_context

        mock_plans.return_value = [
            {"symbol": "AAPL", "entry": 182.0, "stop": 180.0,
             "target_1": 185.0, "target_2": 188.0, "score": 80,
             "score_label": "A", "pattern": "normal"},
        ]
        mock_alerts.return_value = [
            {"symbol": "AAPL", "direction": "SELL",
             "alert_type": "stop_loss_hit"},
        ]
        mock_prior.return_value = {
            "close": 179.0, "high": 183.0, "low": 174.0,
            "ma20": 181.0, "ma50": 175.0, "ema20": 180.5,
            "ema50": 176.0, "rsi14": 35.0, "pattern": None,
            "direction": "down",
        }
        intra_df = pd.DataFrame({
            "Open": [180.0], "High": [180.5], "Low": [178.0],
            "Close": [178.5], "Volume": [1000],
        }, index=pd.to_datetime(["2026-03-07 10:00"]))
        mock_intra.return_value = intra_df
        mock_sr.return_value = []

        result = assemble_scanner_context(["AAPL"])
        blob = result[0]
        assert blob["invalidated"] is True
        assert blob["reprojected_plan"] is not None
        assert "entry" in blob["reprojected_plan"]
        assert "support_label" in blob["reprojected_plan"]


# ---------------------------------------------------------------------------
# Invalidation + edge text in compute_scanner_rank
# ---------------------------------------------------------------------------

class TestScannerRankInvalidation:
    """Tests for invalidation handling in compute_scanner_rank()."""

    def test_edge_includes_support_label(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "AAPL",
            "intraday": {"current_price": 182.50},
            "prior_day": {
                "close": 182.00, "ma20": 181.50, "ma50": 175.00,
                "ema20": 182.00, "ema50": 176.00, "rsi14": 42.0,
                "pattern": "normal", "direction": "up",
            },
            "plan": {"entry": 181.50, "stop": 180.00, "target_1": 185.00},
            "alerts_today": [],
        }
        result = compute_scanner_rank(blob)
        edge = result["edge"]
        # Should reference the nearest MA label and price
        assert "support" in edge.lower() or "SMA" in edge or "EMA" in edge

    def test_invalidated_edge_says_stopped_out(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "AAPL",
            "intraday": {"current_price": 178.0},
            "prior_day": {
                "close": 179.0, "ma20": 181.0, "ma50": 175.0,
                "ema20": 180.0, "ema50": 176.0, "rsi14": 35.0,
                "pattern": None, "direction": "down",
            },
            "alerts_today": [],
            "invalidated": True,
            "reprojected_plan": {
                "entry": 175.0, "stop": 173.25,
                "target_1": 183.0, "target_2": 191.0,
                "support": 175.0, "support_label": "50 SMA",
                "risk_per_share": 1.75, "rr_ratio": 4.57,
            },
        }
        result = compute_scanner_rank(blob)
        assert "STOPPED OUT" in result["edge"]
        assert "50 SMA" in result["edge"]

    def test_invalidated_no_reproj_edge(self):
        from analytics.intel_hub import compute_scanner_rank

        blob = {
            "symbol": "AAPL",
            "intraday": {"current_price": 170.0},
            "prior_day": {
                "close": 171.0, "ma20": 175.0, "ma50": 178.0,
                "ema20": 176.0, "ema50": 179.0, "rsi14": 25.0,
                "pattern": None, "direction": "down",
            },
            "alerts_today": [],
            "invalidated": True,
            "reprojected_plan": None,
        }
        result = compute_scanner_rank(blob)
        assert "STOPPED OUT" in result["edge"]
        assert "no valid support" in result["edge"].lower()

    def test_invalidated_rank_penalty(self):
        from analytics.intel_hub import compute_scanner_rank

        base_blob = {
            "symbol": "AAPL",
            "intraday": {"current_price": 182.50},
            "prior_day": {
                "close": 182.00, "ma20": 181.50, "ma50": 175.00,
                "ema20": 182.00, "ema50": 176.00, "rsi14": 42.0,
                "pattern": "inside", "direction": "up",
            },
            "alerts_today": [{"direction": "BUY"}],
        }

        # Normal score
        normal = compute_scanner_rank(base_blob)

        # Invalidated (with reprojection) — should be 30 pts lower, floor at 20
        inv_blob = {
            **base_blob,
            "invalidated": True,
            "reprojected_plan": {
                "entry": 175.0, "stop": 173.25,
                "target_1": 183.0, "target_2": 191.0,
                "support": 175.0, "support_label": "50 SMA",
                "risk_per_share": 1.75, "rr_ratio": 4.57,
            },
        }
        inv = compute_scanner_rank(inv_blob)
        assert inv["rank_score"] == max(20, normal["rank_score"] - 30)
