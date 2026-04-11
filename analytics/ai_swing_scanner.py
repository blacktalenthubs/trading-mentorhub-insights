"""AI Swing Trade Scanner — daily chart entry detection at key EMA/weekly levels.

Uses Claude Sonnet for deeper daily chart analysis. Runs 2x/day:
- 9:05 AM ET (pre-market, before daily open)
- 3:30 PM ET (pre-close, catch end-of-day setups)

Swing entry rules:
- Daily EMA close above (20/50/100/200 EMA reclaim on daily close)
- Weekly level hold (prior week low or multi-week support hold)
- Trend continuation pullback (pullback to rising EMA in uptrend)
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date

from alert_config import ANTHROPIC_API_KEY, CLAUDE_MODEL_SONNET

logger = logging.getLogger(__name__)

# Dedup: one swing signal per symbol per direction per day
_swing_fired: dict[str, set[tuple]] = {}
_swing_session: str = ""


def _resolve_api_key() -> str:
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    return ""


def build_swing_prompt(
    symbol: str,
    daily_bars: list[dict],
    prior_day: dict | None,
) -> str:
    """Build specialized swing trade prompt using daily chart data."""

    prompt = (
        "You are a swing trade entry detector analyzing DAILY charts. "
        "Your ONLY job: determine if a SWING LONG entry is confirmed based on daily closes.\n\n"
        "SWING ENTRY RULES (fire LONG only if ONE is confirmed):\n\n"
        "1. DAILY EMA CLOSE ABOVE: Price CLOSES above key daily EMA (20/50/100/200) after being below.\n"
        "   Confirmation: daily candle CLOSE above the EMA (not just intraday wick).\n"
        "   Entry = EMA level. Stop = below EMA or prior swing low.\n\n"
        "2. WEEKLY LEVEL HOLD: Price tests prior week low or multi-week support and holds on daily close.\n"
        "   Confirmation: daily close above the weekly level after testing it.\n"
        "   Entry = weekly support level. Stop = below the weekly level.\n\n"
        "3. TREND PULLBACK TO EMA: In uptrend (higher highs + higher lows on daily), "
        "price pulls back to a rising EMA and daily close holds above.\n"
        "   Confirmation: EMA is rising (today > 5 days ago) + daily close above EMA.\n"
        "   Entry = rising EMA level. Stop = below prior swing low.\n\n"
        "RESISTANCE WARNINGS:\n"
        "- If price is approaching weekly high or key daily MA from below, output RESISTANCE.\n\n"
        "OUTPUT FORMAT (plain text, no markdown):\n\n"
        "SETUP: [rule name or RESISTANCE or NONE]\n"
        "Direction: LONG / RESISTANCE / WAIT\n"
        "Entry: $price\n"
        "Stop: $price\n"
        "T1: $price (next daily resistance)\n"
        "T2: $price (second resistance or measured move)\n"
        "Conviction: HIGH / MEDIUM / LOW\n"
        "Reason: 1 sentence — what confirmed this swing entry\n\n"
        "STRICT RULES:\n"
        "- ONLY fire LONG if a daily CLOSE confirms the setup.\n"
        "- Swing trades hold for days to weeks — use daily levels, not intraday.\n"
        "- Entry = the key level (EMA, weekly support), NOT current price.\n"
        "- T1 = next overhead daily resistance. T2 = second resistance.\n"
        "- If no setup is confirmed on daily close, output WAIT.\n"
        "- MAXIMUM 80 WORDS total.\n"
    )

    parts = [prompt]

    # Prior day levels + MAs
    if prior_day:
        levels = [f"\n[DAILY LEVELS — {symbol}]"]
        for key, label in [
            ("high", "Yesterday High"),
            ("low", "Yesterday Low"),
            ("close", "Yesterday Close"),
            ("ema20", "Daily 20EMA"), ("ema50", "Daily 50EMA"),
            ("ema100", "Daily 100EMA"), ("ema200", "Daily 200EMA"),
            ("ma20", "Daily 20MA"), ("ma50", "Daily 50MA"),
            ("ma100", "Daily 100MA"), ("ma200", "Daily 200MA"),
        ]:
            val = prior_day.get(key)
            if val and val > 0:
                levels.append(f"{label}: ${val:.2f}")

        # Previous EMA values for trend detection (rising vs falling)
        ema20_prev = prior_day.get("ema20_prev")
        if ema20_prev and ema20_prev > 0:
            levels.append(f"20EMA 5d ago: ${ema20_prev:.2f}")

        # Weekly levels
        pw_high = prior_day.get("prior_week_high")
        pw_low = prior_day.get("prior_week_low")
        if pw_high and pw_high > 0:
            levels.append(f"Prior Week High: ${pw_high:.2f}")
        if pw_low and pw_low > 0:
            levels.append(f"Prior Week Low: ${pw_low:.2f}")

        # Monthly levels
        pm_high = prior_day.get("prior_month_high")
        pm_low = prior_day.get("prior_month_low")
        if pm_high and pm_high > 0:
            levels.append(f"Prior Month High: ${pm_high:.2f}")
        if pm_low and pm_low > 0:
            levels.append(f"Prior Month Low: ${pm_low:.2f}")

        rsi = prior_day.get("rsi14")
        if rsi:
            levels.append(f"RSI14: {rsi:.1f}")

        parts.append("\n".join(levels))

    # Daily bars (last 20 for trend context)
    if daily_bars:
        lines = [f"\n[DAILY BARS — last {min(len(daily_bars), 20)} days]"]
        for b in daily_bars[-20:]:
            lines.append(
                f"O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} "
                f"C={b['close']:.2f} V={b.get('volume', 0):.0f}"
            )
        parts.append("\n".join(lines))

    return "\n".join(parts)


def parse_swing_response(text: str) -> dict:
    """Parse structured swing trade signal from Claude response."""
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

    setup_match = re.search(r"SETUP:\s*(.+?)(?:\n|$)", text)
    if setup_match:
        result["setup_type"] = setup_match.group(1).strip()

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


def scan_swing_trade(symbol: str, api_key: str) -> dict | None:
    """Scan one symbol for swing trade entries using daily chart + Sonnet."""
    from analytics.intraday_data import fetch_prior_day
    from config import is_crypto_alert_symbol
    import yfinance as yf

    is_crypto = is_crypto_alert_symbol(symbol)

    try:
        # Fetch daily bars (last 30 days for trend context)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="3mo")
        if hist.empty or len(hist) < 10:
            logger.warning("AI swing scan: insufficient daily bars for %s", symbol)
            return None

        daily_bars = [
            {"open": float(r["Open"]), "high": float(r["High"]),
             "low": float(r["Low"]), "close": float(r["Close"]),
             "volume": float(r["Volume"])}
            for _, r in hist.tail(20).iterrows()
        ]

        prior_day = fetch_prior_day(symbol, is_crypto=is_crypto)

        prompt = build_swing_prompt(symbol, daily_bars, prior_day)

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system_with_cache = [
            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
        ]

        start = time.time()
        response = client.messages.create(
            model=CLAUDE_MODEL_SONNET,  # Sonnet for swing — needs more reasoning
            max_tokens=250,
            system=system_with_cache,
            messages=[{"role": "user", "content": f"Analyze {symbol} daily chart for swing entry."}],
            timeout=20.0,
        )
        elapsed = time.time() - start

        response_text = response.content[0].text.strip()
        logger.info("AI swing scan %s: %.1fs, %d tokens — %s",
                     symbol, elapsed, response.usage.input_tokens, response_text[:100])

        parsed = parse_swing_response(response_text)
        parsed["symbol"] = symbol
        parsed["price"] = float(hist.iloc[-1]["Close"])
        parsed["signal_source"] = "swing_trade"
        return parsed

    except Exception:
        logger.exception("AI swing scan failed for %s", symbol)
        return None


def swing_scan_cycle(sync_session_factory) -> int:
    """Swing trade scan cycle — runs 2x/day (pre-market + pre-close)."""
    global _swing_fired, _swing_session

    session = date.today().isoformat()
    if _swing_session != session:
        _swing_fired.clear()
        _swing_session = session

    api_key = _resolve_api_key()
    if not api_key:
        logger.warning("AI swing scan: no API key, skipping")
        return 0

    try:
        from sqlalchemy import select
        from app.models.watchlist import WatchlistItem
        from app.models.user import User
        from app.models.alert import Alert

        with sync_session_factory() as db:
            all_items = db.execute(
                select(WatchlistItem.symbol, WatchlistItem.user_id)
            ).all()

            symbol_users: dict[str, list[int]] = {}
            for sym, uid in all_items:
                symbol_users.setdefault(sym, []).append(uid)

            symbols = list(symbol_users.keys())
            if not symbols:
                return 0

            logger.info("AI swing scan: scanning %d symbols", len(symbols))
            total_alerts = 0

            for symbol in symbols:
                result = scan_swing_trade(symbol, api_key)
                if not result:
                    continue

                direction = result.get("direction")
                setup_type = result.get("setup_type", "")
                entry = result.get("entry", 0)
                reason = result.get("reason", "")
                conviction = result.get("conviction", "MEDIUM")

                if not direction or direction == "WAIT":
                    logger.info("AI swing scan %s: WAIT — %s", symbol, reason or "no setup")
                    continue

                # RESISTANCE warning
                if direction == "RESISTANCE":
                    _res_key = (symbol, "SWING_RESISTANCE")
                    fired = _swing_fired.get(session, set())
                    if _res_key in fired:
                        continue
                    fired.add(_res_key)
                    _swing_fired[session] = fired

                    _msg = f"SWING RESISTANCE {symbol} — {reason}" if reason else f"SWING RESISTANCE {symbol}"
                    for uid in symbol_users[symbol]:
                        db.add(Alert(
                            user_id=uid, symbol=symbol,
                            alert_type="ai_swing_resistance", direction="NOTICE",
                            price=result.get("price", 0), entry=entry,
                            message=_msg, score=0, session_date=session,
                        ))
                    db.commit()
                    logger.info("AI swing scan %s: RESISTANCE", symbol)
                    continue

                # LONG entry
                if not entry or entry <= 0:
                    continue

                # Dedup: one swing per symbol per day
                dedup_key = (symbol, "SWING_LONG")
                fired = _swing_fired.get(session, set())
                if dedup_key in fired:
                    continue
                fired.add(dedup_key)
                _swing_fired[session] = fired

                score = {"HIGH": 85, "MEDIUM": 65, "LOW": 45}.get(conviction, 65)
                setup_label = setup_type or "Swing entry"
                message = f"SWING: {setup_label} — {reason}" if reason else f"SWING: {setup_label}"

                for uid in symbol_users[symbol]:
                    alert = Alert(
                        user_id=uid, symbol=symbol,
                        alert_type="ai_swing_long",
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

                # Telegram
                try:
                    from alerting.notifier import _send_telegram_to
                    import html as _html

                    _stop = f"${result['stop']:.2f}" if result.get("stop") else "N/A"
                    _t1 = f"${result['t1']:.2f}" if result.get("t1") else "N/A"
                    _t2 = f"${result['t2']:.2f}" if result.get("t2") else "N/A"
                    _tg_msg = (
                        f"<b>SWING LONG {_html.escape(symbol)} ${result.get('price', entry):.2f}</b>\n"
                        f"Entry ${entry:.2f} · Stop {_stop} · T1 {_t1} · T2 {_t2}\n"
                        f"Setup: {_html.escape(setup_label)}\n"
                        f"Conviction: {conviction}"
                    )

                    for uid in symbol_users[symbol]:
                        user = db.get(User, uid)
                        if user and user.telegram_enabled and user.telegram_chat_id:
                            _send_telegram_to(_tg_msg, user.telegram_chat_id)
                            logger.info("AI swing scan %s: SWING LONG → Telegram user %d", symbol, uid)
                except Exception:
                    logger.exception("AI swing scan: Telegram failed for %s", symbol)

            logger.info("AI swing scan complete: %d alerts from %d symbols", total_alerts, len(symbols))
            return total_alerts

    except Exception:
        logger.exception("AI swing scan cycle failed")
        return 0
