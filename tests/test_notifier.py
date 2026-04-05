"""Unit tests for notification tier routing and message formatting."""

from unittest.mock import patch

from analytics.intraday_rules import AlertSignal, AlertType
from alerting.notifier import _format_email_body, _format_sms_body, notify


def _make_signal(
    alert_type=AlertType.MA_BOUNCE_20,
    direction="BUY",
    score=50,
    score_label="B",
) -> AlertSignal:
    return AlertSignal(
        symbol="AAPL",
        alert_type=alert_type,
        direction=direction,
        price=100.0,
        entry=100.0,
        stop=99.0,
        score=score,
        score_label=score_label,
        message="test",
    )


class TestTelegramTierRouting:
    @patch("alerting.notifier._send_telegram_to", return_value=True)
    @patch("alerting.notifier.send_email", return_value=True)
    @patch("alerting.notifier.TELEGRAM_CHAT_ID", "12345")
    @patch("alerting.notifier.TELEGRAM_BOT_TOKEN", "fake-token")
    def test_buy_signal_sends_telegram(self, mock_email, mock_tg):
        """BUY signal → sends via Telegram."""
        sig = _make_signal(score=90, score_label="A+")
        email_sent, sms_sent = notify(sig)
        assert email_sent is True
        assert sms_sent is True
        mock_tg.assert_called_once()

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    @patch("alerting.notifier.send_email", return_value=True)
    @patch("alerting.notifier.TELEGRAM_CHAT_ID", "12345")
    @patch("alerting.notifier.TELEGRAM_BOT_TOKEN", "fake-token")
    def test_stop_loss_sends_telegram(self, mock_email, mock_tg):
        """STOP_LOSS_HIT → sends via Telegram."""
        sig = _make_signal(
            alert_type=AlertType.STOP_LOSS_HIT,
            direction="SELL",
            score=0,
            score_label="C",
        )
        email_sent, sms_sent = notify(sig)
        assert email_sent is True
        assert sms_sent is True

    def test_target_hit_suppressed_from_telegram(self):
        """TARGET_1_HIT → suppressed from Telegram (monitor sends T1 NOTIFY instead)."""
        sig = _make_signal(
            alert_type=AlertType.TARGET_1_HIT,
            direction="SELL",
            score=0,
            score_label="C",
        )
        body = _format_sms_body(sig)
        assert body is None

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    @patch("alerting.notifier.send_email", return_value=True)
    @patch("alerting.notifier.TELEGRAM_CHAT_ID", "12345")
    @patch("alerting.notifier.TELEGRAM_BOT_TOKEN", "fake-token")
    def test_telegram_buttons_sent_with_alert_id(self, mock_email, mock_tg):
        """When alert_id is provided + Telegram configured, buttons are included."""
        sig = _make_signal(score=80, score_label="A")
        notify(sig, alert_id=42)
        mock_tg.assert_called_once()
        _, kwargs = mock_tg.call_args
        assert kwargs.get("reply_markup") is not None
        assert "inline_keyboard" in kwargs["reply_markup"]

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    @patch("alerting.notifier.send_email", return_value=True)
    @patch("alerting.notifier.TELEGRAM_CHAT_ID", "12345")
    @patch("alerting.notifier.TELEGRAM_BOT_TOKEN", "fake-token")
    def test_telegram_no_buttons_without_alert_id(self, mock_email, mock_tg):
        """When no alert_id, no buttons are sent."""
        sig = _make_signal(score=80, score_label="A")
        notify(sig)
        mock_tg.assert_called_once()
        _, kwargs = mock_tg.call_args
        assert kwargs.get("reply_markup") is None


class TestSmsFormat:
    def test_buy_format_has_long_direction(self):
        sig = _make_signal(score=82, score_label="A")
        sig.target_1 = 101.5
        sig.target_2 = 103.0
        body = _format_sms_body(sig)
        assert "LONG AAPL" in body

    def test_buy_includes_entry_and_stop(self):
        sig = _make_signal(score=70, score_label="B+")
        sig.target_1 = 101.5
        sig.target_2 = 103.0
        body = _format_sms_body(sig)
        assert "Entry $100.00" in body
        assert "Stop $99.00" in body

    def test_buy_includes_t1_and_t2(self):
        sig = _make_signal(score=70, score_label="B+")
        sig.target_1 = 101.5
        sig.target_2 = 103.0
        body = _format_sms_body(sig)
        assert "T1 $101.50" in body
        assert "T2 $103.00" in body

    def test_sell_suppressed_for_non_exit_types(self):
        """Non-exit SELL alerts (resistance approach) should be suppressed."""
        sig = AlertSignal(
            symbol="NVDA",
            alert_type=AlertType.RESISTANCE_PRIOR_HIGH,
            direction="SELL",
            price=182.57,
            message="Prior High Resistance $182.59",
        )
        body = _format_sms_body(sig)
        assert body is None  # suppressed

    def test_stop_loss_formats_correctly(self):
        sig = AlertSignal(
            symbol="AAPL",
            alert_type=AlertType.STOP_LOSS_HIT,
            direction="SELL",
            price=99.0,
            message="Stop hit",
        )
        body = _format_sms_body(sig)
        assert "STOPPED OUT" in body
        assert "AAPL" in body

    def test_buy_conviction_high(self):
        sig = _make_signal(score=80, score_label="A")
        sig.target_1 = 101.0
        body = _format_sms_body(sig)
        assert "Conviction: HIGH" in body

    def test_buy_conviction_medium(self):
        sig = _make_signal(score=60, score_label="B")
        sig.target_1 = 101.0
        body = _format_sms_body(sig)
        assert "Conviction: MEDIUM" in body

    def test_truncated_to_4000_chars(self):
        sig = _make_signal(score=80, score_label="A")
        sig.target_1 = 101.0
        sig.target_2 = 102.0
        sig.message = "x" * 5000
        body = _format_sms_body(sig)
        assert len(body) <= 4000


class TestShortFilter:
    """Verify only structural shorts pass through to Telegram."""

    def test_pdh_failed_breakout_allowed(self):
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.PDH_FAILED_BREAKOUT,
            direction="SHORT", price=105.0, entry=105.0, stop=106.0,
        )
        body = _format_sms_body(sig)
        assert body is not None
        assert "SHORT AAPL" in body

    def test_support_breakdown_allowed(self):
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.SUPPORT_BREAKDOWN,
            direction="SHORT", price=98.0, entry=98.0, stop=99.5,
        )
        body = _format_sms_body(sig)
        assert body is not None

    def test_session_high_double_top_allowed(self):
        sig = AlertSignal(
            symbol="BTC-USD", alert_type=AlertType.SESSION_HIGH_DOUBLE_TOP,
            direction="SHORT", price=67500.0, entry=67500.0, stop=68000.0,
        )
        body = _format_sms_body(sig)
        assert body is not None

    def test_ema_rejection_short_allowed(self):
        sig = AlertSignal(
            symbol="ETH-USD", alert_type=AlertType.EMA_REJECTION_SHORT,
            direction="SHORT", price=2050.0, entry=2050.0, stop=2060.0,
        )
        body = _format_sms_body(sig)
        assert body is not None

    def test_vwap_loss_sent_as_notice(self):
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.VWAP_LOSS,
            direction="SHORT", price=99.0, entry=99.0, stop=100.0,
        )
        body = _format_sms_body(sig)
        assert body is not None
        assert "NOTICE" in body
        assert "VWAP lost" in body

    def test_session_low_breakdown_sent_as_notice(self):
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.SESSION_LOW_BREAKDOWN,
            direction="SHORT", price=97.0, entry=97.0, stop=98.0,
        )
        body = _format_sms_body(sig)
        assert body is not None
        assert "NOTICE" in body
        assert "Session low broken" in body

    def test_morning_low_breakdown_sent_as_notice(self):
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.MORNING_LOW_BREAKDOWN,
            direction="SHORT", price=96.0, entry=96.0, stop=97.0,
        )
        body = _format_sms_body(sig)
        assert body is not None
        assert "NOTICE" in body
        assert "Morning low broken" in body

    def test_consol_breakout_short_suppressed(self):
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.CONSOL_BREAKOUT_SHORT,
            direction="SHORT", price=98.0, entry=98.0, stop=99.0,
        )
        body = _format_sms_body(sig)
        assert body is None

    def test_intraday_ema_rejection_suppressed(self):
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.INTRADAY_EMA_REJECTION_SHORT,
            direction="SHORT", price=99.0, entry=99.0, stop=100.0,
        )
        body = _format_sms_body(sig)
        assert body is None


class TestEmailFormat:
    def test_email_body_for_buy(self):
        sig = _make_signal(score=82, score_label="A")
        sig.target_1 = 101.5
        sig.target_2 = 103.0
        body = _format_email_body(sig)
        assert "LONG AAPL" in body
        assert "Entry" in body

    def test_email_body_for_stop(self):
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.STOP_LOSS_HIT,
            direction="SELL", price=99.0,
        )
        body = _format_email_body(sig)
        assert "STOPPED OUT" in body

    def test_email_fallback_for_suppressed(self):
        """Suppressed types get a simple fallback email body."""
        sig = AlertSignal(
            symbol="AAPL", alert_type=AlertType.TARGET_1_HIT,
            direction="SELL", price=101.0,
        )
        body = _format_email_body(sig)
        # T1 is suppressed from Telegram but email still gets a fallback
        assert "SELL" in body
        assert "AAPL" in body
