"""Pre-market brief — build and send a daily pre-market Telegram summary.

Includes an AI analysis layer that synthesizes the data dump into an
actionable game plan (top 3 setups, SPY outlook, risk warnings).
Sent to Pro/Elite users with Telegram enabled.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytz

from alerting.alert_store import today_session
from alerting.notifier import _send_telegram, _send_telegram_to
from analytics.intraday_data import (
    compute_overnight_context,
    compute_premarket_brief,
    fetch_overnight_futures,
    fetch_premarket_bars,
    fetch_prior_day,
    get_spy_context,
)
from db import get_all_watchlist_symbols

logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")

# Once-per-day guards
_brief_sent_date: str | None = None
_ai_brief_sent_date: str | None = None

_AI_PREMARKET_MODEL = "claude-sonnet-4-20250514"

_AI_PREMARKET_SYSTEM = """\
You are a sharp day-trading coach delivering specific if/then trade plans. \
Given today's pre-market data, overnight futures, key levels, and SPY regime, \
produce actionable trade plans for each stock.

Structure your response EXACTLY like this:

SPY OUTLOOK: [regime + key levels + overnight bias in 1-2 sentences]
TODAY'S BIAS: [Bullish/Bearish/Neutral] — [reason]

TRADE PLANS:

[SYMBOL] [price] — [pattern: INSIDE DAY / GAP UP / etc.]
  BUY: If [condition with specific price], entry [price], stop [price], T1 VWAP [price]
  SELL: If rejected at [resistance level + price], exit
  KEY: PDL [price] | PDH [price] | EMA20 [price] | VWAP ~[price]

[repeat for each symbol, ranked by conviction]

AVOID: [symbols or conditions to stay away from today]

Rules:
- Write a specific if/then trade plan for EVERY symbol in the data
- Always include exact price levels from the data — never say "near support"
- BUY scenarios: reference PDL reclaim, morning low hold, MA bounce, VWAP reclaim
- SELL scenarios: reference PDH rejection, MA resistance, VWAP rejection, PDL breakdown
- T1 should be VWAP when buying from below VWAP
- If overnight futures are bearish, flag caution on BUY setups
- Rank by conviction — best setup first
- No markdown formatting — plain text only
- Write dollar amounts WITHOUT the $ symbol to avoid rendering issues
- Be concise — one BUY line and one SELL line per symbol"""


def _format_spy_header(spy_ctx: dict) -> str:
    """Format SPY regime one-liner for the brief header."""
    close = spy_ctx.get("close", 0)
    regime = spy_ctx.get("regime", "UNKNOWN")
    rsi = spy_ctx.get("spy_rsi14")
    trend = spy_ctx.get("trend", "neutral")

    emoji = {"bullish": "\U0001f7e2", "bearish": "\U0001f534", "neutral": "\U0001f7e1"}.get(trend, "\U0001f7e1")
    rsi_str = f" | RSI {rsi:.0f}" if rsi is not None else ""
    return f"{emoji} SPY ${close:.2f} | {regime}{rsi_str}"


def _format_symbol_line(brief: dict) -> str:
    """Format a single symbol's pre-market summary."""
    symbol = brief["symbol"]
    flags = brief.get("flags", [])
    pm_last = brief["pm_last"]
    pm_change = brief["pm_change_pct"]
    pm_range = brief["pm_range_pct"]

    sign = "+" if pm_change >= 0 else ""
    flags_str = " | ".join(flags) if flags else "No flags"

    lines = [
        f"  {symbol} \u2014 {flags_str}",
        f"  PM: ${pm_last:.2f} ({sign}{pm_change:.1f}%) | Range: {pm_range:.1f}%",
    ]
    return "\n".join(lines)


def _format_overnight_section(overnight: dict) -> str:
    """Format the OVERNIGHT FUTURES section for the premarket brief."""
    lines = ["\nOVERNIGHT FUTURES"]

    for future_sym in ["ES=F", "NQ=F"]:
        data = overnight.get(future_sym)
        if data is None:
            continue
        sign = "+" if data["on_change_pct"] >= 0 else ""
        gap_sign = "+" if data["projected_gap_pct"] >= 0 else ""
        lines.append(
            f"  {future_sym} ({data['equity_symbol']}): "
            f"{data['on_last']:.2f} ({sign}{data['on_change_pct']:.1f}%) "
            f"| H: {data['on_high']:.2f} L: {data['on_low']:.2f} "
            f"| Gap est: {gap_sign}{data['projected_gap_pct']:.1f}%"
        )

    bias = overnight.get("overnight_bias", "UNKNOWN")
    bias_emoji = {
        "BULLISH": "\U0001f7e2", "BEARISH": "\U0001f534", "FLAT": "\U0001f7e1",
    }.get(bias, "\u2753")
    lines.append(f"  {bias_emoji} Overnight Bias: {bias}")

    return "\n".join(lines)


def build_premarket_message() -> str | None:
    """Build the pre-market brief message text.

    Returns formatted string or None if no data available.
    """
    symbols = get_all_watchlist_symbols()
    if not symbols:
        return None

    # Gather briefs for each symbol
    briefs: list[dict] = []
    for symbol in symbols:
        pm_bars = fetch_premarket_bars(symbol)
        if pm_bars.empty:
            continue
        prior = fetch_prior_day(symbol)
        if prior is None:
            continue
        brief = compute_premarket_brief(symbol, pm_bars, prior)
        if brief is not None:
            briefs.append(brief)

    if not briefs:
        return None

    # SPY header + overnight futures
    spy_ctx = get_spy_context()
    now_et = datetime.now(ET)
    date_str = now_et.strftime("%b %-d, %Y")

    parts: list[str] = [
        f"PRE-MARKET BRIEF \u2014 {date_str}",
        "",
        _format_spy_header(spy_ctx),
    ]

    # Overnight futures context (ES=F, NQ=F)
    try:
        es_bars = fetch_overnight_futures("ES=F")
        nq_bars = fetch_overnight_futures("NQ=F")
        spy_close = spy_ctx.get("close", 0.0)
        qqq_prior = fetch_prior_day("QQQ")
        qqq_close = qqq_prior["close"] if qqq_prior else 0.0
        overnight_ctx = compute_overnight_context(
            es_bars, nq_bars, spy_close, qqq_close,
        )
        if overnight_ctx:
            parts.append(_format_overnight_section(overnight_ctx))
    except Exception:
        logger.warning("Overnight futures data unavailable")

    # Group by priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    briefs.sort(key=lambda b: priority_order.get(b["priority_label"], 3))

    current_priority = None
    for brief in briefs:
        label = brief["priority_label"]
        if label != current_priority:
            current_priority = label
            parts.append(f"\n--- {label} PRIORITY ---")
        parts.append(_format_symbol_line(brief))

    return "\n".join(parts)


def _build_ai_premarket_prompt(data_brief: str) -> str:
    """Build the user prompt for AI pre-market analysis.

    Enriches the data brief with daily plans AND key technical levels
    (MAs, EMAs, prior day high/low) for each symbol so the AI can
    produce specific if/then trade plans with exact prices.
    """
    session = today_session()
    parts = [data_brief]

    # Add daily plans
    try:
        from db import get_all_daily_plans
        plans = get_all_daily_plans(session)
        if plans:
            sorted_plans = sorted(plans, key=lambda p: p.get("score", 0), reverse=True)[:10]
            lines = ["", "DAILY PLANS (by score):"]
            for p in sorted_plans:
                lines.append(
                    f"  {p['symbol']} score={p.get('score', '?')}({p.get('score_label', '')}) "
                    f"pattern={p.get('pattern', 'N/A')} "
                    f"entry={p.get('entry', 'N/A')} stop={p.get('stop', 'N/A')} "
                    f"T1={p.get('target_1', 'N/A')}"
                )
            parts.append("\n".join(lines))
    except Exception:
        logger.debug("AI premarket: daily plans not available")

    # Add key technical levels for each symbol
    try:
        from analytics.intraday_data import fetch_prior_day
        from config import is_crypto_alert_symbol

        # Get watchlist symbols from the data brief (parse symbol names)
        import re
        symbols = re.findall(r"^\s+(\S+)\s+—\s+GAP", data_brief, re.MULTILINE)
        if not symbols:
            symbols = re.findall(r"^\s+(\S+)\s+—", data_brief, re.MULTILINE)

        if symbols:
            lines = ["", "KEY LEVELS PER SYMBOL:"]
            for sym in symbols[:12]:
                try:
                    prior = fetch_prior_day(sym, is_crypto=is_crypto_alert_symbol(sym))
                    if not prior:
                        continue
                    pdh = prior.get("high", 0)
                    pdl = prior.get("low", 0)
                    pc = prior.get("close", 0)
                    ema20 = prior.get("ema20", 0)
                    ema50 = prior.get("ema50", 0)
                    ema100 = prior.get("ema100", 0)
                    ema200 = prior.get("ema200", 0)
                    rsi = prior.get("rsi14", 0)
                    pattern = prior.get("pattern", "normal")

                    lines.append(
                        f"  {sym}: PDH={pdh:.2f} PDL={pdl:.2f} Close={pc:.2f} "
                        f"EMA20={ema20:.2f} EMA50={ema50:.2f} EMA100={ema100:.2f} "
                        f"EMA200={ema200:.2f} RSI={rsi:.1f} Pattern={pattern}"
                    )
                except Exception:
                    pass
            parts.append("\n".join(lines))
    except Exception:
        logger.debug("AI premarket: key levels not available")

    return "\n".join(parts)


def build_ai_premarket_analysis(data_brief: str) -> str | None:
    """Generate AI pre-market analysis using Sonnet.

    Takes the raw data brief as input, enriches with daily plans,
    and returns the AI game plan text or None on failure.
    """
    from alert_config import ANTHROPIC_API_KEY

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        try:
            from db import get_db
            with get_db() as conn:
                row = conn.execute(
                    "SELECT anthropic_api_key FROM user_notification_prefs "
                    "WHERE anthropic_api_key != '' LIMIT 1"
                ).fetchone()
                api_key = row["anthropic_api_key"] if row else ""
        except Exception:
            pass

    if not api_key:
        logger.info("AI premarket: no API key available")
        return None

    prompt = _build_ai_premarket_prompt(data_brief)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_AI_PREMARKET_MODEL,
            max_tokens=1024,
            system=_AI_PREMARKET_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        analysis = response.content[0].text.strip()

        now_et = datetime.now(ET)
        date_str = now_et.strftime("%b %-d, %Y")
        return f"AI GAME PLAN \u2014 {date_str}\n\n{analysis}"

    except Exception:
        logger.exception("Failed to generate AI premarket analysis")
        return None


def send_premarket_brief() -> bool:
    """Send the pre-market brief via Telegram (once per day).

    Returns True if sent, False if skipped or failed.
    """
    global _brief_sent_date

    session = today_session()
    if _brief_sent_date == session:
        logger.debug("Pre-market brief already sent for %s", session)
        return False

    msg = build_premarket_message()
    if not msg:
        logger.info("Pre-market brief: no data to send")
        return False

    sent = _send_telegram(msg)
    if sent:
        _brief_sent_date = session
        logger.info("Pre-market brief sent for %s", session)
    return sent


def _build_user_premarket(user_id: int) -> str | None:
    """Build pre-market data brief for a specific user's watchlist."""
    try:
        from db import get_watchlist
        symbols = get_watchlist(user_id)
    except Exception:
        symbols = []

    if not symbols:
        return None

    briefs: list[dict] = []
    for symbol in symbols:
        try:
            pm_bars = fetch_premarket_bars(symbol)
            if pm_bars.empty:
                continue
            prior = fetch_prior_day(symbol)
            if prior is None:
                continue
            brief = compute_premarket_brief(symbol, pm_bars, prior)
            if brief is not None:
                briefs.append(brief)
        except Exception:
            continue

    if not briefs:
        return None

    spy_ctx = get_spy_context()
    now_et = datetime.now(ET)
    date_str = now_et.strftime("%b %-d, %Y")

    parts: list[str] = [
        f"PRE-MARKET BRIEF \u2014 {date_str}",
        "",
        _format_spy_header(spy_ctx),
    ]

    for b in briefs:
        parts.append(_format_symbol_line(b))

    return "\n".join(parts)


def send_ai_premarket_brief() -> bool:
    """Send per-user AI pre-market game plan to Pro users (once per day).

    Each user gets analysis customized to their personal watchlist.
    Returns True if at least one message was sent.
    """
    global _ai_brief_sent_date

    session = today_session()
    if _ai_brief_sent_date == session:
        logger.debug("AI premarket brief already sent for %s", session)
        return False

    # Get all Pro users with Telegram enabled
    try:
        from db import get_pro_users_with_telegram
        users = get_pro_users_with_telegram()
    except Exception:
        logger.exception("AI premarket: failed to get user list")
        users = []

    if not users:
        # Fallback: send global brief
        data_brief = build_premarket_message()
        if data_brief:
            analysis = build_ai_premarket_analysis(data_brief)
            if analysis:
                sent = _send_telegram(analysis)
                if sent:
                    _ai_brief_sent_date = session
                return sent
        return False

    any_sent = False
    for u in users:
        chat_id = u.get("telegram_chat_id", "")
        user_id = u.get("user_id")
        if not chat_id or not user_id:
            continue

        try:
            # Build per-user data brief from their watchlist
            user_brief = _build_user_premarket(user_id)
            if not user_brief:
                # Fallback to global brief if user has no symbols
                user_brief = build_premarket_message()
            if not user_brief:
                continue

            analysis = build_ai_premarket_analysis(user_brief)
            if not analysis:
                continue

            ok = _send_telegram_to(analysis, chat_id)
            if ok:
                any_sent = True
                logger.info(
                    "AI premarket sent to user %s (tier=%s, symbols=%s)",
                    user_id, u.get("tier", "?"),
                    len(user_brief.split("\n")),
                )
        except Exception:
            logger.exception("AI premarket failed for user %s", user_id)

    if any_sent:
        _ai_brief_sent_date = session
        logger.info("AI premarket brief delivered for %s", session)

    return any_sent
