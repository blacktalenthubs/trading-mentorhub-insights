"""Crypto prior_day must be YESTERDAY's candle, not today's partial one.

Regression for the 2026-09-05 BTC alert: the scanner reported a prior-day high of
$79,754 — roughly the CURRENT session's high — against a real prior-day high of
$81,426. `pdh_rejection` then fired the instant price ticked down off its own high.

Cause: Coinbase DAILY candles are bucketed at 00:00 UTC, but
`_fetch_coinbase_candles` converts the index to ET-naive. That shift lands today's
bar on yesterday's ET date (00:00 UTC = 20:00 ET the previous day), so the
"is the last bar today?" test read false and the picker took `hist.iloc[-1]` —
today's partial bar — as the prior day.

These tests exercise the date arithmetic directly, so they need no network.
"""

from __future__ import annotations

import pandas as pd
import pytest

ET = "America/New_York"


def _coinbase_style_index(utc_days: list[str]) -> pd.DatetimeIndex:
    """UTC-bucketed daily candles, converted to ET-naive the way the fetcher does."""
    idx = pd.to_datetime([f"{d} 00:00:00" for d in utc_days], utc=True)
    return idx.tz_convert(ET).tz_localize(None)


def _pick(index: pd.DatetimeIndex, now_utc: pd.Timestamp) -> int:
    """The fixed bar-pick: -2 when the newest bar is today's partial, else -1."""
    et_off = now_utc.tz_convert(ET).utcoffset()
    today_utc = now_utc.tz_convert("UTC").normalize().tz_localize(None)
    bar_utc_date = (index[-1] - et_off).normalize()
    return -2 if bar_utc_date >= today_utc else -1


def _pick_old(index: pd.DatetimeIndex, now_utc: pd.Timestamp) -> int:
    """The buggy version — compared the ET-shifted date against ET today."""
    today_et = now_utc.tz_convert(ET).normalize().tz_localize(None)
    return -2 if index[-1].normalize() >= today_et else -1


class TestCryptoPriorDayBarPick:
    def test_todays_partial_bar_is_not_the_prior_day(self):
        """The BTC case: Sept 5 UTC bar exists and must NOT be the prior day."""
        idx = _coinbase_style_index(["2026-09-03", "2026-09-04", "2026-09-05"])
        now = pd.Timestamp("2026-09-05T17:47:00Z")  # 13:47 ET, mid-session
        assert _pick(idx, now) == -2, "must skip today's partial bar"

    def test_the_old_logic_reproduced_the_bug(self):
        """Proves the cause rather than asserting the fix in a vacuum."""
        idx = _coinbase_style_index(["2026-09-03", "2026-09-04", "2026-09-05"])
        now = pd.Timestamp("2026-09-05T17:47:00Z")
        assert _pick_old(idx, now) == -1, "old logic took today's bar — the bug"
        assert _pick(idx, now) != _pick_old(idx, now)

    def test_completed_history_uses_the_newest_bar(self):
        """No bar for today yet → the newest bar IS the prior day."""
        idx = _coinbase_style_index(["2026-09-03", "2026-09-04"])
        now = pd.Timestamp("2026-09-05T17:47:00Z")
        assert _pick(idx, now) == -1

    @pytest.mark.parametrize("now_iso", [
        "2026-09-05T00:30:00Z",  # just after the UTC bucket opens
        "2026-09-05T12:00:00Z",
        "2026-09-05T23:59:00Z",  # just before it closes
    ])
    def test_holds_all_day(self, now_iso):
        """Whenever we poll during the UTC day, today's bar stays excluded."""
        idx = _coinbase_style_index(["2026-09-03", "2026-09-04", "2026-09-05"])
        assert _pick(idx, pd.Timestamp(now_iso)) == -2

    def test_holds_in_winter_offset(self):
        """EST is UTC-5 — the offset is read live, so January works too."""
        idx = _coinbase_style_index(["2026-01-13", "2026-01-14", "2026-01-15"])
        now = pd.Timestamp("2026-01-15T18:00:00Z")
        assert _pick(idx, now) == -2
