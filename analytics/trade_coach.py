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
                sym_data = data
            else:
                sym_data = data[sym]
            close = sym_data["Close"].dropna()
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

            # Prior day high/low (PDH/PDL) — critical key levels
            # For crypto: use Coinbase via fetch_prior_day (yfinance drops daily bars)
            try:
                _is_crypto = sym.endswith("-USD")
                if _is_crypto:
                    from analytics.intraday_data import fetch_prior_day as _fpd
                    _pd = _fpd(sym, is_crypto=True)
                    if _pd:
                        info["pdh"] = round(float(_pd["high"]), 2)
                        info["pdl"] = round(float(_pd["low"]), 2)
                else:
                    highs = sym_data["High"].dropna()
                    lows = sym_data["Low"].dropna()
                    if len(highs) >= 2 and len(lows) >= 2:
                        info["pdh"] = round(float(highs.iloc[-2]), 2)
                        info["pdl"] = round(float(lows.iloc[-2]), 2)
            except Exception:
                pass

            # Weekly high/low (prior completed week)
            try:
                highs = sym_data["High"].dropna()
                lows = sym_data["Low"].dropna()
                if not highs.empty and not lows.empty:
                    weekly = pd.DataFrame({"High": highs, "Low": lows}).resample("W-FRI").agg({
                        "High": "max", "Low": "min",
                    })
                    if len(weekly) >= 2:
                        last_bar_date = close.index[-1].normalize()
                        last_weekly_date = weekly.index[-1].normalize()
                        pw = weekly.iloc[-2] if last_bar_date <= last_weekly_date else weekly.iloc[-1]
                        info["prior_week_high"] = round(float(pw["High"]), 2)
                        info["prior_week_low"] = round(float(pw["Low"]), 2)
            except Exception:
                pass  # weekly levels are best-effort

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

def assemble_context(hub_symbol: str | None = None) -> dict:
    """Gather trading context from existing DB functions. Cached 5 min.

    If *hub_symbol* is provided, also gathers hub-specific context
    (fundamentals, S/R levels, weekly trend, win rates) via intel_hub.
    """
    session = date.today().isoformat()
    bucket = _time_bucket()
    cache_key = (session, bucket)

    if cache_key in _context_cache:
        return _context_cache[cache_key]

    # Lazy imports to avoid circular imports (same pattern as narrator.py)
    from alerting.real_trade_store import get_closed_trades, get_open_trades, get_real_trade_stats
    from alerting.options_trade_store import get_options_trade_stats
    from alerting.alert_store import get_alerts_today, get_session_dates, get_session_summary
    from analytics.intraday_data import get_spy_context
    from db import get_all_daily_plans

    # Find previous session date for "yesterday's alerts"
    prev_session = None
    session_dates = _safe_call(get_session_dates)
    if session_dates:
        past = [d for d in session_dates if d < session]
        if past:
            prev_session = past[0]  # most recent before today

    from alerting.paper_trader import (
        get_open_paper_trades_for_coach,
        get_closed_paper_trades_for_coach,
        get_paper_trade_stats,
    )

    ctx = {
        "open_trades": _safe_call(get_open_trades),
        "recent_closed": _safe_call(get_closed_trades, 10),
        "trade_stats": _safe_call(get_real_trade_stats),
        "options_stats": _safe_call(get_options_trade_stats),
        "session_summary": _safe_call(get_session_summary, session),
        "today_alerts": _safe_call(get_alerts_today, session),
        "prev_session_summary": _safe_call(get_session_summary, prev_session) if prev_session else None,
        "prev_session_date": prev_session,
        "spy_context": _safe_call(get_spy_context),
        "daily_plans": _safe_call(get_all_daily_plans, session),
        "paper_open": _safe_call(get_open_paper_trades_for_coach),
        "paper_closed": _safe_call(get_closed_paper_trades_for_coach, 10),
        "paper_stats": _safe_call(get_paper_trade_stats),
    }

    # Collect symbols from watchlist + open trades for technical data
    symbols = set()
    symbols.add("SPY")
    if ctx["daily_plans"]:
        symbols.update(p["symbol"] for p in ctx["daily_plans"])
    if ctx["open_trades"]:
        symbols.update(t["symbol"] for t in ctx["open_trades"])
    if ctx["paper_open"]:
        symbols.update(t["symbol"] for t in ctx["paper_open"])

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

    # ACK history — decision quality and recent journal entries
    try:
        from analytics.intel_hub import get_decision_quality, get_trading_journal
        # Get admin uid (same as monitor.py pattern)
        from db import get_db
        with get_db() as conn:
            _row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
            _uid = _row["id"] if _row else 1
        ctx["decision_quality"] = _safe_call(get_decision_quality, _uid, 90)
        ctx["ack_journal"] = _safe_call(get_trading_journal, _uid, 30)
    except Exception:
        logger.debug("trade_coach: ACK history failed")

    # Win rates by alert type and by symbol (for rule-specific coaching)
    try:
        from analytics.intel_hub import get_alert_win_rates
        wr = _safe_call(get_alert_win_rates, 90)
        if wr:
            ctx["win_rates_by_type"] = wr.get("by_alert_type", {})
            ctx["win_rates_by_symbol"] = wr.get("by_symbol", {})
    except Exception:
        logger.debug("trade_coach: win rates failed")

    # Hub-specific context for focused symbol analysis
    if hub_symbol:
        try:
            from analytics.intel_hub import assemble_hub_context
            ctx["hub"] = assemble_hub_context(hub_symbol)
        except Exception:
            logger.debug("trade_coach: hub context failed for %s", hub_symbol)

    _context_cache[cache_key] = ctx
    return ctx


def format_system_prompt(context: dict) -> str:
    """Build system prompt with embedded trading context."""
    sections: list[str] = []

    # Persona
    hub = context.get("hub")
    _coach_prompt = (
        "You are a trading analyst. Be extremely brief.\n\n"
        "FORMAT (plain text, no markdown):\n\n"
        "CHART READ: 1 short sentence.\n\n"
        "ACTION:\n"
        "Direction: LONG / SHORT / WAIT\n"
        "Entry: $price — level name\n"
        "Stop: $price | T1: $price | T2: $price\n\n"
        "STRICT RULES:\n"
        "- MAXIMUM 50 WORDS TOTAL. No exceptions.\n"
        "- No explanations, no commentary, no context, no disclaimers.\n"
        "- Just CHART READ + ACTION. Nothing else.\n"
        "- Prices from the data only. Plain text. No markdown.\n"
        "- PDH = yesterday's high, PDL = yesterday's low. Do not confuse with today's levels."
    )
    if hub:
        sections.append(_coach_prompt)
    else:
        sections.append(_coach_prompt)

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

    # User's current chart bars (from frontend — the exact chart they're looking at)
    user_bars = context.get("user_chart_bars")
    user_tf = context.get("user_chart_timeframe", "")
    if user_bars:
        _tf_label = user_tf if user_tf else "chart"
        _sym = hub.get("symbol", "") if hub else ""
        lines = [f"[CHART DATA — {_sym} {_tf_label} — LAST {len(user_bars)} BARS (what the user sees right now)]"]
        for bar in user_bars:
            lines.append(
                f"{bar['time']}  O={bar['open']}  H={bar['high']}  "
                f"L={bar['low']}  C={bar['close']}  vol={bar['volume']:,}"
            )
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
            # PDH/PDL — CRITICAL: these are YESTERDAY's high/low, not today's
            if "pdh" in t:
                parts.append(f"PDH(yesterday high)=${t['pdh']:.2f}")
            if "pdl" in t:
                parts.append(f"PDL(yesterday low)=${t['pdl']:.2f}")
            for key, label in [("ma50", "50MA"), ("ma100", "100MA"), ("ma200", "200MA"),
                               ("ema20", "20EMA"), ("ema50", "50EMA"),
                               ("ema100", "100EMA"), ("ema200", "200EMA")]:
                if key in t:
                    parts.append(f"{label}=${t[key]:.2f}")
            if "rsi14" in t:
                parts.append(f"RSI={t['rsi14']:.1f}")
            if "prior_week_high" in t:
                parts.append(f"WeekHi=${t['prior_week_high']:.2f}")
            if "prior_week_low" in t:
                parts.append(f"WeekLo=${t['prior_week_low']:.2f}")
            lines.append("  ".join(parts))
        sections.append("\n".join(lines))

    # Session summary + individual alerts (today)
    summary = context.get("session_summary")
    today_alerts = context.get("today_alerts") or []
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
        for a in today_alerts[:20]:
            score = a.get("score") or "?"
            conf = a.get("confidence") or ""
            msg = a.get("message") or ""
            price = a.get("price") or 0
            entry = a.get("entry") or 0
            stop = a.get("stop") or 0
            t1 = a.get("target_1") or 0
            t2 = a.get("target_2") or 0
            # Truncate message to keep prompt compact
            if len(msg) > 120:
                msg = msg[:120] + "..."
            # Score factor breakdown if available
            _sf = a.get("score_factors") or {}
            _sf_str = ""
            if _sf:
                _fl = {"ma": "MA", "vol": "Vol", "conf": "Conf", "vwap": "VWAP",
                       "rr": "R:R", "confluence": "Cnfl", "mtf": "MTF"}
                _sf_str = "  factors={" + ",".join(f"{_fl.get(k,k)}:{v}" for k, v in _sf.items() if v) + "}"
            lines.append(
                f"- {a.get('symbol', '?')} {a.get('direction', '?')} "
                f"{(a.get('alert_type') or '').replace('_', ' ')}  "
                f"score={score} conf={conf}  price=${price:.2f}  "
                f"entry=${entry:.2f}  stop=${stop:.2f}  "
                f"T1=${t1:.2f}  T2=${t2:.2f}"
                + _sf_str
                + (f"  [{msg}]" if msg else "")
            )
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
            pnl = t.get("pnl") or 0
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            lines.append(f"- {t['symbol']}  P&L: {pnl_str}  status={t.get('status', 'closed')}")
        sections.append("\n".join(lines))

    # Paper trading: REMOVED from Coach context — not used, adds noise and
    # confuses AI into mentioning positions that don't exist for the user.

    # Hub context (when user is focused on a specific symbol)
    hub = context.get("hub")
    if hub:
        hub_sym = hub.get("symbol", "")

        # Fundamentals
        fnd = hub.get("fundamentals")
        if fnd:
            lines = [f"[SYMBOL FUNDAMENTALS — {hub_sym}]"]
            if fnd.get("pe"):
                lines.append(f"PE: {fnd['pe']:.1f}")
            if fnd.get("forward_pe"):
                lines.append(f"Forward PE: {fnd['forward_pe']:.1f}")
            if fnd.get("market_cap_fmt"):
                lines.append(f"Market Cap: {fnd['market_cap_fmt']}")
            if fnd.get("sector"):
                lines.append(f"Sector: {fnd['sector']}")
            if fnd.get("beta"):
                lines.append(f"Beta: {fnd['beta']:.2f}")
            if fnd.get("earnings_date"):
                lines.append(f"Next Earnings: {fnd['earnings_date']}")
            if fnd.get("dividend_yield"):
                lines.append(f"Div Yield: {fnd['dividend_yield']:.2%}")
            sections.append("\n".join(lines))

        # S/R levels (top 10)
        sr = hub.get("sr_levels")
        if sr:
            lines = [f"[KEY S/R LEVELS — {hub_sym}]"]
            for lvl in sr[:10]:
                lines.append(
                    f"- ${lvl['level']:.2f} {lvl['label']} ({lvl['type']}) "
                    f"dist={lvl['distance_pct']:+.2f}%"
                )
            sections.append("\n".join(lines))

        # Weekly trend
        wt = hub.get("weekly_trend")
        if wt:
            lines = [f"[WEEKLY TREND — {hub_sym}]"]
            lines.append(f"Direction: {wt.get('direction', 'unknown')}")
            if wt.get("close"):
                lines.append(f"Weekly close: ${wt['close']:.2f}")
            for key in ("wma10", "wma20", "wma50"):
                if key in wt:
                    lines.append(f"{key.upper()}: ${wt[key]:.2f}")
            sections.append("\n".join(lines))

        # Win rates
        wr = hub.get("win_rates")
        if wr:
            lines = [f"[HISTORICAL WIN RATES — {hub_sym}]"]
            sym_wr = wr.get("symbol")
            if sym_wr:
                lines.append(
                    f"{hub_sym}: {sym_wr['win_rate']}% "
                    f"({sym_wr['wins']}W/{sym_wr['losses']}L/{sym_wr['unknown']}U)"
                )
            overall = wr.get("overall", {})
            if overall:
                lines.append(
                    f"Overall: {overall.get('win_rate', 0)}% "
                    f"({overall.get('total', 0)} signals)"
                )
            sections.append("\n".join(lines))

    # Win rates by alert type (rule-specific coaching)
    wr_by_type = context.get("win_rates_by_type", {})
    if wr_by_type:
        # Show top performers and worst performers
        _typed = [(k, v) for k, v in wr_by_type.items() if v.get("total", 0) >= 3]
        if _typed:
            _typed.sort(key=lambda x: x[1].get("win_rate", 0), reverse=True)
            lines = ["[WIN RATES BY ALERT TYPE — 90 DAYS (min 3 signals)]"]
            for name, wr in _typed[:15]:
                label = name.replace("_", " ")
                lines.append(
                    f"- {label}: {wr['win_rate']}% "
                    f"({wr['wins']}W/{wr['losses']}L/{wr.get('unknown', 0)}U of {wr['total']})"
                )
            sections.append("\n".join(lines))

    # Win rates by symbol
    wr_by_sym = context.get("win_rates_by_symbol", {})
    if wr_by_sym:
        _symd = [(k, v) for k, v in wr_by_sym.items() if v.get("total", 0) >= 3]
        if _symd:
            _symd.sort(key=lambda x: x[1].get("win_rate", 0), reverse=True)
            lines = ["[WIN RATES BY SYMBOL — 90 DAYS (min 3 signals)]"]
            for sym, wr in _symd[:15]:
                lines.append(
                    f"- {sym}: {wr['win_rate']}% "
                    f"({wr['wins']}W/{wr['losses']}L of {wr['total']})"
                )
            sections.append("\n".join(lines))

    # ACK decision history
    dq = context.get("decision_quality")
    if dq:
        took = dq.get("took", {})
        skipped = dq.get("skipped", {})
        if took.get("total", 0) > 0 or skipped.get("total", 0) > 0:
            lines = ["[TRADE DECISION QUALITY — 90 DAYS]"]
            if took.get("total", 0) > 0:
                lines.append(
                    f"Took: {took['total']} trades, {took['win_rate']}% win rate "
                    f"({took['wins']}W/{took['losses']}L)"
                )
            if skipped.get("total", 0) > 0:
                lines.append(
                    f"Skipped: {skipped['total']} alerts, {skipped['win_rate']}% would have won "
                    f"({skipped['wins']}W/{skipped['losses']}L)"
                )
            edge = dq.get("decision_edge")
            if edge is not None:
                if edge > 0:
                    lines.append(f"Decision edge: +{edge}% (good filtering — took better trades)")
                elif edge < 0:
                    lines.append(f"Decision edge: {edge}% (skipped trades did better)")
                else:
                    lines.append("Decision edge: 0% (same performance)")
            sections.append("\n".join(lines))

    ack_journal = context.get("ack_journal")
    if ack_journal:
        lines = ["[RECENT TRADE DECISIONS — LAST 30 DAYS]"]
        for entry in ack_journal[:15]:
            action = entry["user_action"]
            sym = entry["symbol"]
            setup = entry["alert_type"].replace("_", " ")
            outcome = entry.get("outcome", "open")
            pnl = entry.get("pnl")
            pnl_str = f" PnL={pnl:+.2f}" if pnl is not None else ""
            lines.append(f"- {sym} {setup}: {action.upper()} → {outcome}{pnl_str}")
        sections.append("\n".join(lines))

        # --- Behavioral pattern analysis (derived from journal) ---
        took_by_type: dict[str, dict] = {}
        skipped_by_type: dict[str, dict] = {}
        for entry in ack_journal:
            atype = entry["alert_type"].replace("_", " ")
            outcome = entry.get("outcome", "open")
            bucket = took_by_type if entry["user_action"] == "took" else skipped_by_type
            if atype not in bucket:
                bucket[atype] = {"total": 0, "wins": 0, "losses": 0}
            bucket[atype]["total"] += 1
            if outcome == "win":
                bucket[atype]["wins"] += 1
            elif outcome == "loss":
                bucket[atype]["losses"] += 1

        behavior_lines = ["[BEHAVIORAL PATTERNS — COACHING INSIGHTS]"]
        has_insights = False

        # Find rules user skips that actually win
        for atype, stats in skipped_by_type.items():
            if stats["total"] >= 2 and stats["wins"] > stats["losses"]:
                wr = round(stats["wins"] / stats["total"] * 100)
                behavior_lines.append(
                    f"- MISSED EDGE: You skip '{atype}' alerts but they win {wr}% "
                    f"({stats['wins']}W/{stats['losses']}L of {stats['total']}) — consider trusting this setup more"
                )
                has_insights = True

        # Find rules user takes that consistently lose
        for atype, stats in took_by_type.items():
            if stats["total"] >= 2 and stats["losses"] > stats["wins"]:
                wr = round(stats["wins"] / stats["total"] * 100)
                behavior_lines.append(
                    f"- LEAK: You take '{atype}' alerts but they win only {wr}% "
                    f"({stats['wins']}W/{stats['losses']}L of {stats['total']}) — add filters or reduce size"
                )
                has_insights = True

        # Find rules user takes that win well
        for atype, stats in took_by_type.items():
            if stats["total"] >= 3 and stats["wins"] > 0:
                wr = round(stats["wins"] / stats["total"] * 100)
                if wr >= 60:
                    behavior_lines.append(
                        f"- STRENGTH: '{atype}' is your best setup at {wr}% win rate "
                        f"({stats['wins']}W/{stats['losses']}L) — lean into this"
                    )
                    has_insights = True

        if has_insights:
            sections.append("\n".join(behavior_lines))

    # Rules
    if hub:
        sections.append(
            "[RULES]\n"
            "- Structure responses with markdown: headers, bold, bullets\n"
            "- NEVER use the $ character for dollar amounts — write '150.25' or 'USD 150.25' instead\n"
            "- Lead with trade thesis, then key levels, then supporting data\n"
            "- Use probability language, never guarantee outcomes\n"
            "- Call out overexposure if 3+ open positions\n"
            "- Say 'not enough data' if context is missing\n"
            "- Keep responses focused but thorough (5-15 lines)"
        )
    else:
        sections.append(
            "[RULES]\n"
            "- 2-4 sentences max. Lead with levels and action.\n"
            "- NEVER use the $ character — write dollar amounts as plain numbers\n"
            "- Use probability language, never guarantee outcomes\n"
            "- Call out overexposure if 3+ open positions\n"
            "- Say 'not enough data' if context is missing\n"
            "- No markdown formatting — plain text only"
        )

    return "\n\n".join(sections)


def ask_coach(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 256,
    model: str | None = None,
) -> Generator[str, None, None]:
    """Send conversation to Claude, yield streamed text chunks.

    *model* overrides the default CLAUDE_MODEL (e.g., Sonnet for Pro/Elite).

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
    use_model = model or CLAUDE_MODEL

    # Use prompt caching for system prompt — it rarely changes mid-session
    # This reduces cost by ~90% on repeated queries for the same symbol
    system_with_cache = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    with client.messages.stream(
        model=use_model,
        max_tokens=max_tokens,
        system=system_with_cache,
        messages=messages,
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk
