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
from typing import Optional

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

# Time-based dedup: suppress rapid-fire LONGs/SHORTs for the same symbol
_last_long_time: dict[str, float] = {}   # {symbol: epoch of last LONG fire}
_last_short_time: dict[str, float] = {}  # {symbol: epoch of last SHORT fire}
_LONG_DEDUP_WINDOW = int(os.environ.get("LONG_DEDUP_WINDOW_SEC", "600"))
_SHORT_DEDUP_WINDOW = int(os.environ.get("SHORT_DEDUP_WINDOW_SEC", "600"))

_last_crypto_scan: float = 0.0
_CRYPTO_SCAN_INTERVAL = int(os.environ.get("CRYPTO_SCAN_INTERVAL_SEC", "7200"))  # 2 hours

# Exit scan cooldown — (trade_id, status) -> last_sent_ts. 30-min cooldown per pair.
_exit_notified: dict[tuple[int, str], float] = {}
_EXIT_COOLDOWN_SEC = 1800  # 30 min

# Spec 44: WAIT override — env flag for instant rollback
_WAIT_OVERRIDE = os.environ.get("WAIT_OVERRIDE_ENABLED", "true").lower() == "true"

# Spec 45: Multi-timeframe confluence — env flag for instant rollback
_MTF_CONFLUENCE = os.environ.get("MTF_CONFLUENCE_ENABLED", "true").lower() == "true"

# Setup keywords indicating AI identified a valid LONG setup
_LONG_SETUP_SIGNALS = [
    "reclaim", "bounc", "higher low", "holding above",
    "breakout", "flipped support", "bull", "held support",
    "pull", "intact", "buying opportunity", "support test",
    "holding vwap", "holding support",
]

# AI phrases that mean "not yet" — suppress override even if setup keywords match
_WAIT_QUALIFIERS = [
    "waiting for", "awaiting", "minimal confirmation", "no confirmation",
    "without clear", "no clear",
]

# Setup keywords indicating AI identified a valid SHORT setup
_SHORT_SETUP_SIGNALS = [
    "reject", "lower high", "fail", "breakdown", "lost vwap",
    "bear",
]


def _compute_stop_t1(parsed: dict, prior_day: dict | None, bars_5m: list[dict] | None) -> None:
    """Fill in stop/T1 from structural levels when AI didn't provide them."""
    entry = parsed.get("entry", 0)
    direction = (parsed.get("direction") or "").upper()
    if not entry or entry <= 0 or direction not in ("LONG", "SHORT"):
        return

    levels: list[float] = []
    if prior_day:
        for k in ("high", "low", "ma20", "ma50", "ma100", "ma200"):
            v = prior_day.get(k)
            if v and v > 0:
                levels.append(float(v))
    if bars_5m:
        session_high = max(b["high"] for b in bars_5m)
        session_low = min(b["low"] for b in bars_5m)
        tp_vol = sum(((b["high"] + b["low"] + b["close"]) / 3) * b.get("volume", 1) for b in bars_5m)
        vol = sum(b.get("volume", 1) for b in bars_5m)
        vwap = tp_vol / vol if vol > 0 else bars_5m[-1]["close"]
        levels.extend([session_high, session_low, vwap])

    below = sorted([l for l in levels if l < entry * 0.999], reverse=True)
    above = sorted([l for l in levels if l > entry * 1.001])

    if direction == "LONG":
        if not parsed.get("stop") and below:
            parsed["stop"] = below[0]
        if not parsed.get("t1") and above:
            parsed["t1"] = above[0]
    elif direction == "SHORT":
        if not parsed.get("stop") and above:
            parsed["stop"] = above[0]
        if not parsed.get("t1") and below:
            parsed["t1"] = below[0]


def _compute_htf_bias(bars: list[dict]) -> str:
    """Spec 45: compute trend bias from higher-timeframe bars."""
    if not bars or len(bars) < 5:
        return "NEUTRAL"

    closes = [b["close"] for b in bars]
    span = min(20, len(closes))
    alpha = 2 / (span + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = alpha * c + (1 - alpha) * ema

    current = closes[-1]
    price_vs_ema = "above" if current > ema * 1.001 else ("below" if current < ema * 0.999 else "at")

    lows = [b["low"] for b in bars[-3:]]
    highs = [b["high"] for b in bars[-3:]]
    higher_lows = lows[-1] > lows[0] and lows[-2] >= lows[0]
    lower_highs = highs[-1] < highs[0] and highs[-2] <= highs[0]

    bull_signals = (price_vs_ema == "above") + higher_lows
    bear_signals = (price_vs_ema == "below") + lower_highs

    if bull_signals >= 2:
        return "BULL"
    if bear_signals >= 2:
        return "BEAR"
    if bull_signals > bear_signals:
        return "BULL"
    if bear_signals > bull_signals:
        return "BEAR"
    return "NEUTRAL"


def _format_htf_context(bias_4h: str, bias_1h: str) -> str:
    """Spec 45: format HTF bias block for AI prompt injection."""
    if bias_4h == "NEUTRAL" and bias_1h == "NEUTRAL":
        return ""

    if bias_4h == bias_1h == "BULL":
        alignment = "ALIGNED BULL — favor LONG setups"
    elif bias_4h == bias_1h == "BEAR":
        alignment = "ALIGNED BEAR — favor SHORT / RESISTANCE"
    elif bias_4h == "BEAR" and bias_1h != "BEAR":
        alignment = "CONFLICTING — 4H bearish, be cautious with LONGs"
    elif bias_4h == "BULL" and bias_1h != "BULL":
        alignment = "CONFLICTING — 4H bullish, be cautious with SHORTs"
    else:
        alignment = "NEUTRAL — no strong multi-TF trend"

    return (
        f"[HIGHER TIMEFRAME BIAS]\n"
        f"4H Trend: {bias_4h} | 1H Trend: {bias_1h}\n"
        f"Alignment: {alignment}"
    )


def _apply_wait_override(
    parsed: dict, symbol: str = "",
    prior_day: dict | None = None, bars_5m: list[dict] | None = None,
    htf_bias_4h: str = "NEUTRAL", htf_bias_1h: str = "NEUTRAL",
) -> dict:
    """Spec 44: detect when AI described a valid setup but returned WAIT.

    Override to LONG MEDIUM (or SHORT MEDIUM) so the alert fires. The AI reads
    data correctly — it just won't commit. This gate enforces commitment.
    """
    if not _WAIT_OVERRIDE:
        return parsed

    direction = (parsed.get("direction") or "").upper()
    if direction != "WAIT":
        return parsed

    reason_lower = (parsed.get("reason") or "").lower()
    if not reason_lower:
        return parsed

    # AI phrases that mean "not yet" — don't override
    if any(q in reason_lower for q in _WAIT_QUALIFIERS):
        return parsed

    long_detected = any(kw in reason_lower for kw in _LONG_SETUP_SIGNALS)
    short_detected = any(kw in reason_lower for kw in _SHORT_SETUP_SIGNALS)

    if long_detected and not short_detected:
        parsed["direction"] = "LONG"
        parsed["conviction"] = "MEDIUM"
        parsed["_override"] = True
        if not parsed.get("entry") or parsed.get("entry", 0) <= 0:
            parsed["entry"] = parsed.get("price", 0)
        _compute_stop_t1(parsed, prior_day, bars_5m)
        logger.info(
            "AI day scan %s: WAIT→LONG override (entry=$%.2f, stop=$%.2f, t1=$%.2f, reason: %s)",
            symbol, parsed.get("entry", 0), parsed.get("stop") or 0, parsed.get("t1") or 0,
            (parsed.get("reason") or "")[:80],
        )
    elif short_detected and not long_detected:
        parsed["direction"] = "SHORT"
        parsed["conviction"] = "MEDIUM"
        parsed["_override"] = True
        if not parsed.get("entry") or parsed.get("entry", 0) <= 0:
            parsed["entry"] = parsed.get("price", 0)
        _compute_stop_t1(parsed, prior_day, bars_5m)
        logger.info(
            "AI day scan %s: WAIT→SHORT override (entry=$%.2f, stop=$%.2f, t1=$%.2f, reason: %s)",
            symbol, parsed.get("entry", 0), parsed.get("stop") or 0, parsed.get("t1") or 0,
            (parsed.get("reason") or "")[:80],
        )

    # Spec 45: MTF gate — block counter-trend WAIT overrides
    # But allow when 1H agrees with the direction (intraday reversal)
    if _MTF_CONFLUENCE and parsed.get("_override") and htf_bias_4h != "NEUTRAL":
        new_dir = (parsed.get("direction") or "").upper()
        if new_dir == "LONG" and htf_bias_4h == "BEAR" and htf_bias_1h != "BULL":
            logger.info("AI day scan %s: MTF gate blocked WAIT→LONG override (4H=%s 1H=%s)", symbol, htf_bias_4h, htf_bias_1h)
            parsed["direction"] = "WAIT"
            parsed.pop("_override", None)
        elif new_dir == "SHORT" and htf_bias_4h == "BULL" and htf_bias_1h != "BEAR":
            logger.info("AI day scan %s: MTF gate blocked WAIT→SHORT override (4H=%s 1H=%s)", symbol, htf_bias_4h, htf_bias_1h)
            parsed["direction"] = "WAIT"
            parsed.pop("_override", None)

    return parsed


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
    live_price: float | None = None,
    htf_context: str | None = None,
    spy_daily_regime: str | None = None,
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
        "HIGHER TIMEFRAME: When 4H trend is BEAR, counter-trend LONGs need stronger\n"
        "confirmation (prefer MEDIUM+ conviction). When aligned, be decisive.\n\n"
        "CONVICTION LADDER — rate by CONFLUENCE (count the confirmations):\n"
        "Confirmations for LONG (price-action first, indicators are optional):\n"
        "  (a) higher low structure on 5-min (last swing low ABOVE prior swing low)\n"
        "  (b) volume picking up on the bounce bar (>0.7x avg)\n"
        "  (c) multi-level confluence (price at 2+ levels: e.g. VWAP + 50MA, PDL + 100EMA)\n"
        "  (d) reclaim pattern (price briefly broke level, now back above)\n"
        "  (e) RSI modifier — only counts if it reinforces price action, never as primary\n"
        "- HIGH: 3 or more confirmations present\n"
        "- MEDIUM: 2 confirmations\n"
        "- LOW: 1 confirmation or just touching the level\n"
        "Confirmations for SHORT (mirror):\n"
        "  (a) lower high structure on 5-min\n"
        "  (b) volume on rejection bar (>0.7x avg)\n"
        "  (c) multi-level confluence (resistance stack)\n"
        "  (d) failed breakout (price briefly pushed through, now back below)\n"
        "  (e) RSI modifier — only counts if it reinforces price action, never as primary\n"
        "- Same scoring: 3+ = HIGH, 2 = MEDIUM, 1 = LOW.\n"
        "Do NOT default to LOW when multiple confirmations are present.\n"
        "Volume alone is NOT required for HIGH — confluence matters more than any single metric.\n"
        "State which confirmations apply in the Reason field.\n\n"
        "RSI POLICY (critical — the user trades intraday, not swing):\n"
        "- NEVER lead the Reason with RSI. Lead with the structural level.\n"
        "- NEVER cite RSI as the primary reason for WAIT or RESISTANCE.\n"
        "- A stock at RSI 70+ in a trending market is NORMAL, not a sell signal.\n"
        "  It can keep running for hours and still offer LONG pullback entries.\n"
        "- Mention RSI ONLY when it genuinely adds information — do not echo it in\n"
        "  every update. Silence on RSI is preferred over redundant 'RSI overbought'.\n\n"
        "VWAP TIMING:\n"
        "- VWAP is NOT reliable in the first 30 minutes of the session (before 10:00 ET).\n"
        "  Too little volume has accumulated — early-session VWAP is just 'near the open'.\n"
        "  Do not cite VWAP as support/resistance before 10:00 ET. Use PDH/PDL,\n"
        "  session high/low, and daily MA/EMA as primary levels until VWAP settles.\n\n"
        "KEY LEVELS THAT ALWAYS WARRANT FIRING (never just WAIT at these):\n"
        "- Daily MA test (20/50/100/200) within 0.3%\n"
        "- PDH/PDL reclaim or rejection\n"
        "- VWAP reclaim after break\n"
        "- Session high/low single-test (don't wait for double-test intraday)\n"
        "- Prior swing high/low retest\n"
        "- WEEKLY high breakout (close above + volume >= 0.7x) → LONG at breakout level\n"
        "- WEEKLY high reclaim (just broke, pulling back to it) → LONG (flipped support)\n"
        "- WEEKLY low bounce / hold → LONG at weekly low\n"
        "- MONTHLY high/low breakout or reclaim → LONG\n"
        "- Prior-week / prior-month high/low retest → LONG on hold\n\n"
        "FLIPPED LEVEL RULE (critical — avoid calling flipped support as RESISTANCE):\n"
        "- When price breaks a resistance level and pulls back to it, that level becomes SUPPORT.\n"
        "  Fire LONG on the retest, NOT RESISTANCE.\n"
        "- Same inverse: former support that price broke DOWN through becomes resistance on SHORT.\n"
        "- Example: weekly high $2327 broke at 14:00, price now pulling back to $2327 at 16:00 →\n"
        "  LONG (weekly high reclaim), NOT RESISTANCE.\n\n"
        "CONTEXT-AWARE FRAMING (do not call post-move pullbacks 'mid-range'):\n"
        "- If price made a directional move (>0.5% in the last 2-4 bars) then pulled back,\n"
        "  this is a PULLBACK-BUY setup — not 'mid-range indecision'.\n"
        "- Pullback to VWAP after breakout = LONG (buyers defending the move), not WAIT.\n"
        "- Pullback to a just-broken level = LONG (flipped-support retest), not WAIT.\n"
        "- 'Mid-range' framing only applies when NO directional move preceded the current zone.\n\n"
        "SHORT RULES (tight — fire only at real structural rejections):\n"
        "VALID SHORT setups (any one is enough — not conjunctive):\n"
        "- PDH rejection (price tested prior day high, forming lower high)\n"
        "- Daily MA rejection from below (20/50/100/200 MA or EMA) — price tests, fails\n"
        "- Weekly high rejection (prior-week high tested and held down)\n"
        "- Monthly high rejection\n"
        "- Prior swing high rejection on daily chart\n"
        "RSI is NOT a SHORT trigger on its own — a stock can stay above 70 for\n"
        "hours in a strong trend and keep offering LONG entries. RSI only matters\n"
        "as one optional confirmation on top of a structural rejection.\n"
        "NEVER fire SHORT *trade alerts* on these (they're strength, not weakness):\n"
        "- Session high break or hold with volume → this is LONG continuation, never SHORT\n"
        "- Session high first-test without structural level confluence → NOT a SHORT trade\n"
        "- Breakouts through prior day / session levels on volume → LONG, not SHORT\n"
        "Session high as RESISTANCE NOTICE is STILL VALUABLE:\n"
        "- Always OK to emit RESISTANCE notice at session high — it's informational\n"
        "  (heads-up on approaching resistance, useful as profit target for longs).\n"
        "- Just don't classify it as SHORT trade direction without structural confluence.\n\n"
        "WAIT is only for: price mid-range (>0.3% from every level), no recent directional\n"
        "move (<0.5% in last 4 bars), no structural setup forming.\n\n"
        "OUTPUT (plain text, no markdown):\n\n"
        "SETUP: [what you see — e.g. PDL bounce, VWAP reclaim, 50MA rejection, PDH fail]\n"
        "Direction: LONG / SHORT / RESISTANCE / WAIT\n"
        "Entry: $price (the key level, not current price)\n"
        "Stop: $price (LONG: below support; SHORT: above resistance)\n"
        "T1: $price (LONG: next resistance above; SHORT: next support below)\n"
        "T2: $price (LONG: second resistance; SHORT: second support)\n"
        "Conviction: HIGH / MEDIUM / LOW\n"
        "Reason: 1 sentence — lead with the LEVEL + price action. Volume optional.\n"
        "  GOOD: 'PDL bounce with higher low on 5-min, volume 1.2x avg'\n"
        "  GOOD: '50MA reclaim after pullback, flipped support'\n"
        "  BAD:  'RSI overbought at session high' (RSI-first, no level priority)\n"
        "  BAD:  'Price at VWAP with RSI 72' (before 10:00 ET)\n\n"
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

        # CRITICAL: use live_price (real-time last trade) for "current price"
        # The 5-min bar close can be 2-7 minutes stale during forming bars.
        # AI must evaluate LEVELS/STRUCTURE from bars but ANCHOR "where we
        # are now" to the live price.
        _now_price = live_price if (live_price and live_price > 0) else bars_5m[-1]['close']
        _bar_close = bars_5m[-1]['close']
        _live_note = ""
        if live_price and abs(live_price - _bar_close) / _bar_close > 0.002:
            _live_note = (
                f"\n⚠ LIVE PRICE ${live_price:.2f} differs from last bar close "
                f"${_bar_close:.2f} — use LIVE price for 'where are we now' "
                f"decisions. The bar close is recent history."
            )
        parts.append(
            f"\n[INTRADAY LEVELS]\n"
            f"Session High: ${session_high:.2f}\n"
            f"Session Low: ${session_low:.2f}\n"
            f"VWAP: ${vwap:.2f}\n"
            f"Current Price (LIVE — real-time last trade): ${_now_price:.2f}\n"
            f"Last 5-min bar close: ${_bar_close:.2f} (may be 2-5 min old)\n"
            f"Volume Ratio: {vol_ratio:.1f}x avg"
            f"{_live_note}"
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

    if htf_context:
        parts.append(f"\n{htf_context}")

    if spy_daily_regime:
        _is_spy = symbol.upper() == "SPY"
        _trending_spy_carve_out = (
            "\n[MARKET REGIME: TRENDING — SPY above 8 & 21 daily EMA]\n"
            "Strong upside momentum on the broader market.\n"
            "This IS SPY — intraday shorts on structural rejection ARE VALID.\n"
            "Fire SHORT with HIGH conviction ONLY on one of:\n"
            "  - PDH rejection (tested, lower high forming)\n"
            "  - PDL breakdown with volume >= 1.5x avg\n"
            "  - VWAP loss with volume >= 1.5x avg\n"
            "  - Key MA/EMA rejection from below (20/50/100/200 MA or EMA)\n"
            "No volume / weak structure → MEDIUM or LOW (will be filtered).\n"
            "Still fire LONG at support bounces as usual."
        )
        _regime_guidance = {
            "TRENDING": _trending_spy_carve_out if _is_spy else (
                "\n[MARKET REGIME: TRENDING — SPY above 8 & 21 daily EMA]\n"
                "Strong upside momentum. Focus on LONG setups at key MA bounces.\n"
                "Do NOT fire SHORT — counter-trend shorts lose in trending markets.\n"
                "Only output SHORT if rejection at MULTI-DAY structural level with HIGH conviction."
            ),
            "CAUTIOUS": (
                "\n[MARKET REGIME: CAUTIOUS — SPY below 8 EMA, above 21 EMA]\n"
                "Market pulling back. Reduce LONG conviction by one notch.\n"
                "Only fire LONG at strongest levels (100/200 MA, multi-day double bottom).\n"
                "SHORT setups at resistance are now valid."
            ),
            "TACTICAL": (
                "\n[MARKET REGIME: TACTICAL — SPY below 21 daily EMA]\n"
                "No swing trades or overnight holds. Focus on intraday tactical trades.\n"
                "Trade around key levels and MAs — BOTH long and short setups are valid.\n"
                "Prioritize clean intraday setups at support/resistance with tight stops."
            ),
        }
        parts.append(_regime_guidance.get(spy_daily_regime, ""))

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


def scan_day_trade(symbol: str, api_key: str, active_positions: list[dict] | None = None,
                   spy_daily_regime: str | None = None) -> dict | None:
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
        bars_4h_df = (
            fetch_intraday_crypto(symbol, interval="4h")
            if is_crypto
            else fetch_intraday(symbol, period="10d", interval="4h")
        )
        prior_day = fetch_prior_day(symbol, is_crypto=is_crypto)

        # LIVE price — closest to what the user sees on their chart. Uses
        # Alpaca latest-trade endpoint, not the stale 5-min bar close.
        # Falls back to last-bar close if live fetch fails.
        from analytics.intraday_data import fetch_latest_price
        live_price = fetch_latest_price(symbol)
        bar_close = float(bars_5m_df.iloc[-1]["Close"])
        current_price = live_price if live_price else bar_close
        if live_price and abs(live_price - bar_close) / bar_close > 0.003:
            logger.info(
                "%s live-vs-bar drift: live=$%.2f bar_close=$%.2f (%.2f%%)",
                symbol, live_price, bar_close,
                (live_price - bar_close) / bar_close * 100,
            )

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
        bars_4h = []
        if bars_4h_df is not None and not (hasattr(bars_4h_df, "empty") and bars_4h_df.empty):
            bars_4h = [
                {"open": float(r["Open"]), "high": float(r["High"]),
                 "low": float(r["Low"]), "close": float(r["Close"]),
                 "volume": float(r["Volume"])}
                for _, r in bars_4h_df.tail(20).iterrows()
            ]

        # Spec 45: compute HTF bias
        bias_4h = _compute_htf_bias(bars_4h) if _MTF_CONFLUENCE else "NEUTRAL"
        bias_1h = _compute_htf_bias(bars_1h) if _MTF_CONFLUENCE else "NEUTRAL"
        htf_context = _format_htf_context(bias_4h, bias_1h) if _MTF_CONFLUENCE else ""

        prompt = build_day_trade_prompt(
            symbol, bars_5m, bars_1h, prior_day, active_positions,
            live_price=live_price,
            htf_context=htf_context or None,
            spy_daily_regime=spy_daily_regime,
        )

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system_with_cache = [
            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
        ]

        start = time.time()
        response = client.messages.create(
            model=CLAUDE_MODEL,
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

        # Spec 44: override WAIT when reason describes a valid setup
        # Spec 45: pass HTF biases to gate counter-trend overrides
        _apply_wait_override(
            parsed, symbol, prior_day=prior_day, bars_5m=bars_5m,
            htf_bias_4h=bias_4h, htf_bias_1h=bias_1h,
        )

        # Staleness gate (progress-to-target): a setup is stale if price has
        # traveled >50% of the distance from entry to T1 (the move already
        # played out). Works for any volatility / R:R because it's self-scaled
        # to the setup size. Falls back to no-gate if T1 missing.
        #
        # LONG:   progress = (current - entry) / (T1 - entry)
        # SHORT:  progress = (entry - current) / (entry - T1)
        #
        # Progress threshold: 0.5 → stale (more than halfway to target).
        _dir = (parsed.get("direction") or "").upper()
        _entry = parsed.get("entry") or 0
        _t1 = parsed.get("t1") or 0
        STALE_THRESHOLD = 0.5
        if _entry > 0 and current_price > 0 and _t1 > 0:
            if _dir == "LONG" and _t1 > _entry:
                progress = (current_price - _entry) / (_t1 - _entry)
                if progress > STALE_THRESHOLD:
                    logger.info(
                        "AI day scan %s: LONG stale — entry $%.2f, T1 $%.2f, now $%.2f (%.0f%% to T1)",
                        symbol, _entry, _t1, current_price, progress * 100,
                    )
                    parsed["direction"] = "WAIT"
                    parsed["reason"] = (
                        f"Setup {progress*100:.0f}% to T1 — move already played. "
                        f"Entry $${_entry:.2f}, T1 $${_t1:.2f}, now $${current_price:.2f}. "
                        f"Await next setup."
                    ).replace("$$", "$")
            elif _dir == "SHORT" and _t1 < _entry:
                progress = (_entry - current_price) / (_entry - _t1)
                if progress > STALE_THRESHOLD:
                    logger.info(
                        "AI day scan %s: SHORT stale — entry $%.2f, T1 $%.2f, now $%.2f (%.0f%% to T1)",
                        symbol, _entry, _t1, current_price, progress * 100,
                    )
                    parsed["direction"] = "WAIT"
                    parsed["reason"] = (
                        f"Setup {progress*100:.0f}% to T1 — move already played. "
                        f"Entry $${_entry:.2f}, T1 $${_t1:.2f}, now $${current_price:.2f}. "
                        f"Await next setup."
                    ).replace("$$", "$")

        # SHORT policy (regime-aware):
        # TRENDING: suppress all SHORTs EXCEPT SPY HIGH-conviction (intraday
        #   key-level breaks override daily bull bias — PDH rejection, PDL/VWAP
        #   breakdown on volume, MA/EMA rejection). SPY LOW/MEDIUM → RESISTANCE.
        # CAUTIOUS/TACTICAL: allow SHORTs, but LOW conviction → RESISTANCE
        if parsed.get("direction") == "SHORT":
            conv = (parsed.get("conviction") or "MEDIUM").upper()
            sym_upper = symbol.upper()
            if spy_daily_regime == "TRENDING":
                if sym_upper == "SPY" and conv == "HIGH":
                    logger.info("AI day scan SPY: HIGH SHORT allowed in TRENDING (intraday key-level break)")
                else:
                    parsed["direction"] = "RESISTANCE"
                    logger.info(
                        "AI day scan %s: SHORT → RESISTANCE (TRENDING regime, conv=%s)",
                        symbol, conv,
                    )
            elif sym_upper == "SPY":
                if conv == "LOW":
                    logger.info("AI day scan %s: SPY SHORT LOW suppressed (min MEDIUM)", symbol)
                    parsed["direction"] = "RESISTANCE"
            else:
                if conv == "LOW":
                    parsed["direction"] = "RESISTANCE"
                    logger.info("AI day scan %s: SHORT LOW → RESISTANCE", symbol)

        return parsed

    except Exception:
        logger.exception("AI day scan failed for %s", symbol)
        return None


def day_scan_cycle(
    sync_session_factory,
    symbols_filter: Optional[set[str]] = None,
    exclude_symbols: Optional[set[str]] = None,
) -> int:
    """Main day trade scan cycle — runs every 3 min during market hours.

    symbols_filter: if set, scan only these symbols (e.g. {"SPY"}).
    exclude_symbols: if set, skip these symbols (e.g. {"SPY"} when a
        separate faster job is scanning SPY).
    """
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
        _last_long_time.clear()
        _last_short_time.clear()
        _day_session = session

        # Seed _day_fired from today's alerts so worker restarts don't refire.
        # Rebuild the (symbol, LONG|SHORT|RESISTANCE, bucket) keys by mapping
        # alert_type → dedup direction (what the firing code uses).
        try:
            from sqlalchemy import text as _t
            _type_to_dir = {
                "ai_day_long": "LONG",
                "ai_day_short": "SHORT",
                "ai_resistance": "RESISTANCE",
                "ai_scan_resistance": "RESISTANCE",
            }
            with sync_session_factory() as _seed_db:
                rows = _seed_db.execute(_t(
                    "SELECT DISTINCT symbol, alert_type, entry FROM alerts "
                    "WHERE session_date = :d "
                    "AND alert_type IN ('ai_day_long', 'ai_day_short', "
                    "                   'ai_resistance', 'ai_scan_resistance') "
                    "AND entry IS NOT NULL"
                ), {"d": session}).fetchall()
                seeded = set()
                for sym, atype, entry in rows:
                    dedup_dir = _type_to_dir.get(atype)
                    if not dedup_dir or not entry or entry <= 0:
                        continue
                    seeded.add((sym, dedup_dir, _level_bucket(entry)))
                if seeded:
                    _day_fired[session] = seeded
                    logger.info("AI day scan: seeded dedup from DB — %d keys", len(seeded))
                if _LONG_DEDUP_WINDOW > 0 or _SHORT_DEDUP_WINDOW > 0:
                    time_rows = _seed_db.execute(_t(
                        "SELECT symbol, alert_type, MAX(created_at) AS last_ts "
                        "FROM alerts WHERE session_date = :d "
                        "AND alert_type IN ('ai_day_long', 'ai_day_short') "
                        "GROUP BY symbol, alert_type"
                    ), {"d": session}).fetchall()
                    for sym, atype, last_ts in time_rows:
                        if not last_ts:
                            continue
                        if hasattr(last_ts, "timestamp"):
                            ts = last_ts.timestamp()
                        else:
                            from datetime import datetime as _dt
                            ts = _dt.fromisoformat(str(last_ts)).timestamp()
                        if atype == "ai_day_long":
                            _last_long_time[sym] = ts
                        elif atype == "ai_day_short":
                            _last_short_time[sym] = ts
                    if _last_long_time or _last_short_time:
                        logger.info(
                            "AI day scan: seeded time dedup — %d LONG, %d SHORT symbols",
                            len(_last_long_time), len(_last_short_time),
                        )
        except Exception:
            logger.warning("AI day scan: dedup seed failed", exc_info=True)

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
            # Cost-control: SCAN_USER_EMAIL restricts scanning to one user's
            # watchlist (not all users'). Unset = scan every user's watchlist
            # (production default).
            _scan_email = os.environ.get("SCAN_USER_EMAIL", "vbolofinde@gmail.com").strip().lower()
            if _scan_email:
                _uid_row = db.execute(
                    select(User.id).where(User.email == _scan_email)
                ).fetchone()
                if _uid_row:
                    _scan_uid = _uid_row[0]
                    all_items = db.execute(
                        select(WatchlistItem.symbol, WatchlistItem.user_id)
                        .where(WatchlistItem.user_id == _scan_uid)
                    ).all()
                    logger.info(
                        "AI day scan: SCAN_USER_EMAIL=%s (uid=%d) — %d watchlist rows",
                        _scan_email, _scan_uid, len(all_items),
                    )
                else:
                    logger.warning(
                        "AI day scan: SCAN_USER_EMAIL=%s not found — no scan this cycle",
                        _scan_email,
                    )
                    return 0
            else:
                all_items = db.execute(
                    select(WatchlistItem.symbol, WatchlistItem.user_id)
                ).all()

            symbol_users: dict[str, list[int]] = {}
            for sym, uid in all_items:
                symbol_users.setdefault(sym, []).append(uid)

            # Cost-control: crypto scanned every 2 hours (not every cycle).
            # Stocks are the focus — crypto only needs periodic checks.
            from config import is_crypto_alert_symbol
            from datetime import datetime as _dt
            import pytz as _pytz
            _et_hour = _dt.now(_pytz.timezone("America/New_York")).hour
            _crypto_active = 6 <= _et_hour < 22

            global _last_crypto_scan
            _now_ts = time.time()
            _crypto_due = (_now_ts - _last_crypto_scan) >= _CRYPTO_SCAN_INTERVAL

            def _symbol_allowed(sym: str) -> bool:
                if not is_market_hours_for_symbol(sym):
                    return False
                if is_crypto_alert_symbol(sym):
                    if not _crypto_active or not _crypto_due:
                        return False
                return True

            symbols = [s for s in symbol_users if _symbol_allowed(s)]
            if symbols_filter:
                _sf = {s.upper() for s in symbols_filter}
                symbols = [s for s in symbols if s.upper() in _sf]
            if exclude_symbols:
                _ex = {s.upper() for s in exclude_symbols}
                symbols = [s for s in symbols if s.upper() not in _ex]
            if not symbols:
                return 0

            if any(is_crypto_alert_symbol(s) for s in symbols):
                _last_crypto_scan = _now_ts

            # Fetch SPY daily regime for AI prompt context
            _spy_daily_regime = None
            try:
                from analytics.intraday_data import get_spy_context as _get_spy_ctx
                _spy_daily_ctx = _get_spy_ctx()
                _spy_daily_regime = _spy_daily_ctx.get("spy_daily_regime") if _spy_daily_ctx else None
            except Exception:
                pass
            logger.info(
                "AI day scan: scanning %d symbols (regime=%s)",
                len(symbols), _spy_daily_regime or "UNKNOWN",
            )

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
                result = scan_day_trade(symbol, api_key, spy_daily_regime=_spy_daily_regime)
                if not result:
                    continue

                direction = result.get("direction")
                setup_type = result.get("setup_type", "")
                entry = result.get("entry", 0)
                reason = result.get("reason", "")
                conviction = result.get("conviction", "MEDIUM")

                # Heartbeat: for priority symbols (SPY/NVDA/ETH-USD) + symbols where
                # any watching user holds an open position, we ALWAYS run the WAIT
                # emission block (AI UPDATE message) even when AI returned
                # LONG/SHORT/RESISTANCE. The normal direction-specific handling
                # still runs afterward to fire trade alerts on top of the heartbeat.
                _priority_symbols = {"SPY", "NVDA", "ETH-USD"}
                _anyone_holds = any(
                    user_open_longs.get((uid, symbol)) or user_open_shorts.get((uid, symbol))
                    for uid in symbol_users.get(symbol, [])
                )
                _heartbeat_symbol = (symbol.upper() in _priority_symbols) or _anyone_holds

                # WAIT — no setup confirmed, record to DB for AI Scan feed
                # Also run for priority heartbeat (but fall through to trade handling after)
                # Spec 44: skip WAIT block entirely for overridden results — they
                # should fire as LONG/SHORT, not send a duplicate AI UPDATE first.
                _is_override = result.get("_override", False)
                if ((not direction) or (direction == "WAIT") or _heartbeat_symbol) and not _is_override:
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
                            # Policy: AI UPDATES (WAIT) only deliver for
                            #   (a) SPY / NVDA / ETH-USD (always — market + crypto barometers),
                            #   (b) symbols where this specific user holds a position.
                            # Everything else: skip. DB row is still written above (dashboard).
                            # Per-user opt-in still gated by wait_alerts_enabled below.
                            _is_priority_sym = symbol.upper() in {"SPY", "NVDA", "ETH-USD"}
                            for _uid in symbol_users[symbol]:
                                _user_holds = (
                                    user_open_longs.get((_uid, symbol))
                                    or user_open_shorts.get((_uid, symbol))
                                )
                                if not _is_priority_sym and not _user_holds:
                                    logger.info(
                                        "WAIT skip uid=%d sym=%s reason=not_priority_no_position",
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
                    # Only skip further processing if direction was truly WAIT.
                    # For priority-heartbeat with non-WAIT direction, fall through
                    # to direction-specific trade alert handling (LONG/SHORT/RESISTANCE).
                    if (not direction) or (direction == "WAIT"):
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

                    if _SHORT_DEDUP_WINDOW > 0:
                        _now_ts_s = time.time()
                        _last_s = _last_short_time.get(symbol, 0)
                        if _now_ts_s - _last_s < _SHORT_DEDUP_WINDOW:
                            logger.info(
                                "AI day scan %s: SHORT suppressed — last SHORT %.0fs ago (window=%ds)",
                                symbol, _now_ts_s - _last_s, _SHORT_DEDUP_WINDOW,
                            )
                            continue
                        _last_short_time[symbol] = _now_ts_s

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

                if _LONG_DEDUP_WINDOW > 0:
                    _now_ts = time.time()
                    _last = _last_long_time.get(symbol, 0)
                    if _now_ts - _last < _LONG_DEDUP_WINDOW:
                        logger.info(
                            "AI day scan %s: LONG suppressed — last LONG %.0fs ago (window=%ds)",
                            symbol, _now_ts - _last, _LONG_DEDUP_WINDOW,
                        )
                        continue
                    _last_long_time[symbol] = _now_ts

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
            _scan_email = os.environ.get("SCAN_USER_EMAIL", "vbolofinde@gmail.com").strip().lower()
            _scan_uid: int | None = None
            if _scan_email:
                from app.models.user import User as _User
                _uid_row = db.execute(
                    select(_User.id).where(_User.email == _scan_email)
                ).fetchone()
                if _uid_row:
                    _scan_uid = _uid_row[0]
                else:
                    logger.warning(
                        "exit scan: SCAN_USER_EMAIL=%s not found — skipping cycle",
                        _scan_email,
                    )
                    return 0

            _q = select(RealTrade).where(RealTrade.status == "open")
            if _scan_uid is not None:
                _q = _q.where(RealTrade.user_id == _scan_uid)
            open_trades = db.execute(_q).scalars().all()

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
