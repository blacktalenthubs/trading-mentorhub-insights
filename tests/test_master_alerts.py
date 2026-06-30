"""Master Alerts — the canonical curated quality set delivered to opt-in users.

A user with `master_alerts` ON is gated by MASTER_ALERT_TYPES instead of their
personal type toggles, so opting in = the platform's whole curated feed, zero-config.
This locks WHICH types are in that set (and that the muted noise stays out).
"""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parent.parent / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.tv_webhook import MASTER_ALERT_TYPES, _is_allowed_alert_type  # noqa: E402


def _ok(t: str) -> bool:
    return _is_allowed_alert_type(t, MASTER_ALERT_TYPES)


def test_quality_core_is_included():
    for t in ("tv_rc_4h_long", "tv_rc_daily_long", "tv_weekly_rc", "tv_monthly_rc",
              "tv_staged_pdl_held", "tv_staged_pdh_break", "tv_gap_up_continuation_long",
              "tv_rsi_oversold", "tv_swing_rsi_30", "tv_monthly_box", "tv_mobo_rch",
              "tv_cml_held", "tv_pml_held", "tv_weekly_10w_reclaim"):
        assert _ok(t), t


def test_muted_noise_is_excluded():
    # the types the admin muted this session — must NOT be in the curated feed
    for t in ("tv_rc_daily_hrec", "tv_rc_4h_hrec", "tv_reclaim_long",
              "tv_rsi_70", "tv_ma_bounce_long_v3_ema8",
              "tv_staged_pdh_rejection", "tv_orl_held", "tv_orh_break"):
        assert not _ok(t), t


def test_kept_ma_bounces_in_excluded_ema8():
    assert _ok("tv_ma_bounce_long_v3_ema21")
    assert _ok("tv_ma_bounce_long_v3_ema50")
    assert _ok("tv_ma_bounce_long_v3_ema200")
    assert not _ok("tv_ma_bounce_long_v3_ema8")   # the one MA the admin turned off


def test_obsolete_short_excluded_structural_short_kept():
    assert _ok("tv_staged_pdl_break")             # the one kept structural short
    assert not _ok("tv_rc_4h_short")              # retired short
