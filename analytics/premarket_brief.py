"""Pre-market brief — build and send a daily pre-market Telegram summary."""

from __future__ import annotations

import logging
from datetime import datetime

import pytz

from alerting.alert_store import today_session
from alerting.notifier import _send_telegram
from analytics.intraday_data import (
    compute_premarket_brief,
    fetch_premarket_bars,
    fetch_prior_day,
    get_spy_context,
)
from db import get_all_watchlist_symbols

logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")

# Once-per-day guard
_brief_sent_date: str | None = None


def _format_spy_header(spy_ctx: dict) -> str:
    """Format SPY regime one-liner for the brief header."""
    close = spy_ctx.get("close", 0)
    regime = spy_ctx.get("regime", "UNKNOWN")
    rsi = spy_ctx.get("spy_rsi14")
    trend = spy_ctx.get("trend", "neutral")

    emoji = {"bullish": "\U0001f7e2", "bearish": "\U0001f534", "neutral": "\U0001f7e1"}.get(trend, "\U0001f7e1")
    rsi_str = f" | RSI {rsi:.0f}" if rsi is not None else ""
    return f"{emoji} SPY ${close:.2f} | {regime}{rsi_str}"


def _format_symbol_line(brief: dict) -> str:
    """Format a single symbol's pre-market summary."""
    symbol = brief["symbol"]
    flags = brief.get("flags", [])
    pm_last = brief["pm_last"]
    pm_change = brief["pm_change_pct"]
    pm_range = brief["pm_range_pct"]

    sign = "+" if pm_change >= 0 else ""
    flags_str = " | ".join(flags) if flags else "No flags"

    lines = [
        f"  {symbol} \u2014 {flags_str}",
        f"  PM: ${pm_last:.2f} ({sign}{pm_change:.1f}%) | Range: {pm_range:.1f}%",
    ]
    return "\n".join(lines)


def build_premarket_message() -> str | None:
    """Build the pre-market brief message text.

    Returns formatted string or None if no data available.
    """
    symbols = get_all_watchlist_symbols()
    if not symbols:
        return None

    # Gather briefs for each symbol
    briefs: list[dict] = []
    for symbol in symbols:
        pm_bars = fetch_premarket_bars(symbol)
        if pm_bars.empty:
            continue
        prior = fetch_prior_day(symbol)
        if prior is None:
            continue
        brief = compute_premarket_brief(symbol, pm_bars, prior)
        if brief is not None:
            briefs.append(brief)

    if not briefs:
        return None

    # SPY header
    spy_ctx = get_spy_context()
    now_et = datetime.now(ET)
    date_str = now_et.strftime("%b %-d, %Y")

    parts: list[str] = [
        f"PRE-MARKET BRIEF \u2014 {date_str}",
        "",
        _format_spy_header(spy_ctx),
    ]

    # Group by priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    briefs.sort(key=lambda b: priority_order.get(b["priority_label"], 3))

    current_priority = None
    for brief in briefs:
        label = brief["priority_label"]
        if label != current_priority:
            current_priority = label
            parts.append(f"\n--- {label} PRIORITY ---")
        parts.append(_format_symbol_line(brief))

    return "\n".join(parts)


def send_premarket_brief() -> bool:
    """Send the pre-market brief via Telegram (once per day).

    Returns True if sent, False if skipped or failed.
    """
    global _brief_sent_date

    session = today_session()
    if _brief_sent_date == session:
        logger.debug("Pre-market brief already sent for %s", session)
        return False

    msg = build_premarket_message()
    if not msg:
        logger.info("Pre-market brief: no data to send")
        return False

    sent = _send_telegram(msg)
    if sent:
        _brief_sent_date = session
        logger.info("Pre-market brief sent for %s", session)
    return sent
