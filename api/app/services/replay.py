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
    alert_user_id = alert.get("user_id")

    # If this is an exit/SELL alert, find the original entry alert for levels
    if alert.get("direction") in ("SELL",) and not alert.get("entry"):
        with get_db() as conn:
            # Look for the entry alert — same symbol, same session (or recent for crypto)
            entry_row = conn.execute(
                """SELECT id, entry, stop, target_1, target_2, score, direction,
                          alert_type, message, created_at
                   FROM alerts
                   WHERE symbol = ? AND session_date = ?
                     AND direction IN ('BUY', 'SHORT')
                     AND entry IS NOT NULL AND entry > 0
                   ORDER BY created_at DESC LIMIT 1""",
                (symbol, session_date),
            ).fetchone()

            # For crypto, also check prior session if no match
            if not entry_row and symbol.endswith("-USD"):
                entry_row = conn.execute(
                    """SELECT id, entry, stop, target_1, target_2, score, direction,
                              alert_type, message, created_at
                       FROM alerts
                       WHERE symbol = ?
                         AND direction IN ('BUY', 'SHORT')
                         AND entry IS NOT NULL AND entry > 0
                       ORDER BY created_at DESC LIMIT 1""",
                    (symbol,),
                ).fetchone()

            if entry_row:
                alert["entry"] = entry_row["entry"]
                alert["stop"] = entry_row["stop"]
                alert["target_1"] = entry_row["target_1"]
                alert["target_2"] = entry_row["target_2"]
                if not alert.get("score"):
                    alert["score"] = entry_row["score"]
                alert["direction"] = entry_row["direction"]
                alert["alert_type"] = entry_row["alert_type"]
                alert["message"] = entry_row["message"]
                # Use the entry alert's timestamp for bar indexing
                alert["_entry_created_at"] = str(entry_row["created_at"])

    # Fetch 5-min OHLCV for the session
    try:
        from analytics.intraday_data import fetch_intraday
        df = fetch_intraday(symbol)

        if df is None or df.empty:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d", interval="5m")

        if df is None or df.empty:
            return {"alert": _clean_alert(alert), "bars": [], "outcome": "no_data",
                    "alert_bar_index": 0, "outcome_bar_index": 0,
                    "outcome_price": None, "pnl_per_share": 0, "pnl_pct": 0}

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
        return {"alert": _clean_alert(alert), "bars": [], "outcome": "fetch_error",
                "alert_bar_index": 0, "outcome_bar_index": 0,
                "outcome_price": None, "pnl_per_share": 0, "pnl_pct": 0}

    # Find alert bar index — use entry timestamp if available (for exit alerts)
    entry_time = alert.get("_entry_created_at") or str(alert.get("created_at", ""))
    alert_bar_index = _find_closest_bar(bars, entry_time)

    # Determine outcome from alerts table
    outcome = "open"
    outcome_bar_index = len(bars) - 1
    outcome_price = None

    with get_db() as conn:
        # Filter by user_id if available
        if alert_user_id:
            outcome_rows = conn.execute(
                """SELECT alert_type, price, created_at FROM alerts
                   WHERE symbol = ? AND session_date = ? AND user_id = ?
                     AND alert_type IN ('target_1_hit', 'target_2_hit', 'stop_loss_hit', 'auto_stop_out')
                   ORDER BY created_at""",
                (symbol, session_date, alert_user_id),
            ).fetchall()
        else:
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

    # Trim bars: wider window for better context
    # Show 6 bars before alert (setup) and extend to outcome + 8 bars after
    start = max(0, alert_bar_index - 6)
    end = min(len(bars), max(outcome_bar_index + 8, alert_bar_index + 36))
    trimmed_bars = bars[start:end]
    adj_alert_idx = alert_bar_index - start
    adj_outcome_idx = outcome_bar_index - start

    return {
        "alert": _clean_alert(alert),
        "bars": trimmed_bars,
        "alert_bar_index": max(0, adj_alert_idx),
        "outcome": outcome,
        "outcome_bar_index": min(max(0, adj_outcome_idx), len(trimmed_bars) - 1),
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

    target = timestamp[:19]
    best_idx = 0

    for i, bar in enumerate(bars):
        bar_ts = bar["timestamp"][:19]
        if bar_ts <= target:
            best_idx = i

    return best_idx
