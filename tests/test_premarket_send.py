"""Unit tests for pre-market brief — build_premarket_message + send_premarket_brief."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_pm_bars(rows: list[dict], date: str = "2025-06-02") -> pd.DataFrame:
    """Create synthetic pre-market bars with proper datetime index."""
    records = []
    for r in rows:
        records.append({
            "Open": r.get("open", 100),
            "High": r.get("high", 101),
            "Low": r.get("low", 99),
            "Close": r.get("close", 100.5),
        })
    df = pd.DataFrame(records, index=pd.DatetimeIndex([
        pd.Timestamp(f"{date} {r['time']}") for r in rows
    ]))
    return df


def _make_prior_day(
    close=100.0, high=102.0, low=98.0, open_=99.5,
    ma20=100.0, ma50=97.0, parent_range=4.0,
) -> dict:
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1_000_000,
        "ma20": ma20,
        "ma50": ma50,
        "pattern": "inside",
        "direction": "bullish",
        "is_inside": False,
        "parent_high": high + 1,
        "parent_low": low - 1,
        "parent_range": parent_range,
        "prior_week_high": high + 2,
        "prior_week_low": low - 2,
    }


def _make_brief(symbol="NVDA", priority="HIGH", flags=None, pm_last=144.2, pm_change_pct=1.5, pm_range_pct=1.2):
    return {
        "symbol": symbol,
        "pm_high": pm_last + 1,
        "pm_low": pm_last - 1,
        "pm_last": pm_last,
        "pm_change_pct": pm_change_pct,
        "gap_pct": pm_change_pct,
        "gap_type": "gap_up" if pm_change_pct > 0 else "flat",
        "above_prior_high": False,
        "below_prior_low": False,
        "near_ma20": True,
        "near_ma50": False,
        "pm_range_pct": pm_range_pct,
        "priority_score": 60 if priority == "HIGH" else 30 if priority == "MEDIUM" else 10,
        "priority_label": priority,
        "flags": flags if flags is not None else ["GAP UP +1.5%", "NEAR 20MA"],
    }


def _spy_ctx(trend="bullish", regime="TRENDING_UP", close=520.3, rsi=58.0):
    return {
        "trend": trend,
        "close": close,
        "regime": regime,
        "spy_rsi14": rsi,
        "ma20": 518.0,
        "ma50": 510.0,
        "ma5": 519.0,
    }


# ===== build_premarket_message =====


class TestBuildPremarketMessage:
    """Tests for build_premarket_message()."""

    @patch("analytics.premarket_brief.get_all_watchlist_symbols", return_value=[])
    def test_returns_none_when_no_symbols(self, _mock_ws):
        from analytics.premarket_brief import build_premarket_message
        assert build_premarket_message() is None

    @patch("analytics.premarket_brief.get_spy_context", return_value=_spy_ctx())
    @patch("analytics.premarket_brief.fetch_prior_day", return_value=_make_prior_day())
    @patch("analytics.premarket_brief.fetch_premarket_bars", return_value=pd.DataFrame())
    @patch("analytics.premarket_brief.get_all_watchlist_symbols", return_value=["AAPL"])
    def test_returns_none_when_no_pm_data(self, _ws, _pm, _pd, _spy):
        from analytics.premarket_brief import build_premarket_message
        assert build_premarket_message() is None

    @patch("analytics.premarket_brief.get_spy_context")
    @patch("analytics.premarket_brief.compute_premarket_brief")
    @patch("analytics.premarket_brief.fetch_prior_day")
    @patch("analytics.premarket_brief.fetch_premarket_bars")
    @patch("analytics.premarket_brief.get_all_watchlist_symbols")
    def test_high_priority_first(self, mock_ws, mock_pm, mock_pd, mock_brief, mock_spy):
        mock_ws.return_value = ["AAPL", "NVDA", "GOOGL"]
        mock_pm.return_value = _make_pm_bars([{"time": "08:00"}])
        mock_pd.return_value = _make_prior_day()
        mock_spy.return_value = _spy_ctx()

        # AAPL=MEDIUM, NVDA=HIGH, GOOGL=LOW
        mock_brief.side_effect = [
            _make_brief("AAPL", "MEDIUM", ["NEAR 50MA"], pm_last=188.5, pm_change_pct=0.2, pm_range_pct=0.2),
            _make_brief("NVDA", "HIGH", ["GAP UP +1.5%", "NEAR 20MA"], pm_last=144.2, pm_change_pct=1.5, pm_range_pct=1.2),
            _make_brief("GOOGL", "LOW", [], pm_last=165.3, pm_change_pct=0.2, pm_range_pct=0.2),
        ]

        from analytics.premarket_brief import build_premarket_message
        msg = build_premarket_message()

        assert msg is not None
        # HIGH must appear before MEDIUM
        high_pos = msg.index("HIGH PRIORITY")
        medium_pos = msg.index("MEDIUM PRIORITY")
        low_pos = msg.index("LOW PRIORITY")
        assert high_pos < medium_pos < low_pos

    @patch("analytics.premarket_brief.get_spy_context")
    @patch("analytics.premarket_brief.compute_premarket_brief")
    @patch("analytics.premarket_brief.fetch_prior_day")
    @patch("analytics.premarket_brief.fetch_premarket_bars")
    @patch("analytics.premarket_brief.get_all_watchlist_symbols")
    def test_spy_header_bullish(self, mock_ws, mock_pm, mock_pd, mock_brief, mock_spy):
        mock_ws.return_value = ["AAPL"]
        mock_pm.return_value = _make_pm_bars([{"time": "08:00"}])
        mock_pd.return_value = _make_prior_day()
        mock_spy.return_value = _spy_ctx(trend="bullish", regime="TRENDING_UP", close=520.3, rsi=58.0)
        mock_brief.return_value = _make_brief("AAPL", "MEDIUM")

        from analytics.premarket_brief import build_premarket_message
        msg = build_premarket_message()

        assert msg is not None
        assert "SPY" in msg
        assert "$520.30" in msg
        assert "TRENDING_UP" in msg

    @patch("analytics.premarket_brief.get_spy_context")
    @patch("analytics.premarket_brief.compute_premarket_brief")
    @patch("analytics.premarket_brief.fetch_prior_day")
    @patch("analytics.premarket_brief.fetch_premarket_bars")
    @patch("analytics.premarket_brief.get_all_watchlist_symbols")
    def test_spy_header_bearish(self, mock_ws, mock_pm, mock_pd, mock_brief, mock_spy):
        mock_ws.return_value = ["AAPL"]
        mock_pm.return_value = _make_pm_bars([{"time": "08:00"}])
        mock_pd.return_value = _make_prior_day()
        mock_spy.return_value = _spy_ctx(trend="bearish", regime="TRENDING_DOWN", close=480.0, rsi=35.0)
        mock_brief.return_value = _make_brief("AAPL", "LOW")

        from analytics.premarket_brief import build_premarket_message
        msg = build_premarket_message()

        assert msg is not None
        assert "SPY" in msg
        assert "TRENDING_DOWN" in msg

    @patch("analytics.premarket_brief.get_spy_context")
    @patch("analytics.premarket_brief.compute_premarket_brief")
    @patch("analytics.premarket_brief.fetch_prior_day")
    @patch("analytics.premarket_brief.fetch_premarket_bars")
    @patch("analytics.premarket_brief.get_all_watchlist_symbols")
    def test_symbol_line_format(self, mock_ws, mock_pm, mock_pd, mock_brief, mock_spy):
        mock_ws.return_value = ["NVDA"]
        mock_pm.return_value = _make_pm_bars([{"time": "08:00"}])
        mock_pd.return_value = _make_prior_day()
        mock_spy.return_value = _spy_ctx()
        mock_brief.return_value = _make_brief(
            "NVDA", "HIGH",
            flags=["GAP UP +1.5%", "NEAR 20MA"],
            pm_last=144.2, pm_change_pct=1.5, pm_range_pct=1.2,
        )

        from analytics.premarket_brief import build_premarket_message
        msg = build_premarket_message()

        assert msg is not None
        assert "NVDA" in msg
        assert "GAP UP +1.5%" in msg
        assert "NEAR 20MA" in msg
        assert "$144.20" in msg

    @patch("analytics.premarket_brief.get_spy_context")
    @patch("analytics.premarket_brief.compute_premarket_brief")
    @patch("analytics.premarket_brief.fetch_prior_day")
    @patch("analytics.premarket_brief.fetch_premarket_bars")
    @patch("analytics.premarket_brief.get_all_watchlist_symbols")
    def test_no_flags_shows_no_flags(self, mock_ws, mock_pm, mock_pd, mock_brief, mock_spy):
        mock_ws.return_value = ["GOOGL"]
        mock_pm.return_value = _make_pm_bars([{"time": "08:00"}])
        mock_pd.return_value = _make_prior_day()
        mock_spy.return_value = _spy_ctx()
        mock_brief.return_value = _make_brief("GOOGL", "LOW", flags=[], pm_last=165.3, pm_change_pct=0.1)

        from analytics.premarket_brief import build_premarket_message
        msg = build_premarket_message()

        assert msg is not None
        assert "GOOGL" in msg
        assert "No flags" in msg


# ===== send_premarket_brief =====


class TestSendPremarketBrief:
    """Tests for send_premarket_brief()."""

    def setup_method(self):
        """Reset module-level guard between tests."""
        import analytics.premarket_brief as mod
        mod._brief_sent_date = None

    @patch("analytics.premarket_brief.build_premarket_message", return_value=None)
    def test_returns_false_when_no_message(self, _mock):
        from analytics.premarket_brief import send_premarket_brief
        assert send_premarket_brief() is False

    @patch("analytics.premarket_brief._send_telegram", return_value=True)
    @patch("analytics.premarket_brief.build_premarket_message", return_value="test msg")
    @patch("analytics.premarket_brief.today_session", return_value="2025-06-02")
    def test_sends_once_per_day(self, _ts, _msg, _tg):
        from analytics.premarket_brief import send_premarket_brief
        assert send_premarket_brief() is True
        # Second call same day — skipped
        assert send_premarket_brief() is False

    @patch("analytics.premarket_brief._send_telegram", return_value=True)
    @patch("analytics.premarket_brief.build_premarket_message", return_value="test msg")
    @patch("analytics.premarket_brief.today_session")
    def test_sends_on_new_day(self, mock_ts, _msg, _tg):
        from analytics.premarket_brief import send_premarket_brief
        mock_ts.return_value = "2025-06-02"
        assert send_premarket_brief() is True

        mock_ts.return_value = "2025-06-03"
        assert send_premarket_brief() is True

    @patch("analytics.premarket_brief._send_telegram", return_value=True)
    @patch("analytics.premarket_brief.build_premarket_message", return_value="test msg")
    @patch("analytics.premarket_brief.today_session", return_value="2025-06-02")
    def test_calls_telegram(self, _ts, _msg, mock_tg):
        from analytics.premarket_brief import send_premarket_brief
        send_premarket_brief()
        mock_tg.assert_called_once_with("test msg")
