"""RTH gate — equities route only 09:30-16:00 ET; SPY/QQQ, crypto and futures exempt.

Guards the 2026-08-26 change: premarket/after-hours equity alerts are persisted with
suppressed_reason="outside_rth" instead of being delivered.
"""
from datetime import datetime

import pytz

from api.app.routers.tv_webhook import session_suppress_reason

ET = pytz.timezone("America/New_York")


def _et(y, m, d, hh, mm):
    return ET.localize(datetime(y, m, d, hh, mm))


# A Tuesday.
PRE = _et(2026, 8, 25, 8, 30)
OPEN_EDGE = _et(2026, 8, 25, 9, 30)
MID = _et(2026, 8, 25, 12, 0)
CLOSE_EDGE = _et(2026, 8, 25, 16, 0)
AFTER = _et(2026, 8, 25, 18, 0)
SATURDAY = _et(2026, 8, 29, 12, 0)


class TestEquities:
    def test_premarket_suppressed(self):
        assert session_suppress_reason("AAPL", PRE) == "outside_rth"

    def test_after_hours_suppressed(self):
        assert session_suppress_reason("AAPL", AFTER) == "outside_rth"

    def test_weekend_suppressed(self):
        assert session_suppress_reason("AAPL", SATURDAY) == "outside_rth"

    def test_rth_routes(self):
        assert session_suppress_reason("AAPL", MID) is None

    def test_open_edge_routes(self):
        """09:30 exactly is IN session — the opening bar is the point."""
        assert session_suppress_reason("AAPL", OPEN_EDGE) is None

    def test_close_edge_suppressed(self):
        """16:00 exactly is OUT — the session is over at the bell."""
        assert session_suppress_reason("AAPL", CLOSE_EDGE) == "outside_rth"


class TestExempt:
    def test_spy_premarket_routes(self):
        assert session_suppress_reason("SPY", PRE) is None

    def test_qqq_after_hours_routes(self):
        assert session_suppress_reason("QQQ", AFTER) is None

    def test_spy_lowercase_routes(self):
        assert session_suppress_reason("spy", PRE) is None

    def test_other_index_still_gated(self):
        """IWM is in the regime allow-list but NOT the RTH exemption — separate lists."""
        assert session_suppress_reason("IWM", PRE) == "outside_rth"


class TestFuturesUnchanged:
    def test_futures_keep_their_window(self):
        """ES1! at 08:30 is inside 04:00-16:00 — must NOT be caught by the equity gate."""
        assert session_suppress_reason("ES1!", PRE) is None

    def test_futures_overnight_still_suppressed(self):
        assert session_suppress_reason("ES1!", _et(2026, 8, 25, 2, 0)) == "outside_session"

    def test_futures_after_close_suppressed(self):
        assert session_suppress_reason("ES1!", AFTER) == "outside_session"


class TestCrypto:
    def test_crypto_never_suppressed(self):
        for when in (PRE, MID, AFTER, SATURDAY):
            assert session_suppress_reason("BTCUSD", when) is None


class TestCryptoTickerFormats:
    """TV posts BTCUSD / BINANCE:BTCUSDT; config stores BTC-USD. All must be exempt —
    a 24h market silenced outside RTH would be the worst possible failure here."""

    def test_tv_bare_format(self):
        assert session_suppress_reason("BTCUSD", PRE) is None

    def test_config_format(self):
        assert session_suppress_reason("BTC-USD", AFTER) is None

    def test_exchange_prefixed_usdt(self):
        assert session_suppress_reason("BINANCE:BTCUSDT", SATURDAY) is None

    def test_eth_variants(self):
        for sym in ("ETHUSD", "ETH-USD", "COINBASE:ETHUSD"):
            assert session_suppress_reason(sym, PRE) is None

    def test_equity_not_mistaken_for_crypto(self):
        """A ticker merely ending in USD must not slip through."""
        assert session_suppress_reason("XYZUSD", PRE) == "outside_rth"


class TestSettingsToggles:
    """Each session toggles independently from Settings (regime_config)."""

    def test_premarket_on_lets_premarket_through(self):
        assert session_suppress_reason("AAPL", PRE, allow_premarket=True) is None

    def test_premarket_on_does_not_open_after_hours(self):
        assert session_suppress_reason("AAPL", AFTER, allow_premarket=True) == "outside_rth"

    def test_afterhours_on_lets_after_hours_through(self):
        assert session_suppress_reason("AAPL", AFTER, allow_afterhours=True) is None

    def test_afterhours_on_does_not_open_premarket(self):
        assert session_suppress_reason("AAPL", PRE, allow_afterhours=True) == "outside_rth"

    def test_both_on_restores_old_behaviour(self):
        for when in (PRE, AFTER):
            assert session_suppress_reason("AAPL", when, allow_premarket=True, allow_afterhours=True) is None

    def test_weekend_stays_suppressed_even_with_both_on(self):
        """Saturday isn't a session — no toggle should open it."""
        assert session_suppress_reason(
            "AAPL", SATURDAY, allow_premarket=True, allow_afterhours=True,
        ) == "outside_rth"

    def test_custom_exempt_list(self):
        assert session_suppress_reason("NVDA", PRE, exempt=frozenset({"NVDA"})) is None
        assert session_suppress_reason("SPY", PRE, exempt=frozenset({"NVDA"})) == "outside_rth"

    def test_toggles_do_not_affect_futures(self):
        assert session_suppress_reason(
            "ES1!", _et(2026, 8, 25, 2, 0), allow_premarket=True, allow_afterhours=True,
        ) == "outside_session"
