"""Tests for deterministic swing-trade qualification (spec 56).

Two regimes — BOUNCE (SPY above its 21 EMA) and RSI (SPY below it). Pure-function
tests on fixture daily series — no DB, no network, no LLM.
"""

from __future__ import annotations

import pandas as pd

from analytics.swing_quality import (
    REGIME_BOUNCE,
    REGIME_RSI,
    SwingQualification,
    SwingRuleHit,
    _ema,
    evaluate_swing_quality,
    spy_regime,
    swing_exit_triggered,
)


# --- fixture helpers -------------------------------------------------------


def _df(closes, lows=None, highs=None, opens=None) -> pd.DataFrame:
    """Build a daily OHLC DataFrame from a list of closes."""
    rows = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = opens[i] if opens is not None else prev
        lo = lows[i] if lows is not None else min(o, c) * 0.997
        hi = highs[i] if highs is not None else max(o, c) * 1.003
        rows.append({"open": o, "high": hi, "low": lo, "close": c})
        prev = c
    return pd.DataFrame(rows)


def _append(df: pd.DataFrame, open_, high, low, close) -> pd.DataFrame:
    bar = {"open": open_, "high": high, "low": low, "close": close}
    return pd.concat([df, pd.DataFrame([bar])], ignore_index=True)


def _rising(n=260, start=100.0, step=0.6) -> pd.DataFrame:
    return _df([start + i * step for i in range(n)])


def _falling(n=260, start=320.0, step=0.6) -> pd.DataFrame:
    return _df([start - i * step for i in range(n)])


# --- spy_regime ------------------------------------------------------------


def test_spy_above_21ema_is_bounce_regime():
    assert spy_regime(_rising(120)) == REGIME_BOUNCE


def test_spy_below_21ema_is_rsi_regime():
    assert spy_regime(_falling(120)) == REGIME_RSI


def test_spy_regime_defaults_to_bounce_without_history():
    assert spy_regime(_rising(5)) == REGIME_BOUNCE


# --- swing_exit_triggered --------------------------------------------------


def test_exit_fires_on_close_below_stop():
    assert swing_exit_triggered(100.0, 99.99) is True


def test_exit_does_not_fire_at_or_above_stop():
    assert swing_exit_triggered(100.0, 100.0) is False
    assert swing_exit_triggered(100.0, 105.0) is False


# --- BOUNCE regime: key-MA defense & reclaim ------------------------------


def test_bounce_hold_qualifies():
    """A stock in a bullish MA stack whose day low tags a key MA and closes
    back above it qualifies — entry = the MA, stop = the day's low."""
    base = _rising(n=260)
    ema50 = float(_ema(base["close"], 50).iloc[-1])
    df = _append(base, open_=ema50 * 1.01, high=ema50 * 1.012,
                 low=ema50 * 0.99, close=ema50 * 1.004)
    q = evaluate_swing_quality("TEST", df, REGIME_BOUNCE)
    assert q is not None
    assert q.mode == "bounce"
    assert q.direction == "LONG"
    assert any(h.rule in ("ma_hold", "ma_reclaim") for h in q.rules)
    assert any("50" in h.level for h in q.rules)
    # Entry is typed by the defended MA — a 50-period MA here.
    assert "50" in q.entry_level
    # Entry sits at the MA (below the close); stop is the day's low.
    assert q.stop < q.entry < q.close
    assert q.stop == round(ema50 * 0.99, 2)


def test_bounce_reclaim_qualifies():
    """Prior close below a key MA, current bar tags it and closes back above."""
    base = _rising(n=260)
    ema50 = float(_ema(base["close"], 50).iloc[-1])
    df = _append(base, open_=ema50, high=ema50 * 1.002,
                 low=ema50 * 0.985, close=ema50 * 0.99)          # bar A — below
    ema50b = float(_ema(df["close"], 50).iloc[-1])
    df = _append(df, open_=ema50b * 0.995, high=ema50b * 1.012,
                 low=ema50b * 0.99, close=ema50b * 1.006)        # bar B — reclaim
    q = evaluate_swing_quality("TEST", df, REGIME_BOUNCE)
    assert q is not None
    assert any(h.rule == "ma_reclaim" for h in q.rules)


def test_bounce_close_below_tagged_ma_does_not_qualify():
    """The day's low tags a MA but the candle closes below it → no qualify."""
    base = _rising(n=260)
    ema50 = float(_ema(base["close"], 50).iloc[-1])
    df = _append(base, open_=ema50 * 1.0, high=ema50 * 1.005,
                 low=ema50 * 0.985, close=ema50 * 0.99)  # closed below the MA
    assert evaluate_swing_quality("TEST", df, REGIME_BOUNCE) is None


def test_bounce_rejects_inverted_ma_stack():
    """A downtrend — MAs stacked above price (50 < 100 < 200) — never qualifies,
    even when a bar closes above a MA. (META / NFLX case.)"""
    base = _falling(n=260)
    ema50 = float(_ema(base["close"], 50).iloc[-1])
    df = _append(base, open_=ema50 * 0.99, high=ema50 * 1.03,
                 low=ema50 * 0.98, close=ema50 * 1.02)
    assert evaluate_swing_quality("TEST", df, REGIME_BOUNCE) is None


def test_bounce_multi_ma_merges_into_one_candidate():
    """A deep pullback that tags several key MAs → one candidate, many hits."""
    base = _rising(n=260)
    ema100 = float(_ema(base["close"], 100).iloc[-1])
    ema50 = float(_ema(base["close"], 50).iloc[-1])
    df = _append(base, open_=ema50 * 1.01, high=ema50 * 1.02,
                 low=ema100 * 0.99, close=ema50 * 1.004)
    q = evaluate_swing_quality("TEST", df, REGIME_BOUNCE)
    assert q is not None
    assert len(q.rules) >= 2
    assert q.symbol == "TEST"


def test_bounce_too_few_bars_returns_none():
    """The 200 MA needs history — a short series cannot qualify in bounce mode."""
    assert evaluate_swing_quality("TEST", _rising(50), REGIME_BOUNCE) is None


# --- RSI regime: oversold recovery ----------------------------------------


def _rsi_recovery_series() -> pd.DataFrame:
    closes = [100.0] * 60
    c = 100.0
    for _ in range(16):           # decline — drives RSI into oversold
        c *= 0.975
        closes.append(c)
    for _ in range(3):            # recovery — lifts RSI back above 30
        c *= 1.035
        closes.append(c)
    return _df(closes)


def test_rsi_recovery_qualifies():
    q = evaluate_swing_quality("TEST", _rsi_recovery_series(), REGIME_RSI)
    assert q is not None
    assert q.mode == "rsi"
    assert any(h.rule == "rsi_recovery" for h in q.rules)
    assert q.entry_level == "RSI 30"
    # RSI mode: entry is the close, stop is the day's low.
    assert q.entry == q.close
    assert q.stop <= q.entry


def test_rsi_still_oversold_does_not_qualify():
    closes = [100.0] * 60
    c = 100.0
    for _ in range(20):           # sustained decline, RSI stays <= 30
        c *= 0.975
        closes.append(c)
    assert evaluate_swing_quality("TEST", _df(closes), REGIME_RSI) is None


# --- regime isolation ------------------------------------------------------


def test_bounce_setup_does_not_qualify_in_rsi_regime():
    """A clean bullish bounce evaluated under the RSI regime → no RSI rule."""
    base = _rising(n=260)
    ema50 = float(_ema(base["close"], 50).iloc[-1])
    df = _append(base, open_=ema50 * 1.01, high=ema50 * 1.012,
                 low=ema50 * 0.99, close=ema50 * 1.004)
    assert evaluate_swing_quality("TEST", df, REGIME_RSI) is None


def test_rsi_setup_does_not_qualify_in_bounce_regime():
    """An oversold-recovery series is a downtrend → fails the bounce stack."""
    assert evaluate_swing_quality("TEST", _rsi_recovery_series(), REGIME_BOUNCE) is None


# --- transparency + determinism -------------------------------------------


def test_summary_names_the_rule():
    q = evaluate_swing_quality("TEST", _rsi_recovery_series(), REGIME_RSI)
    assert q is not None
    assert q.summary.startswith("Swing setup:")
    assert "RSI" in q.summary


def test_entry_stop_targets_ordered():
    base = _rising(n=260)
    ema50 = float(_ema(base["close"], 50).iloc[-1])
    df = _append(base, open_=ema50 * 1.01, high=ema50 * 1.012,
                 low=ema50 * 0.99, close=ema50 * 1.004)
    q = evaluate_swing_quality("TEST", df, REGIME_BOUNCE)
    assert q is not None
    assert q.stop < q.entry < q.target_1 < q.target_2


def test_deterministic():
    base = _rising(n=260)
    ema50 = float(_ema(base["close"], 50).iloc[-1])
    df = _append(base, open_=ema50 * 1.01, high=ema50 * 1.012,
                 low=ema50 * 0.99, close=ema50 * 1.004)
    a = evaluate_swing_quality("TEST", df, REGIME_BOUNCE, session_date="2026-05-21")
    b = evaluate_swing_quality("TEST", df, REGIME_BOUNCE, session_date="2026-05-21")
    assert a == b
    assert isinstance(a, SwingQualification)
    assert all(isinstance(h, SwingRuleHit) for h in a.rules)
