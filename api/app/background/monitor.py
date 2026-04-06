"""Multi-tenant alert monitor — runs inside FastAPI via APScheduler.

For each Pro user, polls their watchlist, evaluates rules, fires alerts.
Market data is deduplicated: same symbol across users = one yfinance fetch.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from alert_config import COOLDOWN_MINUTES  # noqa: E402
from analytics.intraday_data import fetch_intraday, fetch_prior_day, get_spy_context  # noqa: E402
from analytics.intraday_rules import AlertSignal, AlertType, evaluate_rules  # noqa: E402
from analytics.market_hours import is_market_hours, is_market_hours_for_symbol  # noqa: E402

logger = logging.getLogger("monitor")

# Burst cooldown: prevent rapid BUY notification spam (in-memory, resets on restart)
_last_buy_notify: Dict[str, "datetime"] = {}  # {symbol: datetime}
_last_buy_session: str = ""

# Track SPY inside day notice (one per session)
_spy_inside_day_notified: bool = False

# Direction lock: once BUY/SHORT fires for a symbol, suppress opposite for 30 min
_direction_lock: Dict[str, tuple] = {}  # {symbol: (direction, datetime)}

# SPY SHORT gate: when SPY gets a SHORT alert, suppress equity BUY entries for 30 min
_spy_short_time: "datetime | None" = None


def poll_all_users(sync_session_factory) -> int:
    """Run one poll cycle for all Pro users.

    Uses synchronous SQLAlchemy since this runs in a background thread.
    Returns total alerts fired across all users.
    """
    try:
        return _poll_all_users_inner(sync_session_factory)
    except Exception:
        logger.exception("Poll cycle FAILED — will retry next cycle")
        return 0


def _poll_all_users_inner(sync_session_factory) -> int:
    from app.models.user import Subscription, User  # noqa: E402
    from app.models.watchlist import WatchlistItem  # noqa: E402
    from app.models.alert import ActiveEntry, Alert, Cooldown  # noqa: E402

    global _last_buy_session, _spy_inside_day_notified, _spy_short_time
    session_date = date.today().isoformat()
    # Crypto uses UTC date so dedup resets at midnight UTC (not server time)
    _utc_date = datetime.utcnow().date().isoformat()
    total_alerts = 0

    # Clear stale burst cooldown tracking on new session
    if _last_buy_session != session_date:
        _last_buy_notify.clear()
        _spy_inside_day_notified = False
        _last_buy_session = session_date

    with sync_session_factory() as db:
        # Get Pro + Premium users (paid or active trial)
        from datetime import datetime as _dt, timezone as _tz
        _now = _dt.now(_tz.utc)
        pro_users = db.execute(
            select(User.id).join(Subscription).where(
                Subscription.status == "active",
                (
                    Subscription.tier.in_(["pro", "premium", "admin"])
                    | (
                        (Subscription.trial_ends_at.isnot(None))
                        & (Subscription.trial_ends_at > _now)
                    )
                ),
            )
        ).scalars().all()

        if not pro_users:
            logger.info("No Pro/Premium/Trial users — skipping poll")
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

        for uid, syms in user_symbols.items():
            logger.info("User %d watchlist: %s", uid, ", ".join(syms) if syms else "(empty)")

        if not all_symbols:
            return 0

        # Filter to symbols whose market is open (crypto always, stocks during hours)
        active_symbols = {s for s in all_symbols if is_market_hours_for_symbol(s)}
        logger.info("Active symbols (market open): %s", ", ".join(sorted(active_symbols)) if active_symbols else "(none)")
        if not active_symbols:
            logger.info("No active market symbols — skipping poll")
            return 0

        # Deduplicated market data fetches (also write to app cache for API reuse)
        from app.cache import cache_get, cache_set

        intraday_cache: dict[str, object] = {}
        prior_day_cache: dict[str, object] = {}
        for symbol in active_symbols:
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

        # Regime narrator: check for SPY regime shift (L3 parity)
        try:
            from analytics.regime_narrator import check_regime_shift
            check_regime_shift(spy_ctx)
        except Exception:
            logger.debug("Regime narrator check failed", exc_info=True)

        # Compute spy_gate for alert gating (parity with V1 monitor.py:241-310)
        _spy_gate = None
        try:
            from analytics.intraday_rules import compute_spy_gate
            from analytics.intraday_data import compute_vwap, compute_opening_range
            _spy_bars = intraday_cache.get("SPY")
            if _spy_bars is not None and not (hasattr(_spy_bars, "empty") and _spy_bars.empty):
                _spy_vwap = compute_vwap(_spy_bars)
                _spy_gate = compute_spy_gate(_spy_bars, _spy_vwap)

                # Morning low check
                _spy_or = compute_opening_range(_spy_bars)
                if _spy_or and _spy_or.get("or_complete"):
                    _spy_gate["morning_low"] = _spy_or["or_low"]
                    _spy_last_close = float(_spy_bars.iloc[-1]["Close"])
                    _spy_gate["below_morning_low"] = _spy_last_close < _spy_or["or_low"]
                else:
                    _spy_gate["below_morning_low"] = False
                    _spy_gate["morning_low"] = 0

                # SPY inside day detection
                _spy_prior = prior_day_cache.get("SPY")
                if _spy_prior and _spy_or and _spy_or.get("or_complete"):
                    _pdh = _spy_prior.get("high", 0)
                    _pdl = _spy_prior.get("low", 0)
                    _today_high = float(_spy_bars["High"].max())
                    _today_low = float(_spy_bars["Low"].min())
                    _spy_gate["inside_day"] = _today_high < _pdh and _today_low > _pdl
                else:
                    _spy_gate["inside_day"] = False
        except Exception:
            logger.debug("SPY gate computation failed", exc_info=True)

        # Load user objects for notification routing
        user_rows = {u.id: u for u in db.execute(
            select(User).where(User.id.in_(pro_users))
        ).scalars().all()}

        # Evaluate per user
        for user_id in pro_users:
            symbols = user_symbols.get(user_id, [])
            if not symbols:
                continue

            # Load user's fired alerts for dedup (equity session + crypto UTC session)
            _dedup_dates = {session_date, _utc_date}
            db_alerts = db.execute(
                select(Alert.symbol, Alert.alert_type, Alert.session_date).where(
                    Alert.user_id == user_id, Alert.session_date.in_(_dedup_dates)
                )
            ).all()
            # Build per-session dedup sets
            _fired_equity: set[tuple[str, str]] = {(a[0], a[1]) for a in db_alerts if a[2] == session_date}
            _fired_crypto: set[tuple[str, str]] = {(a[0], a[1]) for a in db_alerts if a[2] == _utc_date}

            # Load cooldowns
            cooldown_rows = db.execute(
                select(Cooldown.symbol).where(
                    Cooldown.user_id == user_id, Cooldown.session_date == session_date
                )
            ).scalars().all()
            cooled_symbols = set(cooldown_rows)

            # Post-stop re-fire: after stop-out + cooldown expiry, allow BUY signals
            # to re-fire for the same symbol (parity with V1 monitor.py:207-226)
            _stop_types = {"stop_loss_hit"}
            stopped_symbols = {a[0] for a in db_alerts if a[1] in _stop_types}
            _sell_types = _stop_types | {
                "target_1_hit", "target_2_hit", "support_breakdown",
                "resistance_prior_high", "resistance_prior_low",
                "hourly_resistance_approach", "ma_resistance",
                "weekly_high_resistance", "ema_resistance",
                "opening_range_breakdown",
            }
            for sym in stopped_symbols:
                if sym not in cooled_symbols:
                    fired_today = {
                        (s, at) for s, at in fired_today
                        if s != sym or at in _sell_types
                    }

            # Load alert category preferences for this user
            try:
                from app.models.alert_prefs import UserAlertCategoryPref
                from alert_config import ALERT_TYPE_TO_CATEGORY, EXIT_ALERT_TYPES
                pref_rows = db.execute(
                    select(UserAlertCategoryPref.category_id, UserAlertCategoryPref.enabled).where(
                        UserAlertCategoryPref.user_id == user_id
                    )
                ).all()
                _cat_prefs = {r[0]: bool(r[1]) for r in pref_rows}
                # Get min_score from user
                _user_row = db.execute(
                    select(User.min_alert_score).where(User.id == user_id)
                ).scalar_one_or_none()
                _min_score = _user_row or 0
            except Exception:
                _cat_prefs = {}
                _min_score = 0

            for symbol in symbols:
                # Skip symbols whose market is closed (crypto always passes)
                if not is_market_hours_for_symbol(symbol):
                    continue

                # Crypto uses UTC date for session so dedup resets at midnight UTC
                from config import is_crypto_alert_symbol
                _is_crypto = is_crypto_alert_symbol(symbol)
                _sym_session = _utc_date if _is_crypto else session_date
                fired_today = _fired_crypto if _is_crypto else _fired_equity

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

                # BUG-10 fix: check if current price reached any active entry's T1
                # Only notify if user has an OPEN real trade (clicked "Took")
                # One T1 notification per symbol per session — no spam
                _t1_symbol_key = (symbol, "_t1_notify")
                if (active_rows and intraday is not None
                        and not (hasattr(intraday, "empty") and intraday.empty)
                        and _t1_symbol_key not in fired_today):
                    # Check if user has an open real trade for this symbol
                    from app.models.paper_trade import RealTrade
                    _open_trade_row = db.execute(
                        select(RealTrade.id, RealTrade.alert_id).where(
                            RealTrade.user_id == user_id,
                            RealTrade.symbol == symbol,
                            RealTrade.status == "open",
                        ).limit(1)
                    ).first()
                    _has_open_trade = _open_trade_row[0] if _open_trade_row else None
                    _trade_alert_id = _open_trade_row[1] if _open_trade_row else None

                    if _has_open_trade:
                        _last_price = float(intraday.iloc[-1]["Close"])
                        # Find the best active entry with T1
                        _best_ae = None
                        for ae in active_rows:
                            _t1 = ae.target_1 or 0
                            _entry = ae.entry_price or 0
                            if _t1 > 0 and _entry > 0 and _last_price >= _t1 * 0.998:
                                _best_ae = ae
                                break

                        if _best_ae:
                            ae = _best_ae
                            _t1 = ae.target_1
                            _entry = ae.entry_price
                            fired_today.add(_t1_symbol_key)
                            _pnl = round(_last_price - _entry, 2)
                            _pnl_pct = round((_pnl / _entry) * 100, 2)
                            _user = user_rows.get(user_id)
                            if _user and _user.telegram_enabled and _user.telegram_chat_id:
                                try:
                                    from alerting.notifier import _send_telegram_to
                                    _at_resistance = False
                                    _resistance_label = ""
                                    if prior_day:
                                        _pdh = prior_day.get("high", 0)
                                        if _pdh > 0 and abs(_t1 - _pdh) / _pdh < 0.003:
                                            _at_resistance = True
                                            _resistance_label = "PDH"
                                    _reversal_hint = ""
                                    if _at_resistance:
                                        _reversal_hint = f"\nAt {_resistance_label} resistance — potential SHORT reversal"

                                    _msg = (
                                        f"<b>T1 REACHED — {symbol} ${_last_price:.2f}</b>\n"
                                        f"Your LONG from ${_entry:.2f} is at target\n"
                                        f"P&L: ${_pnl:.2f} ({_pnl_pct:+.1f}%)\n"
                                        f"Take profits or trail stop"
                                        f"{_reversal_hint}"
                                    )
                                    # Use alert_id for exit button (bot looks up alerts table)
                                    # Falls back to trade_id if no alert_id linked
                                    _exit_id = _trade_alert_id or _has_open_trade
                                    _buttons = {
                                        "inline_keyboard": [[
                                            {"text": "\U0001f6d1 Exit Trade", "callback_data": f"exit:{_exit_id}"},
                                        ]]
                                    }
                                    _send_telegram_to(_msg, _user.telegram_chat_id, reply_markup=_buttons)
                                    logger.info("T1 NOTIFY: user=%d %s T1=$%.2f reached, entry=$%.2f", user_id, symbol, _t1, _entry)

                                    # Persist in DB so dedup survives across poll cycles
                                    _t1_alert = Alert(
                                        user_id=user_id,
                                        symbol=symbol,
                                        alert_type="_t1_notify",
                                        direction="NOTICE",
                                        price=_last_price,
                                        session_date=_sym_session,
                                    )
                                    db.add(_t1_alert)
                                except Exception:
                                    pass

                # ENHANCEMENT-3: Removed — retest bounce alerts were too noisy.
                # Structural entries (PDL reclaim, consolidation breakout, MA bounce)
                # already cover the important re-entry scenarios.

                try:
                    signals = evaluate_rules(
                        symbol, intraday, prior_day, active,
                        spy_context=spy_ctx,
                        spy_gate=_spy_gate,
                        is_cooled_down=symbol in cooled_symbols,
                        fired_today=fired_today,
                    )
                except Exception:
                    logger.exception("Error evaluating %s for user %d", symbol, user_id)
                    continue

                # BUG-4 fix: adjust BUY targets to nearest overhead resistance
                if prior_day and signals:
                    _overhead = []
                    _pdh = prior_day.get("high", 0)
                    _ema20 = prior_day.get("ema20", 0)
                    _ema50 = prior_day.get("ema50", 0)
                    _nearest_sup = prior_day.get("nearest_support", 0)
                    for _lv in [_pdh, _ema20, _ema50, _nearest_sup]:
                        if _lv and _lv > 0:
                            _overhead.append(_lv)

                    for sig in signals:
                        if sig.direction == "BUY" and sig.entry and sig.target_1:
                            # Find nearest overhead resistance above entry but below current T1
                            _closer = [r for r in _overhead if sig.entry < r < sig.target_1]
                            if _closer:
                                _new_t1 = min(_closer)
                                sig.target_2 = sig.target_1  # old T1 becomes T2
                                sig.target_1 = round(_new_t1, 2)

                # Per-symbol budget: max 2 entry alerts per symbol per session
                _entry_count = db.execute(
                    select(func.count()).where(
                        Alert.user_id == user_id,
                        Alert.symbol == symbol,
                        Alert.session_date == _sym_session,
                        Alert.direction.in_(["BUY", "SHORT"]),
                    )
                ).scalar() or 0

                for signal in signals:
                  try:
                    # SPY SHORT gate: if SPY shorted recently, suppress equity BUY entries
                    if (signal.direction == "BUY"
                            and not _is_crypto
                            and symbol != "SPY"
                            and _spy_short_time is not None
                            and (datetime.utcnow() - _spy_short_time).total_seconds() < 1800):
                        logger.info("SPY GATE: %s BUY suppressed — SPY SHORT fired %ds ago",
                                    symbol, int((datetime.utcnow() - _spy_short_time).total_seconds()))
                        continue

                    # Enforce per-symbol budget: max 2 entries per session
                    if signal.direction in ("BUY", "SHORT") and _entry_count >= 2:
                        logger.info("BUDGET: %s %s suppressed — %d entries already this session",
                                    symbol, signal.alert_type.value, _entry_count)
                        continue
                    # Dedup check
                    key = (symbol, signal.alert_type.value)
                    if key in fired_today:
                        continue

                    # BUG-5 fix: suppress conflicting direction alerts
                    # Don't send SHORT when user has active LONG, and vice versa
                    if active_rows and signal.direction in ("BUY", "SHORT"):
                        _active_dirs = {a.alert_type for a in active_rows}
                        _has_long = any(not at.startswith("short") and not at.startswith("ema_rejection") for at in _active_dirs)
                        _has_short = any(at.startswith("short") or at.startswith("ema_rejection") or at.startswith("consol_breakout_short") for at in _active_dirs)
                        if signal.direction == "SHORT" and _has_long:
                            logger.info("SUPPRESSED: %s %s SHORT — active LONG entry exists", symbol, signal.alert_type.value)
                            continue
                        if signal.direction == "BUY" and _has_short:
                            logger.info("SUPPRESSED: %s %s BUY — active SHORT entry exists", symbol, signal.alert_type.value)
                            continue

                    # BUG-7 fix: suppress BUY breakout at resistance when user has active LONG from below
                    # The breakout level IS the user's exit point, not a new entry
                    if active_rows and signal.direction == "BUY":
                        _breakout_types = {"consol_breakout_long", "prior_day_high_breakout",
                                           "inside_day_breakout", "weekly_high_breakout",
                                           "opening_range_breakout", "first_hour_high_breakout"}
                        if signal.alert_type.value in _breakout_types:
                            for ae in active_rows:
                                t1 = ae.target_1 or 0
                                if t1 > 0 and signal.entry and abs(signal.entry - t1) / t1 < 0.01:
                                    logger.info(
                                        "SUPPRESSED: %s %s BUY — breakout near active LONG T1 $%.2f (exit point, not entry)",
                                        symbol, signal.alert_type.value, t1,
                                    )
                                    continue

                    # Direction lock: suppress ALL alerts (same or opposite) within 30 min
                    # Prevents: BUY→SHORT flip-flop AND SHORT→SHORT spam at same level
                    if signal.direction in ("BUY", "SHORT"):
                        _lock = _direction_lock.get(symbol)
                        if _lock:
                            _locked_dir, _locked_time = _lock
                            _elapsed = (datetime.utcnow() - _locked_time).total_seconds()
                            if _elapsed < 1800:  # 30 min cooldown
                                if _locked_dir != signal.direction:
                                    logger.info(
                                        "DIRECTION LOCK: %s %s suppressed — %s fired %ds ago",
                                        symbol, signal.direction, _locked_dir, int(_elapsed),
                                    )
                                    continue
                                elif _locked_dir == signal.direction:
                                    # Same direction repeat — suppress SHORT spam
                                    logger.info(
                                        "REPEAT LOCK: %s %s suppressed — same direction fired %ds ago",
                                        symbol, signal.direction, int(_elapsed),
                                    )
                                    continue

                    # Generate AI narrative for education context
                    _narrative = ""
                    try:
                        from analytics.ai_narrator import generate_narrative
                        _narrative = generate_narrative(signal) or ""
                    except Exception:
                        pass

                    # Cluster narrator: richer AI synthesis for multi-signal confluence
                    if "[+" in (signal.message or "") and "confirming:" in (signal.message or ""):
                        try:
                            import re as _re
                            _match = _re.search(r"\[\+\d+ confirming: (.+?)\]", signal.message)
                            if _match:
                                _conf_types = [t.strip() for t in _match.group(1).split(",")]
                                from analytics.cluster_narrator import narrate_cluster
                                _cluster = narrate_cluster(signal, _conf_types)
                                if _cluster:
                                    _narrative = _cluster
                        except Exception:
                            logger.debug("Cluster narrator failed for %s", symbol)

                    # Coerce numpy types to native Python (psycopg2 can't serialize np.float64)
                    def _py(v):
                        if v is None:
                            return None
                        try:
                            return v.item()  # numpy scalar → Python native
                        except (AttributeError, ValueError):
                            pass
                        # Force float/int conversion for any numeric type
                        try:
                            if isinstance(v, (int, float)):
                                return v
                            return float(v)
                        except (TypeError, ValueError):
                            return v

                    # Clean message — keep useful details, strip SPY noise
                    import re as _re_clean
                    _clean_msg = signal.message or ""
                    if " | " in _clean_msg:
                        _parts = _clean_msg.split(" | ")
                        _noise_patterns = (
                            "SPY ", "CAUTION:", "BOUNCE QUALITY:",
                            "CHOPPY", "normal volume", "Defending",
                            "15m trend", "HA bearish", "HA bullish",
                            "session:", "reduced confidence",
                            "SPY at ", "market —",
                        )
                        _clean_parts = [
                            p for p in _parts
                            if not any(p.strip().startswith(n) or n in p for n in _noise_patterns)
                        ]
                        _clean_msg = " | ".join(_clean_parts).strip()

                    # Record alert
                    alert = Alert(
                        user_id=user_id,
                        symbol=signal.symbol,
                        alert_type=signal.alert_type.value,
                        direction=signal.direction,
                        price=_py(signal.price),
                        entry=_py(signal.entry),
                        stop=_py(signal.stop),
                        target_1=_py(signal.target_1),
                        target_2=_py(signal.target_2),
                        confidence=signal.confidence,
                        message=_clean_msg,
                        narrative=_narrative,
                        score=int(signal.score) if signal.score else 0,
                        session_date=_sym_session,
                    )
                    db.add(alert)
                    fired_today.add(key)

                    # Set direction lock + increment budget counter
                    if signal.direction in ("BUY", "SHORT"):
                        _direction_lock[symbol] = (signal.direction, datetime.utcnow())
                        _entry_count += 1
                        # SPY SHORT gate: suppress equity BUYs until SPY finds support
                        if symbol == "SPY" and signal.direction == "SHORT":
                            _spy_short_time = datetime.utcnow()
                            logger.info("SPY GATE SET: SPY SHORT fired — suppressing equity BUY entries")
                        # SPY BUY clears the gate — market found support
                        if symbol == "SPY" and signal.direction == "BUY" and _spy_short_time is not None:
                            logger.info("SPY GATE CLEARED: SPY BUY fired — resuming equity BUY entries (gate was %ds)",
                                        int((datetime.utcnow() - _spy_short_time).total_seconds()))
                            _spy_short_time = None

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
                            entry_price=_py(signal.entry),
                            stop_price=_py(signal.stop),
                            target_1=_py(signal.target_1),
                            target_2=_py(signal.target_2),
                            alert_type=signal.alert_type.value,
                            session_date=_sym_session,
                        ))

                    # Stop/target: NOTIFY only — do NOT auto-close trades (BUG-9)
                    # User controls exits. System only informs that levels were breached.
                    # Still add cooldown after stop to prevent re-entry spam.
                    if signal.alert_type in (AlertType.STOP_LOSS_HIT, AlertType.AUTO_STOP_OUT):
                        db.add(Cooldown(
                            user_id=user_id,
                            symbol=symbol,
                            cooldown_until="",
                            reason=signal.alert_type.value,
                            session_date=_sym_session,
                        ))
                    # Target hits: notify but don't close — user decides when to take profits

                    # Preference gate: check if user wants this alert category + score
                    _at_val = signal.alert_type.value
                    _send_notification = True
                    if _at_val not in EXIT_ALERT_TYPES:
                        _cat = ALERT_TYPE_TO_CATEGORY.get(_at_val)
                        if _cat and not _cat_prefs.get(_cat, True):
                            _send_notification = False
                        elif _min_score > 0 and signal.score < _min_score:
                            _send_notification = False

                    if not _send_notification:
                        logger.info(
                            "PREF FILTERED: user=%d %s %s (dashboard only)",
                            user_id, signal.symbol, _at_val,
                        )

                    # Burst cooldown: suppress rapid BUY notification spam
                    if _send_notification and signal.direction == "BUY":
                        _prev = _last_buy_notify.get(symbol)
                        _now = datetime.utcnow()
                        if _prev and (_now - _prev).total_seconds() < COOLDOWN_MINUTES * 60:
                            _send_notification = False
                            logger.info(
                                "BURST COOLDOWN: user=%d %s %s — suppressed (%ds since last BUY)",
                                user_id, symbol, _at_val, (_now - _prev).total_seconds(),
                            )

                    # Track BUY notification time for burst cooldown
                    if _send_notification and signal.direction == "BUY":
                        _last_buy_notify[symbol] = datetime.utcnow()

                    # Commit immediately so alert is persisted + has ID for Telegram buttons
                    db.commit()

                    # Push to SSE (only if preference allows)
                    alert_data = {
                        "symbol": signal.symbol,
                        "alert_type": signal.alert_type.value,
                        "direction": signal.direction,
                        "price": signal.price,
                        "message": signal.message,
                    }
                    if _send_notification:
                        try:
                            from app.background.alert_bus import publish
                            publish(user_id, alert_data)
                        except Exception:
                            pass

                    # Telegram notification (per-user)
                    if _send_notification:
                        _user = user_rows.get(user_id)
                        if _user and _user.telegram_enabled and _user.telegram_chat_id:
                            try:
                                from alerting.notifier import notify_user
                                _prefs = {
                                    "telegram_enabled": True,
                                    "telegram_chat_id": _user.telegram_chat_id,
                                    "email_enabled": _user.email_enabled,
                                    "notification_email": _user.email,
                                }
                                _email_ok, _tg_ok = notify_user(signal, _prefs, alert_id=alert.id)
                                logger.info(
                                    "NOTIFY: user=%d %s %s tg=%s email=%s",
                                    user_id, signal.symbol, signal.alert_type.value,
                                    _tg_ok, _email_ok,
                                )
                            except Exception:
                                logger.warning(
                                    "Telegram notify FAILED for user=%d %s",
                                    user_id, signal.symbol,
                                    exc_info=True,
                                )
                        else:
                            logger.info(
                                "NOTIFY SKIP: user=%d tg_enabled=%s chat_id=%s",
                                user_id,
                                getattr(_user, 'telegram_enabled', None),
                                getattr(_user, 'telegram_chat_id', None),
                            )

                    # Push notification (APNs) — only if preference allows
                    if _send_notification:
                        try:
                            from app.models.device_token import DeviceToken
                            from app.services.push_service import send_push_sync

                            tokens = db.execute(
                                select(DeviceToken.token).where(
                                    DeviceToken.user_id == user_id,
                                    DeviceToken.platform == "ios",
                                )
                            ).scalars().all()
                            if tokens:
                                label = signal.alert_type.value.replace("_", " ").title()
                                push_title = (
                                    f"{signal.direction} {signal.symbol} "
                                    f"${signal.price:.2f}"
                                )
                                send_push_sync(
                                    list(tokens),
                                    title=push_title,
                                    body=label,
                                    data=alert_data,
                                    thread_id=signal.symbol,
                                )
                        except Exception:
                            logger.debug(
                                "Push notification skipped for user=%d", user_id,
                                exc_info=True,
                            )

                    total_alerts += 1
                    logger.info(
                        "ALERT: user=%d %s %s %s @ $%.2f",
                        user_id, signal.direction, signal.symbol,
                        signal.alert_type.value, signal.price,
                    )

                  except Exception:
                    logger.exception(
                        "Signal processing failed: user=%d %s %s",
                        user_id, symbol, signal.alert_type.value if signal else "?",
                    )
                    continue

        # Individual alerts already committed above

    logger.info("Poll complete: %d alerts across %d users", total_alerts, len(pro_users))
    return total_alerts
