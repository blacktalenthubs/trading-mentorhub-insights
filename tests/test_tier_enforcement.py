"""Tests for tier enforcement, trial system, and usage limits.

Tests the core tier logic directly — no FastAPI or DB required.
Imports the tier module directly to avoid V1 app.py namespace collision.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Direct import helpers ──
# The project root has app.py (V1 Streamlit) which conflicts with api/app/.
# We import the tier and dependencies modules directly by file path.

_api_dir = Path(__file__).resolve().parents[1] / "api"


def _load_module(name: str, filepath: Path):
    """Load a Python module by file path, bypassing sys.path conflicts."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load tier.py (no dependencies on other app modules)
tier_mod = _load_module("_test_tier", _api_dir / "app" / "tier.py")

# For dependencies, we need to mock the heavy imports (sqlalchemy, jose, etc.)
# but we can test get_user_tier, is_trial_active, trial_days_remaining directly
# since they only use the User mock object — no DB needed.


# ---------------------------------------------------------------------------
# Unit tests for api/app/tier.py
# ---------------------------------------------------------------------------

class TestTierModule:
    def test_tier_rank_ordering(self):
        assert tier_mod.tier_rank("free") < tier_mod.tier_rank("pro")
        assert tier_mod.tier_rank("pro") < tier_mod.tier_rank("premium")
        assert tier_mod.tier_rank("premium") < tier_mod.tier_rank("admin")

    def test_tier_rank_unknown_defaults_to_free(self):
        assert tier_mod.tier_rank("garbage") == tier_mod.tier_rank("free")

    def test_has_access_same_tier(self):
        assert tier_mod.has_access("pro", "pro") is True

    def test_has_access_higher_tier(self):
        assert tier_mod.has_access("premium", "pro") is True

    def test_has_access_lower_tier_denied(self):
        assert tier_mod.has_access("free", "pro") is False

    def test_has_access_admin_has_everything(self):
        assert tier_mod.has_access("admin", "premium") is True

    def test_get_limits_free(self):
        limits = tier_mod.get_limits("free")
        assert limits["watchlist_max"] == 5
        assert limits["ai_queries_per_day"] == 3
        assert limits["ai_scan_alerts_per_day"] == 3
        assert limits["visible_alerts"] == 10
        assert limits["telegram_alerts"] is True
        assert limits["paper_trading"] is False

    def test_get_limits_pro(self):
        limits = tier_mod.get_limits("pro")
        assert limits["watchlist_max"] == 10
        assert limits["ai_queries_per_day"] == 50
        assert limits["ai_scan_alerts_per_day"] is None  # unlimited
        assert limits["visible_alerts"] is None
        assert limits["telegram_alerts"] is True
        assert limits["paper_trading"] is False

    def test_get_limits_premium(self):
        limits = tier_mod.get_limits("premium")
        assert limits["watchlist_max"] == 25
        assert limits["ai_queries_per_day"] is None
        assert limits["paper_trading"] is True
        assert limits["backtesting"] is True

    def test_get_limits_unknown_tier_returns_free(self):
        limits = tier_mod.get_limits("nonexistent")
        assert limits["watchlist_max"] == 5

    def test_trial_duration(self):
        assert tier_mod.TRIAL_DURATION_DAYS == 3


# ---------------------------------------------------------------------------
# Unit tests for tier logic in dependencies.py
# We reimplement the pure functions here to avoid the import chain issue.
# These mirror the exact logic from api/app/dependencies.py.
# ---------------------------------------------------------------------------

def get_user_tier(user):
    """Mirror of api/app/dependencies.py:get_user_tier"""
    if not user.subscription:
        return "free"
    sub = user.subscription
    if sub.status == "active" and sub.tier in ("pro", "premium", "admin"):
        return sub.tier
    if sub.tier == "free" and sub.trial_ends_at:
        if datetime.now(timezone.utc) < sub.trial_ends_at.replace(tzinfo=timezone.utc):
            return "pro"
    return "free"


def is_trial_active(user):
    """Mirror of api/app/dependencies.py:is_trial_active"""
    if not user.subscription:
        return False
    sub = user.subscription
    if sub.tier in ("pro", "premium"):
        return False
    if sub.trial_ends_at:
        return datetime.now(timezone.utc) < sub.trial_ends_at.replace(tzinfo=timezone.utc)
    return False


def trial_days_remaining(user):
    """Mirror of api/app/dependencies.py:trial_days_remaining"""
    if not user.subscription or not user.subscription.trial_ends_at:
        return 0
    ends = user.subscription.trial_ends_at.replace(tzinfo=timezone.utc)
    remaining = (ends - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        return 0
    return max(1, int(remaining / 86400) + 1)


def _make_user(tier="free", status="active", trial_ends_at=None):
    """Create a mock User with a mock Subscription."""
    user = MagicMock()
    sub = MagicMock()
    sub.tier = tier
    sub.status = status
    sub.trial_ends_at = trial_ends_at
    user.subscription = sub
    user.id = 1
    return user


class TestGetUserTier:
    def test_free_user_no_trial(self):
        user = _make_user(tier="free", trial_ends_at=None)
        assert get_user_tier(user) == "free"

    def test_pro_user(self):
        user = _make_user(tier="pro")
        assert get_user_tier(user) == "pro"

    def test_premium_user(self):
        user = _make_user(tier="premium")
        assert get_user_tier(user) == "premium"

    def test_free_user_with_active_trial(self):
        trial_end = datetime.now(timezone.utc) + timedelta(days=2)
        trial_end_naive = trial_end.replace(tzinfo=None)
        user = _make_user(tier="free", trial_ends_at=trial_end_naive)
        assert get_user_tier(user) == "pro"

    def test_free_user_with_expired_trial(self):
        trial_end = datetime.now(timezone.utc) - timedelta(days=1)
        trial_end_naive = trial_end.replace(tzinfo=None)
        user = _make_user(tier="free", trial_ends_at=trial_end_naive)
        assert get_user_tier(user) == "free"

    def test_no_subscription(self):
        user = MagicMock()
        user.subscription = None
        assert get_user_tier(user) == "free"

    def test_canceled_subscription(self):
        user = _make_user(tier="pro", status="canceled")
        assert get_user_tier(user) == "free"

    def test_premium_not_blocked_by_require_pro_logic(self):
        """Regression: old require_pro checked `!= 'pro'` which blocked premium."""
        assert tier_mod.has_access("premium", "pro") is True

    def test_admin_is_highest(self):
        user = _make_user(tier="admin")
        assert get_user_tier(user) == "admin"


class TestTrialHelpers:
    def test_is_trial_active_during_trial(self):
        trial_end = datetime.now(timezone.utc) + timedelta(days=2)
        user = _make_user(tier="free", trial_ends_at=trial_end.replace(tzinfo=None))
        assert is_trial_active(user) is True

    def test_is_trial_active_after_expiry(self):
        trial_end = datetime.now(timezone.utc) - timedelta(hours=1)
        user = _make_user(tier="free", trial_ends_at=trial_end.replace(tzinfo=None))
        assert is_trial_active(user) is False

    def test_is_trial_active_for_paid_user(self):
        user = _make_user(tier="pro")
        assert is_trial_active(user) is False

    def test_is_trial_active_no_subscription(self):
        user = MagicMock()
        user.subscription = None
        assert is_trial_active(user) is False

    def test_trial_days_remaining_3_days_out(self):
        trial_end = datetime.now(timezone.utc) + timedelta(days=2, hours=5)
        user = _make_user(tier="free", trial_ends_at=trial_end.replace(tzinfo=None))
        remaining = trial_days_remaining(user)
        assert remaining == 3

    def test_trial_days_remaining_expired(self):
        trial_end = datetime.now(timezone.utc) - timedelta(days=1)
        user = _make_user(tier="free", trial_ends_at=trial_end.replace(tzinfo=None))
        assert trial_days_remaining(user) == 0

    def test_trial_days_remaining_no_trial(self):
        user = _make_user(tier="free", trial_ends_at=None)
        assert trial_days_remaining(user) == 0

    def test_trial_days_remaining_less_than_1_day(self):
        trial_end = datetime.now(timezone.utc) + timedelta(hours=5)
        user = _make_user(tier="free", trial_ends_at=trial_end.replace(tzinfo=None))
        assert trial_days_remaining(user) == 1

    def test_trial_days_remaining_exactly_1_day(self):
        trial_end = datetime.now(timezone.utc) + timedelta(days=1)
        user = _make_user(tier="free", trial_ends_at=trial_end.replace(tzinfo=None))
        assert trial_days_remaining(user) >= 1


class TestTierLimitIntegrity:
    """Ensure tier limits are consistent and make business sense."""

    def test_free_limits_are_most_restrictive(self):
        free = tier_mod.get_limits("free")
        pro = tier_mod.get_limits("pro")
        assert free["watchlist_max"] < pro["watchlist_max"]
        assert free["ai_queries_per_day"] < pro["ai_queries_per_day"]

    def test_premium_includes_all_pro_features(self):
        pro = tier_mod.get_limits("pro")
        premium = tier_mod.get_limits("premium")
        for key, val in pro.items():
            if val is True:
                assert premium[key] is True or premium[key] is None, (
                    f"Premium should include pro feature: {key}"
                )

    def test_watchlist_limits_ascending(self):
        assert tier_mod.get_limits("free")["watchlist_max"] == 5
        assert tier_mod.get_limits("pro")["watchlist_max"] == 10
        assert tier_mod.get_limits("premium")["watchlist_max"] == 25

    def test_ai_queries_free_is_3(self):
        assert tier_mod.get_limits("free")["ai_queries_per_day"] == 3

    def test_ai_queries_pro_is_50(self):
        assert tier_mod.get_limits("pro")["ai_queries_per_day"] == 50

    def test_ai_scan_alerts_free_is_3(self):
        """Tight free cap — taste the product then convert."""
        assert tier_mod.get_limits("free")["ai_scan_alerts_per_day"] == 3

    def test_ai_scan_alerts_pro_unlimited(self):
        assert tier_mod.get_limits("pro")["ai_scan_alerts_per_day"] is None

    def test_ai_wait_alerts_free_is_3(self):
        """Free users get 3 WAIT alerts/day — taste of AI discipline, not flood."""
        assert tier_mod.get_limits("free")["ai_wait_alerts_per_day"] == 3

    def test_ai_wait_alerts_pro_unlimited(self):
        assert tier_mod.get_limits("pro")["ai_wait_alerts_per_day"] is None

    def test_ai_wait_alerts_premium_unlimited(self):
        assert tier_mod.get_limits("premium")["ai_wait_alerts_per_day"] is None

    def test_ai_queries_premium_unlimited(self):
        assert tier_mod.get_limits("premium")["ai_queries_per_day"] is None

    def test_paper_trading_premium_only(self):
        assert tier_mod.get_limits("free")["paper_trading"] is False
        assert tier_mod.get_limits("pro")["paper_trading"] is False
        assert tier_mod.get_limits("premium")["paper_trading"] is True

    def test_backtesting_premium_only(self):
        assert tier_mod.get_limits("free")["backtesting"] is False
        assert tier_mod.get_limits("pro")["backtesting"] is False
        assert tier_mod.get_limits("premium")["backtesting"] is True

    def test_telegram_enabled_for_all_tiers(self):
        """All tiers get Telegram; free users are capped via ai_scan_alerts_per_day."""
        assert tier_mod.get_limits("free")["telegram_alerts"] is True
        assert tier_mod.get_limits("pro")["telegram_alerts"] is True
        assert tier_mod.get_limits("premium")["telegram_alerts"] is True

    def test_visible_alerts_free_is_10(self):
        """Launch tuning: free UI shows 10 alerts (was 3) so users see the product working."""
        assert tier_mod.get_limits("free")["visible_alerts"] == 10

    def test_visible_alerts_pro_unlimited(self):
        assert tier_mod.get_limits("pro")["visible_alerts"] is None

    def test_all_tiers_have_same_keys(self):
        free_keys = set(tier_mod.get_limits("free").keys())
        pro_keys = set(tier_mod.get_limits("pro").keys())
        premium_keys = set(tier_mod.get_limits("premium").keys())
        assert free_keys == pro_keys == premium_keys
