"""Tier definitions and feature limits — single source of truth.

All tier-based gating across the app reads from this module.
"""

from __future__ import annotations

from enum import IntEnum


class Tier(IntEnum):
    FREE = 0
    COMP = 1    # comped (family/friends): full telegram, limited dashboard AI
    PRO = 2
    PREMIUM = 3
    ADMIN = 99


TIER_MAP: dict[str, Tier] = {
    "free": Tier.FREE,
    "comp": Tier.COMP,
    "pro": Tier.PRO,
    "premium": Tier.PREMIUM,
    "admin": Tier.ADMIN,
}

# None = unlimited
# Two customer-facing tiers: FREE + PRO ($49/mo). `comp` and `admin` stay
# internal-only. `premium` is retained as a legacy/unlimited superset so any
# existing premium subscriber keeps full access (no customer-facing Premium plan).
#
# Gating philosophy — "preview, don't padlock": every feature is reachable on
# FREE; the cap is on volume, depth, freshness, or the alert firehose — never
# hard access. New keys: screener_preview_rows (top-N visible), alerts_min_grade
# (A-only on free), watchlist_groups_max.
TIER_LIMITS: dict[str, dict] = {
    # FREE — 2026-06-01 public-access launch: free tier now matches PRO
    # for every feature except AI. AI features stay locked to vbolofinde
    # via require_ai_access in dependencies.py (hardcoded, not tier-based).
    # When monetization returns, restore the old caps from git history.
    "free": {
        "watchlist_max": None,
        "watchlist_groups_max": None,
        "ai_queries_per_day": 0,         # AI Coach — admin-only
        "ai_scan_alerts_per_day": 0,     # AI-scan pushes — admin-only
        "ai_wait_alerts_per_day": 0,     # WAIT pushes — admin-only
        "swing_alerts_per_day": None,
        "best_setups_per_day": 0,        # AI Best Setups — admin-only
        "telegram_commands_per_day": 50,
        "alert_history_days": None,
        "visible_alerts": None,          # full feed
        "screener_preview_rows": None,   # full screener
        "alerts_min_grade": None,        # every grade
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,         # unlocked
        "eod_review": True,
        "weekly_review": True,
        "performance_analytics": True,   # unlocked
        "pre_trade_check": True,
        "paper_trading": False,
        "backtesting": False,
    },
    # COMP — comped family/friends: unlimited like Pro, internal-only.
    "comp": {
        "watchlist_max": None,
        "watchlist_groups_max": None,
        "ai_queries_per_day": 3,         # dashboard AI Coach limited
        "ai_scan_alerts_per_day": None,
        "ai_wait_alerts_per_day": None,
        "swing_alerts_per_day": None,
        "best_setups_per_day": 20,
        "telegram_commands_per_day": 50,
        "alert_history_days": None,
        "visible_alerts": None,
        "screener_preview_rows": None,
        "alerts_min_grade": None,
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": True,
        "performance_analytics": True,
        "pre_trade_check": True,
        "paper_trading": False,
        "backtesting": False,
    },
    # PRO $49/mo — the whole thing, uncapped (inherits old Premium features).
    "pro": {
        "watchlist_max": None,          # unlimited
        "watchlist_groups_max": None,
        "ai_queries_per_day": 50,
        "ai_scan_alerts_per_day": None,
        "ai_wait_alerts_per_day": None,
        "swing_alerts_per_day": None,
        "best_setups_per_day": 50,      # generous human-uncapped; protects AI cost
        "telegram_commands_per_day": 50,
        "alert_history_days": None,     # full history (no tier above)
        "visible_alerts": None,
        "screener_preview_rows": None,  # full screeners
        "alerts_min_grade": None,       # all grades
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": True,          # weekly AI retrospective
        "performance_analytics": True,
        "pre_trade_check": True,
        "paper_trading": False,
        "backtesting": False,
    },
    # PREMIUM — legacy unlimited superset (no customer-facing plan; keeps any
    # existing premium subscriber whole).
    "premium": {
        "watchlist_max": None,
        "watchlist_groups_max": None,
        "ai_queries_per_day": None,
        "ai_scan_alerts_per_day": None,
        "ai_wait_alerts_per_day": None,
        "swing_alerts_per_day": None,
        "best_setups_per_day": None,
        "telegram_commands_per_day": None,
        "alert_history_days": None,
        "visible_alerts": None,
        "screener_preview_rows": None,
        "alerts_min_grade": None,
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": True,
        "performance_analytics": True,
        "pre_trade_check": True,
        "paper_trading": True,
        "backtesting": True,
    },
    # ADMIN — explicit unlimited entry so admin never falls back to free limits
    # (e.g. the A-grade alert floor). is_admin_user() is the email-based bypass;
    # this covers subscription.tier == "admin".
    "admin": {
        "watchlist_max": None,
        "watchlist_groups_max": None,
        "ai_queries_per_day": None,
        "ai_scan_alerts_per_day": None,
        "ai_wait_alerts_per_day": None,
        "swing_alerts_per_day": None,
        "best_setups_per_day": None,
        "telegram_commands_per_day": None,
        "alert_history_days": None,
        "visible_alerts": None,
        "screener_preview_rows": None,
        "alerts_min_grade": None,
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": True,
        "performance_analytics": True,
        "pre_trade_check": True,
        "paper_trading": True,
        "backtesting": True,
    },
}

TRIAL_DURATION_DAYS = 3


def get_limits(tier: str) -> dict:
    """Return limits dict for a tier string."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


def tier_rank(tier: str) -> int:
    """Return numeric rank for comparison."""
    return TIER_MAP.get(tier, Tier.FREE)


def has_access(user_tier: str, required_tier: str) -> bool:
    """Check if user_tier >= required_tier."""
    return tier_rank(user_tier) >= tier_rank(required_tier)
