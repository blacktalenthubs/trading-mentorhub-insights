"""AI Day Trade Scanner — specialized entry detection at key intraday levels.

Replaces the generic AI scanner with focused day trade entry rules:
- PDL hold/reclaim (price touches or dips below PDL, closes back above)
- PDH breakout on volume (close above PDH with volume >= 1.5x avg)
- VWAP hold (pullback to VWAP and reclaim)
- Multi-day double bottom hold (same low tested on 2+ sessions)
- Key MA/EMA holds (bounce off 20/50/100/200 MA or EMA)

Uses Claude Haiku for fast, structured level detection.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import date

from alert_config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MODEL_SONNET

logger = logging.getLogger(__name__)

# Dedup: (symbol, setup_type, level_bucket) per session
_day_fired: dict[str, set[tuple]] = {}
_day_session: str = ""
# Track last direction sent to Telegram per symbol — only notify on change
_last_tg_direction: dict[str, str] = {}  # {symbol: "LONG" / "RESISTANCE" / "WAIT"}
_last_tg_time: dict[str, float] = {}  # {symbol: timestamp of last Telegram send}
_last_wait_reason_fp: dict[str, str] = {}  # {symbol: fingerprint of last WAIT reason}
# Per-user rate limit tracking — resets on new session
_user_delivered_count: dict[tuple[int, str], int] = {}  # (uid, session) -> LONG/SHORT/RESISTANCE/EXIT count
_user_limit_notified: set[tuple[int, str]] = set()  # (uid, session) already told about actionable cap
_user_wait_count: dict[tuple[int, str], int] = {}  # (uid, session) -> WAIT Telegram count
_user_wait_limit_notified: set[tuple[int, str]] = set()  # (uid, session) already told about wait cap

# Exit scan cooldown — (trade_id, status) -> last_sent_ts. 30-min cooldown per pair.
_exit_notified: dict[tuple[int, str], float] = {}
_EXIT_COOLDOWN_SEC = 1800  # 30 min


def _resolve_api_key() -> str:
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    return ""


def get_user_ai_scan_count(user_id: int, session_date: str) -> int:
    """Return how many AI scan alerts the user has received today.

    Reads from the usage_limits DB (persistent across worker restarts).
    Falls back to the in-memory cache if DB is unavailable.
    """
    # Try DB first — authoritative across restarts
    try:
        from db import get_db
        from sqlalchemy import text as _t
        with get_db() as conn:
            row = conn.execute(
                _t("SELECT usage_count FROM usage_limits "
                   "WHERE user_id = :uid AND feature = :f AND usage_date = :d"),
                {"uid": user_id, "f": _FEATURE_SCAN, "d": session_date},
            ).fetchone()
            if row is not None:
                return int(row[0] if not hasattr(row, "__getitem__") else row[0])
    except Exception:
        pass
    # Fallback
    return _user_delivered_count.get((user_id, session_date), 0)


# ---------------------------------------------------------------------------
# Persistent rate-limit counters (via usage_limits table — survive worker restarts)
# ---------------------------------------------------------------------------

# Feature keys used in the shared usage_limits table
_FEATURE_SCAN = "ai_scan_telegram"        # LONG / SHORT / RESISTANCE / EXIT delivery

# Loss-leader: alerts on these symbols bypass the daily cap so free users
# can taste the platform on the most important tickers. Other alerts still count.
_UNCAPPED_SYMBOLS = {"SPY", "NVDA"}
_FEATURE_WAIT = "ai_wait_telegram"        # WAIT delivery
_FEATURE_SCAN_NOTIFIED = "ai_scan_cap_notified"   # 1 = already told user about cap today
_FEATURE_WAIT_NOTIFIED = "ai_wait_cap_notified"


def _db_get_count(db, user_id: int, feature: str, usage_date: str) -> int:
    """Sync DB read of today's usage count for a feature. Returns 0 if no row."""
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
        logger.debug("usage_limits read failed for uid=%s feature=%s", user_id, feature)
        return 0


def _db_increment_count(db, user_id: int, feature: str, usage_date: str) -> int:
    """Atomic increment — upsert row, return new count. Idempotent under ON CONFLICT."""
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
        logger.exception("usage_limits increment failed for uid=%s feature=%s", user_id, feature)
    return _db_get_count(db, user_id, feature, usage_date)


_CONVICTION_RANK = {"low": 1, "medium": 2, "high": 3}


def _db_last_wait_info(db, symbol: str, session_date: str) -> tuple[float, str]:
    """Return (age_seconds, reason_fingerprint) of the most recent WAIT alert for
    this symbol today, using the alerts table as source of truth.

    Survives worker restarts — no in-memory state. Returns (huge, "") if none.
    Must be called BEFORE inserting this cycle's WAIT rows so we read the prior one.
    """
    from sqlalchemy import text as _t
    from datetime import datetime as _dt, timezone as _tz
    try:
        row = db.execute(
            _t(
                "SELECT created_at, message FROM alerts "
                "WHERE symbol = :s AND alert_type = 'ai_scan_wait' "
                "AND session_date = :d "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"s": symbol, "d": session_date},
        ).fetchone()
        if not row:
            return (10**9, "")
        ts = row[0]
        msg = row[1] or ""
        # Strip known prefixes before fingerprinting
        reason = msg
        for prefix in ("AI Update: ", "AI: WAIT — "):
            if reason.startswith(prefix):
                reason = reason[len(prefix):]
                break
        fp = _wait_fingerprint(reason)
        # Compute age in seconds
        if isinstance(ts, str):
            try:
                ts = _dt.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                return (10**9, fp)
        now = _dt.utcnow()
        try:
            if ts.tzinfo is not None:
                ts = ts.astimezone(_tz.utc).replace(tzinfo=None)
        except Exception:
            pass
        age = (now - ts).total_seconds()
        return (max(age, 0), fp)
    except Exception:
        logger.debug("last-wait lookup failed for %s", symbol)
        return (10**9, "")


# ---------------------------------------------------------------------------
# Spec 35 — AI Auto-Pilot paper trades (system-level simulated account)
# ---------------------------------------------------------------------------

AUTO_TRADE_NOTIONAL = 10_000  # $10k fixed per signal for comparable P&L


def _close_auto_trade(
    db,
    trade,
    exit_price: float,
    status: str,
    exit_reason: str,
) -> None:
    """Close an open AIAutoTrade with the given exit price + status.

    Computes P&L dollars, %, and R-multiple. Idempotent — callers should
    confirm status=='open' before calling, but we guard anyway.
    """
    from datetime import datetime as _dt

    if trade.status != "open":
        return

    entry = float(trade.entry_price)
    exit_p = float(exit_price)
    shares = float(trade.shares or 0)
    is_long = trade.direction == "BUY"

    # P&L
    per_share_pnl = (exit_p - entry) if is_long else (entry - exit_p)
    pnl_dollars = round(per_share_pnl * shares, 2)
    pnl_pct = round((per_share_pnl / entry) * 100, 4) if entry > 0 else 0.0

    # R-multiple — (exit - entry) / initial risk
    r_mult = None
    if trade.stop_price:
        risk_per_share = abs(entry - float(trade.stop_price))
        if risk_per_share > 0:
            r_mult = round(per_share_pnl / risk_per_share, 2)

    trade.status = status
    trade.exit_price = exit_p
    trade.closed_at = _dt.utcnow()
    trade.exit_reason = exit_reason
    trade.pnl_dollars = pnl_dollars
    trade.pnl_percent = pnl_pct
    trade.r_multiple = r_mult

    logger.info(
        "auto-pilot CLOSE: %s %s entry=$%.2f exit=$%.2f pnl=$%.2f (%+.2f%%) R=%.2f reason=%s",
        trade.symbol, trade.direction, entry, exit_p, pnl_dollars, pnl_pct,
        r_mult if r_mult is not None else 0.0, exit_reason,
    )


def auto_trade_monitor_cycle(sync_session_factory) -> int:
    """Phase 2 — check every open AIAutoTrade for stop/target hits.

    Runs on a scheduler (every minute). For each open trade:
    - Fetch latest bar (uses yfinance fast_info or Coinbase spot)
    - LONG: if price >= target_2 → close at T2; elif >= target_1 → close at T1;
      elif <= stop → close at stop
    - SHORT: inverted
    - EOD for equities (4:00 PM ET): close remaining opens at last print

    Returns number of trades closed this cycle.
    """
    try:
        from sqlalchemy import select
        from app.models.auto_trade import AIAutoTrade
    except Exception:
        logger.debug("auto-trade monitor: model import failed")
        return 0

    try:
        import yfinance as yf  # noqa: F401
    except Exception:
        logger.debug("auto-trade monitor: yfinance unavailable, skipping")
        return 0

    closed = 0
    with sync_session_factory() as db:
        open_trades = db.execute(
            select(AIAutoTrade).where(AIAutoTrade.status == "open")
        ).scalars().all()

        if not open_trades:
            return 0

        # Batch by symbol to minimize price lookups
        symbols = {t.symbol for t in open_trades}
        prices: dict[str, float] = {}
        for sym in symbols:
            try:
                import yfinance as yf
                fi = yf.Ticker(sym).fast_info
                p = float(fi.last_price)
                if p > 0:
                    prices[sym] = p
            except Exception:
                logger.debug("auto-trade monitor: price fetch failed for %s", sym)

        for t in open_trades:
            price = prices.get(t.symbol)
            if price is None:
                continue

            is_long = t.direction == "BUY"
            stop = float(t.stop_price) if t.stop_price else None
            t1 = float(t.target_1_price) if t.target_1_price else None
            t2 = float(t.target_2_price) if t.target_2_price else None

            # Stop-first rule: if both stop and target hit in same cycle, assume stop
            hit_stop = False
            hit_t1 = False
            hit_t2 = False
            if is_long:
                if stop is not None and price <= stop:
                    hit_stop = True
                elif t2 is not None and price >= t2:
                    hit_t2 = True
                elif t1 is not None and price >= t1:
                    hit_t1 = True
            else:  # SHORT
                if stop is not None and price >= stop:
                    hit_stop = True
                elif t2 is not None and price <= t2:
                    hit_t2 = True
                elif t1 is not None and price <= t1:
                    hit_t1 = True

            if hit_stop:
                _close_auto_trade(db, t, stop, "closed_stop", "Stop loss hit")
                closed += 1
            elif hit_t2:
                _close_auto_trade(db, t, t2, "closed_t2", "Target 2 hit")
                closed += 1
            elif hit_t1:
                _close_auto_trade(db, t, t1, "closed_t1", "Target 1 hit")
                closed += 1

        if closed:
            db.commit()

    return closed


def auto_trade_eod_cleanup(sync_session_factory) -> int:
    """Close open equity positions at 4:00 PM ET each trading day.

    Crypto positions stay open overnight (24/7 market). Only equity
    trades hit this cleanup.
    """
    try:
        from sqlalchemy import select
        from app.models.auto_trade import AIAutoTrade
    except Exception:
        return 0

    closed = 0
    with sync_session_factory() as db:
        open_equity = db.execute(
            select(AIAutoTrade).where(
                AIAutoTrade.status == "open",
                AIAutoTrade.market == "equity",
            )
        ).scalars().all()

        if not open_equity:
            return 0

        import yfinance as yf
        for t in open_equity:
            try:
                fi = yf.Ticker(t.symbol).fast_info
                last = float(fi.last_price)
                if last > 0:
                    _close_auto_trade(db, t, last, "closed_eod", "End of day (equity)")
                    closed += 1
            except Exception:
                logger.debug("auto-trade eod: price fetch failed for %s", t.symbol)

        if closed:
            db.commit()

    return closed


def _open_auto_trade(
    db,
    symbol: str,
    direction: str,  # "BUY" or "SHORT"
    alert_id: int | None,
    entry: float,
    stop: float | None,
    t1: float | None,
    t2: float | None,
    setup_type: str | None,
    conviction: str | None,
    session: str,
    is_crypto: bool,
) -> None:
    """Open a simulated paper trade in the AI Auto-Pilot account.

    Dedup: one open auto trade per (symbol, direction). Caller passes the
    AI signal's levels verbatim — we don't second-guess the plan.
    """
    if not entry or entry <= 0:
        return
    try:
        from sqlalchemy import select
        from app.models.auto_trade import AIAutoTrade

        # Dedup: only one open auto trade per (symbol, direction)
        existing = db.execute(
            select(AIAutoTrade.id).where(
                AIAutoTrade.symbol == symbol,
                AIAutoTrade.direction == direction,
                AIAutoTrade.status == "open",
            ).limit(1)
        ).scalar_one_or_none()
        if existing:
            logger.debug("auto-pilot: %s %s already open, skip", symbol, direction)
            return

        shares = round(AUTO_TRADE_NOTIONAL / entry, 4) if entry > 0 else 0
        notional = round(shares * entry, 2)

        # Truncate to fit DB column sizes (defensive — AI sometimes returns long strings)
        _setup_trunc = (setup_type or "")[:100] if setup_type else None
        _conviction_trunc = ((conviction or "").upper() or None)
        if _conviction_trunc:
            _conviction_trunc = _conviction_trunc[:20]

        trade = AIAutoTrade(
            alert_id=alert_id,
            symbol=symbol,
            direction=direction,
            setup_type=_setup_trunc,
            conviction=_conviction_trunc,
            entry_price=entry,
            session_date=session,
            stop_price=stop,
            target_1_price=t1,
            target_2_price=t2,
            shares=shares,
            notional_at_entry=notional,
            status="open",
            market="crypto" if is_crypto else "equity",
        )
        db.add(trade)
        db.flush()
        logger.info(
            "auto-pilot OPEN: %s %s entry=$%.2f stop=$%.2f shares=%.4f trade_id=%d",
            symbol, direction, entry, stop or 0, shares, trade.id,
        )
    except Exception:
        logger.exception("auto-pilot: failed to open trade for %s %s", symbol, direction)
        # CRITICAL: rollback so the failed flush doesn't poison the session
        # for subsequent commits (alert delivery, Telegram sends, etc.)
        try:
            db.rollback()
        except Exception:
            pass


def _wait_fingerprint(reason: str) -> str:
    """Fingerprint a WAIT reason so we only dedup exact/near-identical repeats.

    Strips digits + punctuation, lowercases, keeps first 80 chars.
    "Price at $2207 near VWAP, volume 0.5x" and "Price at $2209 near VWAP,
    volume 0.6x" collapse to the same fingerprint (same structural story).
    "Price near VWAP, volume 0.5x" vs "Price tested session high, rejected"
    → different fingerprints → both fire.
    """
    import re as _re
    if not reason:
        return ""
    cleaned = _re.sub(r"[\d.$,;:!?%()\-—–]+", " ", reason.lower())
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:80]


def _truncate_for_free(reason: str, tier: str, max_len: int = 60) -> tuple[str, bool]:
    """Spec 36 — free users get a headline only on AI Updates, paid get full analysis.

    Returns (display_text, was_truncated).
    - Free: first clause (up to max_len chars), ending with ellipsis if clipped
    - Pro/Premium/Admin: full reason unchanged
    """
    if not reason:
        return ("", False)
    if (tier or "").lower() != "free":
        return (reason, False)

    # Cut at first sentence/clause boundary
    cut = reason
    for delim in (". ", "; ", " — ", " - "):
        if delim in cut:
            cut = cut.split(delim, 1)[0]
            break
    cut = cut.strip(" .;—-")
    if len(cut) > max_len:
        cut = cut[: max_len - 1].rstrip() + "…"
    return (cut, True)


def _user_wants_alert(user, alert_kind: str, conviction: str | None = None) -> bool:
    """Spec 36 — respect user-controlled alert filters before Telegram delivery.

    alert_kind: one of 'LONG', 'SHORT', 'RESISTANCE', 'WAIT', 'EXIT'
    conviction: 'low' / 'medium' / 'high' (ignored for WAIT and EXIT)
    Returns False if the user has opted out of this kind of alert.
    """
    # Master kill switch — user disabled all Telegram alerts
    if not getattr(user, "telegram_enabled", True):
        return False

    if alert_kind == "WAIT":
        return bool(getattr(user, "wait_alerts_enabled", False))

    # Direction filter — distinguish "not set" (None) from "explicitly empty" ("")
    directions_attr = getattr(user, "alert_directions", None)
    if directions_attr is None:
        directions_str = "LONG,SHORT,RESISTANCE,EXIT"  # default when attr missing
    else:
        directions_str = directions_attr
    allowed = {d.strip().upper() for d in directions_str.split(",") if d.strip()}
    if not allowed:
        # User explicitly disabled all directions — treat as opt-out
        return False
    if alert_kind.upper() not in allowed:
        return False

    # Conviction filter (skip for EXIT — exit signals don't carry conviction)
    if alert_kind.upper() != "EXIT":
        user_min = _CONVICTION_RANK.get(
            (getattr(user, "min_conviction", None) or "medium").lower(), 2
        )
        signal_level = _CONVICTION_RANK.get((conviction or "medium").lower(), 2)
        if signal_level < user_min:
            return False

    return True


def _db_mark_notified(db, user_id: int, feature_notified_key: str, usage_date: str) -> bool:
    """Atomic check-and-set. Returns True if this was the FIRST call today (send msg),
    False if already notified (suppress duplicate)."""
    from sqlalchemy import text
    try:
        existing = db.execute(
            text(
                "SELECT usage_count FROM usage_limits "
                "WHERE user_id = :uid AND feature = :f AND usage_date = :d"
            ),
            {"uid": user_id, "f": feature_notified_key, "d": usage_date},
        ).fetchone()
        if existing and int(existing[0]) >= 1:
            return False  # already notified
        # Set the marker
        db.execute(
            text(
                "INSERT INTO usage_limits (user_id, feature, usage_date, usage_count) "
                "VALUES (:uid, :f, :d, 1) "
                "ON CONFLICT (user_id, feature, usage_date) "
                "DO UPDATE SET usage_count = 1"
            ),
            {"uid": user_id, "f": feature_notified_key, "d": usage_date},
        )
        db.commit()
        return True
    except Exception:
        logger.exception("mark_notified failed for uid=%s feature=%s", user_id, feature_notified_key)
        return False


def _level_bucket(price: float) -> float:
    """Round price to 2 significant figures for dedup bucketing."""
    if price <= 0:
        return 0
    digits = len(str(int(price)))
    return round(price, -digits + 2)


def build_day_trade_prompt(
    symbol: str,
    bars_5m: list[dict],
    bars_1h: list[dict],
    prior_day: dict | None,
    active_positions: list[dict] | None = None,  # kept for API compat; not used in multi-user
) -> str:
    """Build specialized day trade prompt with specific confirmation rules.

    Generic prompt — no per-user context. Position-aware filtering happens
    at delivery time (per-user) so one AI call scales to N users.
    """
    _ = active_positions  # unused in multi-user mode

    prompt = (
        "You are a day trade analyst. Read the chart data below and decide:\n"
        "Is there a trade right now?\n\n"
        "WHAT TO LOOK FOR:\n"
        "- Price bouncing off support (session low, PDL, VWAP, daily MA) → LONG\n"
        "- Price rejecting at resistance (session high, PDH, daily MA above) with confirmed structure → SHORT\n"
        "- Price approaching resistance but no confirmed rejection yet → RESISTANCE (notice)\n"
        "- Price between levels with no clear setup → WAIT\n\n"
        "KEY LEVEL PRIORITY (use the dominant level as entry):\n"
        "- Daily MAs (20/50/100/200) are the STRONGEST levels — if price within 0.3% of any daily MA,\n"
        "  that MA is the entry level, regardless of session/PDL proximity.\n"
        "- Next priority: PDH/PDL, then session highs/lows, then VWAP.\n\n"
        "PHILOSOPHY: At a KEY LEVEL, prefer firing LONG/SHORT (with conviction reflecting\n"
        "confirmation strength) over WAIT. The user decides if they take it. Only use WAIT\n"
        "when price is mid-range with no nearby level. Missing a level is worse than firing\n"
        "LOW — the stop is trivial when the entry is at a structural level.\n\n"
        "LONG CONVICTION LADDER (price within 0.3% of key support):\n"
        "- HIGH: higher low structure + volume >= 1.0x avg on bounce bar\n"
        "- MEDIUM: higher low structure forming OR volume 0.5-1.0x (one confirmation missing)\n"
        "- LOW: price touching/holding key support, no structure yet, weak volume (<0.5x)\n"
        "- Fire LONG at LOW rather than WAIT — the level IS the edge. Note 'thin volume' in reason.\n\n"
        "SHORT CONVICTION LADDER (price within 0.3% of key resistance):\n"
        "- HIGH: lower high structure + volume >= 1.0x avg on rejection bar\n"
        "- MEDIUM: lower high forming OR volume 0.5-1.0x\n"
        "- LOW: price touching/holding key resistance, no structure yet, weak volume\n"
        "- Fire SHORT at LOW rather than RESISTANCE-only — level IS the edge.\n\n"
        "KEY LEVELS THAT ALWAYS WARRANT FIRING (never just WAIT at these):\n"
        "- Daily MA test (20/50/100/200) within 0.3%\n"
        "- PDH/PDL reclaim or rejection\n"
        "- VWAP reclaim after break\n"
        "- Session high/low double-test\n"
        "- Prior swing high/low retest\n\n"
        "WAIT is only for: price mid-range (>0.3% from every level), no directional commitment,\n"
        "no structural setup forming.\n\n"
        "OUTPUT (plain text, no markdown):\n\n"
        "SETUP: [what you see — e.g. PDL bounce, VWAP reclaim, 50MA rejection, PDH fail]\n"
        "Direction: LONG / SHORT / RESISTANCE / WAIT\n"
        "Entry: $price (the key level, not current price)\n"
        "Stop: $price (LONG: below support; SHORT: above resistance)\n"
        "T1: $price (LONG: next resistance above; SHORT: next support below)\n"
        "T2: $price (LONG: second resistance; SHORT: second support)\n"
        "Conviction: HIGH / MEDIUM / LOW\n"
        "Reason: 1 sentence — state level + confirmation state (e.g. 'PDL bounce, weak volume 0.3x — LOW conviction')\n\n"
        "RULES:\n"
        "- Be decisive. At a key level, prefer LONG/SHORT LOW over WAIT.\n"
        "- Entry = the key level price, not current price.\n"
        "- Stop = structural level where thesis breaks (below support for LONG, above resistance for SHORT).\n"
        "- MAXIMUM 60 WORDS.\n"
        "- PDH = yesterday's high. PDL = yesterday's low. Daily MAs are from the daily timeframe.\n"
    )

    parts = [prompt]

    # Key levels from prior day
    if prior_day:
        # --- Prior day anchors ---
        levels = [f"\n[KEY LEVELS — {symbol}]"]
        for key, label in [
            ("high", "PDH(yesterday high)"),
            ("low", "PDL(yesterday low)"),
            ("close", "Prior Close"),
        ]:
            val = prior_day.get(key)
            if val and val > 0:
                levels.append(f"{label}: ${val:.2f}")

        # --- Daily MAs — strongest support/resistance on intraday charts ---
        daily_ma_lines = []
        for key, label in [
            ("ma20", "20 Daily MA"), ("ma50", "50 Daily MA"),
            ("ma100", "100 Daily MA"), ("ma200", "200 Daily MA"),
            ("ema20", "20 Daily EMA"), ("ema50", "50 Daily EMA"),
            ("ema100", "100 Daily EMA"), ("ema200", "200 Daily EMA"),
        ]:
            val = prior_day.get(key)
            if val and val > 0:
                daily_ma_lines.append(f"{label}: ${val:.2f}")
        if daily_ma_lines:
            levels.append("")
            levels.append("[DAILY MAs — strong multi-day support/resistance]")
            levels.extend(daily_ma_lines)
            levels.append(
                "If current price is within 0.3% of any daily MA, that MA is the "
                "dominant level — use it as the LONG entry (bounce) or SHORT entry "
                "(rejection) level."
            )
            levels.append("")
        rsi = prior_day.get("rsi14")
        if rsi:
            levels.append(f"RSI14: {rsi:.1f}")
        # Weekly levels
        pw_high = prior_day.get("prior_week_high")
        pw_low = prior_day.get("prior_week_low")
        if pw_high and pw_high > 0:
            levels.append(f"WeekHi: ${pw_high:.2f}")
        if pw_low and pw_low > 0:
            levels.append(f"WeekLo: ${pw_low:.2f}")
        # Monthly levels
        pm_high = prior_day.get("prior_month_high")
        pm_low = prior_day.get("prior_month_low")
        if pm_high and pm_high > 0:
            levels.append(f"MonthHi: ${pm_high:.2f}")
        if pm_low and pm_low > 0:
            levels.append(f"MonthLo: ${pm_low:.2f}")
        # Monthly EMAs
        m_ema8 = prior_day.get("monthly_ema8")
        m_ema20 = prior_day.get("monthly_ema20")
        if m_ema8 and m_ema8 > 0:
            levels.append(f"MonthlyEMA8: ${m_ema8:.2f}")
        if m_ema20 and m_ema20 > 0:
            levels.append(f"MonthlyEMA20: ${m_ema20:.2f}")
        parts.append("\n".join(levels))

    # Intraday levels — data only, AI decides what's important
    if bars_5m:
        session_high = max(b["high"] for b in bars_5m)
        session_low = min(b["low"] for b in bars_5m)
        _tp_vol = sum(((b["high"] + b["low"] + b["close"]) / 3) * b.get("volume", 1) for b in bars_5m)
        _vol = sum(b.get("volume", 1) for b in bars_5m)
        vwap = _tp_vol / _vol if _vol > 0 else bars_5m[-1]["close"]
        avg_vol = sum(b.get("volume", 0) for b in bars_5m) / len(bars_5m) if bars_5m else 0
        last_vol = bars_5m[-1].get("volume", 0)
        vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0

        parts.append(
            f"\n[INTRADAY LEVELS]\n"
            f"Session High: ${session_high:.2f}\n"
            f"Session Low: ${session_low:.2f}\n"
            f"VWAP: ${vwap:.2f}\n"
            f"Current Price: ${bars_5m[-1]['close']:.2f}\n"
            f"Volume Ratio: {vol_ratio:.1f}x avg"
        )

    # 5-min bars (last 20)
    if bars_5m:
        lines = [f"\n[5-MIN BARS — last {min(len(bars_5m), 20)} bars]"]
        for b in bars_5m[-20:]:
            lines.append(
                f"O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} "
                f"C={b['close']:.2f} V={b.get('volume', 0):.0f}"
            )
        parts.append("\n".join(lines))

    # 1-hour bars (last 10) — for context (double bottom detection across sessions)
    if bars_1h:
        lines = [f"\n[1-HOUR BARS — last {min(len(bars_1h), 10)} bars]"]
        for b in bars_1h[-10:]:
            lines.append(
                f"O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} "
                f"C={b['close']:.2f} V={b.get('volume', 0):.0f}"
            )
        parts.append("\n".join(lines))

    return "\n".join(parts)


def parse_day_trade_response(text: str) -> dict:
    """Parse structured day trade signal from Claude response."""
    result = {
        "setup_type": None,
        "direction": None,
        "entry": None,
        "stop": None,
        "t1": None,
        "t2": None,
        "conviction": None,
        "reason": None,
        "raw": text,
    }

    # SETUP
    setup_match = re.search(r"SETUP:\s*(.+?)(?:\n|$)", text)
    if setup_match:
        result["setup_type"] = setup_match.group(1).strip()

    # Direction
    dir_match = re.search(r"Direction:\s*(LONG|SHORT|RESISTANCE|WAIT)", text, re.IGNORECASE)
    if dir_match:
        result["direction"] = dir_match.group(1).upper()

    def _parse_price(pattern: str, txt: str) -> float | None:
        m = re.search(pattern, txt)
        if m:
            return float(m.group(1).replace(",", ""))
        return None

    result["entry"] = _parse_price(r"Entry:\s*\$?([\d,.]+)", text)
    result["stop"] = _parse_price(r"Stop:\s*\$?([\d,.]+)", text)
    result["t1"] = _parse_price(r"T1:\s*\$?([\d,.]+)", text)
    result["t2"] = _parse_price(r"T2:\s*\$?([\d,.]+)", text)

    conv_match = re.search(r"Conviction:\s*(HIGH|MEDIUM|LOW)", text, re.IGNORECASE)
    if conv_match:
        result["conviction"] = conv_match.group(1).upper()

    reason_match = re.search(r"Reason:\s*(.+?)(?:\n|$)", text)
    if reason_match:
        result["reason"] = reason_match.group(1).strip()

    return result


def scan_day_trade(symbol: str, api_key: str, active_positions: list[dict] | None = None) -> dict | None:
    """Scan one symbol for day trade entries using specialized prompt."""
    from analytics.intraday_data import fetch_intraday, fetch_intraday_crypto, fetch_prior_day
    from config import is_crypto_alert_symbol

    is_crypto = is_crypto_alert_symbol(symbol)

    try:
        bars_5m_df = fetch_intraday_crypto(symbol) if is_crypto else fetch_intraday(symbol)
        if bars_5m_df is None or (hasattr(bars_5m_df, "empty") and bars_5m_df.empty):
            logger.warning("AI day scan: no 5m bars for %s", symbol)
            return None

        bars_1h_df = fetch_intraday(symbol, period="5d", interval="1h")
        prior_day = fetch_prior_day(symbol, is_crypto=is_crypto)

        current_price = float(bars_5m_df.iloc[-1]["Close"])

        bars_5m = [
            {"open": float(r["Open"]), "high": float(r["High"]),
             "low": float(r["Low"]), "close": float(r["Close"]),
             "volume": float(r["Volume"])}
            for _, r in bars_5m_df.tail(20).iterrows()
        ]
        bars_1h = []
        if bars_1h_df is not None and not (hasattr(bars_1h_df, "empty") and bars_1h_df.empty):
            bars_1h = [
                {"open": float(r["Open"]), "high": float(r["High"]),
                 "low": float(r["Low"]), "close": float(r["Close"]),
                 "volume": float(r["Volume"])}
                for _, r in bars_1h_df.tail(10).iterrows()
            ]

        prompt = build_day_trade_prompt(symbol, bars_5m, bars_1h, prior_day, active_positions)

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system_with_cache = [
            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
        ]

        start = time.time()
        response = client.messages.create(
            model=CLAUDE_MODEL_SONNET,
            max_tokens=200,
            system=system_with_cache,
            messages=[{"role": "user", "content": f"Scan {symbol} for day trade entry now."}],
            timeout=20.0,
        )
        elapsed = time.time() - start

        response_text = response.content[0].text.strip()
        logger.info("AI day scan %s: %.1fs, %d tokens — %s",
                     symbol, elapsed, response.usage.input_tokens, response_text[:100])

        parsed = parse_day_trade_response(response_text)
        parsed["symbol"] = symbol
        parsed["price"] = current_price
        parsed["signal_source"] = "day_trade"

        # Staleness gate: if price has already moved past the entry level,
        # the bounce/rejection already played out — don't fire a stale alert.
        # LONG: current > entry * 1.004 (0.4% above level) → bounce already happened.
        # SHORT: current < entry * 0.996 (0.4% below level) → rejection done.
        _dir = (parsed.get("direction") or "").upper()
        _entry = parsed.get("entry") or 0
        if _entry > 0 and current_price > 0:
            if _dir == "LONG" and current_price > _entry * 1.004:
                logger.info(
                    "AI day scan %s: LONG stale — entry $%.2f, now $%.2f (+%.1f%%)",
                    symbol, _entry, current_price,
                    (current_price - _entry) / _entry * 100,
                )
                parsed["direction"] = "WAIT"
                parsed["reason"] = (
                    f"Entry level ${_entry:.2f} already tested and reclaimed — "
                    f"price now ${current_price:.2f}. Await next pullback."
                )
            elif _dir == "SHORT" and current_price < _entry * 0.996:
                logger.info(
                    "AI day scan %s: SHORT stale — entry $%.2f, now $%.2f (%.1f%%)",
                    symbol, _entry, current_price,
                    (current_price - _entry) / _entry * 100,
                )
                parsed["direction"] = "WAIT"
                parsed["reason"] = (
                    f"Rejection at ${_entry:.2f} already played — "
                    f"price now ${current_price:.2f}. Await next test."
                )

        # SHORT policy:
        # - SPY: fire SHORT only if conviction is MEDIUM or HIGH (skip LOW)
        # - All other symbols: downgrade SHORT → RESISTANCE (notice, not action)
        if parsed.get("direction") == "SHORT":
            conv = (parsed.get("conviction") or "MEDIUM").upper()
            sym_upper = symbol.upper()
            if sym_upper == "SPY":
                if conv == "LOW":
                    logger.info("AI day scan %s: SPY SHORT LOW suppressed (min MEDIUM)", symbol)
                    parsed["direction"] = "RESISTANCE"
            else:
                # Non-SPY → RESISTANCE notice (user still sees the level, no SHORT action)
                logger.info("AI day scan %s: SHORT → RESISTANCE (SPY-only policy)", symbol)
                parsed["direction"] = "RESISTANCE"

        return parsed

    except Exception:
        logger.exception("AI day scan failed for %s", symbol)
        return None


def day_scan_cycle(sync_session_factory) -> int:
    """Main day trade scan cycle — runs every 3 min during market hours."""
    global _day_fired, _day_session

    session = date.today().isoformat()
    if _day_session != session:
        _day_fired.clear()
        _last_tg_direction.clear()
        _last_tg_time.clear()
        _last_wait_reason_fp.clear()
        _user_delivered_count.clear()
        _user_limit_notified.clear()
        _user_wait_count.clear()
        _user_wait_limit_notified.clear()
        _exit_notified.clear()
        _day_session = session

    api_key = _resolve_api_key()
    if not api_key:
        logger.warning("AI day scan: no API key, skipping")
        return 0

    try:
        from sqlalchemy import select
        from app.models.watchlist import WatchlistItem
        from app.models.user import User
        from app.models.alert import Alert
        from analytics.market_hours import is_market_hours_for_symbol
        from config import is_crypto_alert_symbol  # noqa: F401 used in auto-trade calls

        with sync_session_factory() as db:
            all_items = db.execute(
                select(WatchlistItem.symbol, WatchlistItem.user_id)
            ).all()

            symbol_users: dict[str, list[int]] = {}
            for sym, uid in all_items:
                symbol_users.setdefault(sym, []).append(uid)

            symbols = [s for s in symbol_users if is_market_hours_for_symbol(s)]
            if not symbols:
                return 0

            logger.info("AI day scan: scanning %d symbols", len(symbols))

            # Per-user open-position index — checked at delivery time
            # Maps (user_id, symbol) -> True if that user holds an open LONG / SHORT
            from app.models.paper_trade import RealTrade
            user_open_longs: dict[tuple[int, str], bool] = {}
            user_open_shorts: dict[tuple[int, str], bool] = {}
            try:
                _all_uids = {uid for uids in symbol_users.values() for uid in uids}
                if _all_uids:
                    open_trades = db.execute(
                        select(RealTrade.user_id, RealTrade.symbol, RealTrade.direction).where(
                            RealTrade.status == "open",
                            RealTrade.user_id.in_(_all_uids),
                        )
                    ).all()
                    for uid, sym, direction in open_trades:
                        if direction == "BUY":
                            user_open_longs[(uid, sym)] = True
                        elif direction in ("SHORT", "SELL"):
                            user_open_shorts[(uid, sym)] = True
            except Exception:
                logger.debug("AI day scan: could not build user_open_positions index")

            total_alerts = 0

            for symbol in symbols:
                result = scan_day_trade(symbol, api_key)
                if not result:
                    continue

                direction = result.get("direction")
                setup_type = result.get("setup_type", "")
                entry = result.get("entry", 0)
                reason = result.get("reason", "")
                conviction = result.get("conviction", "MEDIUM")

                # WAIT — no setup confirmed, record to DB for AI Scan feed
                if not direction or direction == "WAIT":
                    # --- Gate check FIRST, using DB (survives restarts) ---
                    # Queries the last ai_scan_wait row for this symbol today
                    # BEFORE we insert this cycle's rows.
                    _level_keywords = ["PDH", "PDL", "VWAP", "session low", "session high",
                                       "20MA", "50MA", "100MA", "200MA", "EMA", "Daily",
                                       "support", "resistance", "weekly", "higher low",
                                       "lower high", "breakdown", "breakout"]
                    _near_level = any(kw.lower() in (reason or "").lower() for kw in _level_keywords)
                    _prev_age, _prev_fp = _db_last_wait_info(db, symbol, session)
                    _cur_fp = _wait_fingerprint(reason or "")
                    _reason_changed = (_cur_fp != _prev_fp)
                    _min_gap = 300 if _reason_changed else 600  # 5 min / 10 min
                    _time_ok = _prev_age >= _min_gap
                    _gate_passes = bool(_near_level and reason and _time_ok)
                    logger.info(
                        "WAIT gate %s: near_level=%s reason_changed=%s age=%.0fs need>=%ds fires=%s",
                        symbol, _near_level, _reason_changed, _prev_age, _min_gap, _gate_passes,
                    )

                    # --- Always record to DB (dashboard feed needs this) ---
                    _wait_msg = f"AI Update: {reason}" if reason else "AI Update: no setup confirmed"
                    for _uid in symbol_users[symbol]:
                      db.add(Alert(
                        user_id=_uid, symbol=symbol,
                        alert_type="ai_scan_wait", direction="NOTICE",
                        price=result.get("price", 0),
                        message=_wait_msg, score=0,
                        session_date=session,
                    ))
                    db.commit()

                    # --- Telegram delivery only if gate passes ---
                    if _gate_passes:
                        _last_tg_direction[symbol] = "WAIT"
                        _last_tg_time[symbol] = time.time()
                        _last_wait_reason_fp[symbol] = _cur_fp
                        try:
                            from alerting.notifier import _send_telegram_to
                            _price_fmt = f"${result.get('price', 0):.2f}"
                            for _uid in symbol_users[symbol]:
                                # Skip WAIT for users already in a position on this symbol
                                if user_open_longs.get((_uid, symbol)) or user_open_shorts.get((_uid, symbol)):
                                    logger.info(
                                        "WAIT skip uid=%d sym=%s reason=holds_position",
                                        _uid, symbol,
                                    )
                                    continue
                                user = db.get(User, _uid)
                                if not user:
                                    logger.info("WAIT skip uid=%d sym=%s reason=user_not_found", _uid, symbol)
                                    continue
                                if not user.telegram_enabled:
                                    logger.info("WAIT skip uid=%d sym=%s reason=telegram_disabled", _uid, symbol)
                                    continue
                                if not user.telegram_chat_id:
                                    logger.info("WAIT skip uid=%d sym=%s reason=no_chat_id", _uid, symbol)
                                    continue
                                # Spec 36 — user preference filter (before rate limit)
                                if not _user_wants_alert(user, "WAIT"):
                                    logger.info(
                                        "WAIT skip uid=%d sym=%s reason=user_pref wait_enabled=%s",
                                        _uid, symbol,
                                        getattr(user, "wait_alerts_enabled", "?"),
                                    )
                                    continue

                                # Resolve tier once for both gating and truncation
                                try:
                                    from api.app.tier import get_limits as _gl
                                    from api.app.dependencies import get_user_tier as _gut
                                    _tier = _gut(user)
                                    _wmax = _gl(_tier).get("ai_wait_alerts_per_day")
                                except Exception:
                                    _tier = "free"
                                    _wmax = None

                                # Per-user WAIT rate limit — persisted in usage_limits
                                if _wmax is not None:
                                    _wcount = _db_get_count(db, _uid, _FEATURE_WAIT, session)
                                    if _wcount >= _wmax:
                                        if _db_mark_notified(db, _uid, _FEATURE_WAIT_NOTIFIED, session):
                                            _send_telegram_to(
                                                f"💤 Daily AI Updates limit reached ({_wmax}/{_wmax}).\n"
                                                f"You still get actionable AI entries. "
                                                f"Upgrade to Pro for unlimited AI transparency.\n"
                                                f"→ https://www.tradingwithai.ai/billing",
                                                user.telegram_chat_id,
                                            )
                                        continue

                                # Spec 36 Option A — truncate reasoning for free users
                                _reason_out, _truncated = _truncate_for_free(reason, _tier)
                                if _truncated:
                                    _user_tg = (
                                        f"<b>AI UPDATE — {symbol} {_price_fmt}</b>\n"
                                        f"{_reason_out}\n"
                                        f"<i>Upgrade to Pro for full AI analysis → "
                                        f"https://www.tradingwithai.ai/billing</i>"
                                    )
                                else:
                                    _user_tg = (
                                        f"<b>AI UPDATE — {symbol} {_price_fmt}</b>\n"
                                        f"{_reason_out}"
                                    )
                                _send_telegram_to(_user_tg, user.telegram_chat_id)
                                _db_increment_count(db, _uid, _FEATURE_WAIT, session)
                        except Exception:
                            pass

                    logger.info("AI day scan %s: WAIT — %s", symbol, reason or "no setup")
                    continue

                # RESISTANCE warning
                if direction == "RESISTANCE":
                    # Dedup resistance per level
                    _res_key = (symbol, "RESISTANCE", _level_bucket(entry or 0))
                    fired = _day_fired.get(session, set())
                    if _res_key in fired:
                        continue
                    fired.add(_res_key)
                    _day_fired[session] = fired

                    _msg = f"RESISTANCE {symbol} — {reason}" if reason else f"RESISTANCE {symbol} — approaching overhead level"
                    # Record per-user so each user sees it in their feed
                    for _uid_r in symbol_users[symbol]:
                        db.add(Alert(
                            user_id=_uid_r, symbol=symbol,
                            alert_type="ai_resistance", direction="NOTICE",
                            price=result.get("price", 0), entry=entry,
                            message=_msg, score=0, session_date=session,
                        ))
                    db.commit()

                    # Send Telegram: direction changed + 30 min cooldown
                    _last_sent_r = _last_tg_time.get(symbol, 0)
                    _cooldown_r = (time.time() - _last_sent_r) > 1800
                    if _last_tg_direction.get(symbol) != "RESISTANCE" or _cooldown_r:
                        _last_tg_direction[symbol] = "RESISTANCE"
                        _last_tg_time[symbol] = time.time()
                        try:
                            from alerting.notifier import _send_telegram_to
                            _tg_msg = (
                                f"<b>AI SIGNAL — RESISTANCE {symbol} ${entry:.2f}</b>\n"
                                f"{reason}\n"
                                f"Action: tighten stop / take profits / watch for rejection"
                            )
                            for uid in symbol_users[symbol]:
                                user = db.get(User, uid)
                                if not (user and user.telegram_enabled and user.telegram_chat_id):
                                    continue
                                # Spec 36 — preference filter
                                if not _user_wants_alert(user, "RESISTANCE", conviction):
                                    continue
                                # Rate limit (DB-backed — survives worker restarts)
                                try:
                                    from api.app.tier import get_limits as _gl
                                    from api.app.dependencies import get_user_tier as _gut
                                    _tier_max_r = _gl(_gut(user)).get("ai_scan_alerts_per_day")
                                    if symbol.upper() in _UNCAPPED_SYMBOLS:
                                        _tier_max_r = None
                                    if _tier_max_r is not None:
                                        if _db_get_count(db, uid, _FEATURE_SCAN, session) >= _tier_max_r:
                                            if _db_mark_notified(db, uid, _FEATURE_SCAN_NOTIFIED, session):
                                                _send_telegram_to(
                                                    f"📊 Daily AI scan limit reached ({_tier_max_r}/{_tier_max_r}).\n"
                                                    f"You won't receive more AI scan alerts today.\n"
                                                    f"Upgrade to Pro for unlimited alerts.\n"
                                                    f"→ https://www.tradingwithai.ai/billing",
                                                    user.telegram_chat_id,
                                                )
                                            continue
                                except Exception:
                                    pass
                                _send_telegram_to(_tg_msg, user.telegram_chat_id)
                                _db_increment_count(db, uid, _FEATURE_SCAN, session)
                        except Exception:
                            logger.exception("AI day scan: Telegram failed for %s", symbol)

                    logger.info("AI day scan %s: RESISTANCE at $%.2f", symbol, entry or 0)
                    continue

                # SHORT entry — mirror of LONG at resistance (Spec 34)
                if direction == "SHORT":
                    if not entry or entry <= 0:
                        continue

                    # Dedup by (symbol, SHORT, level_bucket) — separate from LONG buckets
                    _bucket_s = _level_bucket(entry)
                    _short_dedup_key = (symbol, "SHORT", _bucket_s)
                    _fired_set_s = _day_fired.get(session, set())
                    if _short_dedup_key in _fired_set_s:
                        logger.debug(
                            "AI day scan %s: SHORT at bucket $%.2f already fired, skip",
                            symbol, _bucket_s,
                        )
                        continue
                    _fired_set_s.add(_short_dedup_key)
                    _day_fired[session] = _fired_set_s

                    score_s = {"HIGH": 85, "MEDIUM": 65, "LOW": 45}.get(conviction, 65)
                    setup_label_s = setup_type or "AI short entry"
                    message_s = f"{setup_label_s}: {reason}" if reason else setup_label_s

                    # Record Alert for each user watching — so each user sees it in
                    # their feed and /alerts/history returns it (multi-user correctness)
                    per_user_alert_ids_s: dict[int, int] = {}
                    for _uid_s in symbol_users[symbol]:
                        alert_s = Alert(
                            user_id=_uid_s, symbol=symbol,
                            alert_type="ai_day_short",
                            direction="SHORT",
                            price=result.get("price", entry),
                            entry=entry,
                            stop=result.get("stop"),
                            target_1=result.get("t1"),
                            target_2=result.get("t2"),
                            confidence=conviction.lower(),
                            message=message_s,
                            score=score_s,
                            session_date=session,
                        )
                        db.add(alert_s)
                        db.flush()
                        per_user_alert_ids_s[_uid_s] = alert_s.id
                        total_alerts += 1
                    db.commit()

                    # Spec 35 — auto-open paper trade in the AI Auto-Pilot account
                    _auto_alert_id_s = next(iter(per_user_alert_ids_s.values()), None)
                    _open_auto_trade(
                        db=db, symbol=symbol, direction="SHORT",
                        alert_id=_auto_alert_id_s,
                        entry=entry,
                        stop=result.get("stop"),
                        t1=result.get("t1"),
                        t2=result.get("t2"),
                        setup_type=setup_type,
                        conviction=conviction,
                        session=session,
                        is_crypto=is_crypto_alert_symbol(symbol),
                    )
                    db.commit()

                    # Telegram — ALWAYS deliver new SHORTs. Level dedup already
                    # blocks same-price repeats; a new SHORT at a different level
                    # is fresh info.
                    _last_tg_direction[symbol] = "SHORT"
                    if True:
                        try:
                            from alerting.notifier import _send_telegram_to
                            import html as _html_s

                            _stop_s = f"${result['stop']:.2f}" if result.get("stop") else "N/A"
                            _t1_s = f"${result['t1']:.2f}" if result.get("t1") else "N/A"
                            _t2_s = f"${result['t2']:.2f}" if result.get("t2") else "N/A"
                            _tg_msg_s = (
                                f"<b>AI SIGNAL — SHORT {_html_s.escape(symbol)} ${entry:.2f}</b>\n"
                                f"Entry ${entry:.2f} · Stop {_stop_s} · T1 {_t1_s} · T2 {_t2_s}\n"
                                f"Setup: {_html_s.escape(setup_label_s)}\n"
                                f"Conviction: {conviction}"
                            )

                            for uid in symbol_users[symbol]:
                                # Per-user position check: skip SHORT if user already holds SHORT
                                if user_open_shorts.get((uid, symbol)):
                                    logger.debug(
                                        "AI day scan %s: user %d already holds SHORT, skip delivery",
                                        symbol, uid,
                                    )
                                    continue
                                user = db.get(User, uid)
                                if user and user.telegram_enabled and user.telegram_chat_id:
                                    # Spec 36 — preference filter (SHORT)
                                    if not _user_wants_alert(user, "SHORT", conviction):
                                        continue
                                    # Per-user alert_id for buttons
                                    _user_alert_id_s = per_user_alert_ids_s.get(uid)
                                    _buttons_s = {
                                        "inline_keyboard": [[
                                            {"text": "✅ Took It", "callback_data": f"ack:{_user_alert_id_s}"},
                                            {"text": "❌ Skip", "callback_data": f"skip:{_user_alert_id_s}"},
                                            {"text": "🔴 Exit", "callback_data": f"exit:{_user_alert_id_s}"},
                                        ]]
                                    }
                                    # Rate limit check (DB-backed)
                                    _send_s = True
                                    try:
                                        from api.app.tier import get_limits as _gl
                                        from api.app.dependencies import get_user_tier as _gut
                                        _tier_max_s = _gl(_gut(user)).get("ai_scan_alerts_per_day")
                                        if symbol.upper() in _UNCAPPED_SYMBOLS:
                                            _tier_max_s = None
                                        if _tier_max_s is not None:
                                            if _db_get_count(db, uid, _FEATURE_SCAN, session) >= _tier_max_s:
                                                if _db_mark_notified(db, uid, _FEATURE_SCAN_NOTIFIED, session):
                                                    _send_telegram_to(
                                                        f"📊 Daily AI scan limit reached ({_tier_max_s}/{_tier_max_s}).\n"
                                                        f"You won't receive more AI scan alerts today.\n"
                                                        f"Upgrade to Pro for unlimited alerts.\n"
                                                        f"→ https://www.tradingwithai.ai/billing",
                                                        user.telegram_chat_id,
                                                    )
                                                _send_s = False
                                    except Exception:
                                        pass
                                    if _send_s:
                                        _send_telegram_to(_tg_msg_s, user.telegram_chat_id, reply_markup=_buttons_s)
                                        _db_increment_count(db, uid, _FEATURE_SCAN, session)
                                        logger.info(
                                            "AI day scan %s: SHORT at $%.2f → Telegram user %d",
                                            symbol, entry, uid,
                                        )
                        except Exception:
                            logger.exception("AI day scan: SHORT Telegram failed for %s", symbol)

                    continue  # done with this symbol; don't fall through to LONG block

                # LONG entry
                if not entry or entry <= 0:
                    continue

                # Regime filter: REMOVED (P2 — fire at key levels, no suppression)

                # Dedup by (symbol, LONG, level_bucket) — one LONG per price zone per session.
                # $2205, $2206, $2207 all bucket to $2200 → only first fires.
                # Different level (e.g. $2250) → fires as separate alert.
                _bucket = _level_bucket(entry)
                _level_dedup_key = (symbol, "LONG", _bucket)
                _fired_set = _day_fired.get(session, set())
                if _level_dedup_key in _fired_set:
                    logger.debug(
                        "AI day scan %s: LONG at bucket $%.2f already fired this session, skip",
                        symbol, _bucket,
                    )
                    continue
                _fired_set.add(_level_dedup_key)
                _day_fired[session] = _fired_set

                # Dedup via _day_fired (in-memory, already set above). DB message-based
                # dedup removed — it blocked per-user recording and wasn't needed.

                score = {"HIGH": 85, "MEDIUM": 65, "LOW": 45}.get(conviction, 65)
                setup_label = setup_type or "AI entry"
                message = f"{setup_label}: {reason}" if reason else setup_label

                # Record an Alert for EACH user watching this symbol — so each user
                # sees it in their own feed and /alerts/history returns it. Dedup is
                # handled by _day_fired (one AI call → multiple user records).
                per_user_alert_ids: dict[int, int] = {}  # uid -> alert_id
                for uid in symbol_users[symbol]:
                    alert = Alert(
                        user_id=uid, symbol=symbol,
                        alert_type="ai_day_long",
                        direction="BUY",
                        price=result.get("price", entry),
                        entry=entry,
                        stop=result.get("stop"),
                        target_1=result.get("t1"),
                        target_2=result.get("t2"),
                        confidence=conviction.lower(),
                        message=message,
                        score=score,
                        session_date=session,
                    )
                    db.add(alert)
                    db.flush()
                    per_user_alert_ids[uid] = alert.id
                    total_alerts += 1
                db.commit()

                # Spec 35 — auto-open paper trade in the AI Auto-Pilot account
                _auto_alert_id = next(iter(per_user_alert_ids.values()), None)
                _open_auto_trade(
                    db=db, symbol=symbol, direction="BUY",
                    alert_id=_auto_alert_id,
                    entry=entry,
                    stop=result.get("stop"),
                    t1=result.get("t1"),
                    t2=result.get("t2"),
                    setup_type=setup_type,
                    conviction=conviction,
                    session=session,
                    is_crypto=is_crypto_alert_symbol(symbol),
                )
                db.commit()

                # Telegram — ALWAYS deliver new LONGs that passed level dedup.
                # The _day_fired bucket already prevents same-price spam; a new
                # LONG at a different level is meaningful info and must fire.
                _last_tg_direction[symbol] = "LONG"
                if True:
                    try:
                        from alerting.notifier import _send_telegram_to
                        import html as _html

                        _stop = f"${result['stop']:.2f}" if result.get("stop") else "N/A"
                        _t1 = f"${result['t1']:.2f}" if result.get("t1") else "N/A"
                        _t2 = f"${result['t2']:.2f}" if result.get("t2") else "N/A"
                        _tg_msg = (
                            f"<b>AI SIGNAL — LONG {_html.escape(symbol)} ${entry:.2f}</b>\n"
                            f"Entry ${entry:.2f} · Stop {_stop} · T1 {_t1} · T2 {_t2}\n"
                            f"Setup: {_html.escape(setup_label)}\n"
                            f"Conviction: {conviction}"
                        )

                        for uid in symbol_users[symbol]:
                            # Per-user position check: skip LONG if user already holds this symbol
                            if user_open_longs.get((uid, symbol)):
                                logger.debug(
                                    "AI day scan %s: user %d already holds LONG, skip delivery",
                                    symbol, uid,
                                )
                                continue
                            user = db.get(User, uid)
                            if user and user.telegram_enabled and user.telegram_chat_id:
                                # Spec 36 — preference filter (LONG)
                                if not _user_wants_alert(user, "LONG", conviction):
                                    continue
                                # Each user's Telegram uses THEIR own alert_id for ACK/Skip/Exit buttons
                                _user_alert_id = per_user_alert_ids.get(uid)
                                _buttons = {
                                    "inline_keyboard": [[
                                        {"text": "✅ Took It", "callback_data": f"ack:{_user_alert_id}"},
                                        {"text": "❌ Skip", "callback_data": f"skip:{_user_alert_id}"},
                                        {"text": "🔴 Exit", "callback_data": f"exit:{_user_alert_id}"},
                                    ]]
                                }
                                # Rate limit: check ai_scan_alerts_per_day (per-user in-memory counter)
                                _send = True
                                _tier_max = None
                                try:
                                    from api.app.tier import get_limits as _gl
                                    from api.app.dependencies import get_user_tier as _gut
                                    _tier = _gut(user)
                                    _tier_max = _gl(_tier).get("ai_scan_alerts_per_day")
                                    if symbol.upper() in _UNCAPPED_SYMBOLS:
                                        _tier_max = None
                                    if _tier_max is not None:
                                        _delivered = _db_get_count(db, uid, _FEATURE_SCAN, session)
                                        if _delivered >= _tier_max:
                                            # One cap notification per day (DB-tracked)
                                            if _db_mark_notified(db, uid, _FEATURE_SCAN_NOTIFIED, session):
                                                _send_telegram_to(
                                                    f"📊 Daily AI scan limit reached ({_tier_max}/{_tier_max}).\n"
                                                    f"You won't receive more AI scan alerts today.\n"
                                                    f"Upgrade to Pro for unlimited alerts.\n"
                                                    f"→ https://www.tradingwithai.ai/billing",
                                                    user.telegram_chat_id,
                                                )
                                            _send = False
                                except Exception:
                                    pass  # skip limit on error
                                if _send:
                                    _send_telegram_to(_tg_msg, user.telegram_chat_id, reply_markup=_buttons)
                                    _db_increment_count(db, uid, _FEATURE_SCAN, session)
                                    logger.info("AI day scan %s: LONG at $%.2f → Telegram user %d", symbol, entry, uid)
                    except Exception:
                        logger.exception("AI day scan: Telegram failed for %s", symbol)

            logger.info("AI day scan complete: %d alerts from %d symbols", total_alerts, len(symbols))
            return total_alerts

    except Exception:
        logger.exception("AI day scan cycle failed")
        return 0


# ---------------------------------------------------------------------------
# Phase 3 (Spec 34) — Exit management scan for open positions
# ---------------------------------------------------------------------------


def build_exit_prompt(
    symbol: str,
    direction: str,       # "BUY" (long) or "SHORT"
    entry: float,
    stop: float | None,
    t1: float | None,
    t2: float | None,
    opened_minutes_ago: int,
    bars_5m: list[dict],
) -> str:
    """Build exit-management prompt — decides EXIT_NOW / TAKE_PROFITS / HOLD."""
    is_long = direction == "BUY"
    dir_label = "LONG" if is_long else "SHORT"

    session_high = max((b["high"] for b in bars_5m), default=0) if bars_5m else 0
    session_low = min((b["low"] for b in bars_5m), default=0) if bars_5m else 0
    current_price = bars_5m[-1]["close"] if bars_5m else 0
    if bars_5m:
        _tp_vol = sum(((b["high"] + b["low"] + b["close"]) / 3) * b.get("volume", 1) for b in bars_5m)
        _vol = sum(b.get("volume", 1) for b in bars_5m)
        vwap = _tp_vol / _vol if _vol > 0 else current_price
        avg_vol = sum(b.get("volume", 0) for b in bars_5m) / len(bars_5m) if bars_5m else 0
        last_vol = bars_5m[-1].get("volume", 0)
        vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0
    else:
        vwap = current_price
        vol_ratio = 1.0

    stop_direction = "below" if is_long else "above"
    target_direction = "above" if is_long else "below"
    prompt = (
        "You are managing an open trading position. Your job is NOT to second-guess\n"
        "the original trade plan — the stop is already set to handle failure. Your job\n"
        "is to catch truly exceptional events that invalidate the plan before the stop\n"
        "can trigger, OR to flag a clean exit opportunity at profit.\n\n"
        "CORE PRINCIPLE: TRUST THE STOP. If the stop hasn't hit, the plan is still alive.\n"
        "Normal pullback toward the stop is NOT a reason to exit early.\n\n"
        "OUTPUT (plain text, no markdown):\n\n"
        "Status: EXIT_NOW / TAKE_PROFITS / HOLD\n"
        "Reason: 1 short sentence\n"
        "Action: 1 short sentence\n\n"
        "RULES:\n"
        f"- EXIT_NOW ONLY if the stop has ACTUALLY been breached — price printed AT "
        f"or {stop_direction} the stop level.\n"
        "  Do NOT fire EXIT_NOW for 'approaching stop', 'testing stop zone', or\n"
        "  'structure looks weak'. The stop is the exit. Trust it.\n"
        "  Exception: a single massive volume spike that breaks a MAJOR support/resistance\n"
        "  level well beyond recent range — only then, exit ahead of the stop.\n"
        f"- TAKE_PROFITS ONLY if price has TOUCHED or exceeded T1 AND there's a\n"
        f"  clear rejection candle {stop_direction} T1 (long wick against direction,\n"
        "  or the next bar closes back against T1). Price merely approaching T1 = HOLD.\n"
        "- HOLD is the correct default 95% of the time. Do not invent reasons to exit.\n"
        "  'Consolidation', 'low volume', 'sideways chop' are all HOLD — not EXIT.\n"
        "- MAXIMUM 40 WORDS TOTAL.\n\n"
        f"[POSITION — {symbol} {dir_label}]\n"
        f"Entry: ${entry:.2f} ({opened_minutes_ago} min ago)\n"
    )
    if stop:
        prompt += f"Stop: ${stop:.2f}\n"
    if t1:
        prompt += f"T1: ${t1:.2f}\n"
    if t2:
        prompt += f"T2: ${t2:.2f}\n"

    prompt += (
        f"\n[CURRENT CHART]\n"
        f"Current Price: ${current_price:.2f}\n"
        f"Session High: ${session_high:.2f}\n"
        f"Session Low: ${session_low:.2f}\n"
        f"VWAP: ${vwap:.2f}\n"
        f"Volume Ratio (last bar): {vol_ratio:.1f}x avg\n"
    )

    if bars_5m:
        lines = [f"\n[5-MIN BARS — last {min(len(bars_5m), 20)}]"]
        for b in bars_5m[-20:]:
            lines.append(
                f"O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} "
                f"C={b['close']:.2f} V={b.get('volume', 0):.0f}"
            )
        prompt += "\n".join(lines)

    return prompt


def parse_exit_response(text: str) -> dict:
    """Parse exit management response from Claude."""
    result = {"status": None, "reason": None, "action": None, "raw": text}
    status_match = re.search(r"Status:\s*(EXIT_NOW|TAKE_PROFITS|HOLD)", text, re.IGNORECASE)
    if status_match:
        result["status"] = status_match.group(1).upper()
    reason_match = re.search(r"Reason:\s*(.+?)(?:\n|$)", text)
    if reason_match:
        result["reason"] = reason_match.group(1).strip()
    action_match = re.search(r"Action:\s*(.+?)(?:\n|$)", text)
    if action_match:
        result["action"] = action_match.group(1).strip()
    return result


def scan_open_position(trade_data: dict, bars_5m: list[dict], api_key: str) -> dict | None:
    """Run exit analysis on one open position. Returns parsed dict or None."""
    try:
        prompt = build_exit_prompt(
            symbol=trade_data["symbol"],
            direction=trade_data["direction"],
            entry=trade_data["entry"],
            stop=trade_data.get("stop"),
            t1=trade_data.get("t1"),
            t2=trade_data.get("t2"),
            opened_minutes_ago=trade_data.get("opened_minutes_ago", 0),
            bars_5m=bars_5m,
        )
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        start = time.time()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=150,
            system=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Manage {trade_data['symbol']} position now."}],
            timeout=15.0,
        )
        elapsed = time.time() - start
        response_text = response.content[0].text.strip()
        logger.info("AI exit scan %s: %.1fs — %s", trade_data["symbol"], elapsed, response_text[:80])
        return parse_exit_response(response_text)
    except Exception:
        logger.exception("AI exit scan failed for %s", trade_data.get("symbol"))
        return None


def exit_scan_cycle(sync_session_factory) -> int:
    """Scan all open RealTrades for exit signals. Runs after entry scan."""
    from datetime import datetime

    session = date.today().isoformat()
    api_key = _resolve_api_key()
    if not api_key:
        return 0

    try:
        from sqlalchemy import select
        from app.models.paper_trade import RealTrade
        from app.models.user import User
        from app.models.alert import Alert
        from analytics.intraday_data import fetch_intraday, fetch_intraday_crypto
        from analytics.market_hours import is_market_hours_for_symbol
        from config import is_crypto_alert_symbol

        with sync_session_factory() as db:
            open_trades = db.execute(
                select(RealTrade).where(RealTrade.status == "open")
            ).scalars().all()

            if not open_trades:
                return 0

            total_sent = 0
            now_ts = time.time()

            for trade in open_trades:
                sym = trade.symbol
                if not is_market_hours_for_symbol(sym):
                    continue

                is_crypto = is_crypto_alert_symbol(sym)
                try:
                    bars_df = fetch_intraday_crypto(sym) if is_crypto else fetch_intraday(sym)
                    if bars_df is None or bars_df.empty:
                        continue
                    bars_5m = [
                        {"open": float(r["Open"]), "high": float(r["High"]),
                         "low": float(r["Low"]), "close": float(r["Close"]),
                         "volume": float(r["Volume"])}
                        for _, r in bars_df.tail(20).iterrows()
                    ]
                except Exception:
                    continue

                opened_mins = 0
                if trade.opened_at:
                    try:
                        opened_mins = int((datetime.utcnow() - trade.opened_at).total_seconds() / 60)
                    except Exception:
                        opened_mins = 0

                trade_data = {
                    "symbol": sym,
                    "direction": trade.direction,
                    "entry": trade.entry_price,
                    "stop": trade.stop_price,
                    "t1": trade.target_price,
                    "t2": trade.target_2_price,
                    "opened_minutes_ago": opened_mins,
                }

                result = scan_open_position(trade_data, bars_5m, api_key)
                if not result or not result.get("status"):
                    continue

                status = result["status"]
                if status == "HOLD":
                    continue  # don't notify

                # Cooldown: (trade_id, status) within last 30 min → skip
                cooldown_key = (trade.id, status)
                last_sent = _exit_notified.get(cooldown_key, 0)
                if (now_ts - last_sent) < _EXIT_COOLDOWN_SEC:
                    logger.debug("Exit scan trade %d: %s suppressed by cooldown", trade.id, status)
                    continue
                _exit_notified[cooldown_key] = now_ts

                reason = result.get("reason") or ""
                action = result.get("action") or ""
                alert_msg = f"{status}: {reason}" + (f" | {action}" if action else "")

                exit_alert = Alert(
                    user_id=trade.user_id,
                    symbol=sym,
                    alert_type="ai_exit_signal",
                    direction="NOTICE",
                    price=bars_5m[-1]["close"] if bars_5m else trade.entry_price,
                    message=alert_msg,
                    score=0,
                    session_date=session,
                )
                db.add(exit_alert)
                db.flush()
                _alert_id = exit_alert.id
                db.commit()

                user = db.get(User, trade.user_id)
                if not (user and user.telegram_enabled and user.telegram_chat_id):
                    continue

                # Spec 36 — user preference filter (EXIT signals)
                if not _user_wants_alert(user, "EXIT"):
                    continue

                try:
                    from api.app.tier import get_limits as _gl
                    from api.app.dependencies import get_user_tier as _gut
                    _tier_max = _gl(_gut(user)).get("ai_scan_alerts_per_day")
                    if _tier_max is not None:
                        if _db_get_count(db, trade.user_id, _FEATURE_SCAN, session) >= _tier_max:
                            if _db_mark_notified(db, trade.user_id, _FEATURE_SCAN_NOTIFIED, session):
                                from alerting.notifier import _send_telegram_to
                                _send_telegram_to(
                                    f"📊 Daily AI scan limit reached ({_tier_max}/{_tier_max}).\n"
                                    f"Upgrade to Pro for unlimited alerts.\n"
                                    f"→ https://www.tradingwithai.ai/billing",
                                    user.telegram_chat_id,
                                )
                            continue
                except Exception:
                    pass

                from alerting.notifier import _send_telegram_to
                import html as _html

                if status == "EXIT_NOW":
                    header = f"🔴 AI EXIT NOW — {_html.escape(sym)}"
                    buttons = {"inline_keyboard": [[
                        {"text": "🛑 Exit Trade", "callback_data": f"exit:{_alert_id}"},
                    ]]}
                else:  # TAKE_PROFITS
                    header = f"🎯 AI TAKE PROFITS — {_html.escape(sym)}"
                    buttons = {"inline_keyboard": [[
                        {"text": "🛑 Exit Trade", "callback_data": f"exit:{_alert_id}"},
                        {"text": "✋ Keep Holding", "callback_data": f"hold:{_alert_id}"},
                    ]]}

                tg_msg = (
                    f"<b>{header}</b>\n"
                    f"{_html.escape(reason)}\n"
                    f"Action: {_html.escape(action)}"
                )

                try:
                    _send_telegram_to(tg_msg, user.telegram_chat_id, reply_markup=buttons)
                    _db_increment_count(db, trade.user_id, _FEATURE_SCAN, session)
                    total_sent += 1
                    logger.info(
                        "Exit scan %s trade %d: %s → Telegram user %d",
                        sym, trade.id, status, trade.user_id,
                    )
                except Exception:
                    logger.exception("Exit scan: Telegram failed for %s trade %d", sym, trade.id)

            logger.info("Exit scan complete: %d exit signals sent", total_sent)
            return total_sent

    except Exception:
        logger.exception("Exit scan cycle failed")
        return 0
