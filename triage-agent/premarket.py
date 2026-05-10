"""Premarket sector-breadth brief.

Runs daily at 8:30 AM ET. Fetches premarket prices for indices, sector ETFs,
and the user's watchlist. Computes per-sector breadth (% positive, magnitude).
Picks focus / avoid sectors. Picks top stocks. Polishes with an LLM call that
reads news + earnings catalysts + macro calendar. Sends to Telegram.

Output format mirrors:

    📊 Premarket Heat — Fri 8:30 AM ET
    Tape:  SPY +0.3%  QQQ +1.0%  IWM +0.5%  DIA -0.3%  VIX 17.0
           XLK +1.5%  XLE -1.3%  XLF -0.4%  XLV -0.6%  ...
    ▲ Optics       +6.7%   3/3   AAOI +11.7%
    ▲ Memory       +6.5%   2/2   SNDK +8.2%
    ─ Chips        +0.4%   3/5
    ▼ Power        -1.4%   0/5   OKLO -2.9%

    Focus: Optics, Memory, BTC, Cloud (longs)
    Avoid: Power (red breadth)

    Top picks:
      AAOI ($X) — Optics +11.7% · 3.2× vol · setup at $Y
      SNDK ($X) — Memory +8.2% · ...
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf
from anthropic import Anthropic

logger = logging.getLogger("triage.premarket")

DATABASE_URL    = os.environ.get("DATABASE_URL")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TRIAGE_USER_ID  = int(os.environ.get("TRIAGE_USER_ID", "3"))
PICKS_FILE      = Path(os.environ.get("PREMARKET_PICKS_FILE", "/data/premarket-picks.json"))
LLM_TIER        = os.environ.get("PREMARKET_LLM_TIER", "heavy")  # minimal | standard | heavy

# Standard market context — always fetched for the tape line
INDICES        = ["SPY", "QQQ", "IWM", "DIA"]
VIX_SYMBOL     = "^VIX"  # yfinance symbol for VIX
SECTOR_ETFS    = ["XLK", "XLE", "XLF", "XLV", "XLY", "XLI", "XLB", "XLU", "XLP", "XLRE", "XLC"]


# ──────────────────────────────────────────────────────────────────
# DATA FETCH
# ──────────────────────────────────────────────────────────────────

@dataclass
class PriceMove:
    symbol: str
    last_close: float
    premarket_price: float
    pct_change: float
    volume: int
    avg_volume: float
    rel_volume: float


def fetch_premarket(symbols: list[str]) -> dict[str, PriceMove]:
    """yfinance bulk fetch of premarket data. Returns symbol → PriceMove."""
    if not symbols:
        return {}

    out: dict[str, PriceMove] = {}
    # yfinance's pre/post market data is in info["regularMarketPrice"] vs
    # info["preMarketPrice"]. For sector ETFs and stocks, use the 1d/1m prepost
    # download approach; falls back gracefully when unavailable.
    try:
        # Bulk fetch quotes — fast for many tickers at once
        tickers = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            try:
                t = tickers.tickers.get(sym)
                if t is None:
                    continue
                info = getattr(t, "info", {}) or {}
                last_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
                pre        = info.get("preMarketPrice") or info.get("postMarketPrice")
                # If premarket isn't available (off-hours, illiquid), use regular price
                if pre is None:
                    pre = info.get("regularMarketPrice")
                if last_close is None or pre is None:
                    continue
                volume     = info.get("regularMarketVolume", 0) or 0
                avg_vol    = info.get("averageDailyVolume10Day", 0) or info.get("averageVolume", 1) or 1
                rel_vol    = (volume / avg_vol) if avg_vol else 0.0
                pct_change = (pre - last_close) / last_close * 100.0 if last_close else 0.0

                out[sym] = PriceMove(
                    symbol=sym,
                    last_close=float(last_close),
                    premarket_price=float(pre),
                    pct_change=float(pct_change),
                    volume=int(volume),
                    avg_volume=float(avg_vol),
                    rel_volume=float(rel_vol),
                )
            except Exception as e:
                logger.warning("fetch_premarket: failed for %s: %s", sym, e)
                continue
    except Exception:
        logger.exception("fetch_premarket: bulk fetch failed; falling back per-symbol")
        # Fallback: one-by-one
        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                info = t.info or {}
                last = info.get("regularMarketPreviousClose")
                pre  = info.get("preMarketPrice") or info.get("regularMarketPrice")
                if last is None or pre is None:
                    continue
                out[sym] = PriceMove(
                    symbol=sym,
                    last_close=float(last),
                    premarket_price=float(pre),
                    pct_change=(pre - last) / last * 100.0,
                    volume=info.get("regularMarketVolume", 0) or 0,
                    avg_volume=info.get("averageVolume", 1) or 1,
                    rel_volume=0.0,
                )
            except Exception as e:
                logger.warning("fetch_premarket fallback: failed for %s: %s", sym, e)
    return out


def fetch_news_for(symbols: list[str], max_per_symbol: int = 3) -> dict[str, list[dict]]:
    """Pull recent news headlines per symbol via yfinance. Heavy LLM tier uses this."""
    out = {}
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            news = (t.news or [])[:max_per_symbol]
            out[sym] = [{
                "title": n.get("title"),
                "publisher": n.get("publisher"),
                "publish_time": n.get("providerPublishTime"),
                "summary": n.get("summary", "")[:500],
            } for n in news if n.get("title")]
        except Exception as e:
            logger.debug("fetch_news_for %s: %s", sym, e)
            out[sym] = []
    return out


# ──────────────────────────────────────────────────────────────────
# WATCHLIST + SECTOR LOADING
# ──────────────────────────────────────────────────────────────────

def load_watchlist_groups(user_id: int) -> dict[str, list[str]]:
    """Returns {group_name: [symbols]} for the user's watchlist."""
    out: dict[str, list[str]] = {}
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT g.name AS group_name, w.symbol
                FROM watchlist w
                LEFT JOIN watchlist_group g ON g.id = w.group_id
                WHERE w.user_id = %s
                ORDER BY g.sort_order NULLS LAST, w.symbol
            """, (user_id,))
            for r in cur.fetchall():
                gname = r["group_name"] or "(ungrouped)"
                out.setdefault(gname, []).append(r["symbol"])
    return out


def load_recent_alerts_setups(user_id: int, lookback_hours: int = 24) -> dict[str, dict]:
    """Returns {symbol: latest_alert_setup} for stocks with recent Pine alerts.
    Used to mark stocks as 'tradeable' (entry/stop/T1 already defined)."""
    out = {}
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT ON (symbol)
                    symbol, alert_type, direction, entry, stop, target_1,
                    confidence, volume_ratio, cvd_diverging, created_at
                FROM alerts
                WHERE user_id = %s
                  AND created_at > NOW() - INTERVAL '%s hours'
                ORDER BY symbol, created_at DESC
            """, (user_id, lookback_hours))
            for r in cur.fetchall():
                out[r["symbol"]] = dict(r)
    return out


# ──────────────────────────────────────────────────────────────────
# SECTOR BREADTH + RANKING
# ──────────────────────────────────────────────────────────────────

@dataclass
class SectorBreadth:
    name: str
    symbols: list[str]
    moves: list[PriceMove]   # only those with data
    avg_pct: float
    pct_positive: float       # 0.0 to 1.0
    n_positive: int
    n_total: int
    top_mover: Optional[PriceMove]
    bottom_mover: Optional[PriceMove]


def compute_sector_breadth(
    groups: dict[str, list[str]],
    quotes: dict[str, PriceMove],
) -> list[SectorBreadth]:
    """For each sector, compute breadth metrics. Skip Macro group (handled separately)."""
    out = []
    for gname, syms in groups.items():
        if gname.lower() == "macro":
            continue  # macro is rendered as the tape line, not a sector row
        moves = [quotes[s] for s in syms if s in quotes]
        if not moves:
            continue
        avg_pct = sum(m.pct_change for m in moves) / len(moves)
        n_positive = sum(1 for m in moves if m.pct_change > 0)
        n_total = len(moves)
        pct_positive = n_positive / n_total if n_total else 0
        top_mover = max(moves, key=lambda m: m.pct_change)
        bottom_mover = min(moves, key=lambda m: m.pct_change)
        out.append(SectorBreadth(
            name=gname, symbols=syms, moves=moves,
            avg_pct=avg_pct, pct_positive=pct_positive,
            n_positive=n_positive, n_total=n_total,
            top_mover=top_mover, bottom_mover=bottom_mover,
        ))
    out.sort(key=lambda s: s.avg_pct, reverse=True)
    return out


def classify_sector(s: SectorBreadth) -> str:
    """Return 'bullish' / 'bearish' / 'neutral' classification."""
    if s.avg_pct >= 1.0 and s.pct_positive >= 0.6:
        return "bullish"
    if s.avg_pct <= -1.0 and s.pct_positive <= 0.4:
        return "bearish"
    return "neutral"


def pick_focus_avoid(breadths: list[SectorBreadth]) -> tuple[list[SectorBreadth], list[SectorBreadth]]:
    """Focus = top bullish sectors. Avoid = clear bearish sectors."""
    focus = [s for s in breadths if classify_sector(s) == "bullish"][:4]
    avoid = [s for s in breadths if classify_sector(s) == "bearish"]
    return focus, avoid


# ──────────────────────────────────────────────────────────────────
# STOCK PICKING
# ──────────────────────────────────────────────────────────────────

def composite_score(
    move: PriceMove,
    has_alert_setup: bool,
    confidence: Optional[str],
    cvd_diverging: bool,
) -> float:
    """Composite score for ranking actionable stocks within focus sectors.

    score = (pct_change) × (rel_volume bonus) × (alert_setup bonus) × (cvd bonus)
    """
    score = abs(move.pct_change)  # raw move magnitude

    # Relative volume bonus (capped — diminishing returns above 3x)
    rel_v = move.rel_volume or 1.0
    score *= min(2.0, max(0.5, rel_v / 1.5))  # 0.5x at vol=0.75x; 2x at vol=3x+

    # Setup bonus — stocks with defined entry/stop/T1 are immediately tradeable
    if has_alert_setup:
        score *= 1.5

    # Confidence bonus
    if confidence == "high":
        score *= 1.3
    elif confidence == "medium":
        score *= 1.1

    # CVD divergence bonus
    if cvd_diverging:
        score *= 1.2

    return score


def pick_top_stocks(
    focus_sectors: list[SectorBreadth],
    setups: dict[str, dict],
    n: int = 4,
) -> list[dict]:
    """Pick top-N actionable stocks across focus sectors."""
    candidates = []
    for sec in focus_sectors:
        for move in sec.moves:
            if move.pct_change < 0:
                continue  # focus sectors are bullish; skip negative movers
            setup = setups.get(move.symbol)
            score = composite_score(
                move,
                has_alert_setup=bool(setup),
                confidence=setup.get("confidence") if setup else None,
                cvd_diverging=bool(setup.get("cvd_diverging")) if setup else False,
            )
            candidates.append({
                "symbol":      move.symbol,
                "sector":      sec.name,
                "pct_change":  move.pct_change,
                "rel_volume":  move.rel_volume,
                "premarket_price": move.premarket_price,
                "score":       score,
                "setup":       setup,
            })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:n]


# ──────────────────────────────────────────────────────────────────
# FORMATTING (the brief itself)
# ──────────────────────────────────────────────────────────────────

def _arrow(pct: float) -> str:
    if pct >= 1.5:  return "▲"
    if pct <= -1.5: return "▼"
    return "─"


def _pad(s: str, width: int) -> str:
    return f"{s:<{width}}"


def format_tape_line(quotes: dict[str, PriceMove]) -> str:
    """Indices + sector ETF tape line."""
    parts = []
    for s in INDICES:
        if s in quotes:
            parts.append(f"{s} {quotes[s].pct_change:+.1f}%")
    if VIX_SYMBOL in quotes:
        parts.append(f"VIX {quotes[VIX_SYMBOL].premarket_price:.1f}")
    elif "VIX" in quotes:
        parts.append(f"VIX {quotes['VIX'].premarket_price:.1f}")
    line1 = "Tape: " + "  ".join(parts)

    etf_parts = []
    for s in SECTOR_ETFS:
        if s in quotes:
            etf_parts.append(f"{s} {quotes[s].pct_change:+.1f}%")
    line2 = "      " + "  ".join(etf_parts)

    return line1 + "\n" + line2


def format_sector_row(s: SectorBreadth) -> str:
    arrow = _arrow(s.avg_pct)
    sec_pad = _pad(s.name, 12)
    pct_str = f"{s.avg_pct:+.1f}%"
    breadth_str = f"{s.n_positive}/{s.n_total}"
    if s.top_mover and s.avg_pct > 0:
        top = f"  {s.top_mover.symbol} {s.top_mover.pct_change:+.1f}%"
    elif s.bottom_mover and s.avg_pct < 0:
        top = f"  {s.bottom_mover.symbol} {s.bottom_mover.pct_change:+.1f}%"
    else:
        top = ""
    return f"{arrow} {sec_pad} {pct_str:>7}   {breadth_str}{top}"


def format_picks(picks: list[dict]) -> str:
    if not picks:
        return ""
    lines = ["", "Top picks:"]
    for p in picks:
        sym       = p["symbol"]
        sector    = p["sector"]
        pct       = p["pct_change"]
        price     = p["premarket_price"]
        rel_vol   = p["rel_volume"]
        setup     = p.get("setup")
        setup_str = ""
        if setup:
            entry = setup.get("entry")
            if entry:
                setup_str = f" · setup ${entry:.2f}"
        rv_str = f"{rel_vol:.1f}× vol" if rel_vol else "vol n/a"
        lines.append(f"  {sym} (${price:.2f}) — {sector} {pct:+.1f}% · {rv_str}{setup_str}")
    return "\n".join(lines)


def build_premarket_brief(
    quotes: dict[str, PriceMove],
    breadths: list[SectorBreadth],
    focus: list[SectorBreadth],
    avoid: list[SectorBreadth],
    picks: list[dict],
    polish: Optional[str],
    now: datetime,
) -> str:
    et_str = now.strftime("%a %-I:%M %p ET") if hasattr(now, "strftime") else str(now)
    parts = [f"📊 <b>Premarket Heat</b> — {et_str}", ""]
    parts.append(format_tape_line(quotes))
    parts.append("")
    for s in breadths:
        parts.append(format_sector_row(s))
    parts.append("")

    if focus:
        focus_names = ", ".join(s.name for s in focus)
        parts.append(f"<b>Focus:</b> {focus_names} (longs)")
    if avoid:
        avoid_names = ", ".join(s.name for s in avoid)
        parts.append(f"<b>Avoid:</b> {avoid_names} (red breadth)")
    parts.append(format_picks(picks))

    if polish:
        parts.append("")
        parts.append("🤖 " + polish)

    return "\n".join(parts)[:4000]


# ──────────────────────────────────────────────────────────────────
# LLM POLISH (heavy tier)
# ──────────────────────────────────────────────────────────────────

POLISH_PROMPT = """You are a trading-desk analyst writing a one-paragraph premarket brief.
You'll be given:
- Sector breadth data (bullish / bearish / neutral classification)
- Top stock picks with sector, % move, volume
- News headlines for top movers
- Macro / earnings calendar context

Write a tight 2-4 sentence brief explaining WHY today's setup looks the way it does.
Cite catalysts (earnings, news, macro events) by name when they explain the move.
Don't restate the numbers — they're already in the brief above. Add reasoning, not summary.
"""


def polish_with_llm(
    quotes: dict[str, PriceMove],
    breadths: list[SectorBreadth],
    focus: list[SectorBreadth],
    avoid: list[SectorBreadth],
    picks: list[dict],
    news: dict[str, list[dict]],
) -> Optional[str]:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        ctx = []
        ctx.append("SECTOR BREADTH:")
        for s in breadths:
            cls = classify_sector(s)
            ctx.append(f"  {s.name}: {s.avg_pct:+.1f}% ({s.n_positive}/{s.n_total}) [{cls}]")
        ctx.append("")
        ctx.append("FOCUS SECTORS: " + ", ".join(s.name for s in focus) if focus else "FOCUS SECTORS: none clearly bullish")
        ctx.append("AVOID SECTORS: " + ", ".join(s.name for s in avoid) if avoid else "AVOID SECTORS: none clearly bearish")
        ctx.append("")
        ctx.append("TOP PICKS:")
        for p in picks:
            ctx.append(f"  {p['symbol']} (${p['premarket_price']:.2f}, {p['pct_change']:+.1f}%, {p['sector']})")
        ctx.append("")
        ctx.append("RECENT NEWS HEADLINES (for top movers):")
        for sym, items in news.items():
            if items:
                ctx.append(f"  {sym}:")
                for n in items[:2]:
                    ctx.append(f"    • {n.get('title')}")
        ctx.append("")
        ctx.append("VIX: " + (f"{quotes[VIX_SYMBOL].premarket_price:.1f}"
                              if VIX_SYMBOL in quotes else "n/a"))

        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            system=POLISH_PROMPT,
            messages=[{"role": "user", "content": "\n".join(ctx)}],
        )
        return resp.content[0].text.strip() if resp.content else None
    except Exception:
        logger.exception("polish_with_llm: failed")
        return None


# ──────────────────────────────────────────────────────────────────
# PERSISTENCE — store the morning's picks for EOD grading
# ──────────────────────────────────────────────────────────────────

def persist_morning_picks(
    picks: list[dict],
    focus: list[SectorBreadth],
    avoid: list[SectorBreadth],
    timestamp: datetime,
):
    """Write today's brief details to /data/premarket-picks.json so EOD can grade it."""
    PICKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": timestamp.isoformat(),
        "picks": [
            {
                "symbol": p["symbol"],
                "sector": p["sector"],
                "premarket_price": p["premarket_price"],
                "pct_change": p["pct_change"],
                "score": p["score"],
            } for p in picks
        ],
        "focus_sectors": [
            {"name": s.name, "avg_pct": s.avg_pct,
             "n_positive": s.n_positive, "n_total": s.n_total}
            for s in focus
        ],
        "avoid_sectors": [
            {"name": s.name, "avg_pct": s.avg_pct,
             "n_positive": s.n_positive, "n_total": s.n_total}
            for s in avoid
        ],
    }
    PICKS_FILE.write_text(json.dumps(record, default=str))


# ──────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────

def run_premarket_brief(send: bool = True) -> dict:
    """Main entry. Returns the rendered brief + raw data. Sends to Telegram if send=True."""
    import telegram_post  # lazy import; same package
    from datetime import datetime
    try:
        import pytz
        et = datetime.now(pytz.timezone("America/New_York"))
    except Exception:
        et = datetime.now()

    logger.info("premarket: starting brief at %s", et.isoformat())

    # 1. Build symbol list
    groups = load_watchlist_groups(TRIAGE_USER_ID)
    watchlist_syms = sorted({s for syms in groups.values() for s in syms})
    all_syms = list(set(INDICES + [VIX_SYMBOL] + SECTOR_ETFS + watchlist_syms))

    # 2. Fetch premarket data
    quotes = fetch_premarket(all_syms)
    logger.info("premarket: fetched %d/%d symbols", len(quotes), len(all_syms))

    # 3. Sector breadth
    breadths = compute_sector_breadth(groups, quotes)
    focus, avoid = pick_focus_avoid(breadths)
    logger.info("premarket: %d sectors, %d focus, %d avoid",
                len(breadths), len(focus), len(avoid))

    # 4. Recent setups
    setups = load_recent_alerts_setups(TRIAGE_USER_ID, lookback_hours=24)

    # 5. Top picks
    picks = pick_top_stocks(focus, setups, n=4)

    # 6. Heavy LLM polish: news + catalysts
    polish = None
    if LLM_TIER in ("standard", "heavy"):
        top_symbols_for_news = [p["symbol"] for p in picks]
        if LLM_TIER == "heavy":
            # Add focus-sector top movers' symbols to the news lookup
            for s in focus:
                if s.top_mover:
                    top_symbols_for_news.append(s.top_mover.symbol)
        news = fetch_news_for(list(set(top_symbols_for_news)))
        polish = polish_with_llm(quotes, breadths, focus, avoid, picks, news)

    # 7. Build the brief
    brief = build_premarket_brief(quotes, breadths, focus, avoid, picks, polish, et)

    # 8. Persist for EOD grading
    persist_morning_picks(picks, focus, avoid, et)

    # 9. Send to Telegram
    if send:
        try:
            telegram_post._send(brief)
            logger.info("premarket: brief sent to Telegram")
        except Exception:
            logger.exception("premarket: telegram send failed")

    return {
        "brief": brief,
        "n_quotes": len(quotes),
        "n_focus_sectors": len(focus),
        "n_picks": len(picks),
    }


if __name__ == "__main__":
    # CLI: `python premarket.py [--no-send]` for local testing
    import sys
    send = "--no-send" not in sys.argv
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-7s %(name)s | %(message)s")
    result = run_premarket_brief(send=send)
    print(result["brief"])
