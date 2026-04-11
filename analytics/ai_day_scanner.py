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
_last_day_price: dict[str, float] = {}


def _resolve_api_key() -> str:
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    return ""


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
) -> str:
    """Build specialized day trade prompt with specific confirmation rules."""

    prompt = (
        "You are a day trade entry detector. Your ONLY job: determine if price is AT a key level "
        "with confirmation to enter a LONG trade.\n\n"
        "ENTRY RULES (fire LONG only if ONE of these is confirmed):\n\n"
        "1. PDL HOLD/RECLAIM: Price touches or dips below prior day low (PDL), then 2-3 bars close above PDL.\n"
        "   Entry = PDL level. Stop = below session low.\n\n"
        "2. PDH BREAKOUT ON VOLUME: Price closes above prior day high (PDH) with volume >= 1.5x average.\n"
        "   Entry = PDH level. Stop = below breakout bar low or PDH level.\n\n"
        "3. VWAP HOLD: Price was above VWAP earlier, pulled back to VWAP, 2-3 bars close above VWAP.\n"
        "   Entry = VWAP level. Stop = below session low (next structural support).\n\n"
        "4. DOUBLE BOTTOM HOLD: Price tests the same low from a prior session (within 0.5%).\n"
        "   Second touch holds (2+ bars above). Entry = double bottom level. Stop = below the double bottom low.\n\n"
        "5. MA/EMA HOLD: Price touches 20/50/100/200 MA or EMA and bounces.\n"
        "   Bar low touches MA, next 2-3 bars close above. Entry = MA level. Stop = below the MA.\n\n"
        "STOP RULES — USE STRUCTURAL LEVELS, NOT FIXED PERCENTAGES:\n"
        "- Stop MUST be below the NEXT SUPPORT LEVEL down from entry.\n"
        "- Use real levels from the data: session low, PDL, VWAP, MAs.\n"
        "- Example: VWAP hold entry at $2243 → stop below session low $2230, NOT $2236 (0.3% math).\n"
        "- Example: PDL hold entry at $2235 → stop below session low $2220, NOT $2228.\n"
        "- The stop is where the THESIS BREAKS (support fails), not an arbitrary distance.\n"
        "- NEVER use a fixed % for stop. Always find the structural level.\n\n"
        "RESISTANCE WARNINGS (not entries — informational only):\n"
        "- If price is approaching PDH, weekly high, or key MA from below, output RESISTANCE warning.\n\n"
        "OUTPUT FORMAT (plain text, no markdown):\n\n"
        "SETUP: [rule name from list above, or RESISTANCE, or NONE]\n"
        "Direction: LONG / RESISTANCE / WAIT\n"
        "Entry: $price\n"
        "Stop: $price\n"
        "T1: $price (next resistance level above entry)\n"
        "T2: $price (second resistance level)\n"
        "Conviction: HIGH / MEDIUM / LOW\n"
        "Reason: 1 sentence — what confirmed this entry\n\n"
        "STRICT RULES:\n"
        "- ONLY fire LONG if a specific entry rule above is confirmed with 2-3 bar hold.\n"
        "- Entry = the key level price, NOT current price.\n"
        "- If current price is >0.5% away from the level, output WAIT (stale).\n"
        "- T1 = next overhead resistance. T2 = second resistance.\n"
        "- If no setup is confirmed, output WAIT.\n"
        "- MAXIMUM 60 WORDS total.\n"
        "- PDH = yesterday's high. PDL = yesterday's low.\n"
    )

    parts = [prompt]

    # Key levels from prior day
    if prior_day:
        levels = [f"\n[KEY LEVELS — {symbol}]"]
        for key, label in [
            ("high", "PDH(yesterday high)"),
            ("low", "PDL(yesterday low)"),
            ("close", "Prior Close"),
            ("ma20", "20MA"), ("ma50", "50MA"), ("ma100", "100MA"), ("ma200", "200MA"),
            ("ema20", "20EMA"), ("ema50", "50EMA"), ("ema100", "100EMA"), ("ema200", "200EMA"),
        ]:
            val = prior_day.get(key)
            if val and val > 0:
                levels.append(f"{label}: ${val:.2f}")
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
    dir_match = re.search(r"Direction:\s*(LONG|RESISTANCE|WAIT)", text, re.IGNORECASE)
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


def scan_day_trade(symbol: str, api_key: str) -> dict | None:
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

        prompt = build_day_trade_prompt(symbol, bars_5m, bars_1h, prior_day)

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
        _last_day_price.clear()
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

            # Regime: REMOVED (P2 — no suppression, fire at key levels)

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

                    # Send Telegram
                    try:
                        from alerting.notifier import _send_telegram_to
                        _tg_msg = (
                            f"<b>AI SCAN — RESISTANCE {symbol} ${entry:.2f}</b>\n"
                            f"{reason}\n"
                            f"Action: tighten stop / take profits / watch for rejection"
                        )
                        for uid in symbol_users[symbol]:
                            user = db.get(User, uid)
                            if user and user.telegram_enabled and user.telegram_chat_id:
                                _send_telegram_to(_tg_msg, user.telegram_chat_id)
                    except Exception:
                        logger.exception("AI day scan: Telegram failed for %s", symbol)

                    logger.info("AI day scan %s: RESISTANCE at $%.2f", symbol, entry or 0)
                    continue

                # LONG entry
                if not entry or entry <= 0:
                    continue

                # Regime filter: REMOVED (P2 — fire at key levels, no suppression)

                # Dedup: same setup at same level = skip. Different setup or level = fire.
                # "VWAP HOLD at $2243" fired → skip. "PDL HOLD at $2230" → fire (new setup).
                _level_key = f"{setup_type}_{_level_bucket(entry)}"
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
                    total_alerts += 1

                db.commit()

                # Telegram — clean format
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

                    for uid in symbol_users[symbol]:
                        user = db.get(User, uid)
                        if user and user.telegram_enabled and user.telegram_chat_id:
                            _send_telegram_to(_tg_msg, user.telegram_chat_id)
                            logger.info("AI day scan %s: LONG at $%.2f → Telegram user %d", symbol, entry, uid)
                except Exception:
                    logger.exception("AI day scan: Telegram failed for %s", symbol)

            logger.info("AI day scan complete: %d alerts from %d symbols", total_alerts, len(symbols))
            return total_alerts

    except Exception:
        logger.exception("AI day scan cycle failed")
        return 0
