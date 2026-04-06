"""End-of-day swing trade scanner — Burns-style daily setups.

Runs once daily after market close.  Orchestrates:
1. SPY regime gate check
2. Swing rule evaluation for all watchlist symbols
3. Active swing trade exit checks (RSI target / stop)
4. Watchlist categorisation (buy_zone / strongest / etc.)
"""

from __future__ import annotations

import logging

from alerting.alert_store import record_alert, today_session
from alerting.notifier import notify
from alerting.real_trade_store import (
    close_real_trade,
    get_open_trades,
    stop_real_trade,
)
from analytics.intraday_data import fetch_prior_day, get_spy_context
from analytics.intraday_rules import AlertSignal, AlertType
from analytics.swing_rules import (
    categorize_symbol,
    check_spy_regime,
    evaluate_swing_rules,
)
from db import get_all_watchlist_symbols, get_db

logger = logging.getLogger("swing_scanner")


# ---------------------------------------------------------------------------
# Swing trade DB helpers
# ---------------------------------------------------------------------------

def create_swing_trade(
    signal: AlertSignal,
    stop_type: str,
    entry_rsi: float | None,
    session: str,
) -> int | None:
    """Insert a new swing trade row.  Returns the row id or None on dup."""
    with get_db() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO swing_trades
                   (symbol, alert_type, direction, entry_price, current_price,
                    stop_type, target_type, entry_rsi, current_rsi,
                    status, entry_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
                (
                    signal.symbol,
                    signal.alert_type.value,
                    signal.direction,
                    signal.price,
                    signal.price,
                    stop_type,
                    "rsi_70",
                    entry_rsi,
                    entry_rsi,
                    session,
                ),
            )
            return cur.lastrowid
        except Exception:
            # UNIQUE constraint — already have this trade today
            return None


def get_active_swing_trades() -> list[dict]:
    """Return all active swing trades."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM swing_trades WHERE status = 'active' ORDER BY entry_date"
        ).fetchall()
        return [dict(r) for r in rows]


def close_swing_trade(
    trade_id: int,
    status: str,
    exit_price: float,
    closed_date: str,
) -> None:
    """Mark a swing trade as closed (target_hit or stopped)."""
    with get_db() as conn:
        conn.execute(
            """UPDATE swing_trades
               SET status = ?, current_price = ?, closed_date = ?,
                   pnl_pct = ROUND((? - entry_price) / entry_price * 100, 2)
               WHERE id = ?""",
            (status, exit_price, closed_date, exit_price, trade_id),
        )


def update_swing_trade_price(
    trade_id: int,
    current_price: float,
    current_rsi: float | None,
) -> None:
    """Refresh current price and RSI on an active trade."""
    with get_db() as conn:
        conn.execute(
            """UPDATE swing_trades
               SET current_price = ?, current_rsi = ?
               WHERE id = ?""",
            (current_price, current_rsi, trade_id),
        )


def get_swing_categories(session_date: str) -> list[dict]:
    """Return categorised watchlist for a session date."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM swing_categories
               WHERE session_date = ? ORDER BY category, symbol""",
            (session_date,),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_swing_category(
    symbol: str, category: str, rsi: float | None, session_date: str,
) -> None:
    """Insert or update a symbol's category for the session."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO swing_categories (symbol, category, rsi, session_date)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(symbol, session_date)
               DO UPDATE SET category = excluded.category,
                            rsi = excluded.rsi""",
            (symbol, category, rsi, session_date),
        )


def get_swing_trades_history(limit: int = 50) -> list[dict]:
    """Return closed swing trades, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM swing_trades
               WHERE status != 'active'
               ORDER BY closed_date DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stop-type checkers
# ---------------------------------------------------------------------------

def _auto_close_real_trade(symbol: str, exit_price: float, is_stop: bool) -> None:
    """Close the matching real_trade for a symbol if one exists."""
    open_trades = get_open_trades(trade_type="swing")
    for t in open_trades:
        if t["symbol"] == symbol:
            if is_stop:
                stop_real_trade(t["id"], exit_price, notes="Auto-closed by EOD scan (stopped)")
            else:
                close_real_trade(t["id"], exit_price, notes="Auto-closed by EOD scan (target hit)")
            break


def _check_stop(trade: dict, prior_day: dict) -> bool:
    """Return True if the trade's stop condition is met."""
    stop_type = trade["stop_type"]
    close = prior_day.get("close", 0)

    if stop_type == "ema_cross_under_5_20":
        ema5 = prior_day.get("ema5")
        ema20 = prior_day.get("ema20")
        if ema5 is not None and ema20 is not None and ema5 < ema20:
            return True

    elif stop_type == "close_below_200ma":
        ma200 = prior_day.get("ma200")
        if ma200 is not None and close < ma200:
            return True

    elif stop_type == "close_below_20ema":
        ema20 = prior_day.get("ema20")
        if ema20 is not None and close < ema20:
            return True

    elif stop_type == "close_below_50ma":
        ma50 = prior_day.get("ema50") or prior_day.get("ma50")
        if ma50 is not None and close < ma50:
            return True

    elif stop_type == "close_below_weekly_low":
        pw_low = prior_day.get("prior_week_low")
        if pw_low is not None and close < pw_low:
            return True

    elif stop_type == "close_below_bounce_low":
        # For RSI bounce: stop is close below the entry day's stop price
        stop_price = trade.get("stop_price") or trade.get("entry_price", 0) * 0.97
        if close < stop_price:
            return True

    # Generic: close below prior day low (applies to all swing trades)
    pdl = prior_day.get("low")
    prev_low = prior_day.get("prev_low") or prior_day.get("prior_day_low")
    if prev_low and close < prev_low:
        # Close below PDL is a warning, not auto-stop
        # (user decides via Telegram notification)
        pass

    return False


# ---------------------------------------------------------------------------
# EOD orchestrator
# ---------------------------------------------------------------------------

def swing_scan_eod() -> int:
    """Run the end-of-day swing trade scan.  Returns number of alerts fired."""
    session = today_session()
    total = 0

    # 1. SPY regime gate
    spy_ctx = get_spy_context()
    regime_ok = check_spy_regime(spy_ctx)

    if not regime_ok:
        logger.info(
            "SPY below 20 EMA — swing scanner paused "
            "(close=%.2f, ema20=%.2f)",
            spy_ctx.get("close", 0),
            spy_ctx.get("spy_ema20", 0),
        )

    # 2. Build fired-today set for dedup
    fired_today: set[tuple[str, str]] = set()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT symbol, alert_type FROM alerts WHERE session_date = ?",
            (session,),
        ).fetchall()
        for r in rows:
            fired_today.add((r["symbol"], r["alert_type"]))

    # 3. Scan each watchlist symbol
    symbols = get_all_watchlist_symbols()
    for symbol in symbols:
        try:
            prior_day = fetch_prior_day(symbol)
            if prior_day is None:
                continue

            # Evaluate swing rules (RSI zones always; setups only if regime OK)
            if regime_ok:
                signals = evaluate_swing_rules(
                    symbol, prior_day, spy_ctx, fired_today,
                )
            else:
                # Still fire RSI zone alerts even without regime
                from analytics.swing_rules import check_rsi_zones

                rsi = prior_day.get("rsi14")
                rsi_prev = prior_day.get("rsi14_prev")
                close = prior_day.get("close", 0)
                signals = []
                if rsi is not None:
                    sig = check_rsi_zones(symbol, rsi, rsi_prev, close)
                    if sig and (symbol, sig.alert_type.value) not in fired_today:
                        signals.append(sig)

            # Process signals
            for sig in signals:
                try:
                    email_ok, sms_ok = notify(sig)
                    record_alert(
                        sig,
                        session_date=session,
                        notified_email=email_ok,
                        notified_sms=sms_ok,
                    )
                    fired_today.add((sig.symbol, sig.alert_type.value))
                    total += 1

                    # Create swing trade for setup signals
                    _maybe_create_trade(sig, prior_day, session)

                except Exception:
                    logger.exception("Failed to process swing signal %s %s",
                                     symbol, sig.alert_type.value)

            # Categorise symbol
            category = categorize_symbol(prior_day)
            upsert_swing_category(
                symbol, category, prior_day.get("rsi14"), session,
            )

        except Exception:
            logger.exception("Swing scan failed for %s", symbol)

    # 4. Check active swing trades for exits
    total += _check_active_exits(session, fired_today)

    logger.info("EOD swing scan complete: %d total signals", total)
    return total


def _maybe_create_trade(
    signal: AlertSignal, prior_day: dict, session: str,
) -> None:
    """Create a swing_trades row for setup signals (not RSI-zone notices)."""
    stop_map = {
        AlertType.SWING_EMA_CROSSOVER_5_20: "ema_cross_under_5_20",
        AlertType.SWING_200MA_RECLAIM: "close_below_200ma",
        AlertType.SWING_PULLBACK_20EMA: "close_below_20ema",
        AlertType.SWING_RSI_30_BOUNCE: "close_below_bounce_low",
        AlertType.SWING_200MA_HOLD: "close_below_200ma",
        AlertType.SWING_50MA_HOLD: "close_below_50ma",
        AlertType.SWING_WEEKLY_SUPPORT: "close_below_weekly_low",
    }
    stop_type = stop_map.get(signal.alert_type)
    if stop_type is None:
        return  # RSI zones / management alerts don't create trades

    create_swing_trade(
        signal,
        stop_type=stop_type,
        entry_rsi=prior_day.get("rsi14"),
        session=session,
    )


def _check_active_exits(
    session: str,
    fired_today: set[tuple[str, str]],
) -> int:
    """Check active swing trades for exit conditions.  Returns alerts fired."""
    from alert_config import SWING_RSI_OVERBOUGHT

    active = get_active_swing_trades()
    count = 0

    for trade in active:
        symbol = trade["symbol"]
        try:
            prior_day = fetch_prior_day(symbol)
            if prior_day is None:
                continue

            close = prior_day.get("close", 0)
            rsi = prior_day.get("rsi14")

            # Update current price/RSI
            update_swing_trade_price(trade["id"], close, rsi)

            # Check RSI target — flexible based on entry type
            # RSI 30 bounce entries → target RSI 45-50
            # MA bounce entries → target RSI 65-70
            _entry_type = trade.get("alert_type", "")
            _rsi_target = 45 if "rsi_30" in _entry_type else SWING_RSI_OVERBOUGHT
            if rsi is not None and rsi >= _rsi_target:
                if (symbol, "swing_target_hit") not in fired_today:
                    pnl = ((close - trade["entry_price"]) / trade["entry_price"]) * 100
                    sig = AlertSignal(
                        symbol=symbol,
                        alert_type=AlertType.SWING_TARGET_HIT,
                        direction="SELL",
                        price=close,
                        message=(
                            f"[SWING] Target hit — RSI {rsi:.1f} ≥ 70 | "
                            f"Entry {trade['entry_price']:.2f} → {close:.2f} "
                            f"({pnl:+.1f}%)"
                        ),
                    )
                    email_ok, sms_ok = notify(sig)
                    record_alert(sig, session_date=session,
                                 notified_email=email_ok, notified_sms=sms_ok)
                    close_swing_trade(trade["id"], "target_hit", close, session)
                    _auto_close_real_trade(symbol, close, is_stop=False)
                    fired_today.add((symbol, "swing_target_hit"))
                    count += 1
                continue

            # Check stop condition
            if _check_stop(trade, prior_day):
                if (symbol, "swing_stopped_out") not in fired_today:
                    pnl = ((close - trade["entry_price"]) / trade["entry_price"]) * 100
                    sig = AlertSignal(
                        symbol=symbol,
                        alert_type=AlertType.SWING_STOPPED_OUT,
                        direction="SELL",
                        price=close,
                        message=(
                            f"[SWING] Stopped out — {trade['stop_type']} | "
                            f"Entry {trade['entry_price']:.2f} → {close:.2f} "
                            f"({pnl:+.1f}%)"
                        ),
                    )
                    email_ok, sms_ok = notify(sig)
                    record_alert(sig, session_date=session,
                                 notified_email=email_ok, notified_sms=sms_ok)
                    close_swing_trade(trade["id"], "stopped", close, session)
                    _auto_close_real_trade(symbol, close, is_stop=True)
                    fired_today.add((symbol, "swing_stopped_out"))
                    count += 1

        except Exception:
            logger.exception("Exit check failed for %s", symbol)

    return count
