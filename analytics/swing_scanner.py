"""Swing Trade Scanner — deterministic swing qualification (spec 56).

Pure deterministic math via analytics.swing_quality — no LLM, no AI call.
The only market gate is SPY vs its 21 EMA:

  * SPY at/above the 21 EMA -> bounce mode (key-MA defense / reclaim)
  * SPY below the 21 EMA    -> RSI mode (oversold RSI-30 recovery)

Each entry is typed by the MA it defended (swing_bounce_ema50, … / swing_rsi_30)
so the per-MA toggles in alert_type_config decide which ones route a Telegram
notification. Disabled types still record silently for EOD review.

LONG-only. Each cycle also runs an exit pass: an open swing fires a swing_exit
when its symbol's daily close drops below the stored stop (the entry-day low).
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# Per (symbol, alert_type) cooldown — the same swing alert won't re-fire
# within this many minutes. DB-backed, so it survives process restarts.
_COOLDOWN_MINUTES = 60

# Persistent rate-limit feature keys (shared usage_limits table)
_FEATURE_SWING = "swing_telegram"
_FEATURE_SWING_NOTIFIED = "swing_cap_notified"

_CONVICTION_RANK = {"low": 1, "medium": 2, "high": 3}


# ── Rate-limit helpers ───────────────────────────────────────────────


def _db_get_count(db, user_id: int, feature: str, usage_date: str) -> int:
    from sqlalchemy import text
    try:
        row = db.execute(
            text(
                "SELECT usage_count FROM usage_limits "
                "WHERE user_id = :uid AND feature = :f AND usage_date = :d"
            ),
            {"uid": user_id, "f": feature, "d": usage_date},
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _db_increment_count(db, user_id: int, feature: str, usage_date: str) -> None:
    from sqlalchemy import text
    try:
        db.execute(
            text(
                "INSERT INTO usage_limits (user_id, feature, usage_date, usage_count) "
                "VALUES (:uid, :f, :d, 1) "
                "ON CONFLICT (user_id, feature, usage_date) "
                "DO UPDATE SET usage_count = usage_limits.usage_count + 1"
            ),
            {"uid": user_id, "f": feature, "d": usage_date},
        )
        db.commit()
    except Exception:
        logger.exception("swing usage_limits increment failed uid=%s", user_id)


def _db_mark_notified(db, user_id: int, feature: str, usage_date: str) -> bool:
    from sqlalchemy import text
    try:
        res = db.execute(
            text(
                "INSERT INTO usage_limits (user_id, feature, usage_date, usage_count) "
                "VALUES (:uid, :f, :d, 1) "
                "ON CONFLICT (user_id, feature, usage_date) DO NOTHING"
            ),
            {"uid": user_id, "f": feature, "d": usage_date},
        )
        db.commit()
        return bool(getattr(res, "rowcount", 0))
    except Exception:
        return False


# ── Alert-type routing (per-MA toggles in alert_type_config) ─────────


def _alert_type_for(q) -> str:
    """Map a SwingQualification to its alert_type_config key.

    Uses the first rule hit (rules[0].rule) — entry_level alone is
    ambiguous (e.g., both ma_bounce and golden_cross_retest can have
    entry_level='EMA 50'). Falls back to entry_level for legacy
    ma_hold/ma_reclaim rules which encode the MA in the level.
    """
    rule = q.rules[0].rule if q.rules else ""
    if rule == "rsi_recovery":
        return "swing_rsi_30"
    if rule == "ema_8_21_cross":
        return "swing_8_21_cross"
    if rule == "golden_cross_retest":
        return "swing_golden_cross_retest"
    if rule == "52w_high_retest":
        return "swing_52w_high_retest"
    if rule == "5day_low_reclaim":
        return "swing_5day_low_reclaim"
    # Legacy bounce rules — encode the MA in the type name.
    return "swing_bounce_" + (q.entry_level or "").lower().replace(" ", "")


def _enabled_alert_types(db) -> set[str]:
    """The set of alert types currently enabled in alert_type_config. Fails
    closed (empty set) on error — a disabled/unknown type records silently."""
    from sqlalchemy import select
    from app.models.alert_type_config import AlertTypeConfig
    try:
        rows = db.execute(
            select(AlertTypeConfig.alert_type, AlertTypeConfig.enabled)
        ).all()
        return {at for at, en in rows if en}
    except Exception:
        logger.exception("swing scan: alert_type_config read failed — fail closed")
        return set()


def _on_cooldown(db, symbol: str, alert_type: str) -> bool:
    """True if this symbol+alert_type already fired within the cooldown window.
    Fails open (allows the fire) on error — better a possible dup than a miss."""
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.models.alert import Alert
    cutoff = datetime.utcnow() - timedelta(minutes=_COOLDOWN_MINUTES)
    try:
        hit = db.execute(
            select(Alert.id)
            .where(
                Alert.symbol == symbol,
                Alert.alert_type == alert_type,
                Alert.created_at >= cutoff,
            )
            .limit(1)
        ).scalars().first()
        return hit is not None
    except Exception:
        logger.exception("swing cooldown check failed %s %s", symbol, alert_type)
        return False


# ── Market data ──────────────────────────────────────────────────────


def _fetch_daily(symbol: str):
    """Fetch ~2 years of daily bars for a symbol. None on failure."""
    import yfinance as yf
    try:
        hist = yf.Ticker(symbol).history(period="2y", interval="1d")
        if hist is None or hist.empty:
            return None
        return hist
    except Exception:
        logger.exception("swing: daily fetch failed for %s", symbol)
        return None


def _market_regime() -> str:
    """Read SPY once and decide the regime for the whole cycle — SPY at/above
    its 21 EMA -> bounce mode, below -> RSI mode."""
    from analytics.swing_quality import REGIME_BOUNCE, spy_regime
    hist = _fetch_daily("SPY")
    if hist is None:
        logger.warning("swing scan: SPY fetch failed — defaulting to bounce regime")
        return REGIME_BOUNCE
    return spy_regime(hist)


# ── Formatting + delivery ───────────────────────────────────────────


def _format_entry_msg(q) -> str:
    mode = "Bounce" if q.mode == "bounce" else "RSI recovery"
    lines = [f"SWING LONG ({mode}) — {q.symbol} ${q.close:.2f}"]
    parts = [f"Entry ${q.entry:.2f}", f"Stop ${q.stop:.2f}"]
    if q.target_1:
        parts.append(f"T1 ${q.target_1:.2f}")
    if q.target_2:
        parts.append(f"T2 ${q.target_2:.2f}")
    lines.append(" · ".join(parts))
    lines.append(f"Setup: {q.summary}")
    lines.append("Timeframe: 3-10 days")
    if q.rules:
        lines.append("Why: " + "; ".join(h.detail for h in q.rules))
    return "\n".join(lines)


def _format_exit_msg(symbol: str, close: float, stop: float) -> str:
    return (
        f"SWING EXIT — {symbol} ${close:.2f}\n"
        f"Closed ${close:.2f}, below the stop ${stop:.2f} (entry-day low). "
        f"Swing thesis broken — exit the position."
    )


def _send_telegram(chat_id: str, body: str) -> bool:
    import requests
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": body},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        logger.exception("swing telegram failed chat_id=%s", chat_id)
        return False


def _user_wants_swing(user, direction: str, conviction: str | None) -> bool:
    if not getattr(user, "swing_alerts_enabled", True):
        return False
    min_rank = _CONVICTION_RANK.get(
        (getattr(user, "min_conviction", None) or "medium").lower(), 2
    )
    sig_rank = _CONVICTION_RANK.get((conviction or "medium").lower(), 2)
    if sig_rank < min_rank:
        return False
    dirs_csv = getattr(user, "alert_directions", None) or "LONG,SHORT,RESISTANCE,EXIT"
    allowed = {d.strip().upper() for d in dirs_csv.split(",") if d.strip()}
    return direction.upper() in allowed


def _deliver_entry(db, q, users, session: str, get_limits, enabled_types) -> int:
    """Persist + notify a swing entry. Returns Telegram deliveries.

    Typed by its entry MA (swing_bounce_ema50 etc / swing_rsi_30). If that type
    is disabled in alert_type_config the alert is still recorded with
    suppressed_reason set — visible for EOD review — but not delivered."""
    from app.models.alert import Alert

    conviction = "HIGH" if len(q.rules) >= 2 else "MEDIUM"
    entry = q.entry
    current = q.close
    alert_type = _alert_type_for(q)
    routed = alert_type in enabled_types

    # Proximity gate — only alert when price is actually near the entry level,
    # so we never chase a close that ran far above the defended MA.
    if entry > 0 and current > 0:
        distance_pct = abs(current - entry) / current * 100
        if distance_pct > 1.5:
            logger.info(
                "swing %s: skip — close $%.2f is %.2f%% above entry $%.2f",
                q.symbol, current, distance_pct, entry,
            )
            return 0

    # Cooldown — the same symbol+type won't re-fire within _COOLDOWN_MINUTES.
    if _on_cooldown(db, q.symbol, alert_type):
        logger.info("swing %s: %s on cooldown", q.symbol, alert_type)
        return 0

    body = _format_entry_msg(q)
    score = {"HIGH": 85, "MEDIUM": 65}.get(conviction, 65)
    suppressed = None if routed else "type_not_enabled"
    delivered = 0

    for user in users:
        uid = user.id
        chat_id = user.telegram_chat_id or ""

        try:
            db.add(Alert(
                user_id=uid,
                symbol=q.symbol,
                alert_type=alert_type,
                direction="LONG",
                price=q.close,
                entry=entry,
                stop=q.stop,
                target_1=q.target_1,
                target_2=q.target_2,
                confidence=conviction.lower(),
                message=body,
                score=score,
                session_date=session,
                suppressed_reason=suppressed,
            ))
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("swing entry insert failed uid=%s sym=%s", uid, q.symbol)

        # Disabled type -> recorded silently for EOD review, no delivery.
        if not routed:
            continue
        if not chat_id or not _user_wants_swing(user, "LONG", conviction):
            continue

        tier = "free"
        sub = getattr(user, "subscription", None)
        if sub:
            tier = getattr(sub, "tier", "free") or "free"
        cap = get_limits(tier).get("swing_alerts_per_day") if get_limits else None
        if cap is not None:
            used = _db_get_count(db, uid, _FEATURE_SWING, session)
            if used >= cap:
                if _db_mark_notified(db, uid, _FEATURE_SWING_NOTIFIED, session):
                    _send_telegram(
                        chat_id,
                        f"Daily swing-alert cap reached ({cap}). "
                        f"Upgrade to Pro for unlimited swing alerts.",
                    )
                continue

        if _send_telegram(chat_id, body):
            _db_increment_count(db, uid, _FEATURE_SWING, session)
            delivered += 1

    if not routed:
        logger.info("swing %s: %s recorded silently (type disabled)", q.symbol, alert_type)
    return delivered


def _process_exits(db, symbol: str, hist, users, session: str, enabled_types) -> int:
    """Fire swing_exit when an open swing on this symbol closes below its stored
    stop (the entry-day low). Returns Telegram deliveries."""
    from sqlalchemy import desc, or_, select
    from app.models.alert import Alert
    from analytics.swing_quality import swing_exit_triggered

    try:
        latest_close = float(hist["Close"].iloc[-1])
    except Exception:
        return 0

    routed = "swing_exit" in enabled_types
    suppressed = None if routed else "type_not_enabled"
    delivered = 0
    for user in users:
        uid = user.id
        # Most recent DELIVERED swing entry for this symbol/user. Suppressed
        # (non-routed) entries aren't live positions, so they get no exit.
        entry_alert = db.execute(
            select(Alert)
            .where(
                Alert.user_id == uid,
                Alert.symbol == symbol,
                or_(
                    Alert.alert_type.like("swing_bounce_%"),
                    Alert.alert_type == "swing_rsi_30",
                ),
                Alert.suppressed_reason.is_(None),
            )
            .order_by(desc(Alert.id))
            .limit(1)
        ).scalars().first()
        if entry_alert is None or not entry_alert.stop:
            continue
        # Already exited? An exit recorded after that entry closes the swing.
        already_exited = db.execute(
            select(Alert.id)
            .where(
                Alert.user_id == uid,
                Alert.symbol == symbol,
                Alert.alert_type == "swing_exit",
                Alert.id > entry_alert.id,
            )
            .limit(1)
        ).scalars().first()
        if already_exited is not None:
            continue
        # Open swing — exit only on a daily CLOSE below the stop.
        if not swing_exit_triggered(entry_alert.stop, latest_close):
            continue

        body = _format_exit_msg(symbol, latest_close, float(entry_alert.stop))
        try:
            db.add(Alert(
                user_id=uid,
                symbol=symbol,
                alert_type="swing_exit",
                direction="EXIT",
                price=latest_close,
                stop=entry_alert.stop,
                message=body,
                score=70,
                session_date=session,
                suppressed_reason=suppressed,
            ))
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("swing exit insert failed uid=%s sym=%s", uid, symbol)
            continue

        chat_id = user.telegram_chat_id or ""
        if routed and chat_id and getattr(user, "swing_alerts_enabled", True):
            if _send_telegram(chat_id, body):
                delivered += 1

    return delivered


# ── Main cycle ───────────────────────────────────────────────────────


def swing_scan_cycle(sync_session_factory, force: bool = False, scan_email: Optional[str] = None) -> int:
    """Run one swing scan pass — entries + exits. Returns Telegram deliveries.

    `force=True` bypasses the market-hours gate. Used by the daily EOD
    cron (4:10 PM ET) where the daily bar has just closed but the
    is_market_hours() helper already reports market closed.

    `scan_email` overrides the SCAN_USER_EMAIL env var — used by the
    manual /swing/scan endpoint to scan the authenticated user's
    watchlist instead of the default cost-control single-user filter.
    None falls back to env var (default behaviour for scheduler runs).
    """
    if os.environ.get("SWING_SCAN_ENABLED", "true").lower() in ("0", "false", "no"):
        logger.info("swing scan: disabled via env")
        return 0

    # Only scan during market hours unless force=True — swing entries need
    # live price vs level. Skips weekends/holidays/after-hours for equities.
    # Crypto symbols in watchlists still get scanned (they trade 24/7).
    if not force:
        try:
            from analytics.market_hours import is_market_hours
            if not is_market_hours():
                logger.debug("swing scan: market closed, skipping")
                return 0
        except Exception:
            pass  # if helper unavailable, run anyway

    session = date.today().isoformat()

    # The only market gate: SPY above its 21 EMA -> bounce mode; below -> RSI
    # mode. In a weak market we switch the qualifier rather than skip swings.
    regime = _market_regime()
    logger.info("swing scan: regime=%s", regime)

    from sqlalchemy import select
    from app.models.user import User
    from app.models.watchlist import WatchlistItem

    try:
        from app.tier import get_limits
    except Exception:
        get_limits = None

    delivered = 0
    with sync_session_factory() as db:
        # Per-type routing — which swing alert types are enabled in Settings.
        enabled_types = _enabled_alert_types(db)

        # Build per-symbol → users-watching map from real watchlists.
        # Only scan symbols at least one Telegram-enabled user is watching.
        # Cost-control: SCAN_USER_EMAIL restricts to one user's watchlist
        # for scheduled runs. The manual /swing/scan endpoint passes
        # scan_email=<authenticated user> to override — so tapping the
        # button always scans the logged-in user's own watchlist
        # regardless of which email the env var defaults to.
        import os as _os_scan
        _scan_email = (scan_email or _os_scan.environ.get("SCAN_USER_EMAIL", "vbolofinde@gmail.com") or "").strip().lower()
        _q = (
            select(WatchlistItem.symbol, WatchlistItem.user_id, User)
            .join(User, User.id == WatchlistItem.user_id)
            .where(User.telegram_enabled.is_(True))
        )
        if _scan_email:
            _q = _q.where(User.email == _scan_email)
        rows = db.execute(_q).all()
        if _scan_email:
            logger.info("swing scan: SCAN_USER_EMAIL=%s — %d rows", _scan_email, len(rows))

        symbol_users: dict[str, list] = {}
        for sym, _uid, user in rows:
            symbol_users.setdefault(sym, []).append(user)

        symbols = sorted(symbol_users.keys())
        if not symbols:
            logger.info("swing scan: no watchlist symbols, skipping")
            return 0

        logger.info("swing scan: %d watchlist symbols across %d user-rows",
                    len(symbols), len(rows))

        from analytics.swing_quality import evaluate_swing_quality

        fetch_failures = 0
        qualified = 0
        for symbol in symbols:
            hist = _fetch_daily(symbol)
            if hist is None:
                fetch_failures += 1
                continue
            users = symbol_users[symbol]

            # Entry — qualify the symbol for the current regime.
            q = evaluate_swing_quality(symbol, hist, regime, session_date=session)
            if q is not None:
                qualified += 1
                delivered += _deliver_entry(db, q, users, session, get_limits, enabled_types)

            # Exit — fire when an open swing on this symbol closed below its stop.
            delivered += _process_exits(db, symbol, hist, users, session, enabled_types)

    logger.info(
        "swing scan complete: regime=%s, %d symbols, %d qualified, %d fetch fails, %d deliveries",
        regime, len(symbols), qualified, fetch_failures, delivered,
    )
    # Attach diagnostics so the manual endpoint can surface them in the UI
    # without us needing Railway log access every time a scan returns 0.
    swing_scan_cycle.last_run = {
        "regime": regime,
        "symbols_scanned": len(symbols),
        "symbols_qualified": qualified,
        "fetch_failures": fetch_failures,
        "delivered": delivered,
    }
    return delivered
