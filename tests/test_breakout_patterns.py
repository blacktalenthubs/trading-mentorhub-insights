"""Breakout pattern scanner — detectors, pre-filter, scoring, orchestration, Today writer.

Fixtures are hand-built synthetic OHLCV frames (tests/patterns_fixtures.py): a good
example of each pattern in both stages plus near-misses that must be rejected.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest

from analytics.indicators import add_derived_columns
from patterns.ascending_triangle import detect_ascending_triangle
from patterns.bull_flag import detect_bull_flag
from patterns.common import STAGE_BREAKOUT, STAGE_FORMING, classify_stage, linear_fit
from patterns.config import DEFAULT_CONFIG, BreakoutConfig, FlatBaseConfig, ScannerConfig, ScoreWeights
from patterns.cup_handle import detect_cup_handle
from patterns.flat_base import detect_flat_base
from patterns.prefilter import FILTER_ORDER, prefilter
from patterns.scoring import reason_for, score_hit
from patterns.screener import detect_all, hit_to_row, prepare_frame, run_scan
from patterns.today_writer import (
    EMPTY_MESSAGE,
    REPORT_KIND,
    build_body,
    count_rows_for_date,
    dedupe_rows,
    order_rows,
    read_today,
    write_csv,
    write_today,
)
from tests import patterns_fixtures as fx

C = DEFAULT_CONFIG
B = C.breakout


def prep(df: pd.DataFrame) -> pd.DataFrame:
    return prepare_frame(df, C)


# ── indicators ───────────────────────────────────────────────────────────────

class TestIndicators:
    def test_adds_every_derived_column(self):
        df = add_derived_columns(fx.base_uptrend(n=420))
        for col in ("sma20", "sma50", "sma200", "sma50_slope", "sma200_slope",
                    "avg_vol_50", "rvol", "atr14", "rsi14", "high_52w", "low_52w"):
            assert col in df.columns, col
            assert pd.notna(df[col].iloc[-1]), col

    def test_slope_is_pct_change_over_10_bars(self):
        df = add_derived_columns(fx.base_uptrend(n=420))
        s = df["sma200"]
        expected = (s.iloc[-1] - s.iloc[-11]) / s.iloc[-11]
        assert df["sma200_slope"].iloc[-1] == pytest.approx(expected)
        assert df["sma200_slope"].iloc[-1] > 0

    def test_rvol_is_volume_over_avg50(self):
        df = add_derived_columns(fx.base_uptrend(n=420))
        assert df["rvol"].iloc[-1] == pytest.approx(df["Volume"].iloc[-1] / df["Volume"].iloc[-50:].mean())

    def test_missing_column_raises(self):
        with pytest.raises(ValueError):
            add_derived_columns(pd.DataFrame({"Close": [1, 2, 3]}))


# ── pre-filter ───────────────────────────────────────────────────────────────

class TestPrefilter:
    def test_healthy_uptrend_passes(self):
        assert prefilter(prep(fx.base_uptrend(n=420)), C.prefilter) is None

    def test_liquidity_gate(self):
        df = fx.base_uptrend(n=420)
        df["Volume"] = 100_000.0
        assert prefilter(prep(df), C.prefilter) == "liquidity"
        df = fx.base_uptrend(n=420, start=2.0, end=8.0)
        assert prefilter(prep(df), C.prefilter) == "liquidity"

    def test_below_sma200_gate(self):
        df = fx.base_uptrend(n=420)
        df.loc[df.index[-1], "Close"] = 60.0  # far under the 200 SMA
        assert prefilter(prep(df), C.prefilter) == "above_sma200"

    def test_falling_sma200_gate(self):
        df = fx.base_uptrend(n=420, start=100.0, end=50.0)  # downtrend
        df.loc[df.index[-1], "Close"] = 200.0                # pop above the MA on the last bar
        assert prefilter(prep(df), C.prefilter) == "sma200_rising"

    def test_far_from_52w_high_gate(self):
        df = fx.base_uptrend(n=420)
        # spike a 52w high the close is >25% under, while staying above a rising 200 SMA
        df.loc[df.index[-30], "High"] = 200.0
        assert prefilter(prep(df), C.prefilter) == "near_52w_high"

    def test_too_close_to_52w_low_gate(self):
        df = fx.base_uptrend(n=420, start=90.0, end=100.0)  # only +11% off the low
        assert prefilter(prep(df), C.prefilter) == "off_52w_low"

    def test_filter_order_is_stable(self):
        assert FILTER_ORDER == ("liquidity", "above_sma200", "sma200_rising", "near_52w_high", "off_52w_low")


# ── shared breakout confirmation ─────────────────────────────────────────────

class TestClassifyStage:
    def _frame(self, close, open_, high, low, rvol):
        df = pd.DataFrame({"Open": [open_], "High": [high], "Low": [low], "Close": [close], "Volume": [1.0]})
        df["rvol"] = rvol
        return df

    def test_confirmed_breakout(self):
        assert classify_stage(self._frame(102, 99, 102.5, 98.5, 2.0), 100, 90, B) == (STAGE_BREAKOUT, True, 2.0)

    def test_low_volume_is_not_a_breakout(self):
        stage, ok, rvol = classify_stage(self._frame(102, 99, 102.5, 98.5, 1.2), 100, 90, B)
        assert stage == STAGE_FORMING and ok is False and rvol == 1.2

    def test_upper_wick_is_not_a_breakout(self):
        stage, ok, _ = classify_stage(self._frame(100.5, 99, 106, 98.5, 2.5), 100, 90, B)
        assert stage == STAGE_FORMING and ok is True

    def test_down_bar_is_not_a_breakout(self):
        stage, _, _ = classify_stage(self._frame(101, 103, 103.5, 100.9, 2.5), 100, 90, B)
        assert stage == STAGE_FORMING

    def test_extended_is_rejected(self):
        assert classify_stage(self._frame(110, 99, 110.5, 98.5, 3.0), 100, 90, B) is None

    def test_below_stop_is_rejected(self):
        assert classify_stage(self._frame(85, 88, 88.5, 84, 0.5), 100, 90, B) is None


# ── Pattern 1: cup and handle ────────────────────────────────────────────────

class TestCupHandle:
    def test_forming(self):
        hit = detect_cup_handle(prep(fx.cup_handle()), C.cup_handle, B, "CUP")
        assert hit is not None
        assert hit.stage == STAGE_FORMING and hit.volume_ok is False
        assert 15 <= hit.base_depth_pct <= 35
        assert hit.suggested_stop < hit.buy_point
        assert hit.last_close <= hit.buy_point
        assert hit.metrics["handle_vol_ratio"] < 1.0

    def test_breakout(self):
        hit = detect_cup_handle(prep(fx.cup_handle(with_breakout=True)), C.cup_handle, B, "CUP")
        assert hit is not None
        assert hit.stage == STAGE_BREAKOUT and hit.volume_ok and hit.rvol >= B.min_rvol
        assert hit.last_close > hit.buy_point

    def test_rejects_v_bottom(self):
        assert detect_cup_handle(prep(fx.cup_handle(v_shape=True)), C.cup_handle, B) is None

    def test_rejects_too_deep(self):
        assert detect_cup_handle(prep(fx.cup_handle(depth=0.45)), C.cup_handle, B) is None

    def test_rejects_too_shallow(self):
        assert detect_cup_handle(prep(fx.cup_handle(depth=0.08)), C.cup_handle, B) is None

    def test_rejects_handle_without_volume_dryup(self):
        assert detect_cup_handle(prep(fx.cup_handle(handle_vol=1_500_000)), C.cup_handle, B) is None

    def test_rejects_handle_too_deep(self):
        assert detect_cup_handle(prep(fx.cup_handle(handle_depth=0.22)), C.cup_handle, B) is None

    def test_rejects_handle_too_long(self):
        assert detect_cup_handle(prep(fx.cup_handle(handle_bars=20)), C.cup_handle, B) is None

    def test_rejects_short_cup(self):
        assert detect_cup_handle(prep(fx.cup_handle(cup_bars=20)), C.cup_handle, B) is None


# ── Pattern 2: flat base ─────────────────────────────────────────────────────

class TestFlatBase:
    def test_forming(self):
        hit = detect_flat_base(prep(fx.flat_base()), C.flat_base, B, "FB")
        assert hit is not None
        assert hit.stage == STAGE_FORMING
        assert hit.base_depth_pct <= 15
        assert 25 <= hit.base_length_days <= 60
        assert hit.metrics["vol_ratio"] < 1.0 and hit.metrics["range_ratio"] <= 1.0
        assert hit.metrics["prior_advance"] >= 0.20

    def test_breakout(self):
        hit = detect_flat_base(prep(fx.flat_base(with_breakout=True)), C.flat_base, B, "FB")
        assert hit is not None and hit.stage == STAGE_BREAKOUT and hit.volume_ok

    def test_weak_volume_breakout_stays_forming(self):
        hit = detect_flat_base(prep(fx.flat_base(weak_breakout=True)), C.flat_base, B, "FB")
        assert hit is not None
        assert hit.stage == STAGE_FORMING and hit.volume_ok is False
        assert hit.last_close > hit.buy_point
        assert "unconfirmed" in reason_for(hit)

    def test_rejects_too_deep(self):
        assert detect_flat_base(prep(fx.flat_base(lo1=82.0, lo2=83.0)), C.flat_base, B) is None

    def test_rejects_without_prior_advance(self):
        assert detect_flat_base(prep(fx.flat_base(prior_advance=False)), C.flat_base, B) is None

    def test_rejects_widening_range(self):
        assert detect_flat_base(prep(fx.flat_base(lo1=100.5, hi1=102.0, lo2=98.0, hi2=102.0)), C.flat_base, B) is None

    def test_rejects_expanding_volume(self):
        assert detect_flat_base(prep(fx.flat_base(vol1=800_000, vol2=1_200_000)), C.flat_base, B) is None

    def test_does_not_swallow_prior_advance(self):
        """The window must start where price first tags the top, not 60 bars back."""
        hit = detect_flat_base(prep(fx.flat_base(base_bars=30)), C.flat_base, B, "FB")
        assert hit is not None and hit.base_length_days <= 36
        assert hit.suggested_stop > 97.0


# ── Pattern 3: ascending triangle ────────────────────────────────────────────

class TestAscendingTriangle:
    def test_forming(self):
        hit = detect_ascending_triangle(prep(fx.ascending_triangle()), C.ascending_triangle, B, "TRI")
        assert hit is not None
        assert hit.stage == STAGE_FORMING
        assert hit.metrics["touches"] >= 3
        assert hit.metrics["lows_r2"] >= 0.6
        assert hit.buy_point == pytest.approx(100.2, abs=0.5)
        assert hit.suggested_stop == pytest.approx(98.0, abs=0.5)  # last swing low

    def test_breakout(self):
        hit = detect_ascending_triangle(prep(fx.ascending_triangle(with_breakout=True)), C.ascending_triangle, B, "TRI")
        assert hit is not None and hit.stage == STAGE_BREAKOUT and hit.volume_ok

    def test_rejects_flat_lows(self):
        df = prep(fx.ascending_triangle(troughs=(90.0, 90.0, 90.0, 90.0)))
        assert detect_ascending_triangle(df, C.ascending_triangle, B) is None

    def test_rejects_falling_lows(self):
        df = prep(fx.ascending_triangle(troughs=(98.0, 96.0, 93.0, 90.0)))
        assert detect_ascending_triangle(df, C.ascending_triangle, B) is None

    def test_rejects_lows_far_from_ceiling(self):
        df = prep(fx.ascending_triangle(troughs=(70.0, 74.0, 78.0, 82.0)))
        assert detect_ascending_triangle(df, C.ascending_triangle, B) is None

    def test_rejects_rising_volume(self):
        df = fx.ascending_triangle()
        n = 40
        df.loc[df.index[-n:], "Volume"] = np.linspace(800_000.0, 1_500_000.0, n)
        assert detect_ascending_triangle(prep(df), C.ascending_triangle, B) is None


# ── Pattern 4: bull flag ─────────────────────────────────────────────────────

class TestBullFlag:
    def test_forming(self):
        hit = detect_bull_flag(prep(fx.bull_flag()), C.bull_flag, B, "FLAG")
        assert hit is not None
        assert hit.stage == STAGE_FORMING
        assert hit.metrics["pole_gain"] >= 0.15
        assert hit.metrics["retracement"] <= 0.5
        assert hit.metrics["flag_rvol"] <= 0.8
        assert hit.metrics["pole_rvol"] >= 1.3

    def test_breakout(self):
        hit = detect_bull_flag(prep(fx.bull_flag(with_breakout=True)), C.bull_flag, B, "FLAG")
        assert hit is not None and hit.stage == STAGE_BREAKOUT and hit.volume_ok

    def test_rejects_70pct_retracement(self):
        assert detect_bull_flag(prep(fx.bull_flag(retrace=0.70)), C.bull_flag, B) is None

    def test_rejects_weak_pole(self):
        assert detect_bull_flag(prep(fx.bull_flag(pole_gain=0.08)), C.bull_flag, B) is None

    def test_rejects_noisy_flag_volume(self):
        assert detect_bull_flag(prep(fx.bull_flag(flag_vol=1_300_000)), C.bull_flag, B) is None

    def test_rejects_pole_without_volume(self):
        assert detect_bull_flag(prep(fx.bull_flag(pole_vol=1_000_000)), C.bull_flag, B) is None


# ── scoring / reason ─────────────────────────────────────────────────────────

class TestScoring:
    def test_score_in_range_and_reason_shape(self):
        df = prep(fx.flat_base(with_breakout=True))
        hit = detect_flat_base(df, C.flat_base, B, "FB")
        score = score_hit(hit, df, C.weights)
        assert 0 <= score <= 100
        r = reason_for(hit)
        assert "flat base" in r and "% deep" in r and "volume contracting" in r
        assert "breakout on" in r and "x volume" in r

    def test_weights_are_tunable(self):
        df = prep(fx.flat_base())
        hit = detect_flat_base(df, C.flat_base, B, "FB")
        only_vol = ScoreWeights(volume_dryup=100, tightness=0, duration=0, trend=0)
        only_trend = ScoreWeights(volume_dryup=0, tightness=0, duration=0, trend=100)
        assert score_hit(hit, df, only_vol) == pytest.approx(100 * hit.metrics["volume_dryup"], abs=0.1)
        assert score_hit(hit, df, only_trend) != score_hit(hit, df, only_vol)

    def test_linear_fit_r2(self):
        slope, _, r2 = linear_fit(np.array([1.0, 2.0, 3.0, 4.0]))
        assert slope == pytest.approx(1.0) and r2 == pytest.approx(1.0)


# ── orchestration ────────────────────────────────────────────────────────────

class TestRunScan:
    def _fetch(self, frames):
        def fetch(sym):
            df = frames[sym]
            if isinstance(df, Exception):
                raise df
            return df
        return fetch

    def test_end_to_end_rows_and_funnel(self):
        frames = {
            "FBO": fx.flat_base(with_breakout=True),
            "FBF": fx.flat_base(),
            "FLG": fx.bull_flag(with_breakout=True),
            "SHORT": fx.base_uptrend(n=120),                  # < 400 bars → skipped, logged
            "ILLIQ": fx.base_uptrend(n=420).assign(Volume=50_000.0),
            "DOWN": fx.base_uptrend(n=420, start=100.0, end=50.0),
            "BOOM": RuntimeError("yahoo down"),
            "EMPTY": pd.DataFrame(),
        }
        res = run_scan(frames.keys(), fetch=self._fetch(frames), session_date="2026-09-25")
        assert res.scanned == 8
        assert "SHORT" in res.skipped and "120 bars" in res.skipped["SHORT"]
        assert "BOOM" in res.skipped and "fetch failed" in res.skipped["BOOM"]
        assert res.skipped["EMPTY"] == "no data"
        assert res.funnel["liquidity"] == 1
        assert res.funnel["above_sma200"] + res.funnel["sma200_rising"] >= 1   # DOWN
        assert res.funnel["passed"] == 3
        tickers = {(r["ticker"], r["stage"]) for r in res.rows}
        assert ("FBO", "breakout") in tickers and ("FBF", "forming") in tickers and ("FLG", "breakout") in tickers

        body = res.body(universe="test")
        assert body["empty"] is False and body["breakouts"] == 2 and body["forming"] == 1
        # breakout rows first, then forming; each by score desc
        stages = [r["stage"] for r in body["rows"]]
        assert stages == sorted(stages, key=lambda s: 0 if s == "breakout" else 1)
        bo_scores = [r["score"] for r in body["rows"] if r["stage"] == "breakout"]
        assert bo_scores == sorted(bo_scores, reverse=True)

    def test_row_payload_fields(self):
        df = prep(fx.flat_base(with_breakout=True))
        hit = detect_all(df, "FB", C)[0]
        row = hit_to_row(hit, df, "2026-09-25T20:30:00+00:00")
        for k in ("ticker", "pattern", "stage", "buy_point", "last_close", "pct_to_buy", "suggested_stop",
                  "risk_pct", "rvol", "volume_ok", "base_depth_pct", "base_length_days", "rsi14",
                  "dist_from_200sma_pct", "score", "reason", "scanned_at"):
            assert k in row, k
        assert row["pct_to_buy"] == pytest.approx((row["buy_point"] - row["last_close"]) / row["last_close"] * 100, abs=0.02)
        assert row["risk_pct"] == pytest.approx((row["last_close"] - row["suggested_stop"]) / row["last_close"] * 100, abs=0.02)
        assert row["dist_from_200sma_pct"] > 0 and 0 <= row["rsi14"] <= 100

    def test_earnings_filter_drops_names_reporting_soon(self, monkeypatch):
        import datetime as dt
        import patterns.screener as scr
        soon = dt.date.today() + dt.timedelta(days=3)
        far = dt.date.today() + dt.timedelta(days=40)
        monkeypatch.setattr(scr, "earnings_calendar", lambda syms: {"SOON": soon, "FAR": far})
        frames = {"SOON": fx.flat_base(with_breakout=True), "FAR": fx.flat_base(with_breakout=True)}
        res = run_scan(frames.keys(), fetch=self._fetch(frames), earnings_filter=True)
        assert "SOON" in res.skipped and "earnings" in res.skipped["SOON"]
        assert [r["ticker"] for r in res.rows] == ["FAR"]
        assert res.rows[0]["days_to_earnings"] == 40

    def test_custom_config_is_honoured(self):
        tight = ScannerConfig(flat_base=FlatBaseConfig(max_depth=0.02))
        frames = {"FB": fx.flat_base()}
        res = run_scan(frames.keys(), cfg=tight, fetch=self._fetch(frames))
        assert not [r for r in res.rows if r["pattern"] == "flat_base"]

    def test_chart_flag_renders_png(self, tmp_path):
        pytest.importorskip("matplotlib")
        frames = {"FB": fx.flat_base(with_breakout=True)}
        res = run_scan(frames.keys(), fetch=self._fetch(frames), chart_dir=str(tmp_path))
        assert res.rows and res.rows[0]["chart_path"]
        assert (tmp_path / "FB_flat_base_breakout.png").exists()


# ── Today tab writer ─────────────────────────────────────────────────────────

@pytest.fixture
def sqlite_db(tmp_path):
    path = tmp_path / "today.db"

    @contextmanager
    def _get_db():
        conn = sqlite3.connect(path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    return _get_db


def _rows(*specs):
    out = []
    for ticker, pattern, stage, score in specs:
        out.append({"ticker": ticker, "pattern": pattern, "stage": stage, "score": score,
                    "buy_point": 100.0, "last_close": 99.0, "suggested_stop": 95.0})
    return out


class TestTodayWriter:
    def test_write_is_idempotent_across_two_runs_same_date(self, sqlite_db):
        d = "2026-09-25"
        body1 = build_body(_rows(("AAA", "flat_base", "forming", 50), ("BBB", "bull_flag", "breakout", 70)),
                           session_date=d, scanned_at="t1", scanned=10)
        write_today(body1, d, db_factory=sqlite_db)
        body2 = build_body(_rows(("AAA", "flat_base", "breakout", 80)), session_date=d, scanned_at="t2", scanned=10)
        write_today(body2, d, db_factory=sqlite_db)

        assert count_rows_for_date(d, db_factory=sqlite_db) == 1     # replaced, not appended
        got = read_today(d, db_factory=sqlite_db)
        assert got["scanned_at"] == "t2"
        assert [(r["ticker"], r["pattern"], r["stage"]) for r in got["rows"]] == [("AAA", "flat_base", "breakout")]
        with sqlite_db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM market_reports WHERE kind = ?", (REPORT_KIND,)).fetchone()[0]
        assert n == 1

    def test_different_dates_keep_separate_rows(self, sqlite_db):
        for d in ("2026-09-24", "2026-09-25"):
            write_today(build_body(_rows(("AAA", "flat_base", "forming", 50)), session_date=d, scanned_at=d, scanned=1), d, db_factory=sqlite_db)
        with sqlite_db() as conn:
            n = conn.execute("SELECT COUNT(*) FROM market_reports WHERE kind = ?", (REPORT_KIND,)).fetchone()[0]
        assert n == 2

    def test_empty_state_marker_replaces_yesterdays_rows(self, sqlite_db):
        d = "2026-09-25"
        write_today(build_body(_rows(("AAA", "flat_base", "forming", 50)), session_date=d, scanned_at="t1", scanned=5), d, db_factory=sqlite_db)
        write_today(build_body([], session_date=d, scanned_at="t2", scanned=5), d, db_factory=sqlite_db)
        got = read_today(d, db_factory=sqlite_db)
        assert got["empty"] is True and got["rows"] == [] and got["message"] == EMPTY_MESSAGE

    def test_body_orders_breakouts_first_then_score(self):
        body = build_body(_rows(("A", "flat_base", "forming", 90), ("B", "bull_flag", "breakout", 40),
                                ("C", "cup_handle", "breakout", 75), ("D", "ascending_triangle", "forming", 60)),
                          session_date="d", scanned_at="t", scanned=4)
        assert [r["ticker"] for r in body["rows"]] == ["C", "B", "A", "D"]
        assert body["breakouts"] == 2 and body["forming"] == 2

    def test_dedupe_keeps_highest_score_per_ticker_pattern(self):
        rows = dedupe_rows(_rows(("A", "flat_base", "forming", 50), ("A", "flat_base", "breakout", 70), ("A", "bull_flag", "forming", 60)))
        assert sorted((r["pattern"], r["score"]) for r in rows) == [("bull_flag", 60), ("flat_base", 70)]

    def test_order_rows_unknown_stage_last(self):
        rows = order_rows(_rows(("A", "x", "weird", 99), ("B", "x", "forming", 1)))
        assert [r["ticker"] for r in rows] == ["B", "A"]

    def test_csv_dump(self, tmp_path):
        p = write_csv(_rows(("A", "flat_base", "breakout", 70)), tmp_path / "out" / "hits.csv")
        text = p.read_text()
        assert text.splitlines()[0].startswith("ticker,pattern,stage")
        assert "A,flat_base,breakout" in text

    def test_body_is_json_serialisable(self):
        body = build_body(_rows(("A", "flat_base", "forming", 50)), session_date="d", scanned_at="t", scanned=1,
                          funnel={"liquidity": 1, "passed": 1}, skipped={"Z": "only 10 bars"})
        json.dumps(body)
