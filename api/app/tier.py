"""Tier definitions and feature limits — single source of truth.

All tier-based gating across the app reads from this module.
"""

from __future__ import annotations

from enum import IntEnum


class Tier(IntEnum):
    FREE = 0
    PRO = 1
    PREMIUM = 2
    ADMIN = 99


TIER_MAP: dict[str, Tier] = {
    "free": Tier.FREE,
    "pro": Tier.PRO,
    "premium": Tier.PREMIUM,
    "admin": Tier.ADMIN,
}

# None = unlimited
TIER_LIMITS: dict[str, dict] = {
    "free": {
        "watchlist_max": 5,
        "ai_queries_per_day": 3,        # AI Coach + CoPilot combined (real per-user AI cost)
        "ai_scan_alerts_per_day": 3,    # LONG/SHORT/RESISTANCE/EXIT — taste, then upgrade pull
        "ai_wait_alerts_per_day": 3,    # WAIT Telegram delivery
        "ai_swing_alerts_per_day": 2,   # Spec 38 — swing alerts for free tier (taste)
        "best_setups_per_day": 1,       # Spec 40 — morning planning scan
        "telegram_commands_per_day": 3, # /spy, /eth, /btc commands (real per-user AI cost)
        "alert_history_days": 0,        # today only
        "visible_alerts": 10,           # UI shows 10 alerts; rest blurred to drive upgrade
        "chart_replay_per_day": 1,
        "telegram_alerts": True,        # let free see alerts (they upgrade for more)
        "premarket_brief": False,
        "eod_review": False,
        "weekly_review": False,
        "performance_analytics": False,
        "pre_trade_check": False,
        "paper_trading": False,
        "backtesting": False,
    },
    "pro": {
        "watchlist_max": 10,
        "ai_queries_per_day": 50,
        "ai_scan_alerts_per_day": None, # unlimited
        "ai_wait_alerts_per_day": None, # unlimited — Pro sees full AI transparency
        "ai_swing_alerts_per_day": None, # unlimited
        "best_setups_per_day": 20,
        "telegram_commands_per_day": 50,
        "alert_history_days": 30,
        "visible_alerts": None,
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": False,
        "performance_analytics": True,
        "pre_trade_check": True,
        "paper_trading": False,
        "backtesting": False,
    },
    "premium": {
        "watchlist_max": 25,
        "ai_queries_per_day": None,     # unlimited
        "ai_scan_alerts_per_day": None,
        "ai_wait_alerts_per_day": None,
        "ai_swing_alerts_per_day": None,
        "best_setups_per_day": None,
        "telegram_commands_per_day": None,
        "alert_history_days": None,     # full history
        "visible_alerts": None,
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
