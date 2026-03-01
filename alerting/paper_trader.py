"""Alpaca paper trading integration.

Places bracket orders (market buy + OCA stop + take-profit) on actionable BUY
signals and closes positions on stop/target hits.  All Alpaca imports are lazy
so the module loads even without alpaca-py installed.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from alert_config import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    PAPER_TRADE_ENABLED,
    PAPER_TRADE_MAX_DAILY,
    PAPER_TRADE_MIN_SCORE,
    PAPER_TRADE_POSITION_SIZE,
)
from db import get_db

logger = logging.getLogger("paper_trader")

# Lazy-initialized Alpaca client
_client = None

# Alert types that are informational (not actionable trades)
_NON_ACTIONABLE_TYPES = {"gap_fill", "resistance_prior_high", "support_breakdown"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    """Check if Alpaca paper trading is configured and enabled."""
    return bool(PAPER_TRADE_ENABLED and ALPACA_API_KEY and ALPACA_SECRET_KEY)


def _get_client():
    """Lazy-init the Alpaca TradingClient (paper=True)."""
    global _client
    if _client is None:
        from alpaca.trading.client import TradingClient

        _client = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=True,
        )
    return _client


def _is_actionable_buy(signal) -> bool:
    """Return True if signal is a BUY with entry/stop/target, score >= min, excludes informational."""
    if signal.direction != "BUY":
        return False
    if signal.alert_type.value in _NON_ACTIONABLE_TYPES:
        return False
    if not signal.entry or not signal.stop or not signal.target_1:
        return False
    if getattr(signal, "score", 0) < PAPER_TRADE_MIN_SCORE:
        return False
    return True


def _has_open_position(symbol: str) -> bool:
    """Check local DB for an existing open paper trade on this symbol."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM paper_trades WHERE symbol = ? AND status = 'open' LIMIT 1",
            (symbol,),
        ).fetchone()
        return row is not None


def _daily_trade_count(session_date: str) -> int:
    """Count paper trades opened today."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM paper_trades WHERE session_date = ?",
            (session_date,),
        ).fetchone()
        return row["cnt"] if row else 0


def _calculate_shares(entry_price: float) -> int:
    """Calculate share count: floor(position_size / entry_price)."""
    if entry_price <= 0:
        return 0
    return math.floor(PAPER_TRADE_POSITION_SIZE / entry_price)


# ---------------------------------------------------------------------------
# Order placement
# ---------------------------------------------------------------------------

def place_bracket_order(signal, alert_id: int | None = None) -> bool:
    """Place a bracket order on Alpaca for an actionable BUY signal.

    Returns True if the order was placed, False if skipped or failed.
    """
    if not is_enabled():
        return False

    if not _is_actionable_buy(signal):
        logger.debug("Skipping non-actionable signal: %s %s", signal.symbol, signal.alert_type.value)
        return False

    if _has_open_position(signal.symbol):
        logger.info("Skipping %s — already have an open paper position", signal.symbol)
        return False

    from alerting.alert_store import today_session

    session = today_session()
    if _daily_trade_count(session) >= PAPER_TRADE_MAX_DAILY:
        logger.info("Skipping %s — daily paper trade limit reached (%d)", signal.symbol, PAPER_TRADE_MAX_DAILY)
        return False

    shares = _calculate_shares(signal.entry)
    if shares <= 0:
        logger.warning("Calculated 0 shares for %s @ $%.2f", signal.symbol, signal.entry)
        return False

    try:
        from alpaca.trading.requests import (
            MarketOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce

        order_data = MarketOrderRequest(
            symbol=signal.symbol,
            qty=shares,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(signal.target_1, 2)),
            stop_loss=StopLossRequest(stop_price=round(signal.stop, 2)),
        )

        client = _get_client()
        order = client.submit_order(order_data=order_data)
        alpaca_order_id = str(order.id) if order else None

        # Record in local DB
        with get_db() as conn:
            conn.execute(
                """INSERT INTO paper_trades
                   (symbol, direction, shares, entry_price, stop_price, target_price,
                    status, alert_type, alert_id, alpaca_order_id, session_date)
                   VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
                (
                    signal.symbol, "BUY", shares, signal.entry,
                    signal.stop, signal.target_1,
                    signal.alert_type.value, alert_id, alpaca_order_id, session,
                ),
            )

        logger.info(
            "PAPER TRADE: BUY %d shares %s @ ~$%.2f | stop=$%.2f | target=$%.2f | order=%s",
            shares, signal.symbol, signal.entry, signal.stop, signal.target_1,
            alpaca_order_id,
        )
        return True

    except Exception:
        logger.exception("Failed to place paper bracket order for %s", signal.symbol)
        return False


# ---------------------------------------------------------------------------
# Position closing
# ---------------------------------------------------------------------------

def close_position(symbol: str, exit_price: float, reason: str = "") -> bool:
    """Close an open paper position via Alpaca and update local DB.

    Returns True if closed, False if no position or failed.
    """
    if not is_enabled():
        return False

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, shares, entry_price FROM paper_trades WHERE symbol = ? AND status = 'open' LIMIT 1",
            (symbol,),
        ).fetchone()

    if not row:
        logger.debug("No open paper position for %s to close", symbol)
        return False

    trade_id = row["id"]
    shares = row["shares"]
    entry_price = row["entry_price"]
    pnl = (exit_price - entry_price) * shares if entry_price else 0

    try:
        client = _get_client()
        close_order = client.close_position(symbol_or_asset_id=symbol)
        close_order_id = str(close_order.id) if close_order else None
    except Exception:
        logger.exception("Alpaca close_position failed for %s, updating local DB only", symbol)
        close_order_id = None

    # Update local DB regardless of Alpaca result
    now = datetime.now().isoformat()
    status = "stopped" if "stop" in reason.lower() else "closed"
    with get_db() as conn:
        conn.execute(
            """UPDATE paper_trades
               SET exit_price = ?, pnl = ?, status = ?,
                   alpaca_close_order_id = ?, closed_at = ?
               WHERE id = ?""",
            (exit_price, pnl, status, close_order_id, now, trade_id),
        )

    logger.info(
        "PAPER CLOSE: %s %d shares @ $%.2f | P&L=$%.2f | reason=%s",
        symbol, shares, exit_price, pnl, reason,
    )
    return True


# ---------------------------------------------------------------------------
# Reconciliation — sync local DB with Alpaca state
# ---------------------------------------------------------------------------

def sync_open_trades() -> int:
    """Reconcile local open trades with Alpaca.

    For each open trade in our DB, check the bracket order status on Alpaca.
    If a leg (take-profit or stop-loss) has filled, update our DB with the
    actual fill price and P&L.

    Returns the number of trades synced (closed).
    """
    if not is_enabled():
        return 0

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, symbol, shares, entry_price, alpaca_order_id "
            "FROM paper_trades WHERE status = 'open' AND alpaca_order_id IS NOT NULL"
        ).fetchall()

    if not rows:
        return 0

    synced = 0
    client = _get_client()

    for row in rows:
        try:
            from alpaca.trading.requests import GetOrderByIdRequest

            order = client.get_order_by_id(
                order_id=row["alpaca_order_id"],
                filter=GetOrderByIdRequest(nested=True),
            )

            if not order.legs:
                continue

            # Check each leg for a fill
            filled_leg = None
            for leg in order.legs:
                if str(leg.status) == "filled":
                    filled_leg = leg
                    break

            if not filled_leg:
                continue

            # Determine exit price and reason from the filled leg
            fill_price = float(filled_leg.filled_avg_price or 0)
            if not fill_price:
                continue

            # Identify which leg: limit = take-profit, stop = stop-loss
            leg_type = str(filled_leg.type) if filled_leg.type else ""
            if "limit" in leg_type and "stop" not in leg_type:
                reason = "target_hit (alpaca)"
                status = "closed"
            else:
                reason = "stop_hit (alpaca)"
                status = "stopped"

            entry_price = row["entry_price"] or 0
            shares = row["shares"]
            pnl = (fill_price - entry_price) * shares

            now = datetime.now().isoformat()
            with get_db() as conn:
                conn.execute(
                    """UPDATE paper_trades
                       SET exit_price = ?, pnl = ?, status = ?, closed_at = ?
                       WHERE id = ?""",
                    (fill_price, pnl, status, now, row["id"]),
                )

            logger.info(
                "SYNC: %s %d shares | exit=$%.2f | P&L=$%.2f | %s",
                row["symbol"], shares, fill_price, pnl, reason,
            )
            synced += 1

        except Exception:
            logger.exception("Failed to sync order %s for %s", row["alpaca_order_id"], row["symbol"])

    if synced:
        logger.info("Synced %d paper trade(s) from Alpaca", synced)
    return synced


# ---------------------------------------------------------------------------
# Queries (for dashboard)
# ---------------------------------------------------------------------------

def get_account_info() -> dict | None:
    """Get Alpaca paper account info (equity, cash, buying_power)."""
    if not is_enabled():
        return None
    try:
        account = _get_client().get_account()
        return {
            "equity": float(account.equity or 0),
            "cash": float(account.cash or 0),
            "buying_power": float(account.buying_power or 0),
            "last_equity": float(account.last_equity or 0),
            "portfolio_value": float(account.portfolio_value or 0),
        }
    except Exception:
        logger.exception("Failed to get Alpaca account info")
        return None


def get_open_positions() -> list[dict]:
    """Get live open positions from Alpaca."""
    if not is_enabled():
        return []
    try:
        positions = _get_client().get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": int(float(p.qty or 0)),
                "market_value": float(p.market_value or 0),
                "current_price": float(p.current_price or 0),
                "avg_entry_price": float(p.avg_entry_price or 0),
                "unrealized_pl": float(p.unrealized_pl or 0),
                "unrealized_plpc": float(p.unrealized_plpc or 0) * 100,
            }
            for p in positions
        ]
    except Exception:
        logger.exception("Failed to get Alpaca positions")
        return []


def get_paper_trades_history(limit: int = 100) -> list[dict]:
    """Get closed paper trades from local DB."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM paper_trades
               WHERE status != 'open'
               ORDER BY closed_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_paper_trade_stats() -> dict:
    """Aggregate stats: win rate, total P&L, expectancy, avg win/loss, R:R."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT pnl FROM paper_trades WHERE status != 'open' AND pnl IS NOT NULL"
        ).fetchall()

    if not rows:
        return {
            "total_trades": 0, "winners": 0, "losers": 0,
            "win_rate": 0.0, "total_pnl": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0,
            "expectancy": 0.0, "risk_reward": 0.0,
        }

    pnls = [r["pnl"] for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total = len(pnls)
    win_rate = len(wins) / total * 100 if total else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    rr = abs(avg_win / avg_loss) if avg_loss else 0
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    return {
        "total_trades": total,
        "winners": len(wins),
        "losers": len(losses),
        "win_rate": win_rate,
        "total_pnl": sum(pnls),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "risk_reward": rr,
    }
