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
