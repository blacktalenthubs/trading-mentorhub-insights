"""Premarket swing alert refresh -- updates stale prices before market open."""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def fetch_premarket_price(symbol: str) -> float | None:
    """Fetch current premarket or last price for a symbol."""
    from config import is_crypto_alert_symbol

    # Crypto: use Coinbase (real-time)
    if is_crypto_alert_symbol(symbol):
        try:
            from analytics.intraday_data import _fetch_coinbase_candles

            df = _fetch_coinbase_candles(symbol, 300, 1)  # 1 candle, 5-min
            if not df.empty:
                return round(float(df["Close"].iloc[-1]), 2)
        except Exception:
            pass

    # Equities: use yfinance
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        # Try premarket price first, then regular price
        price = getattr(info, "last_price", None)
        if price and price > 0:
            return round(float(price), 2)
    except Exception:
        logger.warning("Failed to fetch premarket price for %s", symbol, exc_info=True)

    return None


def refresh_pending_swing_alerts(sync_session_factory) -> dict:
    """Refresh today's swing alerts with current premarket prices.

    Returns summary dict: {refreshed: int, invalidated: int, details: list}
    """
    from datetime import datetime

    from db import get_db

    session = date.today().isoformat()
    summary = {"refreshed": 0, "invalidated": 0, "details": []}

    # Query today's swing alerts (handle DBs without new columns gracefully)
    with get_db() as conn:
        try:
            rows = conn.execute(
                """SELECT id, symbol, alert_type, price, entry, stop, target_1,
                          setup_level, setup_condition
                   FROM alerts
                   WHERE session_date = ? AND alert_type LIKE 'swing_%'
                     AND gap_invalidated = 0 AND refreshed_at IS NULL""",
                (session,),
            ).fetchall()
        except Exception:
            # Fallback: columns may not exist yet on older DBs
            rows = conn.execute(
                """SELECT id, symbol, alert_type, price, entry, stop, target_1
                   FROM alerts
                   WHERE session_date = ? AND alert_type LIKE 'swing_%'""",
                (session,),
            ).fetchall()

    if not rows:
        logger.info("No pending swing alerts to refresh")
        return summary

    logger.info("Refreshing %d swing alerts for session %s", len(rows), session)

    for row in rows:
        alert_id = row["id"]
        symbol = row["symbol"]
        # Handle missing columns gracefully
        try:
            setup_level = row["setup_level"]
        except (KeyError, IndexError):
            setup_level = None
        original_entry = row["entry"] or row["price"]
        try:
            original_stop = row["stop"]
        except (KeyError, IndexError):
            original_stop = None

        current_price = fetch_premarket_price(symbol)
        if current_price is None:
            logger.warning("No premarket price for %s -- skipping", symbol)
            continue

        # Compute gap from setup level (or original entry if no setup_level)
        reference = setup_level or original_entry or 0
        if reference <= 0:
            continue

        gap_pct = round(((current_price - reference) / reference) * 100, 2)

        now = datetime.utcnow().isoformat()

        if abs(gap_pct) > 5.0:
            # Gap too large -- invalidate
            with get_db() as conn:
                conn.execute(
                    """UPDATE alerts SET gap_invalidated = 1, gap_pct = ?,
                       refreshed_at = ? WHERE id = ?""",
                    (gap_pct, now, alert_id),
                )
            summary["invalidated"] += 1
            summary["details"].append(
                {
                    "symbol": symbol,
                    "action": "invalidated",
                    "gap_pct": gap_pct,
                    "setup": row["setup_condition"] or row["alert_type"],
                }
            )
            logger.info(
                "%s: INVALIDATED -- gap %.1f%% from setup level", symbol, gap_pct
            )
        else:
            # Refresh entry/stop with current price context
            # Simple refresh: adjust entry to current price, keep stop structure
            refreshed_entry = current_price
            refreshed_stop = None
            if original_stop and original_entry and original_entry > 0:
                # Maintain same stop distance ratio
                stop_distance_pct = (original_entry - original_stop) / original_entry
                refreshed_stop = round(current_price * (1 - stop_distance_pct), 2)

            with get_db() as conn:
                conn.execute(
                    """UPDATE alerts SET refreshed_entry = ?, refreshed_stop = ?,
                       gap_pct = ?, refreshed_at = ? WHERE id = ?""",
                    (refreshed_entry, refreshed_stop, gap_pct, now, alert_id),
                )
            summary["refreshed"] += 1
            summary["details"].append(
                {
                    "symbol": symbol,
                    "action": "refreshed",
                    "original": original_entry,
                    "refreshed": refreshed_entry,
                    "gap_pct": gap_pct,
                }
            )
            logger.info(
                "%s: refreshed $%.2f -> $%.2f (gap %.1f%%)",
                symbol,
                original_entry or 0,
                refreshed_entry,
                gap_pct,
            )

    logger.info(
        "Swing refresh complete: %d refreshed, %d invalidated",
        summary["refreshed"],
        summary["invalidated"],
    )
    return summary


def format_refresh_summary(summary: dict) -> str:
    """Format a Telegram message for the premarket refresh summary."""
    if summary["refreshed"] == 0 and summary["invalidated"] == 0:
        return ""

    parts = ["<b>SWING PREMARKET UPDATE</b>"]
    parts.append(
        f"{summary['refreshed']} refreshed, {summary['invalidated']} invalidated\n"
    )

    for d in summary["details"]:
        sym = d["symbol"]
        if d["action"] == "invalidated":
            parts.append(f"\u274c {sym}: INVALIDATED ({d['gap_pct']:+.1f}% gap)")
        else:
            parts.append(
                f"\u2705 {sym}: ${d.get('original', 0):.2f} -> ${d.get('refreshed', 0):.2f} ({d['gap_pct']:+.1f}%)"
            )

    return "\n".join(parts)
