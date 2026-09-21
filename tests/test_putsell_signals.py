"""Put-seller engine — the four oversold-reversal triggers + the weekly-RSI watch."""
import pandas as pd

from analytics.putsell_signals import detect_putsell


def _ohlc(rows):
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])


def _flat_weekly(price, n=60):
    return _ohlc([[price, price + 1, price - 1, price, 10.0] for _ in range(n)])


def test_daily_rsi_reversal_fires():
    # Long uptrend, then a dip that pushes daily RSI under 40, then a green turn-up bar.
    prices = [100.0 + i * 0.3 for i in range(210)]        # steady climb
    prices += [163.0, 158.0, 153.0, 149.0, 146.0, 149.0]  # sharp drop (RSI<40) then up
    daily = _ohlc([[p, p + 0.5, p - 1.0, p, 10.0] for p in prices])
    # last bar green: open below close
    daily.iloc[-1, daily.columns.get_loc("Open")] = 147.0
    sig = detect_putsell(daily, _flat_weekly(150.0), "T")
    assert sig is not None
    assert "Daily RSI reversal" in sig.triggers
    assert sig.strike < sig.price          # strike is OTM (below price)


def test_weekly_oversold_name_is_listed_even_without_a_trigger():
    # Daily is quiet (no reversal, no bounce) but the WEEKLY RSI is deep under 40.
    daily = _ohlc([[100.0, 100.5, 99.5, 100.0, 10.0] for _ in range(210)])
    wk = [100.0 - i for i in range(20)]                    # falling weekly → RSI well under 40
    weekly = _ohlc([[p, p + 0.5, p - 0.5, p, 10.0] for p in wk])
    sig = detect_putsell(daily, weekly, "T")
    assert sig is not None
    assert sig.weekly_oversold and not sig.fired           # on the watch, not firing


def test_quiet_name_returns_none():
    # Flat daily AND flat weekly around a mid RSI → nothing to surface.
    daily = _ohlc([[100.0, 101.0, 99.0, 100.0 + (i % 2), 10.0] for i in range(210)])
    weekly = _ohlc([[100.0, 101.0, 99.0, 100.0 + (i % 2), 10.0] for i in range(60)])
    assert detect_putsell(daily, weekly, "T") is None


def test_200_sma_bounce_fires():
    # Price rides above a rising 200 SMA, wicks down to tag it, closes back above (green).
    prices = [80.0 + i * 0.2 for i in range(210)]          # 200 SMA well below price
    daily = _ohlc([[p, p + 0.5, p - 0.5, p, 10.0] for p in prices])
    sma200 = daily["Close"].rolling(200).mean().iloc[-1]
    # last bar: low tags the 200 SMA, closes above it, green
    daily.iloc[-1] = [sma200 + 0.5, sma200 + 2.0, sma200 - 0.2, sma200 + 1.5, 10.0]
    sig = detect_putsell(daily, _flat_weekly(prices[-1]), "T")
    assert sig is not None
    assert "200 SMA bounce" in sig.triggers
