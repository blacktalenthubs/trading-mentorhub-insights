"""Multi-tenant alert monitor — runs inside FastAPI via APScheduler.

For each Pro user, polls their watchlist, evaluates rules, fires alerts.
Market data is deduplicated: same symbol across users = one yfinance fetch.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from alert_config import COOLDOWN_MINUTES  # noqa: E402
from analytics.intraday_data import fetch_intraday, fetch_prior_day, get_spy_context  # noqa: E402
from analytics.intraday_rules import AlertSignal, AlertType, evaluate_rules  # noqa: E402
from analytics.market_hours import is_market_hours  # noqa: E402

logger = logging.getLogger("monitor")


def poll_all_users(sync_session_factory) -> int:
    """Run one poll cycle for all Pro users.

    Uses synchronous SQLAlchemy since this runs in a background thread.
    Returns total alerts fired across all users.
    """
    if not is_market_hours():
        logger.info("Market closed — skipping poll")
        return 0

    from app.models.user import Subscription, User  # noqa: E402
    from app.models.watchlist import WatchlistItem  # noqa: E402
    from app.models.alert import ActiveEntry, Alert, Cooldown  # noqa: E402

    session_date = date.today().isoformat()
    total_alerts = 0

    with sync_session_factory() as db:
        # Get Pro users
        pro_users = db.execute(
            select(User.id).join(Subscription).where(
                Subscription.tier == "pro", Subscription.status == "active"
            )
        ).scalars().all()

        if not pro_users:
            logger.info("No Pro users — skipping poll")
            return 0

        # Gather all unique symbols across Pro users (dedup fetches)
        user_symbols: Dict[int, List[str]] = {}
        all_symbols: set[str] = set()
        for user_id in pro_users:
            symbols = db.execute(
                select(WatchlistItem.symbol).where(WatchlistItem.user_id == user_id)
            ).scalars().all()
            user_symbols[user_id] = list(symbols)
            all_symbols.update(symbols)

        if not all_symbols:
            return 0

        # Deduplicated market data fetches (also write to app cache for API reuse)
        from app.cache import cache_get, cache_set

        intraday_cache: dict[str, object] = {}
        prior_day_cache: dict[str, object] = {}
        for symbol in all_symbols:
            intraday_cache[symbol] = fetch_intraday(symbol)
            prior_day_cache[symbol] = fetch_prior_day(symbol)

            # Warm the API cache so user requests hit cache instead of yfinance
            if intraday_cache[symbol] is not None and not (
                hasattr(intraday_cache[symbol], "empty") and intraday_cache[symbol].empty
            ):
                df = intraday_cache[symbol]
                bars = [
                    {
                        "timestamp": str(ts),
                        "open": round(row["Open"], 2),
                        "high": round(row["High"], 2),
                        "low": round(row["Low"], 2),
                        "close": round(row["Close"], 2),
                        "volume": round(row["Volume"], 0),
                    }
                    for ts, row in df.iterrows()
                ]
                cache_set(f"intraday:{symbol}", bars, 180)

            if prior_day_cache[symbol]:
                cache_set(f"prior_day:{symbol}", prior_day_cache[symbol], 3600)

        spy_ctx = get_spy_context()

        # Evaluate per user
        for user_id in pro_users:
            symbols = user_symbols.get(user_id, [])
            if not symbols:
                continue

            # Load user's fired alerts for dedup
            db_alerts = db.execute(
                select(Alert.symbol, Alert.alert_type).where(
                    Alert.user_id == user_id, Alert.session_date == session_date
                )
            ).all()
            fired_today: set[tuple[str, str]] = {(a[0], a[1]) for a in db_alerts}

            # Load cooldowns
            cooldown_rows = db.execute(
                select(Cooldown.symbol).where(
                    Cooldown.user_id == user_id, Cooldown.session_date == session_date
                )
            ).scalars().all()
            cooled_symbols = set(cooldown_rows)

            for symbol in symbols:
                intraday = intraday_cache.get(symbol)
                prior_day = prior_day_cache.get(symbol)

                if intraday is None or (hasattr(intraday, "empty") and intraday.empty):
                    continue

                # Get active entries for this user/symbol
                active_rows = db.execute(
                    select(ActiveEntry).where(
                        ActiveEntry.user_id == user_id,
                        ActiveEntry.symbol == symbol,
                        ActiveEntry.status == "active",
                    )
                ).scalars().all()
                active = [
                    {
                        "entry_price": a.entry_price,
                        "stop_price": a.stop_price,
                        "target_1": a.target_1,
                        "target_2": a.target_2,
                        "alert_type": a.alert_type,
                    }
                    for a in active_rows
                ]

                try:
                    signals = evaluate_rules(
                        symbol, intraday, prior_day, active,
                        spy_context=spy_ctx,
                        is_cooled_down=symbol in cooled_symbols,
                        fired_today=fired_today,
                    )
                except Exception:
                    logger.exception("Error evaluating %s for user %d", symbol, user_id)
                    continue

                for signal in signals:
                    # Dedup check
                    key = (symbol, signal.alert_type.value)
                    if key in fired_today:
                        continue

                    # Record alert
                    alert = Alert(
                        user_id=user_id,
                        symbol=signal.symbol,
                        alert_type=signal.alert_type.value,
                        direction=signal.direction,
                        price=signal.price,
                        entry=signal.entry,
                        stop=signal.stop,
                        target_1=signal.target_1,
                        target_2=signal.target_2,
                        confidence=signal.confidence,
                        message=signal.message,
                        session_date=session_date,
                    )
                    db.add(alert)
                    fired_today.add(key)

                    # Create active entry for BUY signals
                    _non_entry_types = {
                        AlertType.GAP_FILL, AlertType.SUPPORT_BREAKDOWN,
                        AlertType.RESISTANCE_PRIOR_HIGH, AlertType.PDH_REJECTION,
                        AlertType.HOURLY_RESISTANCE_APPROACH,
                        AlertType.MA_RESISTANCE, AlertType.RESISTANCE_PRIOR_LOW,
                        AlertType.OPENING_RANGE_BREAKDOWN,
                    }
                    if signal.direction == "BUY" and signal.alert_type not in _non_entry_types:
                        db.add(ActiveEntry(
                            user_id=user_id,
                            symbol=symbol,
                            entry_price=signal.entry,
                            stop_price=signal.stop,
                            target_1=signal.target_1,
                            target_2=signal.target_2,
                            alert_type=signal.alert_type.value,
                            session_date=session_date,
                        ))

                    # Stop/target: close entries and add cooldown
                    if signal.alert_type in (AlertType.STOP_LOSS_HIT, AlertType.AUTO_STOP_OUT):
                        for ae in active_rows:
                            ae.status = "closed"
                        db.add(Cooldown(
                            user_id=user_id,
                            symbol=symbol,
                            cooldown_until="",
                            reason=signal.alert_type.value,
                            session_date=session_date,
                        ))

                    if signal.alert_type in (AlertType.TARGET_1_HIT, AlertType.TARGET_2_HIT):
                        for ae in active_rows:
                            ae.status = "closed"

                    # Push to SSE
                    try:
                        from app.background.alert_bus import publish
                        publish(user_id, {
                            "symbol": signal.symbol,
                            "alert_type": signal.alert_type.value,
                            "direction": signal.direction,
                            "price": signal.price,
                            "message": signal.message,
                        })
                    except Exception:
                        pass

                    total_alerts += 1
                    logger.info(
                        "ALERT: user=%d %s %s %s @ $%.2f",
                        user_id, signal.direction, signal.symbol,
                        signal.alert_type.value, signal.price,
                    )

        db.commit()

    logger.info("Poll complete: %d alerts across %d users", total_alerts, len(pro_users))
    return total_alerts
