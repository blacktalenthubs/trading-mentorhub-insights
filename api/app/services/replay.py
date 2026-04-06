"""Chart Replay — fetch OHLCV window around an alert + compute outcome."""

from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def get_replay_data(alert_id: int, user_id: int | None = None) -> dict | None:
    """Build replay data for an alert.

    Returns dict with alert info, OHLCV bars, outcome, and bar indices.
    """
    from db import get_db

    # Load alert
    with get_db() as conn:
        if user_id:
            row = conn.execute(
                "SELECT * FROM alerts WHERE id = ? AND user_id = ?",
                (alert_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM alerts WHERE id = ?", (alert_id,),
            ).fetchone()

    if not row:
        return None

    alert = dict(row)
    symbol = alert["symbol"]
    session_date = alert.get("session_date", date.today().isoformat())

    # If this is an exit/SELL alert, find the original entry alert for levels
    if alert.get("direction") in ("SELL", "SHORT") and not alert.get("entry"):
        with get_db() as conn:
            entry_row = conn.execute(
                """SELECT entry, stop, target_1, target_2, score, direction, alert_type, message
                   FROM alerts
                   WHERE symbol = ? AND session_date = ?
                     AND direction IN ('BUY', 'SHORT')
                     AND entry IS NOT NULL AND entry > 0
                   ORDER BY created_at DESC LIMIT 1""",
                (symbol, session_date),
            ).fetchone()
            if entry_row:
                alert["entry"] = entry_row["entry"]
                alert["stop"] = entry_row["stop"]
                alert["target_1"] = entry_row["target_1"]
                alert["target_2"] = entry_row["target_2"]
                if not alert.get("score"):
                    alert["score"] = entry_row["score"]
                # Use the entry alert's direction for P&L calculation
                alert["direction"] = entry_row["direction"]
                alert["alert_type"] = entry_row["alert_type"]
                alert["message"] = entry_row["message"]

    # Fetch 5-min OHLCV for the session
    try:
        from analytics.intraday_data import fetch_intraday
        df = fetch_intraday(symbol)

        if df is None or df.empty:
            # Try fetching historical for past dates
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d", interval="5m")

        if df is None or df.empty:
            return {"alert": _clean_alert(alert), "bars": [], "outcome": "no_data"}

        bars = []
        for ts, r in df.iterrows():
            bars.append({
                "timestamp": str(ts),
                "open": round(float(r["Open"]), 2),
                "high": round(float(r["High"]), 2),
                "low": round(float(r["Low"]), 2),
                "close": round(float(r["Close"]), 2),
                "volume": int(r["Volume"]),
            })

    except Exception:
        logger.exception("Replay: failed to fetch OHLCV for %s", symbol)
        return {"alert": _clean_alert(alert), "bars": [], "outcome": "fetch_error"}

    # Find alert bar index (closest bar to alert timestamp)
    alert_time = alert.get("created_at", "")
    alert_bar_index = _find_closest_bar(bars, str(alert_time))

    # Determine outcome from alerts table
    outcome = "open"
    outcome_bar_index = len(bars) - 1
    outcome_price = None

    with get_db() as conn:
        outcome_rows = conn.execute(
            """SELECT alert_type, price, created_at FROM alerts
               WHERE symbol = ? AND session_date = ?
                 AND alert_type IN ('target_1_hit', 'target_2_hit', 'stop_loss_hit', 'auto_stop_out')
               ORDER BY created_at""",
            (symbol, session_date),
        ).fetchall()

    for o in outcome_rows:
        if o["alert_type"] in ("target_1_hit", "target_2_hit"):
            outcome = o["alert_type"]
            outcome_price = o["price"]
            outcome_bar_index = _find_closest_bar(bars, str(o["created_at"]))
            break
        elif o["alert_type"] in ("stop_loss_hit", "auto_stop_out"):
            outcome = o["alert_type"]
            outcome_price = o["price"]
            outcome_bar_index = _find_closest_bar(bars, str(o["created_at"]))
            break

    # Calculate P&L
    entry = alert.get("entry") or alert.get("price", 0)
    pnl_per_share = 0
    pnl_pct = 0
    if outcome_price and entry:
        if alert.get("direction") == "SHORT":
            pnl_per_share = round(entry - outcome_price, 2)
        else:
            pnl_per_share = round(outcome_price - entry, 2)
        pnl_pct = round(pnl_per_share / entry * 100, 2) if entry else 0

    # Trim bars: show from max(0, alert-12) to min(len, alert+24)
    start = max(0, alert_bar_index - 12)
    end = min(len(bars), max(outcome_bar_index + 6, alert_bar_index + 24))
    trimmed_bars = bars[start:end]
    adj_alert_idx = alert_bar_index - start
    adj_outcome_idx = outcome_bar_index - start

    return {
        "alert": _clean_alert(alert),
        "bars": trimmed_bars,
        "alert_bar_index": adj_alert_idx,
        "outcome": outcome,
        "outcome_bar_index": min(adj_outcome_idx, len(trimmed_bars) - 1),
        "outcome_price": outcome_price,
        "pnl_per_share": pnl_per_share,
        "pnl_pct": pnl_pct,
    }


def _clean_alert(alert: dict) -> dict:
    """Return only the fields needed for replay display."""
    return {
        "id": alert.get("id"),
        "symbol": alert.get("symbol"),
        "direction": alert.get("direction"),
        "alert_type": alert.get("alert_type", "").replace("_", " ").title(),
        "price": alert.get("price"),
        "entry": alert.get("entry"),
        "stop": alert.get("stop"),
        "target_1": alert.get("target_1"),
        "target_2": alert.get("target_2"),
        "score": alert.get("score"),
        "message": alert.get("message"),
        "created_at": str(alert.get("created_at", "")),
        "session_date": alert.get("session_date"),
    }


def _find_closest_bar(bars: list[dict], timestamp: str) -> int:
    """Find the bar index closest to the given timestamp."""
    if not bars or not timestamp:
        return 0

    # Simple string comparison — works for ISO timestamps
    target = timestamp[:19]  # trim to YYYY-MM-DDTHH:MM:SS
    best_idx = 0
    best_diff = float("inf")

    for i, bar in enumerate(bars):
        bar_ts = bar["timestamp"][:19]
        # Compare as strings (works for same-day ISO format)
        if bar_ts <= target:
            best_idx = i

    return best_idx
