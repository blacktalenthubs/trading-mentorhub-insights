"""Support/Oversold engine — rising-MA & VWAP/POC/VAL bounces, RSI reclaims, the watch."""
import pandas as pd

from analytics.support_signals import detect_support
from analytics.volume_profile_signals import compute_profile


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


# ── Volume-profile triggers (validated live on SPY/APP/NVDA/QQQ, 2026-09-21) ──

def _node(price, n, vol=20.0):
    return [[price, price + 1, price - 1, price, vol] for _ in range(n)]


def test_poc_reclaim_fires_on_a_wick_from_below():
    # 150 bars concentrate volume at 100 → POC ~100. Prior close BELOW it; last bar wicks
    # down to the POC and closes back above it, green → POC reclaim (like APP).
    rows = _node(100.0, 150)
    rows[-2] = [99.0, 99.5, 97.5, 98.0, 20.0]        # prev close below the POC
    rows[-1] = [98.5, 103.0, 99.4, 102.0, 20.0]      # wick tags ~POC, closes above, green
    sig = detect_support(_ohlc(rows), _flat_weekly(100.0), "T")
    assert sig is not None and "POC reclaim" in sig.triggers


def test_no_volume_signal_when_price_sits_above_the_node():
    # The QQQ staleness bug: price has been ABOVE the node for >1 bar (not a fresh cross) and
    # never wicks to it → no volume signal (edge-triggered, not state-based).
    rows = _node(100.0, 150)
    rows[-2] = [108.0, 109.0, 107.0, 108.0, 20.0]    # already above the node yesterday
    rows[-1] = [108.5, 111.0, 108.0, 110.0, 20.0]    # still above, no wick to it, no cross
    sig = detect_support(_ohlc(rows), _flat_weekly(108.0), "T")
    if sig is not None:
        assert not any(t.startswith(("POC", "HVN")) or "VAL" in t for t in sig.triggers)


def test_hvn_break_fires_on_a_crossover():
    # Two nodes (100 = POC, ~115 = HVN). Last bar crosses UP through the 115 node from below.
    rows = _node(100.0, 90) + _node(115.0, 58)
    rows[-2] = [113.0, 114.0, 112.0, 113.0, 20.0]    # prev close below the HVN
    rows[-1] = [113.5, 119.0, 112.5, 118.0, 20.0]    # closes above it (a break), low ≠ POC
    sig = detect_support(_ohlc(rows), _flat_weekly(115.0), "T")
    assert sig is not None and "HVN break" in sig.triggers


def test_ambiguous_flag_on_two_near_tied_nodes():
    # QQQ case: two separated peaks of nearly equal volume → the POC can flip by data source.
    rows = _node(100.0, 75, 20.0) + _node(130.0, 75, 19.0)
    prof = compute_profile(_ohlc(rows))
    assert prof is not None and prof.peak_ratio >= 0.9      # flagged ambiguous


def test_single_node_is_not_ambiguous():
    prof = compute_profile(_ohlc(_node(100.0, 150) + _node(120.0, 8, 1.0)))
    assert prof is not None and prof.peak_ratio < 0.95      # one clear POC (SPY-like)
