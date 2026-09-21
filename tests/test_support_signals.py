"""Support/Oversold engine — rising-MA & VWAP/POC/VAL bounces, RSI reclaims, the watch."""
import pandas as pd

from analytics.support_signals import detect_support


def _ohlc(rows):
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])


def _flat_weekly(price, n=60):
    # Alternate up/down a touch so weekly RSI sits ~50 (a dead-flat series computes RSI 0,
    # which would look "oversold"). This represents a calm, not-oversold weekly.
    return _ohlc([[price + (i % 2), price + (i % 2) + 1, price + (i % 2) - 1, price + (i % 2), 10.0]
                  for i in range(n)])


def test_rising_50_ma_bounce_fires():
    # Steady climb → rising 20/50 SMA well below price; last bar wicks to the 50 and holds.
    prices = [80.0 + i * 0.25 for i in range(210)]
    daily = _ohlc([[p, p + 0.5, p - 0.5, p, 10.0] for p in prices])
    sma50 = daily["Close"].rolling(50).mean().iloc[-1]
    daily.iloc[-1] = [sma50 + 0.5, sma50 + 2.0, sma50 - 0.1, sma50 + 1.5, 10.0]
    sig = detect_support(daily, _flat_weekly(prices[-1]), "T")
    assert sig is not None
    assert "Rising 20/50 MA" in sig.triggers
    assert sig.strike < sig.price


def test_falling_ma_bounce_does_not_fire():
    # Downtrend → the 20/50 SMA is FALLING, so a tag of it is not a rising-support bounce.
    prices = [200.0 - i * 0.4 for i in range(210)]
    daily = _ohlc([[p, p + 0.5, p - 0.5, p, 10.0] for p in prices])
    sma50 = daily["Close"].rolling(50).mean().iloc[-1]
    daily.iloc[-1] = [sma50 + 0.5, sma50 + 2.0, sma50 - 0.1, sma50 + 1.5, 10.0]
    sig = detect_support(daily, _flat_weekly(prices[-1]), "T")
    # may still be None or oversold-watch, but must NOT claim a rising-MA support
    if sig is not None:
        assert "Rising 20/50 MA" not in sig.triggers


def test_weekly_oversold_name_is_listed_without_a_trigger():
    daily = _ohlc([[100.0, 100.5, 99.5, 100.0, 10.0] for _ in range(210)])
    wk = [100.0 - i for i in range(20)]                # falling weekly → RSI well under 40
    weekly = _ohlc([[p, p + 0.5, p - 0.5, p, 10.0] for p in wk])
    sig = detect_support(daily, weekly, "T")
    assert sig is not None
    assert sig.weekly_oversold and not sig.at_support   # on the watch, not bouncing


def test_quiet_uptrend_name_returns_none():
    # Rising but NOT tagging any support (trades well above the MAs), mid RSI → nothing.
    prices = [80.0 + i * 0.25 for i in range(210)]
    daily = _ohlc([[p, p + 0.3, p - 0.1, p, 10.0] for p in prices])   # tight, no wick to MA
    assert detect_support(daily, _flat_weekly(prices[-1]), "T") is None
