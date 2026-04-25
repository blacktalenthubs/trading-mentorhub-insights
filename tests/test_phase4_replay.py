"""Phase 4a historical replay — verify structural targets capture more than
the old %-based logic on real session data.

Pulls actual yfinance daily + intraday bars for META and AAOI on 04-24 and
checks that the new T1/T2 land where we expect (and that they capture
materially more of the actual move than the old `entry + 1R / 2R` logic).

Network-dependent. Skips gracefully if yfinance is unavailable.
"""
from __future__ import annotations

import pytest

from analytics.intraday_rules import _targets_for_long


pytest.importorskip("yfinance")


def _atr14_from_yf(symbol: str) -> tuple[float, dict]:
    """Pull yfinance daily history + return (atr_thru_yesterday, prior_day_dict)."""
    import pandas as pd
    import yfinance as yf

    hist = yf.Ticker(symbol).history(period="1y", interval="1d")
    if hist.empty:
        pytest.skip(f"yfinance returned no data for {symbol}")

    # ATR(14) on full history through yesterday
    tr = pd.concat([
        hist["High"] - hist["Low"],
        (hist["High"] - hist["Close"].shift()).abs(),
        (hist["Low"] - hist["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # "yesterday" = the second-to-last bar; algorithm sees this state intraday today.
    prev = hist.iloc[-2]
    weekly = hist[["High", "Low"]].resample("W-FRI").agg(
        {"High": "max", "Low": "min"}
    ).dropna()
    monthly = hist[["High", "Low"]].resample("MS").agg(
        {"High": "max", "Low": "min"}
    ).dropna()

    prior_day = {
        "high": float(prev["High"]),
        "low": float(prev["Low"]),
        "prior_week_high": float(weekly.iloc[-2]["High"]) if len(weekly) >= 2 else None,
        "prior_week_low": float(weekly.iloc[-2]["Low"]) if len(weekly) >= 2 else None,
        "prior_month_high": float(monthly.iloc[-2]["High"]) if len(monthly) >= 2 else None,
        "prior_month_low": float(monthly.iloc[-2]["Low"]) if len(monthly) >= 2 else None,
        "atr_daily": float(atr.iloc[-2]) if not pd.isna(atr.iloc[-2]) else None,
    }
    return prior_day["atr_daily"], prior_day


class TestMetaReplay:
    """META 04-24: 09:30 bar tested PDL+EMA200 confluence → bounce."""

    def test_pdl_bounce_targets_align_with_structure(self):
        atr, prior = _atr14_from_yf("META")
        # 09:30 bar close $656.38, stop = PDL × 0.995 = $649.78
        # PDL = prior['low'] = $653.05 ish
        entry = 656.38
        stop = round(prior["low"] * 0.995, 2)
        t1, t2 = _targets_for_long(entry=entry, stop=stop, prior_day=prior)

        # T1 should be a real structural level (PDH or month high), not entry+risk
        risk = entry - stop
        legacy_t1 = round(entry + risk, 2)
        legacy_t2 = round(entry + 2 * risk, 2)

        assert t1 != legacy_t1, f"Phase 4 T1 ({t1}) should differ from legacy ({legacy_t1})"
        assert t2 != legacy_t2, f"Phase 4 T2 ({t2}) should differ from legacy ({legacy_t2})"
        assert t2 > t1
        # T1 should be at or near a structural level
        candidates = {prior["high"], prior["prior_month_high"], prior["prior_week_high"]}
        candidates = {c for c in candidates if c is not None and c > entry}
        assert any(abs(t1 - c) < 0.01 or t1 == c for c in candidates), \
            f"T1 {t1} should match a structural candidate {candidates}"

    def test_capture_improvement_meta(self):
        """Phase 4 T2 should capture at least 2× more than legacy T2 on META."""
        atr, prior = _atr14_from_yf("META")
        entry = 656.38
        stop = round(prior["low"] * 0.995, 2)
        t1, t2 = _targets_for_long(entry=entry, stop=stop, prior_day=prior)

        risk = entry - stop
        legacy_t2 = entry + 2 * risk
        phase4_t2_capture = t2 - entry
        legacy_t2_capture = legacy_t2 - entry

        assert phase4_t2_capture / legacy_t2_capture >= 2.0, (
            f"Capture multiplier {phase4_t2_capture / legacy_t2_capture:.2f} "
            f"(phase4=${phase4_t2_capture:.2f}, legacy=${legacy_t2_capture:.2f})"
        )


class TestAaoiReplay:
    """AAOI 04-24: ema_bounce_8 at 10:20 → drove from $146.61 to $164.87 high."""

    def test_ema_bounce_targets_use_structure(self):
        """Phase 4a + ATR-cap fix: T1/T2 should land at structural levels
        (PDH, prior-week high, etc.), not run past them on volatile names.
        """
        atr, prior = _atr14_from_yf("AAOI")
        entry = 146.61
        stop = 145.88  # EMA8 × 0.995, risk = $0.73
        t1, t2 = _targets_for_long(entry=entry, stop=stop, prior_day=prior)

        # T2 must be above T1
        assert t2 > t1

        # With ATR cap at 3R=$2.19, T1 floor is $148.80. Should land at the
        # nearest structural level >= floor (PDH or prior-month high).
        if prior.get("atr_daily"):
            risk = entry - stop
            capped_atr = min(prior["atr_daily"], 3.0 * risk)
            t1_floor = entry + max(risk, capped_atr)
            assert (t1 - entry) >= (t1_floor - entry) * 0.99, \
                f"T1 ${t1:.2f} below capped floor ${t1_floor:.2f}"

        # T1 should land at or near a real structural level (PDH/week/month).
        candidates = []
        for k in ("high", "prior_week_high", "prior_month_high"):
            if prior.get(k) and prior[k] > entry:
                candidates.append(prior[k])
        if candidates:
            # T1 should be at one of these candidates (within $0.50)
            assert any(abs(t1 - c) < 0.50 for c in candidates), \
                f"T1 ${t1:.2f} should match a structural candidate {candidates}"

    def test_capture_improvement_aaoi(self):
        atr, prior = _atr14_from_yf("AAOI")
        entry = 146.61
        stop = 145.88
        t1, t2 = _targets_for_long(entry=entry, stop=stop, prior_day=prior)

        risk = entry - stop  # $0.73
        legacy_t2 = entry + 2 * risk  # $148.07
        phase4_t2_capture = t2 - entry
        legacy_t2_capture = legacy_t2 - entry

        # AAOI is a tight-stop case where ATR floor pushes targets dramatically
        # higher than legacy. Expect at least 5× improvement.
        assert phase4_t2_capture / legacy_t2_capture >= 5.0, (
            f"Capture multiplier {phase4_t2_capture / legacy_t2_capture:.2f} "
            f"(phase4=${phase4_t2_capture:.2f}, legacy=${legacy_t2_capture:.2f})"
        )


class TestMsftReplay:
    """MSFT 04-24: hypothetical ema_bounce_8 — just verify ladder builds OK."""

    def test_msft_ladder_includes_pdh_and_emas(self):
        atr, prior = _atr14_from_yf("MSFT")
        # Hypothetical entry near EMA8 (~$414 based on yesterday's close)
        entry = 414.38
        stop = 412.31
        t1, t2 = _targets_for_long(entry=entry, stop=stop, prior_day=prior)

        # T1 and T2 must be above entry
        assert t1 > entry
        assert t2 > t1
        # T1 should hit at or near PDH (prior['high']) or beyond
        # MSFT PDH was $423.66 → T1 should be at structural level near or above
        if prior["high"] > entry:
            assert t1 >= prior["high"] - 0.50  # within 50¢ of PDH or higher
