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
import re
import time
from datetime import date

from alert_config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

# Dedup: (symbol, setup_type, level_bucket) per session
_day_fired: dict[str, set[tuple]] = {}
_day_session: str = ""
# Track last direction sent to Telegram per symbol — only notify on change
_last_tg_direction: dict[str, str] = {}  # {symbol: "LONG" / "RESISTANCE" / "WAIT"}
_last_tg_time: dict[str, float] = {}  # {symbol: timestamp of last Telegram send}
# Per-user rate limit tracking — resets on new session
_user_delivered_count: dict[tuple[int, str], int] = {}  # (uid, session) -> count
_user_limit_notified: set[tuple[int, str]] = set()  # (uid, session) already told about cap

# Exit scan cooldown — (trade_id, status) -> last_sent_ts. 30-min cooldown per pair.
_exit_notified: dict[tuple[int, str], float] = {}
_EXIT_COOLDOWN_SEC = 1800  # 30 min


def _resolve_api_key() -> str:
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    return ""


def get_user_ai_scan_count(user_id: int, session_date: str) -> int:
    """Return how many AI scan alerts the user has received today (in-memory counter)."""
    return _user_delivered_count.get((user_id, session_date), 0)


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
        "LONG CONFIRMATION RULES (critical — avoid false bottoms):\n"
        "- Require HIGHER LOW structure: last bar's low must be ABOVE the prior swing low.\n"
        "  First touch of support with no higher low yet → WAIT (not LONG).\n"
        "- Require VOLUME > 1.0x average on the bounce bar, OR 2+ bars holding above the level.\n"
        "- If price is just pinned at support with declining/flat structure → WAIT.\n\n"
        "SHORT CONFIRMATION RULES (mirror of LONG — critical, avoid false tops):\n"
        "- Require LOWER HIGH structure: last bar's high must be BELOW the prior swing high.\n"
        "  First touch of resistance with no lower high yet → RESISTANCE (notice, not SHORT).\n"
        "- Require VOLUME > 1.0x average on the rejection bar, OR 2+ bars holding below the level.\n"
        "- If price is just pinned at resistance with flat structure → WAIT.\n"
        "- Only fire SHORT when the reversal STRUCTURE is confirmed, not on hope.\n\n"
        "OUTPUT (plain text, no markdown):\n\n"
        "SETUP: [what you see — e.g. PDL bounce, VWAP reclaim, 50MA rejection, PDH fail]\n"
        "Direction: LONG / SHORT / RESISTANCE / WAIT\n"
        "Entry: $price (the key level, not current price)\n"
        "Stop: $price (LONG: below support; SHORT: above resistance)\n"
        "T1: $price (LONG: next resistance above; SHORT: next support below)\n"
        "T2: $price (LONG: second resistance; SHORT: second support)\n"
        "Conviction: HIGH / MEDIUM / LOW\n"
        "Reason: 1 sentence — must mention higher low + volume for LONG, lower high + volume for SHORT\n\n"
        "RULES:\n"
        "- Be decisive, but respect the confirmation rules above.\n"
        "- Entry = the key level price, not current price.\n"
        "- Stop = structural level where thesis breaks (below support for LONG, above resistance for SHORT).\n"
        "- LONG without higher low + volume → WAIT.\n"
        "- SHORT without lower high + volume → RESISTANCE or WAIT (NOT a SHORT).\n"
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
            model=CLAUDE_MODEL,
            max_tokens=200,
            system=system_with_cache,
            messages=[{"role": "user", "content": f"Scan {symbol} for day trade entry now."}],
            timeout=15.0,
        )
        elapsed = time.time() - start

        response_text = response.content[0].text.strip()
        logger.info("AI day scan %s: %.1fs, %d tokens — %s",
                     symbol, elapsed, response.usage.input_tokens, response_text[:100])

        parsed = parse_day_trade_response(response_text)
        parsed["symbol"] = symbol
        parsed["price"] = current_price
        parsed["signal_source"] = "day_trade"
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
        _user_delivered_count.clear()
        _user_limit_notified.clear()
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
                    _wait_msg = f"AI: WAIT — {reason}" if reason else "AI: WAIT — no setup confirmed"
                    for _uid in symbol_users[symbol]:
                      db.add(Alert(
                        user_id=_uid, symbol=symbol,
                        alert_type="ai_scan_wait", direction="NOTICE",
                        price=result.get("price", 0),
                        message=_wait_msg, score=0,
                        session_date=session,
                    ))
                    db.commit()

                    # Send WAIT to Telegram: direction changed + 30 min cooldown
                    _level_keywords = ["PDH", "PDL", "VWAP", "session low", "session high",
                                       "50MA", "100MA", "200MA", "support", "resistance", "weekly"]
                    _near_level = any(kw.lower() in (reason or "").lower() for kw in _level_keywords)
                    _prev_dir = _last_tg_direction.get(symbol)
                    _last_sent = _last_tg_time.get(symbol, 0)
                    _cooldown_ok = (time.time() - _last_sent) > 1800  # 30 min
                    if _near_level and reason and (_prev_dir != "WAIT" or _cooldown_ok):
                        _last_tg_direction[symbol] = "WAIT"
                        _last_tg_time[symbol] = time.time()
                        try:
                            from alerting.notifier import _send_telegram_to
                            _tg_msg = (
                                f"<b>AI SCAN — {symbol} ${result.get('price', 0):.2f}</b>\n"
                                f"{reason}"
                            )
                            for _uid in symbol_users[symbol]:
                                user = db.get(User, _uid)
                                if user and user.telegram_enabled and user.telegram_chat_id:
                                    _send_telegram_to(_tg_msg, user.telegram_chat_id)
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
                    _first_uid = symbol_users[symbol][0]
                    db.add(Alert(
                        user_id=_first_uid, symbol=symbol,
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
                                f"<b>AI SCAN — RESISTANCE {symbol} ${entry:.2f}</b>\n"
                                f"{reason}\n"
                                f"Action: tighten stop / take profits / watch for rejection"
                            )
                            for uid in symbol_users[symbol]:
                                user = db.get(User, uid)
                                if not (user and user.telegram_enabled and user.telegram_chat_id):
                                    continue
                                # Rate limit (per-user in-memory counter)
                                try:
                                    from api.app.tier import get_limits as _gl
                                    from api.app.dependencies import get_user_tier as _gut
                                    _tier_max_r = _gl(_gut(user)).get("ai_scan_alerts_per_day")
                                    if _tier_max_r is not None:
                                        _uid_key_r = (uid, session)
                                        if _user_delivered_count.get(_uid_key_r, 0) >= _tier_max_r:
                                            if _uid_key_r not in _user_limit_notified:
                                                _send_telegram_to(
                                                    f"📊 Daily AI scan limit reached ({_tier_max_r}/{_tier_max_r}).\n"
                                                    f"You won't receive more AI scan alerts today.\n"
                                                    f"Upgrade to Pro for unlimited alerts.\n"
                                                    f"→ https://www.tradesignalwithai.com/billing",
                                                    user.telegram_chat_id,
                                                )
                                                _user_limit_notified.add(_uid_key_r)
                                            continue
                                except Exception:
                                    pass
                                _send_telegram_to(_tg_msg, user.telegram_chat_id)
                                _user_delivered_count[(uid, session)] = \
                                    _user_delivered_count.get((uid, session), 0) + 1
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

                    _first_uid_s = symbol_users[symbol][0]
                    alert_s = Alert(
                        user_id=_first_uid_s, symbol=symbol,
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
                    total_alerts += 1
                    _alert_id_s = alert_s.id
                    db.commit()

                    # Telegram — direction-change gate (SHORT distinct from LONG/RESISTANCE/WAIT)
                    if _last_tg_direction.get(symbol) == "SHORT":
                        logger.debug("AI day scan %s: SHORT already notified, skip Telegram", symbol)
                    else:
                        _last_tg_direction[symbol] = "SHORT"
                        try:
                            from alerting.notifier import _send_telegram_to
                            import html as _html_s

                            _stop_s = f"${result['stop']:.2f}" if result.get("stop") else "N/A"
                            _t1_s = f"${result['t1']:.2f}" if result.get("t1") else "N/A"
                            _t2_s = f"${result['t2']:.2f}" if result.get("t2") else "N/A"
                            _tg_msg_s = (
                                f"<b>AI SCAN — SHORT {_html_s.escape(symbol)} ${entry:.2f}</b>\n"
                                f"Entry ${entry:.2f} · Stop {_stop_s} · T1 {_t1_s} · T2 {_t2_s}\n"
                                f"Setup: {_html_s.escape(setup_label_s)}\n"
                                f"Conviction: {conviction}"
                            )
                            _buttons_s = {
                                "inline_keyboard": [[
                                    {"text": "✅ Took It", "callback_data": f"ack:{_alert_id_s}"},
                                    {"text": "❌ Skip", "callback_data": f"skip:{_alert_id_s}"},
                                    {"text": "🔴 Exit", "callback_data": f"exit:{_alert_id_s}"},
                                ]]
                            }

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
                                    # Rate limit check (same counter as LONG)
                                    _send_s = True
                                    try:
                                        from api.app.tier import get_limits as _gl
                                        from api.app.dependencies import get_user_tier as _gut
                                        _tier_max_s = _gl(_gut(user)).get("ai_scan_alerts_per_day")
                                        if _tier_max_s is not None:
                                            _uid_key_s = (uid, session)
                                            if _user_delivered_count.get(_uid_key_s, 0) >= _tier_max_s:
                                                if _uid_key_s not in _user_limit_notified:
                                                    _send_telegram_to(
                                                        f"📊 Daily AI scan limit reached ({_tier_max_s}/{_tier_max_s}).\n"
                                                        f"You won't receive more AI scan alerts today.\n"
                                                        f"Upgrade to Pro for unlimited alerts.\n"
                                                        f"→ https://www.tradesignalwithai.com/billing",
                                                        user.telegram_chat_id,
                                                    )
                                                    _user_limit_notified.add(_uid_key_s)
                                                _send_s = False
                                    except Exception:
                                        pass
                                    if _send_s:
                                        _send_telegram_to(_tg_msg_s, user.telegram_chat_id, reply_markup=_buttons_s)
                                        _user_delivered_count[(uid, session)] = \
                                            _user_delivered_count.get((uid, session), 0) + 1
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

                # Also keep message-based dedup as backup safety
                _existing = db.execute(
                    select(Alert.id).where(
                        Alert.symbol == symbol,
                        Alert.alert_type == "ai_day_long",
                        Alert.session_date == session,
                        Alert.message.contains(setup_type or "AI"),
                    ).limit(1)
                ).scalar_one_or_none()
                if _existing:
                    logger.debug("AI day scan %s: dedup skip — %s already fired", symbol, setup_type)
                    continue

                score = {"HIGH": 85, "MEDIUM": 65, "LOW": 45}.get(conviction, 65)
                setup_label = setup_type or "AI entry"
                message = f"{setup_label}: {reason}" if reason else setup_label

                # Record once (first user) — not per-user to avoid 7x duplication
                _first_uid = symbol_users[symbol][0]
                for uid in [_first_uid]:
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
                    db.flush()  # get alert.id for Telegram buttons
                    total_alerts += 1
                _alert_id = alert.id

                db.commit()

                # Telegram — only send if direction changed from last notification
                if _last_tg_direction.get(symbol) == "LONG":
                    logger.debug("AI day scan %s: LONG already notified, skip Telegram", symbol)
                else:
                    _last_tg_direction[symbol] = "LONG"
                    try:
                        from alerting.notifier import _send_telegram_to
                        import html as _html

                        _stop = f"${result['stop']:.2f}" if result.get("stop") else "N/A"
                        _t1 = f"${result['t1']:.2f}" if result.get("t1") else "N/A"
                        _t2 = f"${result['t2']:.2f}" if result.get("t2") else "N/A"
                        _tg_msg = (
                            f"<b>AI SCAN — LONG {_html.escape(symbol)} ${entry:.2f}</b>\n"
                            f"Entry ${entry:.2f} · Stop {_stop} · T1 {_t1} · T2 {_t2}\n"
                            f"Setup: {_html.escape(setup_label)}\n"
                            f"Conviction: {conviction}"
                        )
                        _buttons = {
                            "inline_keyboard": [[
                                {"text": "✅ Took It", "callback_data": f"ack:{_alert_id}"},
                                {"text": "❌ Skip", "callback_data": f"skip:{_alert_id}"},
                                {"text": "🔴 Exit", "callback_data": f"exit:{_alert_id}"},
                            ]]
                        }

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
                                # Rate limit: check ai_scan_alerts_per_day (per-user in-memory counter)
                                _send = True
                                _tier_max = None
                                try:
                                    from api.app.tier import get_limits as _gl
                                    from api.app.dependencies import get_user_tier as _gut
                                    _tier = _gut(user)
                                    _tier_max = _gl(_tier).get("ai_scan_alerts_per_day")
                                    if _tier_max is not None:
                                        _uid_key = (uid, session)
                                        _delivered = _user_delivered_count.get(_uid_key, 0)
                                        if _delivered >= _tier_max:
                                            # Only notify about the cap ONCE per day
                                            if _uid_key not in _user_limit_notified:
                                                _send_telegram_to(
                                                    f"📊 Daily AI scan limit reached ({_tier_max}/{_tier_max}).\n"
                                                    f"You won't receive more AI scan alerts today.\n"
                                                    f"Upgrade to Pro for unlimited alerts.\n"
                                                    f"→ https://www.tradesignalwithai.com/billing",
                                                    user.telegram_chat_id,
                                                )
                                                _user_limit_notified.add(_uid_key)
                                            _send = False
                                except Exception:
                                    pass  # skip limit on error
                                if _send:
                                    _send_telegram_to(_tg_msg, user.telegram_chat_id, reply_markup=_buttons)
                                    # Increment per-user counter
                                    _user_delivered_count[(uid, session)] = \
                                        _user_delivered_count.get((uid, session), 0) + 1
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

    break_term = "lower low" if is_long else "higher high"
    thesis_term = "higher low" if is_long else "lower high"
    prompt = (
        "You are managing an open trading position. Read the position data and\n"
        "current chart, decide if the user should act on their position RIGHT NOW.\n\n"
        "OUTPUT (plain text, no markdown):\n\n"
        "Status: EXIT_NOW / TAKE_PROFITS / HOLD\n"
        "Reason: 1 short sentence\n"
        "Action: 1 short sentence — specific action (exit, trim, or continue holding)\n\n"
        "RULES:\n"
        f"- EXIT_NOW if: price within 0.2% of stop, {thesis_term} structure broken "
        f"(new {break_term}), or volume collapsed and price stalled at entry.\n"
        "- TAKE_PROFITS if: price within 0.5% of T1, rejection candle at T1, "
        "or volume spike into T1.\n"
        "- HOLD otherwise. Default to HOLD — do not harass the user.\n"
        "- Be conservative. Only act on clear structural signals.\n"
        "- MAXIMUM 50 WORDS TOTAL.\n\n"
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

                try:
                    from api.app.tier import get_limits as _gl
                    from api.app.dependencies import get_user_tier as _gut
                    _tier_max = _gl(_gut(user)).get("ai_scan_alerts_per_day")
                    if _tier_max is not None:
                        _uid_key = (trade.user_id, session)
                        if _user_delivered_count.get(_uid_key, 0) >= _tier_max:
                            if _uid_key not in _user_limit_notified:
                                from alerting.notifier import _send_telegram_to
                                _send_telegram_to(
                                    f"📊 Daily AI scan limit reached ({_tier_max}/{_tier_max}).\n"
                                    f"Upgrade to Pro for unlimited alerts.\n"
                                    f"→ https://www.tradesignalwithai.com/billing",
                                    user.telegram_chat_id,
                                )
                                _user_limit_notified.add(_uid_key)
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
                    _user_delivered_count[(trade.user_id, session)] = \
                        _user_delivered_count.get((trade.user_id, session), 0) + 1
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
