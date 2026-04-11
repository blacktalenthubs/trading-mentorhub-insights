"""AI Scanner — proactive AI-powered alerts running parallel to rule engine.

Scans each watchlist symbol on a schedule, calls Claude with chart context,
parses structured output, records alerts. Same quality as AI Coach but automated.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date

from alert_config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

# Dedup: track (symbol, direction, entry_bucket) per session
_scan_fired: dict[str, set[tuple]] = {}
_scan_session: str = ""

# Track last scan price per symbol — skip if <0.3% change
_last_scan_price: dict[str, float] = {}


def _resolve_api_key() -> str:
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    try:
        from db import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT anthropic_api_key FROM user_notification_prefs "
                "WHERE anthropic_api_key != '' LIMIT 1"
            ).fetchone()
            return row["anthropic_api_key"] if row else ""
    except Exception:
        return ""


def build_scan_prompt(
    symbol: str,
    bars_5m: list[dict],
    bars_1h: list[dict],
    prior_day: dict | None,
    technicals: dict | None,
) -> str:
    """Build AI scan prompt — same as Coach but without user-specific data."""

    parts = [
        "You are an intraday trading analyst. Your job: determine WHERE price is relative to key levels.\n\n"
        "STEP 1 — Calculate distance from current price to EACH level below.\n"
        "STEP 2 — Classify position:\n"
        "  AT SUPPORT (within 0.3% of support level) → potential LONG\n"
        "  AT RESISTANCE (within 0.3% of resistance level) → potential SHORT\n"
        "  APPROACHING (0.3-0.8% from level) → WAIT, note which level\n"
        "  MID-RANGE (>0.8% from all levels) → WAIT\n\n"
        "FORMAT (plain text, no markdown):\n\n"
        "CHART READ: 1 sentence — where price is relative to nearest level.\n\n"
        "POSITION: AT SUPPORT / AT RESISTANCE / APPROACHING / MID-RANGE\n\n"
        "ACTION:\n"
        "Direction: LONG / SHORT / WAIT\n"
        "Entry: $price — level name\n"
        "Stop: $price\n"
        "T1: $price (next resistance if LONG, next support if SHORT)\n"
        "T2: $price\n"
        "Conviction: HIGH / MEDIUM / LOW\n\n"
        "SUPPORT LEVELS (BUY when price is AT these):\n"
        "- Session low, Prior day low (PDL), VWAP (reclaim from below),\n"
        "  VWAP (pullback hold), MA bounce (20/50/100/200), Weekly low, Fib 50%/61.8%\n\n"
        "RESISTANCE LEVELS (SHORT when price is AT these):\n"
        "- Session high, Prior day high (PDH), VWAP loss (drop below),\n"
        "  MA rejection, Weekly high\n\n"
        "STRICT RULES:\n"
        "- MAXIMUM 60 WORDS.\n"
        "- ONLY fire LONG/SHORT if price is AT a level (within 0.3%).\n"
        "- If price is between levels or extended, Direction = WAIT.\n"
        "- Entry = the key level price, NOT current price.\n"
        "- T1 = next level in trade direction. T2 = level after T1.\n"
        "- PDH = yesterday's high. PDL = yesterday's low. Don't confuse with today's.\n"
        "- Education only, not financial advice."
    ]

    # Key levels from prior day
    if prior_day:
        levels = [f"[KEY LEVELS — {symbol}]"]
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
        parts.append("\n".join(levels))

    # Additional technicals (weekly levels, etc.)
    if technicals:
        tech_parts = []
        for key, label in [("pdh", "PDH"), ("pdl", "PDL"),
                           ("ma50", "50MA"), ("ma100", "100MA"), ("ma200", "200MA"),
                           ("prior_week_high", "WeekHi"), ("prior_week_low", "WeekLo")]:
            if key in technicals:
                tech_parts.append(f"{label}=${technicals[key]:.2f}")
        if tech_parts:
            parts.append(f"[TECHNICALS] {' '.join(tech_parts)}")

    # Intraday levels from 5m bars + pre-calculated position detection
    if bars_5m:
        session_high = max(b["high"] for b in bars_5m)
        session_low = min(b["low"] for b in bars_5m)
        _tp_vol = sum(((b["high"] + b["low"] + b["close"]) / 3) * b.get("volume", 1) for b in bars_5m)
        _vol = sum(b.get("volume", 1) for b in bars_5m)
        vwap = _tp_vol / _vol if _vol > 0 else bars_5m[-1]["close"]
        current = bars_5m[-1]["close"]

        # Pre-calculate distance to each key level — code math, no AI guessing
        support_levels = []
        resistance_levels = []

        def _add_level(name: str, price: float, is_support: bool):
            if price and price > 0:
                dist = abs(current - price) / price
                entry = {"name": name, "price": price, "distance_pct": dist}
                if is_support:
                    support_levels.append(entry)
                else:
                    resistance_levels.append(entry)

        # Support levels (below or near current price)
        _add_level("Session Low", session_low, current >= session_low * 0.998)
        _add_level("VWAP", vwap, current <= vwap * 1.002)
        if prior_day:
            pdl = prior_day.get("low", 0)
            pdh = prior_day.get("high", 0)
            if pdl > 0:
                _add_level("PDL(yesterday low)", pdl, current >= pdl * 0.998)
            if pdh > 0:
                _add_level("PDH(yesterday high)", pdh, current <= pdh * 1.002)
            for key, label in [("ma50", "50MA"), ("ma100", "100MA"), ("ma200", "200MA")]:
                val = prior_day.get(key, 0)
                if val and val > 0 and val < current:
                    _add_level(label, val, True)

        # Resistance levels (above current price)
        _add_level("Session High", session_high, current <= session_high * 1.002)
        if prior_day:
            pdh = prior_day.get("high", 0)
            if pdh > 0 and pdh > current:
                _add_level("PDH(yesterday high)", pdh, False)

        # Find nearest support and resistance
        nearby_support = sorted([s for s in support_levels if s["distance_pct"] <= 0.008], key=lambda x: x["distance_pct"])
        nearby_resistance = sorted([r for r in resistance_levels if r["distance_pct"] <= 0.008], key=lambda x: x["distance_pct"])

        at_support = [s for s in nearby_support if s["distance_pct"] <= 0.003]
        at_resistance = [r for r in nearby_resistance if r["distance_pct"] <= 0.003]

        # Determine position (code-calculated, not AI)
        if at_support:
            position = f"AT SUPPORT — {at_support[0]['name']} ${at_support[0]['price']:.2f} (distance: {at_support[0]['distance_pct']*100:.2f}%)"
        elif at_resistance:
            position = f"AT RESISTANCE — {at_resistance[0]['name']} ${at_resistance[0]['price']:.2f} (distance: {at_resistance[0]['distance_pct']*100:.2f}%)"
        elif nearby_support:
            position = f"APPROACHING SUPPORT — {nearby_support[0]['name']} ${nearby_support[0]['price']:.2f} (distance: {nearby_support[0]['distance_pct']*100:.2f}%)"
        elif nearby_resistance:
            position = f"APPROACHING RESISTANCE — {nearby_resistance[0]['name']} ${nearby_resistance[0]['price']:.2f} (distance: {nearby_resistance[0]['distance_pct']*100:.2f}%)"
        else:
            position = "MID-RANGE — price not near any key level"

        parts.append(
            f"[INTRADAY LEVELS]\n"
            f"Session High: ${session_high:.2f}\n"
            f"Session Low: ${session_low:.2f}\n"
            f"VWAP: ${vwap:.2f}\n"
            f"Current Price: ${current:.2f}\n\n"
            f"[POSITION — CALCULATED BY SYSTEM, USE THIS]\n"
            f"{position}\n"
            f"IMPORTANT: The POSITION above is calculated by code (not you). "
            f"If it says AT SUPPORT, you MUST set Direction = LONG with entry at the support level. "
            f"If it says AT RESISTANCE, you MUST set Direction = SHORT. "
            f"If it says APPROACHING or MID-RANGE, you MUST set Direction = WAIT."
        )

    # 5-min bars (last 20)
    if bars_5m:
        lines = [f"[5-MIN BARS — last {len(bars_5m)} bars]"]
        for b in bars_5m[-20:]:
            lines.append(
                f"O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} "
                f"C={b['close']:.2f} V={b.get('volume', 0):.0f}"
            )
        parts.append("\n".join(lines))

    # 1-hour bars (last 10)
    if bars_1h:
        lines = [f"[1-HOUR BARS — last {len(bars_1h)} bars]"]
        for b in bars_1h[-10:]:
            lines.append(
                f"O={b['open']:.2f} H={b['high']:.2f} L={b['low']:.2f} "
                f"C={b['close']:.2f} V={b.get('volume', 0):.0f}"
            )
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def parse_ai_response(text: str) -> dict:
    """Parse CHART READ + ACTION block from AI response.

    Returns dict with: direction, entry, stop, t1, t2, conviction, chart_read.
    Returns None values for missing fields.
    """
    result = {
        "direction": None,
        "entry": None,
        "stop": None,
        "t1": None,
        "t2": None,
        "conviction": None,
        "chart_read": None,
        "position": None,
        "raw": text,
    }

    # CHART READ
    cr_match = re.search(r"CHART READ:\s*(.+?)(?:\n|$)", text)
    if cr_match:
        result["chart_read"] = cr_match.group(1).strip()

    # POSITION
    pos_match = re.search(r"POSITION:\s*(AT SUPPORT|AT RESISTANCE|APPROACHING|MID-RANGE)", text, re.IGNORECASE)
    if pos_match:
        result["position"] = pos_match.group(1).upper()

    # Direction
    dir_match = re.search(r"Direction:\s*(LONG|SHORT|WAIT)", text, re.IGNORECASE)
    if dir_match:
        result["direction"] = dir_match.group(1).upper()

    def _parse_price(pattern: str, text: str) -> float | None:
        """Parse price handling commas in thousands (e.g. $72,987.96)."""
        m = re.search(pattern, text)
        if m:
            return float(m.group(1).replace(",", ""))
        return None

    # Entry
    result["entry"] = _parse_price(r"Entry:\s*\$?([\d,.]+)", text)

    # Stop
    result["stop"] = _parse_price(r"Stop:\s*\$?([\d,.]+)", text)

    # T1
    result["t1"] = _parse_price(r"T1:\s*\$?([\d,.]+)", text)

    # T2
    result["t2"] = _parse_price(r"T2:\s*\$?([\d,.]+)", text)

    # Conviction
    conv_match = re.search(r"Conviction:\s*(HIGH|MEDIUM|LOW)", text, re.IGNORECASE)
    if conv_match:
        result["conviction"] = conv_match.group(1).upper()

    return result


def scan_symbol(
    symbol: str,
    api_key: str,
    model: str = "",
) -> dict | None:
    """Fetch data, call Claude, parse response for one symbol.

    Returns parsed dict or None on failure.
    """
    from analytics.intraday_data import fetch_intraday, fetch_intraday_crypto, fetch_prior_day
    from config import is_crypto_alert_symbol

    is_crypto = is_crypto_alert_symbol(symbol)
    use_model = model or CLAUDE_MODEL

    try:
        # Fetch 5m bars — use Coinbase for crypto (real-time), yfinance for equities
        bars_5m_df = fetch_intraday_crypto(symbol) if is_crypto else fetch_intraday(symbol, period="1d", interval="5m")
        if bars_5m_df is None or (hasattr(bars_5m_df, "empty") and bars_5m_df.empty):
            logger.warning("AI scan: no 5m bars for %s", symbol)
            return None

        # Fetch 1h bars
        bars_1h_df = fetch_intraday(symbol, period="5d", interval="1h")

        # Fetch prior day
        prior_day = fetch_prior_day(symbol, is_crypto=is_crypto)

        # Check if price changed enough since last scan
        current_price = float(bars_5m_df.iloc[-1]["Close"])
        last_price = _last_scan_price.get(symbol, 0)
        if last_price > 0 and abs(current_price - last_price) / last_price < 0.003:
            logger.debug("AI scan: %s skipped — price unchanged (%.2f → %.2f)", symbol, last_price, current_price)
            return None
        _last_scan_price[symbol] = current_price

        # Convert bars to dicts
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

        # Build prompt
        prompt = build_scan_prompt(symbol, bars_5m, bars_1h, prior_day, None)

        # Call Claude (non-streaming)
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system_with_cache = [
            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
        ]

        start = time.time()
        response = client.messages.create(
            model=use_model,
            max_tokens=200,
            system=system_with_cache,
            messages=[{"role": "user", "content": f"Analyze {symbol} now. What's the trade?"}],
            timeout=15.0,
        )
        elapsed = time.time() - start

        response_text = response.content[0].text.strip()
        logger.info("AI scan %s: %.1fs, %d tokens — %s",
                     symbol, elapsed, response.usage.input_tokens, response_text[:80])

        # Parse
        parsed = parse_ai_response(response_text)
        parsed["symbol"] = symbol
        parsed["price"] = current_price
        return parsed

    except Exception:
        logger.exception("AI scan failed for %s", symbol)
        return None


def ai_scan_cycle(sync_session_factory):
    """Main scan cycle — runs on schedule, scans all watchlist symbols."""
    global _scan_fired, _scan_session

    session = date.today().isoformat()
    if _scan_session != session:
        _scan_fired.clear()
        _last_scan_price.clear()
        _scan_session = session

    api_key = _resolve_api_key()
    if not api_key:
        logger.warning("AI scan: no API key configured, skipping")
        return 0

    try:
        from sqlalchemy import select

        with sync_session_factory() as db:
            # Get all unique symbols across all users
            from app.models.watchlist import WatchlistItem
            from app.models.user import User

            all_items = db.execute(
                select(WatchlistItem.symbol, WatchlistItem.user_id)
            ).all()

            # Dedup symbols, track which users watch each
            symbol_users: dict[str, list[int]] = {}
            for sym, uid in all_items:
                symbol_users.setdefault(sym, []).append(uid)

            # Filter: only scan symbols whose market is open
            # Crypto = 24/7, equities = market hours only
            from analytics.market_hours import is_market_hours_for_symbol
            symbols = [s for s in symbol_users.keys() if is_market_hours_for_symbol(s)]
            if not symbols:
                logger.debug("AI scan: no symbols with open markets")
                return 0

            logger.info("AI scan: scanning %d symbols", len(symbols))
            total_alerts = 0

            for symbol in symbols:
                result = scan_symbol(symbol, api_key)
                if not result:
                    continue

                direction = result.get("direction")
                chart_read = result.get("chart_read", "")
                position = result.get("position", "")

                if not direction or direction == "WAIT":
                    # Record WAIT once (not per-user) for AI Scan feed
                    from app.models.alert import Alert as _Alert
                    _wait_msg = f"AI: {position} — {chart_read}" if chart_read else f"AI scan WAIT"
                    _first_uid = symbol_users[symbol][0]
                    db.add(_Alert(
                        user_id=_first_uid, symbol=symbol,
                        alert_type="ai_scan_wait", direction="NOTICE",
                        price=result.get("price", 0),
                        message=_wait_msg, score=0,
                        session_date=session,
                    ))
                    db.commit()
                    logger.info("AI scan %s: WAIT — %s", symbol, chart_read)
                    continue

                entry = result.get("entry", 0)
                if not entry or entry <= 0:
                    continue

                # Dedup: one alert per symbol per direction per session
                # If AI said LONG TSLA once today, don't repeat until direction changes
                dedup_key = (symbol, direction)
                fired = _scan_fired.get(session, set())
                if dedup_key in fired:
                    logger.debug("AI scan %s: dedup skip (%s already fired today)", symbol, direction)
                    continue
                fired.add(dedup_key)
                _scan_fired[session] = fired

                # Map direction
                db_direction = "BUY" if direction == "LONG" else "SHORT"
                alert_type = f"ai_scan_{direction.lower()}"

                # Score from conviction
                conviction = result.get("conviction", "MEDIUM")
                score = {"HIGH": 85, "MEDIUM": 65, "LOW": 45}.get(conviction, 65)

                # Build message
                chart_read = result.get("chart_read", "")
                message = f"AI: {chart_read}" if chart_read else f"AI scan {direction}"

                # Record alert for each user watching this symbol
                from app.models.alert import Alert

                for user_id in symbol_users[symbol]:
                    alert = Alert(
                        user_id=user_id,
                        symbol=symbol,
                        alert_type=alert_type,
                        direction=db_direction,
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

                # Send Telegram notification per user
                try:
                    from alerting.notifier import _send_telegram_to
                    from app.models.user import User

                    _dir_label = "LONG" if direction == "LONG" else "RESISTANCE"
                    _position = result.get("position", "")
                    _pos_line = f"\n{_position}" if _position else ""
                    _stop = f"${result['stop']:.2f}" if result.get("stop") else "N/A"
                    _t1 = f"${result['t1']:.2f}" if result.get("t1") else "N/A"
                    _t2 = f"${result['t2']:.2f}" if result.get("t2") else "N/A"
                    _msg = (
                        f"<b>AI SCAN — {_dir_label} {symbol} ${entry:.2f}</b>{_pos_line}\n"
                        f"Entry: ${entry:.2f} — {chart_read}\n"
                        f"Stop: {_stop} | T1: {_t1} | T2: {_t2}\n"
                        f"Conviction: {conviction}"
                    )

                    for user_id in symbol_users[symbol]:
                        user = db.get(User, user_id)
                        if user and user.telegram_enabled and user.telegram_chat_id:
                            _send_telegram_to(_msg, user.telegram_chat_id)
                            logger.info("AI scan %s: %s at $%.2f → Telegram sent to user %d", symbol, direction, entry, user_id)
                except Exception:
                    logger.exception("AI scan: Telegram send failed for %s", symbol)

            logger.info("AI scan cycle complete: %d alerts from %d symbols", total_alerts, len(symbols))
            return total_alerts

    except Exception:
        logger.exception("AI scan cycle failed")
        return 0
