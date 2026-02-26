"""Shared market hours utility — used by Signal Scanner, Alert Dashboard, and monitor.py."""

from __future__ import annotations

from datetime import datetime

import pytz

from alert_config import (
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
)

ET = pytz.timezone("US/Eastern")

# Session phases: (start_hour, start_minute, end_hour, end_minute)
SESSION_PHASES = {
    "pre_market": (4, 0, 9, 30),
    "opening_range": (9, 30, 10, 0),
    "prime_time": (10, 0, 15, 0),
    "power_hour": (15, 0, 15, 30),
    "last_30": (15, 30, 16, 0),
}


def is_market_hours() -> bool:
    """Check if current time is within US market hours (weekday, 9:30-16:00 ET)."""
    now = datetime.now(ET)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now.replace(
        hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0,
    )
    market_close = now.replace(
        hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0,
    )
    return market_open <= now <= market_close


def get_session_phase() -> str:
    """Return current session phase name, or 'closed' if outside all phases."""
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return "closed"
    current_minutes = now.hour * 60 + now.minute
    for phase, (sh, sm, eh, em) in SESSION_PHASES.items():
        start = sh * 60 + sm
        end = eh * 60 + em
        if start <= current_minutes < end:
            return phase
    return "closed"


def allow_new_entries() -> bool:
    """Returns False during 'opening_range' and 'last_30' phases."""
    phase = get_session_phase()
    return phase not in ("opening_range", "last_30", "closed")
