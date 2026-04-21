"""AI Swing Trade Scanner — Spec 38.

Separate pipeline from the day scanner. Operates on daily bars + prior-day
levels (MAs, EMAs, weekly/monthly H/L, RSI). Fires LONG/SHORT/WAIT at
durable key levels. Runs 2x/day (pre-market + post-close).

Conviction ladder mirrors day scanner: prefer firing LOW at a key level
over WAIT. Users decide.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import date

from alert_config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SONNET

logger = logging.getLogger(__name__)

# Actionability is gated by the AI itself via the prompt's invalidation rule:
# if the closest structural stop is too far from current price, AI outputs WAIT.

# Dedup: (symbol, direction, level_bucket) already fired this session
_swing_fired: dict[str, set[tuple]] = {}
_swing_session: str = ""

# Persistent rate-limit feature keys (shared usage_limits table)
_FEATURE_SWING = "ai_swing_telegram"
_FEATURE_SWING_NOTIFIED = "ai_swing_cap_notified"

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


# ── Prompt ───────────────────────────────────────────────────────────


def build_swing_prompt(
    symbol: str,
    daily_bars: list[dict],
    prior_day: dict | None,
) -> str:
    """Build the swing prompt with daily + weekly + monthly context."""
    prompt = (
        "You are a swing trade analyst. Read the daily chart data below.\n"
        "Is there a multi-day swing trade right now?\n\n"
        "PHILOSOPHY: At a durable key level (200MA, 100MA, weekly MA, monthly\n"
        "pivot, RSI extreme), prefer firing LONG/SHORT with conviction scaled\n"
        "to confirmation strength over WAIT. Swing trades live 3-10 days; the\n"
        "user decides if they take it. The stop is trivial when entry is at\n"
        "structure.\n\n"
        "KEY LEVELS THAT WARRANT FIRING:\n"
        "- 200 Daily MA/EMA test (within 2%)\n"
        "- 100 Daily MA/EMA test (within 1.5%)\n"
        "- 50 Daily MA/EMA test (within 1.5%) — trend pullback\n"
        "- Prior-month high/low (within 2%)\n"
        "- Prior-week high/low (within 2%)\n"
        "- Weekly high BREAKOUT (daily close above prior-week high on volume) → LONG\n"
        "- Weekly high RECLAIM (just broke, pulling back to it) → LONG (flipped support)\n"
        "- Weekly low BOUNCE / HOLD → LONG\n"
        "- Monthly high/low breakout or reclaim → LONG\n"
        "- Daily RSI < 30 (oversold LONG) or > 70 at resistance (overbought SHORT)\n\n"
        "FLIPPED LEVEL RULE (critical):\n"
        "- When price breaks a resistance level and pulls back to it, that level becomes SUPPORT.\n"
        "  Fire LONG on the retest, NOT RESISTANCE.\n"
        "- Same inverse for former support breaking down on SHORT.\n\n"
        "LONG CONVICTION LADDER:\n"
        "- HIGH: at level + bullish daily candle (hammer/engulfing/reclaim) + RSI < 40\n"
        "- MEDIUM: at level + RSI < 50, no confirming candle yet\n"
        "- LOW: at level, just touching, no structure yet\n\n"
        "SHORT CONVICTION LADDER:\n"
        "- HIGH: at resistance + bearish daily candle + RSI > 65\n"
        "- MEDIUM: at resistance + RSI > 55\n"
        "- LOW: at resistance, just arriving\n\n"
        "WAIT only when: price mid-range (>3% from every level, no RSI extreme).\n\n"
        "INVALIDATION GATE (critical — filters un-tradeable setups):\n"
        "- Your Stop must be a REAL structural level (below key support for LONG,\n"
        "  above resistance for SHORT) — NOT an arbitrary percent.\n"
        "- If the closest structural invalidation is more than 5% from CURRENT price,\n"
        "  the setup is NOT tradeable yet — output WAIT with reason\n"
        "  'structural stop too far — await closer approach to level'.\n"
        "- Ask yourself: 'if I enter now, where does the thesis die?' If that\n"
        "  death-point is far away, the trade has no edge — skip it.\n\n"
        "OUTPUT (plain text, no markdown):\n\n"
        "SETUP: [e.g. 200MA bounce + RSI 28, monthly low reversal, weekly MA test]\n"
        "Direction: LONG / SHORT / WAIT\n"
        "Entry: $price (the level, not current)\n"
        "Stop: $price (3-5% below support for LONG / above resistance for SHORT)\n"
        "T1: $price (next structural target, typically 5-10%)\n"
        "T2: $price (second target, typically 10-20%)\n"
        "Conviction: HIGH / MEDIUM / LOW\n"
        "Timeframe: e.g. '3-7 days' or '1-2 weeks'\n"
        "Reason: 1 sentence — level + RSI + candle structure\n\n"
        "RULES:\n"
        "- Be decisive. At a durable level prefer LONG/SHORT LOW over WAIT.\n"
        "- Entry = key level, not current price.\n"
        "- MAXIMUM 70 WORDS.\n"
    )

    parts = [prompt, f"\n[SYMBOL: {symbol}]"]
    if daily_bars:
        parts.append(f"Current Price: ${daily_bars[-1]['close']:.2f}")

    if prior_day:
        levels = ["\n[KEY LEVELS — daily]"]
        for key, label in [
            ("ma20", "20 Daily MA"), ("ma50", "50 Daily MA"),
            ("ma100", "100 Daily MA"), ("ma200", "200 Daily MA"),
            ("ema8", "8 Daily EMA"), ("ema20", "20 Daily EMA"),
            ("ema50", "50 Daily EMA"),
            ("ema100", "100 Daily EMA"), ("ema200", "200 Daily EMA"),
        ]:
            v = prior_day.get(key)
            if v and v > 0:
                levels.append(f"{label}: ${v:.2f}")
        rsi = prior_day.get("rsi14")
        if rsi is not None:
            levels.append(f"Daily RSI14: {rsi:.1f}")
        for key, label in [
            ("prior_week_high", "Prior Week High"),
            ("prior_week_low", "Prior Week Low"),
            ("prior_month_high", "Prior Month High"),
            ("prior_month_low", "Prior Month Low"),
        ]:
            v = prior_day.get(key)
            if v and v > 0:
                levels.append(f"{label}: ${v:.2f}")
        parts.append("\n".join(levels))

    if daily_bars:
        lines = [f"\n[DAILY BARS — last {min(len(daily_bars), 30)}]"]
        for b in daily_bars[-30:]:
            lines.append(
                f"{b.get('date', '')} O={b['open']:.2f} H={b['high']:.2f} "
                f"L={b['low']:.2f} C={b['close']:.2f} V={b.get('volume', 0):.0f}"
            )
        parts.append("\n".join(lines))

    return "\n".join(parts)


# ── Response parsing ─────────────────────────────────────────────────


def parse_swing_response(text: str) -> dict:
    result = {
        "setup_type": None, "direction": None, "entry": None,
        "stop": None, "t1": None, "t2": None,
        "conviction": None, "timeframe": None, "reason": None,
        "raw": text,
    }
    m = re.search(r"SETUP:\s*(.+?)(?:\n|$)", text)
    if m:
        result["setup_type"] = m.group(1).strip()[:200]
    m = re.search(r"Direction:\s*(LONG|SHORT|WAIT)", text, re.IGNORECASE)
    if m:
        result["direction"] = m.group(1).upper()

    def _p(pat: str):
        mm = re.search(pat, text)
        return float(mm.group(1).replace(",", "")) if mm else None

    result["entry"] = _p(r"Entry:\s*\$?([\d,.]+)")
    result["stop"] = _p(r"Stop:\s*\$?([\d,.]+)")
    result["t1"] = _p(r"T1:\s*\$?([\d,.]+)")
    result["t2"] = _p(r"T2:\s*\$?([\d,.]+)")

    m = re.search(r"Conviction:\s*(HIGH|MEDIUM|LOW)", text, re.IGNORECASE)
    if m:
        result["conviction"] = m.group(1).upper()
    m = re.search(r"Timeframe:\s*(.+?)(?:\n|$)", text)
    if m:
        result["timeframe"] = m.group(1).strip()[:50]
    m = re.search(r"Reason:\s*(.+?)(?:\n|$)", text)
    if m:
        result["reason"] = m.group(1).strip()
    return result


# ── Per-symbol scan ──────────────────────────────────────────────────


def scan_swing(symbol: str, api_key: str) -> dict | None:
    """Scan one symbol for a swing setup."""
    from analytics.intraday_data import fetch_prior_day
    import yfinance as yf

    try:
        hist = yf.Ticker(symbol).history(period="3mo", interval="1d")
        if hist is None or hist.empty or len(hist) < 20:
            logger.warning("swing: insufficient daily bars for %s", symbol)
            return None

        daily_bars = [
            {
                "date": idx.strftime("%Y-%m-%d"),
                "open": float(r["Open"]), "high": float(r["High"]),
                "low": float(r["Low"]), "close": float(r["Close"]),
                "volume": float(r["Volume"]),
            }
            for idx, r in hist.tail(30).iterrows()
        ]

        prior_day = fetch_prior_day(symbol, is_crypto=False)
        prompt = build_swing_prompt(symbol, daily_bars, prior_day)

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system_with_cache = [
            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
        ]
        start = time.time()
        response = client.messages.create(
            model=CLAUDE_MODEL_SONNET,
            max_tokens=250,
            system=system_with_cache,
            messages=[{"role": "user", "content": f"Swing scan {symbol} now."}],
            timeout=20.0,
        )
        elapsed = time.time() - start
        response_text = response.content[0].text.strip()
        logger.info("AI swing %s: %.1fs, %d tok — %s",
                    symbol, elapsed, response.usage.input_tokens, response_text[:100])

        parsed = parse_swing_response(response_text)
        parsed["symbol"] = symbol
        parsed["price"] = float(hist.iloc[-1]["Close"])
        return parsed
    except Exception:
        logger.exception("swing scan failed for %s", symbol)
        return None


# ── Formatting + delivery ───────────────────────────────────────────


def _format_swing_msg(result: dict) -> str:
    sym = result["symbol"]
    direction = result["direction"]
    price = result["price"]
    entry = result.get("entry") or price
    stop = result.get("stop")
    t1 = result.get("t1")
    t2 = result.get("t2")
    setup = result.get("setup_type") or ""
    conviction = result.get("conviction") or "MEDIUM"
    timeframe = result.get("timeframe") or "3-10 days"
    reason = result.get("reason") or ""

    lines = [f"AI SWING {direction} — {sym} ${price:.2f}"]
    parts = [f"Entry ${entry:.2f}"]
    if stop:
        parts.append(f"Stop ${stop:.2f}")
    if t1:
        parts.append(f"T1 ${t1:.2f}")
    if t2:
        parts.append(f"T2 ${t2:.2f}")
    lines.append(" · ".join(parts))
    if setup:
        lines.append(f"Setup: {setup}")
    lines.append(f"Timeframe: {timeframe}")
    lines.append(f"Conviction: {conviction}")
    if reason:
        lines.append(f"Reason: {reason}")
    return "\n".join(lines)


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


# ── Main cycle ───────────────────────────────────────────────────────


def swing_scan_cycle(sync_session_factory) -> int:
    """Run one swing scan pass. Returns Telegram deliveries."""
    global _swing_fired, _swing_session

    if os.environ.get("SWING_SCAN_ENABLED", "true").lower() in ("0", "false", "no"):
        logger.info("swing scan: disabled via env")
        return 0

    # Only scan during market hours — swing entries need live price vs level.
    # Skips weekends/holidays/after-hours for equities. Crypto symbols in
    # watchlists still get scanned (they trade 24/7).
    try:
        from analytics.market_hours import is_market_hours
        if not is_market_hours():
            logger.debug("swing scan: market closed, skipping")
            return 0
    except Exception:
        pass  # if helper unavailable, run anyway

    # Regime gate: block swing entries in TACTICAL mode (SPY below 21 EMA)
    try:
        from alert_config import SPY_REGIME_ENABLED, REGIME_TACTICAL_BLOCK_SWINGS
        if SPY_REGIME_ENABLED and REGIME_TACTICAL_BLOCK_SWINGS:
            from analytics.intraday_data import get_spy_context
            _spy_ctx = get_spy_context()
            if _spy_ctx and _spy_ctx.get("spy_daily_regime") == "TACTICAL":
                logger.info("swing scan: TACTICAL regime (SPY below 21 EMA) — skipping")
                return 0
    except Exception:
        pass

    session = date.today().isoformat()
    if _swing_session != session:
        _swing_fired.clear()
        _swing_session = session

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        logger.warning("swing scan: no Anthropic API key")
        return 0

    from sqlalchemy import select
    from app.models.alert import Alert
    from app.models.user import User
    from app.models.watchlist import WatchlistItem

    try:
        from app.tier import get_limits
    except Exception:
        get_limits = None

    delivered = 0
    with sync_session_factory() as db:
        # Build per-symbol → users-watching map from real watchlists.
        # Only scan symbols at least one Telegram-enabled user is watching.
        # Cost-control: SCAN_USER_EMAIL restricts to one user's watchlist.
        import os as _os_scan
        _scan_email = _os_scan.environ.get("SCAN_USER_EMAIL", "vbolofinde@gmail.com").strip().lower()
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

        for symbol in symbols:
            result = scan_swing(symbol, api_key)
            if not result:
                continue

            direction = (result.get("direction") or "").upper()
            conviction = (result.get("conviction") or "MEDIUM").upper()
            entry = result.get("entry") or 0

            # Swings are LONG-only (user policy). SHORT signals are logged but not fired.
            if direction == "SHORT":
                logger.info("swing %s: SHORT suppressed (LONG-only policy)", symbol)
                continue
            if direction != "LONG" or entry <= 0:
                logger.info("swing %s: %s — %s", symbol, direction or "?",
                            (result.get("reason") or "")[:80])
                continue

            # Option B gates — fire only when price is AT or above the level.
            current = result.get("price") or 0
            if current > 0:
                # Proximity gate: price must be within 1.5% of the entry level.
                # Too far away = setup is hypothetical, not actionable yet.
                distance_pct = abs(current - entry) / current * 100
                if distance_pct > 1.5:
                    logger.info(
                        "swing %s: skip — entry $%.2f is %.2f%% from price $%.2f (proximity > 1.5%%)",
                        symbol, entry, distance_pct, current,
                    )
                    continue
                # Reclaim gate: for LONG, current price must be AT or above entry
                # (allow 0.2% slack for level precision). If below, level is not
                # reclaimed — price is still being rejected.
                if current < entry * 0.998:
                    logger.info(
                        "swing %s: skip — current $%.2f below entry $%.2f (level not reclaimed)",
                        symbol, current, entry,
                    )
                    continue

            # Actionability is enforced by the AI prompt's invalidation gate —
            # setups where structural stop is too far from price are returned as WAIT.

            # Dedup — bucket by 1% of entry price (avoid same-level re-fires)
            level_bucket = int(entry / max(entry * 0.01, 0.01))
            fp = (symbol, direction, level_bucket, conviction)
            if fp in _swing_fired.setdefault(symbol, set()):
                logger.info("swing %s: dedup skip", symbol)
                continue
            _swing_fired[symbol].add(fp)

            alert_type = f"ai_swing_{direction.lower()}"
            body = _format_swing_msg(result)
            score = {"HIGH": 85, "MEDIUM": 65, "LOW": 45}.get(conviction, 65)

            for user in symbol_users[symbol]:
                uid = user.id
                chat_id = user.telegram_chat_id or ""

                try:
                    db.add(Alert(
                        user_id=uid,
                        symbol=symbol,
                        alert_type=alert_type,
                        direction=direction,
                        price=result.get("price", 0),
                        entry=entry,
                        stop=result.get("stop"),
                        target_1=result.get("t1"),
                        target_2=result.get("t2"),
                        confidence=conviction.lower(),
                        message=body,
                        score=score,
                        session_date=session,
                        reason=result.get("reason"),
                    ))
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("swing alert insert failed uid=%s sym=%s", uid, symbol)

                if not chat_id:
                    continue
                if not _user_wants_swing(user, direction, conviction):
                    continue

                tier = "free"
                sub = getattr(user, "subscription", None)
                if sub:
                    tier = getattr(sub, "tier", "free") or "free"
                cap = None
                if get_limits:
                    cap = get_limits(tier).get("ai_swing_alerts_per_day")
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

    logger.info("swing scan complete: %d deliveries", delivered)
    return delivered
