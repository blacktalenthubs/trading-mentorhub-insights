"""Position Advisor — AI-powered re-evaluation of open trades.

Checks each open position against current market conditions (price, S/R levels,
SPY regime, volume) and produces actionable recommendations:
  Hold / Tighten stop to $X / Take partial profits / Exit

Can run on-demand (AI Coach button) or automated (Telegram push for Elite).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Generator

import pytz

logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")

_POSITION_ADVISOR_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = """\
You are a sharp position management advisor for an active day/swing trader. \
Given open positions and current market data, evaluate each position and \
provide a specific recommendation.

For EACH open position, respond with this format:
[SYMBOL] — [HOLD / TIGHTEN STOP / TAKE PARTIAL / EXIT]
  Reason: [1 sentence why]
  New stop: [price level if tightening, or "keep current" if holding]

After individual positions, add:
PORTFOLIO NOTE: [1 sentence on overall exposure/risk]

Rules:
- Be specific — reference actual price levels, S/R, and MAs
- Consider: time in trade, distance from stop, distance from target
- If price is near target, suggest taking partial profits
- If support has broken below the stop, recommend EXIT
- If trade is working, suggest tightening stop to breakeven or nearest support
- If a position's symbol is CONSOLIDATING, note the range and advise holding for breakout direction
- If a BREAKOUT just occurred, advise whether the position benefits or is at risk
- Keep the total response under 200 words
- Use probability language, never guarantee outcomes
- No markdown formatting — plain text only
- Write dollar amounts WITHOUT the $ symbol"""


def _resolve_api_key() -> str:
    """Return Anthropic API key (env var first, then DB fallback)."""
    from alert_config import ANTHROPIC_API_KEY
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


def _get_consolidation_states(symbols: list[str]) -> dict[str, dict]:
    """Fetch hourly consolidation state for each symbol."""
    states: dict[str, dict] = {}
    try:
        import yfinance as yf
        from analytics.intraday_rules import detect_hourly_consolidation_break

        for sym in symbols:
            try:
                is_crypto = sym.endswith("-USD")
                period = "5d" if is_crypto else "1d"
                ticker = yf.Ticker(sym)
                bars = ticker.history(period=period, interval="5m")
                if bars.empty:
                    continue
                hbreak = detect_hourly_consolidation_break(bars)
                if hbreak:
                    states[sym] = hbreak
            except Exception:
                continue
    except Exception:
        logger.debug("Consolidation state fetch failed")
    return states


def _build_position_prompt(trades: list[dict], spy_ctx: dict | None,
                           technicals: dict | None,
                           consol_states: dict[str, dict] | None = None) -> str:
    """Build the user prompt with open positions and market context."""
    lines: list[str] = []

    # SPY context
    if spy_ctx:
        lines.append(
            f"SPY: ${spy_ctx.get('close', 0):.2f} | "
            f"Regime: {spy_ctx.get('regime', 'UNKNOWN')} | "
            f"Trend: {spy_ctx.get('trend', 'unknown')}"
        )
        if spy_ctx.get("spy_rsi14"):
            lines.append(f"SPY RSI14: {spy_ctx['spy_rsi14']:.1f}")
        lines.append("")

    # Open positions
    lines.append("OPEN POSITIONS:")
    for t in trades:
        symbol = t.get("symbol", "?")
        tag = "[PAPER] " if t.get("_paper") else ""
        direction = t.get("direction", "BUY")
        entry = t.get("entry_price", 0)
        current = t.get("current_price", entry)
        stop = t.get("stop_price")
        target = t.get("target_price")
        shares = t.get("shares", 0)
        opened = t.get("opened_at", "")

        pnl = (current - entry) * shares if direction == "BUY" else (entry - current) * shares
        pnl_pct = ((current - entry) / entry * 100) if entry > 0 else 0

        pos_line = (
            f"  {tag}{symbol} {direction} {shares} shares @ {entry:.2f} "
            f"| Current: {current:.2f} ({pnl_pct:+.1f}%)"
        )
        if stop:
            pos_line += f" | Stop: {stop:.2f}"
        if target:
            pos_line += f" | Target: {target:.2f}"
        if opened:
            pos_line += f" | Opened: {opened}"
        lines.append(pos_line)

        # Add technicals for this symbol if available
        if technicals and symbol in technicals:
            tech = technicals[symbol]
            tech_parts = []
            for key, label in [("ema20", "20EMA"), ("ema50", "50EMA"),
                               ("ma100", "100MA"), ("ma200", "200MA")]:
                if key in tech:
                    tech_parts.append(f"{label}={tech[key]:.2f}")
            if "rsi14" in tech:
                tech_parts.append(f"RSI={tech['rsi14']:.1f}")
            if tech_parts:
                lines.append(f"    Technicals: {' '.join(tech_parts)}")

        # Add consolidation state
        if consol_states and symbol in consol_states:
            cs = consol_states[symbol]
            status = cs.get("status", "unknown")
            direction = cs.get("direction", "?")
            rh = cs.get("range_high", 0)
            rl = cs.get("range_low", 0)
            rp = cs.get("range_pct", 0)
            atr = cs.get("hourly_atr", 0)
            if status == "consolidating":
                lines.append(
                    f"    CONSOLIDATING: range {rl:.2f}-{rh:.2f} "
                    f"({rp:.1f}%), ATR {atr:.2f}. "
                    f"Breakout above {rh:.2f} or breakdown below {rl:.2f}"
                )
            elif status == "breakout":
                lines.append(
                    f"    BREAKOUT {direction}: broke {'above' if direction == 'UP' else 'below'} "
                    f"range {rl:.2f}-{rh:.2f} ({rp:.1f}%)"
                )

    return "\n".join(lines)


def check_positions(trades: list[dict] | None = None) -> str | None:
    """Run AI position check on open trades.

    If *trades* is None, fetches all open trades from the DB.
    Returns the AI advice text or None on failure.
    """
    if trades is None:
        from alerting.real_trade_store import get_open_trades
        trades = get_open_trades() or []
        # Also include open paper trades
        try:
            from alerting.paper_trader import get_open_paper_trades_for_coach
            paper = get_open_paper_trades_for_coach() or []
            for t in paper:
                t["_paper"] = True
            trades = trades + paper
        except Exception:
            pass

    if not trades:
        return None

    api_key = _resolve_api_key()
    if not api_key:
        logger.info("Position advisor: no API key available")
        return None

    # Gather market context
    spy_ctx = None
    technicals = None
    try:
        from analytics.intraday_data import get_spy_context
        spy_ctx = get_spy_context()
    except Exception:
        logger.debug("Position advisor: SPY context unavailable")

    # Fetch current prices and technicals for open position symbols
    symbols = list({t.get("symbol", "") for t in trades if t.get("symbol")})
    symbols.append("SPY")
    try:
        from analytics.trade_coach import _get_symbol_technicals
        technicals = _get_symbol_technicals(symbols)

        # Update current prices from technicals
        for t in trades:
            sym = t.get("symbol", "")
            if sym in (technicals or {}):
                t["current_price"] = technicals[sym].get("close", t.get("entry_price", 0))
    except Exception:
        logger.debug("Position advisor: technicals unavailable")

    # Add consolidation state for open position symbols
    consol_states = _get_consolidation_states(symbols)
    prompt = _build_position_prompt(trades, spy_ctx, technicals, consol_states)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_POSITION_ADVISOR_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        advice = response.content[0].text.strip()

        now_et = datetime.now(ET)
        time_str = now_et.strftime("%I:%M %p ET")
        return f"POSITION CHECK \u2014 {time_str}\n\n{advice}"

    except Exception:
        logger.exception("Position advisor: AI call failed")
        return None


def check_positions_stream(trades: list[dict] | None = None) -> Generator[str, None, None]:
    """Stream position check for use in Streamlit UI.

    Yields text chunks as they arrive from the API.
    """
    if trades is None:
        from alerting.real_trade_store import get_open_trades
        trades = get_open_trades() or []
        try:
            from alerting.paper_trader import get_open_paper_trades_for_coach
            paper = get_open_paper_trades_for_coach() or []
            for t in paper:
                t["_paper"] = True
            trades = trades + paper
        except Exception:
            pass

    if not trades:
        yield "No open positions to check."
        return

    api_key = _resolve_api_key()
    if not api_key:
        yield "No API key configured."
        return

    # Gather context
    spy_ctx = None
    technicals = None
    try:
        from analytics.intraday_data import get_spy_context
        spy_ctx = get_spy_context()
    except Exception:
        pass

    symbols = list({t.get("symbol", "") for t in trades if t.get("symbol")})
    symbols.append("SPY")
    try:
        from analytics.trade_coach import _get_symbol_technicals
        technicals = _get_symbol_technicals(symbols)
        for t in trades:
            sym = t.get("symbol", "")
            if sym in (technicals or {}):
                t["current_price"] = technicals[sym].get("close", t.get("entry_price", 0))
    except Exception:
        pass

    consol_states = _get_consolidation_states(symbols)
    prompt = _build_position_prompt(trades, spy_ctx, technicals, consol_states)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    with client.messages.stream(
        model=_POSITION_ADVISOR_MODEL,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk


def send_position_updates() -> bool:
    """Send position check to Elite users via Telegram.

    Runs during market hours. Checks if any open trades exist first.

    Returns True if at least one message was sent.
    """
    from alerting.real_trade_store import get_open_trades
    trades = get_open_trades() or []
    try:
        from alerting.paper_trader import get_open_paper_trades_for_coach
        paper = get_open_paper_trades_for_coach() or []
        for t in paper:
            t["_paper"] = True
        trades = trades + paper
    except Exception:
        pass
    if not trades:
        logger.debug("Position advisor: no open trades")
        return False

    advice = check_positions(trades)
    if not advice:
        return False

    # Send to Elite users with Telegram
    try:
        from db import get_pro_users_with_telegram
        from alerting.notifier import _send_telegram_to
        users = get_pro_users_with_telegram()
        elite_users = [u for u in users if u.get("tier") in ("elite", "admin")]
    except Exception:
        logger.exception("Position advisor: failed to get user list")
        return False

    if not elite_users:
        # Fallback to global Telegram
        from alerting.notifier import _send_telegram
        return _send_telegram(advice)

    any_sent = False
    for u in elite_users:
        chat_id = u.get("telegram_chat_id", "")
        if chat_id:
            from alerting.notifier import _send_telegram_to
            ok = _send_telegram_to(advice, chat_id)
            if ok:
                any_sent = True

    return any_sent
