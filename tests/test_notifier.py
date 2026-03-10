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
    @patch("alerting.notifier.send_sms", return_value=True)
    @patch("alerting.notifier.send_email", return_value=True)
    @patch("alerting.notifier.TELEGRAM_BOT_TOKEN", "")
    def test_high_score_sends_email_and_telegram(self, mock_email, mock_sms):
        """A+ signal (score=90) → email + SMS fallback when no Telegram config."""
        sig = _make_signal(score=90, score_label="A+")
        email_sent, sms_sent = notify(sig)
        assert email_sent is True
        assert sms_sent is True
        mock_email.assert_called_once_with(sig)
        mock_sms.assert_called_once_with(sig)

    @patch("alerting.notifier.send_sms", return_value=True)
    @patch("alerting.notifier.send_email", return_value=True)
    @patch("alerting.notifier.TELEGRAM_BOT_TOKEN", "")
    def test_low_score_still_sends_both(self, mock_email, mock_sms):
        """C signal (score=40) → both email and SMS fallback."""
        sig = _make_signal(score=40, score_label="C")
        email_sent, sms_sent = notify(sig)
        assert email_sent is True
        assert sms_sent is True
        mock_email.assert_called_once_with(sig)
        mock_sms.assert_called_once_with(sig)

    @patch("alerting.notifier.send_sms", return_value=True)
    @patch("alerting.notifier.send_email", return_value=True)
    @patch("alerting.notifier.TELEGRAM_BOT_TOKEN", "")
    def test_stop_loss_always_sends_telegram(self, mock_email, mock_sms):
        """STOP_LOSS_HIT (score=0) → email + SMS fallback."""
        sig = _make_signal(
            alert_type=AlertType.STOP_LOSS_HIT,
            direction="SELL",
            score=0,
            score_label="C",
        )
        email_sent, sms_sent = notify(sig)
        assert email_sent is True
        assert sms_sent is True
        mock_sms.assert_called_once_with(sig)

    @patch("alerting.notifier.send_sms", return_value=True)
    @patch("alerting.notifier.send_email", return_value=True)
    @patch("alerting.notifier.TELEGRAM_BOT_TOKEN", "")
    def test_target_hit_always_sends_telegram(self, mock_email, mock_sms):
        """TARGET_1_HIT → email + SMS fallback."""
        sig = _make_signal(
            alert_type=AlertType.TARGET_1_HIT,
            direction="SELL",
            score=0,
            score_label="C",
        )
        email_sent, sms_sent = notify(sig)
        assert email_sent is True
        assert sms_sent is True
        mock_sms.assert_called_once_with(sig)

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
    def test_buy_includes_score_on_first_line(self):
        sig = _make_signal(score=82, score_label="A")
        sig.target_1 = 101.5
        sig.target_2 = 103.0
        body = _format_sms_body(sig)
        first_line = body.split("\n")[0]
        assert "A (82)" in first_line
        assert "POTENTIAL ENTRY AAPL" in first_line

    def test_buy_includes_entry_and_stop(self):
        sig = _make_signal(score=70, score_label="B+")
        sig.target_1 = 101.5
        sig.target_2 = 103.0
        body = _format_sms_body(sig)
        assert "Potential Entry $100.00" in body
        assert "Stop $99.00" in body

    def test_buy_includes_t1_and_t2(self):
        sig = _make_signal(score=70, score_label="B+")
        sig.target_1 = 101.5
        sig.target_2 = 103.0
        body = _format_sms_body(sig)
        assert "T1 $101.50" in body
        assert "T2 $103.00" in body

    def test_sell_simple_format(self):
        sig = AlertSignal(
            symbol="NVDA",
            alert_type=AlertType.RESISTANCE_PRIOR_HIGH,
            direction="SELL",
            price=182.57,
            message="Prior High Resistance $182.59",
        )
        body = _format_sms_body(sig)
        assert "EXIT ZONE NVDA $182.57" in body
        assert "Resistance Prior High" in body
        assert "Entry" not in body
        assert "Stop" not in body

    def test_buy_message_context_included(self):
        sig = _make_signal(score=80, score_label="A")
        sig.target_1 = 101.0
        sig.message = "MA bounce 20 — pulled back to $100 (prime_time) — price above VWAP"
        body = _format_sms_body(sig)
        assert "above VWAP" in body
        assert "prime_time" in body

    def test_truncated_to_4000_chars(self):
        sig = _make_signal(score=80, score_label="A")
        sig.target_1 = 101.0
        sig.target_2 = 102.0
        sig.message = "x" * 5000
        body = _format_sms_body(sig)
        assert len(body) <= 4000


class TestEmailFormat:
    def test_includes_score_line(self):
        sig = _make_signal(score=82, score_label="A")
        sig.target_1 = 101.5
        sig.target_2 = 103.0
        body = _format_email_body(sig)
        assert "Score:   A (82/100)" in body

    def test_real_r_multiples(self):
        sig = _make_signal(score=70, score_label="B+")
        # entry=100, stop=99 → risk=1
        sig.target_1 = 101.5  # +1.5 = 1.5R
        sig.target_2 = 103.0  # +3.0 = 3.0R
        body = _format_email_body(sig)
        assert "1.5R" in body
        assert "3.0R" in body

    def test_risk_percentage(self):
        sig = _make_signal(score=70, score_label="B+")
        body = _format_email_body(sig)
        # entry=100, stop=99 → risk=$1.00 = 1.0%
        assert "1.0%" in body

    def test_no_score_line_when_zero(self):
        sig = _make_signal(score=0, score_label="")
        body = _format_email_body(sig)
        assert "Score:" not in body
