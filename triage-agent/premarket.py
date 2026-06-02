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

from dotenv import load_dotenv
load_dotenv()  # picks up .env when running standalone; harmless on Railway

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
    """Fetch premarket data via bulk yf.download with prepost=True.

    Returns symbol → PriceMove with TODAY's most-recent price (premarket bar
    if before market open, regular bar otherwise) vs YESTERDAY's regular
    close (4:00 PM ET bar from the prior session day).

    Why not yf.Ticker.info? It's a cached endpoint that frequently returns
    stale post-market data instead of today's premarket. Fallback chain in
    the old code (preMarketPrice → postMarketPrice → regularMarketPrice)
    silently served yesterday's after-hours close as if it were today's
    premarket, producing the "looks like prior-day market data" bug. This
    rewrite reads ACTUAL 5-min bars with prepost=True and HARD-FAILS on
    symbols with no today-data — never silently uses yesterday.
    """
    if not symbols:
        return {}

    import pandas as pd
    try:
        import pytz
        et_tz = pytz.timezone("America/New_York")
        now_et = datetime.now(et_tz)
    except Exception:
        et_tz = None
        now_et = datetime.utcnow() - timedelta(hours=4)  # rough ET fallback

    today_et = now_et.date()
    out: dict[str, PriceMove] = {}

    # Bulk-download last 2 trading days at 5m resolution, including pre+post bars.
    # period="5d" covers weekends/holidays; we filter to today/yesterday below.
    try:
        df = yf.download(
            tickers=" ".join(symbols),
            period="5d",
            interval="5m",
            prepost=True,
            group_by="ticker",
            progress=False,
            threads=True,
            auto_adjust=False,
        )
    except Exception:
        logger.exception("fetch_premarket: yf.download failed")
        return {}

    if df is None or df.empty:
        logger.warning("fetch_premarket: yf.download returned empty frame")
        return {}

    # df has a MultiIndex column when multiple tickers; single-level if one.
    is_multi = isinstance(df.columns, pd.MultiIndex)

    # Daily-close lookup (for yesterday's regular-session close, anchored to
    # the 4:00 PM ET bar). Use a separate daily-bar fetch — more reliable
    # than reconstructing from 5m bars across weekends.
    try:
        daily = yf.download(
            tickers=" ".join(symbols),
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            auto_adjust=False,
        )
    except Exception:
        daily = None
        logger.exception("fetch_premarket: daily-bar fetch failed")

    daily_multi = daily is not None and isinstance(daily.columns, pd.MultiIndex)

    for sym in symbols:
        try:
            # Per-symbol slice of the 5m bars
            if is_multi:
                if sym not in df.columns.get_level_values(0):
                    logger.warning("fetch_premarket: no 5m bars for %s", sym)
                    continue
                sym_df = df[sym].dropna(how="all")
            else:
                sym_df = df.dropna(how="all")
            if sym_df.empty:
                logger.warning("fetch_premarket: %s has empty 5m bars", sym)
                continue

            # Convert index to ET so we can filter by today's date
            idx = sym_df.index
            if et_tz is not None:
                try:
                    if idx.tz is None:
                        idx = idx.tz_localize("UTC").tz_convert(et_tz)
                    else:
                        idx = idx.tz_convert(et_tz)
                    sym_df = sym_df.copy()
                    sym_df.index = idx
                except Exception:
                    pass

            # Today's bars (in ET) — must have AT LEAST ONE for symbol to qualify.
            today_bars = sym_df[sym_df.index.date == today_et]
            if today_bars.empty:
                logger.info("fetch_premarket: %s has no today-bars (ET=%s) — skipping",
                            sym, today_et)
                continue

            latest = today_bars.iloc[-1]
            pre_price = float(latest["Close"])
            today_vol = int(today_bars["Volume"].sum() or 0)

            # Yesterday's regular-session close — prefer daily-bar lookup.
            last_close = None
            if daily is not None:
                try:
                    sym_daily = daily[sym].dropna(how="all") if daily_multi else daily.dropna(how="all")
                    # Daily index is date-anchored to session day (no intra-day).
                    # Take the most recent bar STRICTLY before today.
                    prior = sym_daily[sym_daily.index.date < today_et]
                    if not prior.empty:
                        last_close = float(prior.iloc[-1]["Close"])
                except Exception:
                    pass

            # Fallback: use first 5m bar from prior session day in our 5m frame.
            if last_close is None:
                prior_bars = sym_df[sym_df.index.date < today_et]
                if not prior_bars.empty:
                    # Take the last bar of the prior session (closest to 4 PM ET close)
                    last_close = float(prior_bars.iloc[-1]["Close"])

            if last_close is None or last_close == 0:
                logger.warning("fetch_premarket: %s no prior close — skipping", sym)
                continue

            pct_change = (pre_price - last_close) / last_close * 100.0

            # Average volume — use prior session's total volume as proxy.
            # (averageVolume from .info would require a separate call; for the
            # premarket brief, comparing today-so-far vs yesterday-full is
            # a reasonable rel-vol heuristic.)
            avg_vol = 1.0
            if daily is not None:
                try:
                    sym_daily = daily[sym].dropna(how="all") if daily_multi else daily.dropna(how="all")
                    prior_vols = sym_daily[sym_daily.index.date < today_et]["Volume"].tail(5)
                    if not prior_vols.empty:
                        avg_vol = float(prior_vols.mean()) or 1.0
                except Exception:
                    pass

            rel_vol = (today_vol / avg_vol) if avg_vol else 0.0

            out[sym] = PriceMove(
                symbol=sym,
                last_close=last_close,
                premarket_price=pre_price,
                pct_change=float(pct_change),
                volume=today_vol,
                avg_volume=float(avg_vol),
                rel_volume=float(rel_vol),
            )
        except Exception as e:
            logger.warning("fetch_premarket: failed for %s: %s", sym, e)
            continue

    logger.info("fetch_premarket: resolved %d/%d symbols with today-data",
                len(out), len(symbols))
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

def _load_telegram_chat_ids() -> list[str]:
    """Return distinct Telegram chat IDs across all users who linked the bot
    AND have telegram_enabled = true. Used by the premarket fan-out so the
    morning brief reaches every signed-up user, not just the admin chat.
    """
    out: list[str] = []
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT telegram_chat_id
                FROM users
                WHERE telegram_chat_id IS NOT NULL
                  AND telegram_chat_id <> ''
                  AND telegram_enabled = true
            """)
            for (cid,) in cur.fetchall():
                if cid:
                    out.append(str(cid))
    return out


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

# Sector ETFs to surface on the tape line — keep it the heavy hitters.
TAPE_ETFS = ["XLK", "XLE", "XLF", "XLV", "XLI"]


def _sector_emoji(cls: str) -> str:
    return {"bullish": "🟢", "neutral": "⚪", "bearish": "🔴"}.get(cls, "⚪")


def format_tape_block(quotes: dict[str, PriceMove]) -> str:
    """Two-line tape inside a <pre> block for alignment."""
    line1_parts = []
    for s in INDICES:
        if s in quotes:
            line1_parts.append(f"{s:<3} {quotes[s].pct_change:+.1f}%")
    # VIX (level, not %)
    vix_q = quotes.get(VIX_SYMBOL) or quotes.get("VIX")
    if vix_q:
        line1_parts.append(f"VIX {vix_q.premarket_price:.1f}")

    line2_parts = []
    for s in TAPE_ETFS:
        if s in quotes:
            line2_parts.append(f"{s} {quotes[s].pct_change:+.1f}%")

    inner = "   ".join(line1_parts) + "\n" + "   ".join(line2_parts)
    return f"<pre>{inner}</pre>"


def format_sectors_block(breadths: list[SectorBreadth]) -> str:
    """Sector table inside a <pre> block. Grouped bullish → neutral → bearish."""
    if not breadths:
        return ""
    # Group by classification
    groups = {"bullish": [], "neutral": [], "bearish": []}
    for s in breadths:
        groups[classify_sector(s)].append(s)
    # Sort each group by avg_pct (desc within bullish/neutral, asc within bearish)
    groups["bullish"].sort(key=lambda s: s.avg_pct, reverse=True)
    groups["neutral"].sort(key=lambda s: s.avg_pct, reverse=True)
    groups["bearish"].sort(key=lambda s: s.avg_pct)

    rows = []
    for cls in ("bullish", "neutral", "bearish"):
        for s in groups[cls]:
            emoji = _sector_emoji(cls)
            name = f"{s.name:<11}"
            pct = f"{s.avg_pct:+5.1f}%"
            breadth = f"{s.n_positive}/{s.n_total}"
            top = ""
            if cls == "bullish" and s.top_mover:
                top = f"   {s.top_mover.symbol} {s.top_mover.pct_change:+.1f}%"
            elif cls == "bearish" and s.bottom_mover:
                top = f"   {s.bottom_mover.symbol} {s.bottom_mover.pct_change:+.1f}%"
            rows.append(f"{emoji} {name} {pct}   {breadth}{top}")
    return f"<pre>{chr(10).join(rows)}</pre>"


def format_picks_block(picks: list[dict]) -> str:
    """Numbered top picks inside a <pre> block, fixed-width columns."""
    if not picks:
        return ""
    rows = []
    for i, p in enumerate(picks, 1):
        sym     = f"{p['symbol']:<6}"
        sector  = f"{p['sector']:<10}"
        pct     = f"{p['pct_change']:+5.1f}%"
        # Consistent 8-char width regardless of price magnitude
        price   = p["premarket_price"]
        if price >= 1000:
            price_str = f"${price:>7,.0f}"   # "$  1,562"
        else:
            price_str = f"${price:>7.2f}"    # "$ 757.35" / "$  60.80"
        rel_vol = p.get("rel_volume") or 0
        rv      = f"{rel_vol:.1f}× vol"
        setup   = ""
        if p.get("setup") and p["setup"].get("entry"):
            setup = f"  · setup ${p['setup']['entry']:.2f}"
        rows.append(f"{i}. {sym} {price_str}  {sector} {pct}  {rv}{setup}")
    return f"<pre>{chr(10).join(rows)}</pre>"


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

    parts.append("<b>🌐 Tape</b>")
    parts.append(format_tape_block(quotes))
    parts.append("")

    parts.append("<b>📊 Sectors</b>")
    parts.append(format_sectors_block(breadths))
    parts.append("")

    parts.append("<b>🎯 Plan</b>")
    if focus:
        parts.append(f"Focus: <b>{', '.join(s.name for s in focus)}</b> (longs)")
    if avoid:
        parts.append(f"Avoid: <b>{', '.join(s.name for s in avoid)}</b> (red breadth)")
    parts.append("")

    if picks:
        parts.append("<b>⭐ Top Picks</b>")
        parts.append(format_picks_block(picks))
        parts.append("")

    if polish:
        parts.append("<b>🤖 Brief</b>")
        parts.append(polish)

    return "\n".join(parts)[:4000]


# ──────────────────────────────────────────────────────────────────
# LLM POLISH (heavy tier)
# ──────────────────────────────────────────────────────────────────

POLISH_PROMPT = """You are a trading-desk analyst writing one short paragraph for a trader's premarket brief.

Given sector breadth, top picks, news headlines, and macro context, write 2-3 sentences MAX.
Rules:
- NO header (no "**Premarket Brief**" or similar — the brief already has one)
- NO bullet points or lists
- NO restating the numbers — they're in the data above
- DO cite catalysts by name when they explain the move (earnings, Fed, sector news)
- DO note rotation patterns and one thing to watch
- Be specific. "Memory rallying on chip cycle" beats "tech is up".

Output: the paragraph only, no preamble."""


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

    # 9. Send to Telegram — fan out to ALL users with a linked chat_id.
    #    2026-06-02: changed from single-chat send to per-user fan-out so
    #    every signed-up user who's linked their bot gets the morning brief,
    #    matching the alert fan-out launched 2026-06-01. Admin chat keeps
    #    receiving via the env-configured CONVICTION_CHAT_ID fallback when
    #    no users are linked yet (e.g. local dev).
    if send:
        sent_count = 0
        try:
            chat_ids = _load_telegram_chat_ids()
            if not chat_ids:
                telegram_post._send(brief)
                sent_count = 1
            else:
                for cid in chat_ids:
                    try:
                        if telegram_post._send(brief, chat_id=cid):
                            sent_count += 1
                    except Exception:
                        logger.exception("premarket: send failed for chat_id=%s", cid)
            logger.info("premarket: brief sent to %d chat(s)", sent_count)
        except Exception:
            logger.exception("premarket: telegram fan-out failed")

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
