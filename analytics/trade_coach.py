"""AI Trade Coach — context assembly, prompt formatting, Claude streaming."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Generator

from alert_config import CLAUDE_MODEL

logger = logging.getLogger(__name__)

# Cache: (session_date, 5-min bucket) → context dict
_context_cache: dict[tuple[str, int], dict] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_call(fn, *args):
    """Call *fn* and return result, or None on any exception."""
    try:
        return fn(*args)
    except Exception:
        logger.exception("trade_coach: %s failed", getattr(fn, "__name__", fn))
        return None


def _resolve_api_key() -> str:
    """Reuse narrator's key resolution (per-user DB key → env var)."""
    from alerting.narrator import _resolve_api_key as _narrator_resolve
    return _narrator_resolve()


def _time_bucket() -> int:
    """5-minute bucket index for cache keying."""
    now = datetime.now()
    return (now.hour * 60 + now.minute) // 5


def _get_symbol_technicals(symbols: list[str]) -> dict[str, dict]:
    """Fetch key MAs + RSI for a list of symbols via yfinance.

    Returns {symbol: {close, ma50, ma100, ma200, ema20, ema50, ema100, ema200, rsi14}}.
    """
    import yfinance as yf
    import pandas as pd

    if not symbols:
        return {}

    result = {}
    try:
        data = yf.download(symbols, period="1y", group_by="ticker", progress=False)
    except Exception:
        logger.exception("trade_coach: yf.download failed")
        return {}

    for sym in symbols:
        try:
            if len(symbols) == 1:
                close = data["Close"].dropna()
            else:
                close = data[sym]["Close"].dropna()
            if close.empty or len(close) < 50:
                continue

            info: dict = {"close": round(float(close.iloc[-1]), 2)}
            for period in [50, 100, 200]:
                if len(close) >= period:
                    info[f"ma{period}"] = round(float(close.rolling(period).mean().iloc[-1]), 2)
            for span in [20, 50, 100, 200]:
                if len(close) >= span:
                    info[f"ema{span}"] = round(float(close.ewm(span=span, adjust=False).mean().iloc[-1]), 2)

            # RSI14 (Wilder's)
            if len(close) >= 15:
                delta = close.diff()
                gain = delta.clip(lower=0)
                loss = (-delta.clip(upper=0))
                avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean().iloc[-1]
                avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean().iloc[-1]
                if avg_loss > 0:
                    info["rsi14"] = round(100 - 100 / (1 + avg_gain / avg_loss), 1)

            result[sym] = info
        except Exception:
            logger.debug("trade_coach: technicals failed for %s", sym)
            continue

    return result


def _get_spy_hourly_bars(days: int = 2) -> list[dict]:
    """Fetch SPY hourly bars for the last N days via yfinance.

    Returns list of {time, open, high, low, close, volume} dicts.
    """
    import yfinance as yf

    hist = yf.Ticker("SPY").history(period=f"{days}d", interval="1h")
    if hist.empty:
        return []
    bars = []
    for ts, row in hist.iterrows():
        bars.append({
            "time": ts.strftime("%Y-%m-%d %H:%M"),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })
    return bars


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble_context() -> dict:
    """Gather trading context from existing DB functions. Cached 5 min."""
    session = date.today().isoformat()
    bucket = _time_bucket()
    cache_key = (session, bucket)

    if cache_key in _context_cache:
        return _context_cache[cache_key]

    # Lazy imports to avoid circular imports (same pattern as narrator.py)
    from alerting.real_trade_store import get_closed_trades, get_open_trades, get_real_trade_stats
    from alerting.options_trade_store import get_options_trade_stats
    from alerting.alert_store import get_session_dates, get_session_summary
    from analytics.intraday_data import get_spy_context
    from db import get_all_daily_plans

    # Find previous session date for "yesterday's alerts"
    prev_session = None
    session_dates = _safe_call(get_session_dates)
    if session_dates:
        past = [d for d in session_dates if d < session]
        if past:
            prev_session = past[0]  # most recent before today

    ctx = {
        "open_trades": _safe_call(get_open_trades),
        "recent_closed": _safe_call(get_closed_trades, 10),
        "trade_stats": _safe_call(get_real_trade_stats),
        "options_stats": _safe_call(get_options_trade_stats),
        "session_summary": _safe_call(get_session_summary, session),
        "prev_session_summary": _safe_call(get_session_summary, prev_session) if prev_session else None,
        "prev_session_date": prev_session,
        "spy_context": _safe_call(get_spy_context),
        "daily_plans": _safe_call(get_all_daily_plans, session),
    }

    # Collect symbols from watchlist + open trades for technical data
    symbols = set()
    symbols.add("SPY")
    if ctx["daily_plans"]:
        symbols.update(p["symbol"] for p in ctx["daily_plans"])
    if ctx["open_trades"]:
        symbols.update(t["symbol"] for t in ctx["open_trades"])

    technicals = _safe_call(_get_symbol_technicals, list(symbols))
    ctx["technicals"] = technicals or {}

    # Enrich SPY context with 100/200 MAs from technicals
    if ctx["spy_context"] is not None and "SPY" in ctx["technicals"]:
        spy_tech = ctx["technicals"]["SPY"]
        for key in ["ma100", "ma200", "ema100", "ema200"]:
            if key in spy_tech:
                ctx["spy_context"][key] = spy_tech[key]

    # SPY hourly bars (last 2 days) for intraday chart questions
    ctx["spy_hourly"] = _safe_call(_get_spy_hourly_bars, 2)

    _context_cache[cache_key] = ctx
    return ctx


def format_system_prompt(context: dict) -> str:
    """Build system prompt with embedded trading context."""
    sections: list[str] = []

    # Persona
    sections.append(
        "You are a sharp day-trading coach. Be extremely concise — 2-4 sentences max. "
        "Lead with key levels and action: 'Next support 679.62, resistance 685.53. "
        "Watch for bounce at 100 EMA — good entry if it holds.' "
        "Skip explanations the trader already knows. No filler, no preamble. "
        "Talk like a trading buddy on a desk, not a textbook. "
        "Reference actual data from the context sections below."
    )

    # Open positions
    trades = context.get("open_trades")
    if trades:
        lines = ["[OPEN POSITIONS]"]
        for t in trades:
            stop = t.get("stop_price") or "N/A"
            target = t.get("target_price") or "N/A"
            lines.append(
                f"- {t['symbol']} {t['direction']} {t.get('shares', '?')} shares "
                f"@ ${t['entry_price']:.2f}  stop={stop}  target={target}"
            )
        sections.append("\n".join(lines))

    # Performance stats
    stats = context.get("trade_stats")
    if stats and stats.get("total_trades", 0) > 0:
        lines = [
            "[PERFORMANCE]",
            f"Total P&L: ${stats['total_pnl']:.2f}",
            f"Win rate: {stats['win_rate']}%",
            f"Trades: {stats['total_trades']}",
            f"Expectancy: ${stats['expectancy']:.2f}",
            f"Avg win: ${stats['avg_win']:.2f}  Avg loss: ${stats['avg_loss']:.2f}",
        ]
        opts = context.get("options_stats")
        if opts and opts.get("total_trades", 0) > 0:
            lines.append(f"Options P&L: ${opts['total_pnl']:.2f} ({opts['total_trades']} trades)")
        sections.append("\n".join(lines))

    # Market regime
    spy = context.get("spy_context")
    if spy:
        lines = [
            "[MARKET REGIME]",
            f"SPY: ${spy.get('close', 0):.2f}  trend={spy.get('trend', 'unknown')}  regime={spy.get('regime', 'unknown')}",
        ]
        # Key MAs
        ma_parts = []
        for key, label in [("ma20", "20MA"), ("ma50", "50MA"),
                           ("ma100", "100MA"), ("ma200", "200MA"),
                           ("spy_ema20", "20EMA"), ("spy_ema50", "50EMA"),
                           ("ema100", "100EMA"), ("ema200", "200EMA")]:
            val = spy.get(key)
            if val:
                ma_parts.append(f"{label}=${val:.2f}")
        if ma_parts:
            lines.append("  ".join(ma_parts))
        if spy.get("spy_at_ma_support"):
            lines.append(f"SPY at MA support: {spy['spy_at_ma_support']}")
        if spy.get("spy_rsi14"):
            lines.append(f"RSI14: {spy['spy_rsi14']:.1f}")
        if spy.get("intraday_change_pct"):
            lines.append(f"Intraday change: {spy['intraday_change_pct']:.2f}%")
        sections.append("\n".join(lines))

    # SPY hourly bars
    spy_hourly = context.get("spy_hourly")
    if spy_hourly:
        lines = ["[SPY HOURLY BARS — last 2 days]"]
        for bar in spy_hourly:
            lines.append(
                f"{bar['time']}  O={bar['open']}  H={bar['high']}  "
                f"L={bar['low']}  C={bar['close']}  vol={bar['volume']:,}"
            )
        sections.append("\n".join(lines))

    # Daily plans (cap at 15, sorted by score desc)
    plans = context.get("daily_plans")
    if plans:
        sorted_plans = sorted(plans, key=lambda p: p.get("score", 0), reverse=True)[:15]
        lines = ["[TODAY'S WATCHLIST PLANS]"]
        for p in sorted_plans:
            lines.append(
                f"- {p['symbol']}  support={p.get('support', 'N/A')}  "
                f"entry={p.get('entry', 'N/A')}  stop={p.get('stop', 'N/A')}  "
                f"T1={p.get('target_1', 'N/A')}  score={p.get('score', '?')}"
                f"({p.get('score_label', '')})"
            )
        sections.append("\n".join(lines))

    # Symbol technicals (MAs, RSI for watchlist + open trades)
    technicals = context.get("technicals", {})
    if technicals:
        lines = ["[SYMBOL TECHNICALS]"]
        for sym in sorted(technicals.keys()):
            t = technicals[sym]
            parts = [f"{sym}: ${t['close']:.2f}"]
            for key, label in [("ma50", "50MA"), ("ma100", "100MA"), ("ma200", "200MA"),
                               ("ema20", "20EMA"), ("ema50", "50EMA"),
                               ("ema100", "100EMA"), ("ema200", "200EMA")]:
                if key in t:
                    parts.append(f"{label}=${t[key]:.2f}")
            if "rsi14" in t:
                parts.append(f"RSI={t['rsi14']:.1f}")
            lines.append("  ".join(parts))
        sections.append("\n".join(lines))

    # Session summary (today's alerts)
    summary = context.get("session_summary")
    if summary and summary.get("total", 0) > 0:
        lines = [
            "[TODAY'S ALERTS]",
            f"Total: {summary['total']}  BUY: {summary.get('buy_count', 0)}  "
            f"SELL: {summary.get('sell_count', 0)}",
        ]
        if summary.get("t1_hits", 0):
            lines.append(f"T1 hits: {summary['t1_hits']}")
        if summary.get("stopped_out", 0):
            lines.append(f"Stopped out: {summary['stopped_out']}")
        sections.append("\n".join(lines))

    # Previous session alerts (yesterday)
    prev = context.get("prev_session_summary")
    prev_date = context.get("prev_session_date", "previous session")
    if prev and prev.get("total", 0) > 0:
        lines = [
            f"[PREVIOUS SESSION ALERTS — {prev_date}]",
            f"Total: {prev['total']}  BUY: {prev.get('buy_count', 0)}  "
            f"SELL: {prev.get('sell_count', 0)}",
        ]
        if prev.get("t1_hits", 0):
            lines.append(f"T1 hits: {prev['t1_hits']}")
        if prev.get("stopped_out", 0):
            lines.append(f"Stopped out: {prev['stopped_out']}")
        # Include individual alert details
        prev_alerts = prev.get("alerts", [])
        for a in prev_alerts[:15]:
            lines.append(
                f"- {a.get('symbol', '?')} {a.get('direction', '?')} "
                f"{a.get('alert_type', '').replace('_', ' ')}  "
                f"score={a.get('score', '?')}  price=${a.get('price', 0):.2f}"
            )
        sections.append("\n".join(lines))

    # Recent closed trades
    closed = context.get("recent_closed")
    if closed:
        lines = ["[RECENT CLOSED TRADES]"]
        for t in closed[:10]:
            pnl = t.get("pnl", 0)
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            lines.append(f"- {t['symbol']}  P&L: {pnl_str}  status={t.get('status', 'closed')}")
        sections.append("\n".join(lines))

    # Rules
    sections.append(
        "[RULES]\n"
        "- 2-4 sentences max. Lead with levels and action.\n"
        "- Use probability language, never guarantee outcomes\n"
        "- Call out overexposure if 3+ open positions\n"
        "- Say 'not enough data' if context is missing\n"
        "- No markdown formatting — plain text only"
    )

    return "\n\n".join(sections)


def ask_coach(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 768,
) -> Generator[str, None, None]:
    """Send conversation to Claude, yield streamed text chunks.

    Raises ValueError if no API key is configured.
    """
    api_key = _resolve_api_key()
    if not api_key:
        raise ValueError(
            "No Anthropic API key configured. Set ANTHROPIC_API_KEY in "
            "environment or add it in Settings."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk
