"""Scanner redesign Phase 2 — delivery layer.

Covers the three pieces the redesign's delivery depends on:
  1. `_merge_confluence` keeps the collapsed siblings as audit rows and stamps a
     human confluence label on the winner (it used to drop them silently).
  2. `_setup_name` / `_pretty_setup` name the MA-ladder rules like the app feed
     does, so Telegram + the iOS push read "50 SMA Reclaim", not "Ma Reclaim 50".
  3. The SMA 8/21 reclaims are actually wired — enum, ENABLED_RULES and the
     daily MA that feeds them. Phase 1 shipped the enums but nothing else, so
     they could never fire.
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from alert_config import ENABLED_RULES
from alerting.notifier import _pretty_setup
from analytics.intraday_rules import AlertType, check_ma_reclaim

_ROOT = Path(__file__).resolve().parents[1]


def _load_monitor_helpers():
    """Import monitor.py's pure helpers without dragging in the FastAPI app.

    monitor.py imports `app.*` at call time, not import time, but it does live
    under api/ — so put that on the path and load it by file.
    """
    sys.path.insert(0, str(_ROOT / "api"))
    spec = importlib.util.spec_from_file_location(
        "_monitor_under_test", _ROOT / "api" / "app" / "background" / "monitor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Sig:
    """Minimal AlertSignal stand-in — _merge_confluence only reads these."""

    def __init__(self, alert_type, entry, confidence="medium", direction="BUY"):
        self.alert_type = alert_type
        self.entry = entry
        self.confidence = confidence
        self.direction = direction
        self.message = f"{alert_type.value} @ {entry}"


# ── 1. Confluence merge ──────────────────────────────────────────────


def test_merge_keeps_collapsed_siblings_as_audit_rows():
    """SPY 769 double bottom + 21 SMA + 50 EMA → ONE delivered, TWO audit rows."""
    mon = _load_monitor_helpers()
    sigs = [
        _Sig(AlertType.MULTI_DAY_DOUBLE_BOTTOM, 769.21, confidence="high"),
        _Sig(AlertType.MA_RECLAIM_21, 769.18),
        _Sig(AlertType.EMA_RECLAIM_50, 769.30),
    ]
    out = mon._merge_confluence(sigs)

    assert len(out) == 3, "collapsed siblings must survive for the audit trail"
    delivered = [s for s in out if not getattr(s, "_suppressed_reason", None)]
    collapsed = [s for s in out if getattr(s, "_suppressed_reason", None)]
    assert len(delivered) == 1
    assert len(collapsed) == 2
    # The winner is the highest-confidence signal and names every factor.
    winner = delivered[0]
    assert winner.alert_type == AlertType.MULTI_DAY_DOUBLE_BOTTOM
    assert winner.confidence == "high"
    # The message spells the setups out; the (String(50)) label carries the
    # compact factor names.
    assert "confluence ×3" in winner.message
    assert "21 SMA Reclaim" in winner.message
    assert "50 EMA Reclaim" in winner.message
    assert "21 SMA" in winner._confluence_label
    assert "50 EMA" in winner._confluence_label
    assert len(winner._confluence_label) <= 50
    # Every sibling points back at the rule that won.
    for s in collapsed:
        assert s._suppressed_reason == "confluence_collapsed:multi_day_double_bottom"


def test_confluence_label_fits_the_column():
    """Alert.confluence_label is String(50) — never overflow, never cut mid-word."""
    mon = _load_monitor_helpers()
    sigs = [
        _Sig(AlertType.MULTI_DAY_DOUBLE_BOTTOM, 100.00, confidence="high"),
        _Sig(AlertType.MA_RECLAIM_21, 100.01),
        _Sig(AlertType.EMA_RECLAIM_50, 100.02),
        _Sig(AlertType.EMA_RECLAIM_100, 100.03),
        _Sig(AlertType.MA_RECLAIM_200, 100.04),
    ]
    winner = [s for s in mon._merge_confluence(sigs)
              if not getattr(s, "_suppressed_reason", None)][0]
    label = winner._confluence_label
    assert len(label) <= 50
    # Too many factors to name → a count, not a truncated list.
    assert label == "×5 at $100.00"


def test_lone_entry_passes_through_unlabelled():
    """A single entry is not a confluence — no label, no suppression."""
    mon = _load_monitor_helpers()
    sigs = [_Sig(AlertType.MA_RECLAIM_50, 250.00)]
    out = mon._merge_confluence(sigs)
    assert out == sigs
    assert getattr(out[0], "_confluence_label", None) is None
    assert getattr(out[0], "_suppressed_reason", None) is None


def test_entries_at_different_levels_do_not_merge():
    """0.2% band — a double bottom at 769 and a reclaim at 800 are two trades."""
    mon = _load_monitor_helpers()
    sigs = [
        _Sig(AlertType.MULTI_DAY_DOUBLE_BOTTOM, 769.21),
        _Sig(AlertType.MA_RECLAIM_50, 800.00),
    ]
    out = mon._merge_confluence(sigs)
    assert all(not getattr(s, "_suppressed_reason", None) for s in out)
    assert all(getattr(s, "_confluence_label", None) is None for s in out)


# ── 2. Human setup names (feed / Telegram / push parity) ─────────────


def test_ladder_rules_get_human_names():
    assert _pretty_setup("ma_reclaim_50") == "50 SMA Reclaim"
    assert _pretty_setup("ema_reclaim_21") == "21 EMA Reclaim"
    assert _pretty_setup("ma_reclaim_8") == "8 SMA Reclaim"
    assert _pretty_setup("ema_bounce_200") == "200 EMA Bounce"
    # Prefixed TV variants resolve the same way.
    assert _pretty_setup("tv_ma_reclaim_100") == "100 SMA Reclaim"


def test_setup_name_helper_matches_notifier():
    mon = _load_monitor_helpers()
    assert mon._setup_name("ema_reclaim_8") == "8 EMA Reclaim"
    # Unknown rule falls back to title-case rather than raising.
    assert mon._setup_name("some_new_rule") == "Some New Rule"


# ── 3. SMA 8/21 are wired end to end ─────────────────────────────────


def test_sma_8_21_reclaims_are_enabled():
    """Phase 1 added the enums; without these they could never fire."""
    assert "ma_reclaim_8" in ENABLED_RULES
    assert "ma_reclaim_21" in ENABLED_RULES


def test_sma_8_21_reclaim_fires():
    """The rule itself works on the 8/21 SMA exactly as on the EMAs."""
    lvl = 150.00
    bars = pd.DataFrame([
        {"Open": 152.0, "High": 153.0, "Low": 151.5, "Close": 152.5, "Volume": 1000},
        {"Open": 152.5, "High": 152.8, "Low": 149.90, "Close": 151.0, "Volume": 1000},
        {"Open": 151.0, "High": 151.5, "Low": 150.8, "Close": 151.2, "Volume": 1000},
    ])
    sig = check_ma_reclaim("AAPL", bars, lvl, "21MA",
                           AlertType.MA_RECLAIM_21, today_open=152.0)
    assert sig is not None
    assert sig.alert_type == AlertType.MA_RECLAIM_21
    assert sig.direction == "BUY"


# ── 4. Feed contract: every admitted type is a Day trade and explains itself ──

# The types web/src/lib/alertFormat.ts::isScannerEntry admits to the feed.
_SCANNER_FEED_TYPES = [
    "ma_reclaim_8", "ma_reclaim_21", "ma_reclaim_50", "ma_reclaim_100", "ma_reclaim_200",
    "ema_reclaim_8", "ema_reclaim_21", "ema_reclaim_50", "ema_reclaim_100", "ema_reclaim_200",
    "prior_day_low_reclaim", "prior_day_high_breakout", "pdh_retest_hold",
    "multi_day_double_bottom",
]


def test_every_scanner_entry_is_a_day_trade():
    """All 16 land in the Day feed — including the 200s, which are NOT swings here."""
    sys.path.insert(0, str(_ROOT / "api"))
    from app.models.alert_type_config import style_for

    for t in _SCANNER_FEED_TYPES:
        assert style_for(t) == "day_trade", f"{t} would land in the {style_for(t)} feed"


def test_every_scanner_entry_has_a_description():
    """A feed card with no explanation subline is the thing this redesign removed."""
    sys.path.insert(0, str(_ROOT / "api"))
    from app.models.alert_type_config import describe_alert_type

    missing = [t for t in _SCANNER_FEED_TYPES if not describe_alert_type(t)]
    assert not missing, f"no plain-English description for: {missing}"


def test_every_feed_type_can_actually_fire():
    """Nothing reaches the feed allow-list that ENABLED_RULES can't produce.

    The allow-list is the redesign's live entry set — no aspirational rules.
    """
    for t in _SCANNER_FEED_TYPES:
        assert t in ENABLED_RULES, f"{t} is in the feed allow-list but can never fire"


def test_daily_data_exposes_sma_8_21():
    """prior_day must carry ma8/ma21 or the ladder pairs are always None."""
    import inspect

    from analytics import intraday_data

    src = inspect.getsource(intraday_data)
    assert 'hist["MA8"]' in src and 'hist["MA21"]' in src
    assert '"ma8"' in src and '"ma21"' in src
