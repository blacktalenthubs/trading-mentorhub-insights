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
You are a sharp day-trading coach delivering a personalized daily battle plan. \
Given today's pre-market data, overnight futures, key levels, SPY regime, \
open positions, and recent activity, produce actionable trade plans.

Structure your response EXACTLY like this:

SPY OUTLOOK: [regime + key levels + overnight bias in 1-2 sentences]
TODAY'S BIAS: [Bullish/Bearish/Neutral] — [reason]

MANAGE FIRST (if open positions exist):
[For each open position: hold/tighten stop/take profit guidance with prices]

YOUR PLAYS:

[SYMBOL] [price] — [pattern: INSIDE DAY / GAP UP / etc.]
  BUY: If [condition with specific price], entry [price], stop [price], T1 [price]
  SELL: If rejected at [resistance level + price], exit
  KEY: PDL [price] | PDH [price] | EMA20 [price] | VWAP ~[price]

[repeat for each symbol, ranked by conviction]

AVOID: [symbols or conditions to stay away from today]

RISK BUDGET: [comment on recent activity — too many trades? good discipline?]

Rules:
- Write a specific if/then trade plan for EVERY symbol in the data
- Always include exact price levels from the data — never say "near support"
- If user has open positions, address those FIRST (manage before new trades)
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


def _build_ai_premarket_prompt(data_brief: str, user_id: int | None = None) -> str:
    """Build the user prompt for AI pre-market analysis.

    Enriches the data brief with daily plans, key technical levels,
    open positions, and recent performance for personalized battle plans.
    """
    session = today_session()
    parts = [data_brief]

    # Add user's open positions context
    if user_id:
        try:
            from db import get_db
            with get_db() as conn:
                positions = conn.execute(
                    "SELECT symbol, direction, entry_price, stop_price, target_price, "
                    "target_2_price, shares FROM real_trades "
                    "WHERE user_id = ? AND status = 'open'",
                    (user_id,),
                ).fetchall()
                if positions:
                    lines = ["", "YOUR OPEN POSITIONS:"]
                    for p in positions:
                        lines.append(
                            f"  {p['symbol']} {p['direction']} @ {p['entry_price']:.2f} "
                            f"(stop={p['stop_price']}, T1={p['target_price']}, "
                            f"shares={p['shares']})"
                        )
                    parts.append("\n".join(lines))
        except Exception:
            pass

        # Add recent performance stats (last 7 days)
        try:
            from db import get_db
            with get_db() as conn:
                stats = conn.execute(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN user_action = 'took' THEN 1 ELSE 0 END) as took, "
                    "SUM(CASE WHEN user_action = 'skipped' THEN 1 ELSE 0 END) as skipped "
                    "FROM alerts WHERE user_id = ? AND session_date >= date('now', '-7 days')",
                    (user_id,),
                ).fetchone()
                if stats and stats["total"] > 0:
                    parts.append(
                        f"\nRECENT ACTIVITY (7 days): {stats['total']} alerts, "
                        f"{stats['took'] or 0} taken, {stats['skipped'] or 0} skipped"
                    )
        except Exception:
            pass

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


def build_ai_premarket_analysis(data_brief: str, user_id: int | None = None) -> str | None:
    """Generate AI pre-market analysis using Sonnet.

    Takes the raw data brief as input, enriches with daily plans,
    open positions, and returns the AI game plan text or None on failure.
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

    prompt = _build_ai_premarket_prompt(data_brief, user_id=user_id)

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
    """Send per-user pre-market data brief to Pro users (once per day).

    Returns True if at least one message was sent.
    """
    global _brief_sent_date

    session = today_session()
    if _brief_sent_date == session:
        logger.debug("Pre-market brief already sent for %s", session)
        return False

    try:
        from db import get_pro_users_with_telegram
        users = get_pro_users_with_telegram()
    except Exception:
        users = []

    any_sent = False
    for u in users:
        chat_id = u.get("telegram_chat_id", "")
        user_id = u.get("user_id")
        if not chat_id or not user_id:
            continue
        try:
            user_msg = _build_user_premarket(user_id)
            if not user_msg:
                continue
            ok = _send_telegram_to(user_msg, chat_id)
            if ok:
                any_sent = True
        except Exception:
            logger.debug("Pre-market brief failed for user %s", user_id)

    if any_sent:
        _brief_sent_date = session
        logger.info("Pre-market data brief sent for %s", session)
    return any_sent


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
        logger.info("AI premarket: no Pro users with Telegram — skipping")
        _ai_brief_sent_date = session
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

            analysis = build_ai_premarket_analysis(user_brief, user_id=user_id)
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


def generate_premarket_brief(symbols: list[str], user_id: int | None = None) -> str | None:
    """On-demand pre-market brief — called from the API endpoint.

    Returns the AI battle plan text for the given symbols and user.
    """
    if not symbols:
        return None

    # Build data brief for these specific symbols
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
        return "No pre-market data available for your watchlist symbols."

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

    data_brief = "\n".join(parts)

    # Generate AI analysis
    analysis = build_ai_premarket_analysis(data_brief, user_id=user_id)
    if analysis:
        return analysis

    # Fallback to raw data brief if AI fails
    return data_brief
