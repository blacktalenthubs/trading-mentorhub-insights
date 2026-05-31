"""Social Buzz — top tickers being discussed across retail social.

Pulls aggregated mention counts from Apewisdom (free public API that
scrapes WSB / stocks subreddits / Twitter / StockTwits) and filters
against our screener_universe table to drop pump-and-dump micro-caps.

Surfaces in Trade Ideas → Social tab so the user can see what's
gaining attention WITHOUT us having to scrape Twitter directly (which
is a brittle, expensive, ToS-grey-area trap as of 2026).

The fun cross-reference: if a buzz ticker ALSO has a Grade A alert
in our `alerts` table today, the UI flags it as "🔥 Social + Grade A"
— the marketing-worthy synergy.

Schedule: hourly via APScheduler. Cheap — one Apewisdom call covers
50+ tickers, no per-symbol API loops.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from sqlalchemy import desc, select, text


logger = logging.getLogger(__name__)

# Apewisdom — free public API, no auth. Endpoint structure:
#   https://apewisdom.io/api/v1.0/filter/{filter}/page/{page}
# Filters that matter to us: "stocks" (combined stock sentiment), "twitter",
# "stocktwits", "wallstreetbets". We use "stocks" as the umbrella signal
# since it already aggregates the others.
APEWISDOM_BASE = "https://apewisdom.io/api/v1.0/filter/stocks/page/{page}"
APEWISDOM_PAGES = 2          # 100 results/page — pull 2 for more names on thin days
APEWISDOM_TIMEOUT = 10
# Apewisdom 200s for browsers/curl but blocks the default python-requests UA from
# cloud IPs (the prod "stuck/stale" bug) — send a real browser UA + Accept.
APEWISDOM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

# Filter thresholds — keep the snapshot clean.
MIN_MENTIONS_24H = 3         # noise floor — thin/weekend sessions still get entries
MIN_PREV_FOR_GROWTH = 3      # need ≥3 prior mentions before trusting a growth %
TOP_N = 25                   # store top 25, UI typically shows top 10-15

# Filtering policy v2 (2026-05-31): old approach was "only include symbols in
# screener_universe" which was way too narrow — most things retail talks about
# never made it through. New approach: include everything Apewisdom returns
# EXCEPT (a) ETFs (they trend constantly but aren't tradeable as ideas, they're
# index proxies) and (b) symbols that look like junk (too long, no letters, etc.).
#
# Apewisdom already does quality filtering on the data they ingest, so trusting
# their list + a thin exclusion layer gives much better signal.
_EXCLUDED_ETFS: set[str] = {
    # Broad indexes — talked about constantly, never an idea
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VTV", "VUG", "VEA", "VWO",
    "VT", "VEU", "VXUS", "BND", "AGG", "BNDX",
    # Sector SPDRs
    "XLK", "XLE", "XLF", "XLV", "XLY", "XLI", "XLP", "XLU", "XLB", "XLRE", "XLC",
    # Thematic / leveraged — high mention volume, mostly noise
    "ARKK", "ARKW", "ARKG", "ARKQ", "ARKF", "SMH", "SOXX", "SOXL", "SOXS",
    "TQQQ", "SQQQ", "UPRO", "SPXU", "UVXY", "VIXY", "TBT", "TLT", "TMF", "TMV",
    "TZA", "TNA", "SDOW", "UDOW", "SPXL", "SPXS", "FAS", "FAZ",
    # Bond / commodity
    "GLD", "SLV", "GDX", "GDXJ", "USO", "UNG", "DBA", "DBC",
    # Crypto ETFs / proxies
    "GBTC", "ETHE", "BITO", "BITX", "BITI",
    # Dividend / income + thematic ETFs that recur in social chatter
    "SCHD", "DON", "SPCX", "JEPI", "JEPQ", "DGRO", "VYM", "VIG", "SCHG", "QQQM",
}


def _looks_like_valid_ticker(t: str) -> bool:
    """Cheap sanity filter — drop obvious junk before they reach the snapshot."""
    if not t or len(t) > 6:
        return False
    if t in _EXCLUDED_ETFS:
        return False
    # Letters + optional digits (NVDA, BRK.B style is rare in social, OK to skip).
    if not t.replace(".", "").isalnum():
        return False
    return True


def _fetch_apewisdom() -> Optional[list[dict]]:
    """One HTTP call, returns the raw `results` list or None on failure.

    Apewisdom returns JSON like:
      {"count": 50, "pages": 1, "currentPage": 1,
       "results": [
         {"rank": "1", "ticker": "NVDA", "name": "NVIDIA Corp",
          "mentions": "1247", "upvotes": "8842",
          "rank_24h_ago": "3", "mentions_24h_ago": "287",
          "sentiment": "0.42", "sentiment_score": "0.7"}, ...]}
    """
    merged: list[dict] = []
    for page in range(1, APEWISDOM_PAGES + 1):
        url = APEWISDOM_BASE.format(page=page)
        try:
            r = requests.get(url, headers=APEWISDOM_HEADERS, timeout=APEWISDOM_TIMEOUT)
        except requests.RequestException as e:
            logger.warning("Apewisdom network error (page %d): %s", page, e)
            break
        if r.status_code != 200:
            logger.info("Apewisdom returned %d (page %d)", r.status_code, page)
            break
        try:
            data = r.json()
        except ValueError:
            logger.warning("Apewisdom returned non-JSON (page %d)", page)
            break
        results = data.get("results") or []
        if not isinstance(results, list) or not results:
            break
        merged.extend(results)
    return merged or None


def _to_int(v) -> int:
    """Apewisdom returns numeric fields as strings. Be defensive."""
    if v is None:
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


STOCKTWITS_TRENDING_URL = "https://api.stocktwits.com/api/2/trending/symbols.json"


def _fetch_stocktwits_trending() -> list[dict]:
    """Second discovery source — trending EQUITIES on StockTwits. Returns
    [{symbol, watchers, score, summary}]; [] on failure (Apewisdom still works).
    Adds names Apewisdom misses + resilience if Apewisdom blocks the IP."""
    try:
        r = requests.get(STOCKTWITS_TRENDING_URL, headers=APEWISDOM_HEADERS, timeout=APEWISDOM_TIMEOUT)
        if r.status_code != 200:
            logger.info("StockTwits trending returned %d", r.status_code)
            return []
        syms = (r.json() or {}).get("symbols") or []
    except (requests.RequestException, ValueError) as e:
        logger.warning("StockTwits trending error: %s", e)
        return []
    out: list[dict] = []
    for s in syms:
        # Class is "Stock" for equities ("ExchangeTradedFund"/"CRYPTO"/… otherwise).
        if (s.get("instrument_class") or "").lower() != "stock":
            continue  # drop ETFs, crypto, ADRs, misc
        sym = (s.get("symbol_display") or s.get("symbol") or "").upper().strip()
        if not _looks_like_valid_ticker(sym):
            continue
        out.append({
            "symbol": sym,
            "name": s.get("title") or "",
            "watchers": _to_int(s.get("watchlist_count")),
            "score": _to_float(s.get("trending_score")),
            "summary": ((s.get("trends") or {}).get("summary") or "")[:400],
        })
    return out


def _stocktwits_sentiment(symbol: str) -> dict:
    """Per-symbol bull/bear from StockTwits messages (reuses get_social_context).
    Returns {sentiment, bullish_pct, bearish_pct} or {} when too few tagged posts."""
    try:
        from analytics.stocktwits import get_social_context
        ctx = get_social_context(symbol).to_dict()
        if (ctx.get("total_count") or 0) < 3:
            return {}
        bull = ctx.get("bullish_pct") or 0
        bear = ctx.get("bearish_pct") or 0
        if bull >= bear + 15:
            label = "bullish"
        elif bear >= bull + 15:
            label = "bearish"
        else:
            label = "mixed"
        return {"sentiment": label, "bullish_pct": bull, "bearish_pct": bear}
    except Exception:
        return {}


def refresh_social_buzz(session_factory) -> dict:
    """Pull Apewisdom (mention counts) + StockTwits trending (extra names +
    native sentiment), merge, cross-reference today's Grade-A alerts, attach
    real bull/bear sentiment to the displayed names, persist top N.

    Returns summary dict for cron logging.
    """
    from app.models.social_buzz import SocialBuzzSnapshot

    summary = {
        "fetched": 0,
        "after_filter": 0,
        "snapshot_id": None,
        "with_grade_a": 0,
    }

    raw = _fetch_apewisdom()
    if not raw:
        logger.warning("Social buzz: no data from Apewisdom — skip snapshot")
        return summary

    summary["fetched"] = len(raw)

    with session_factory() as session:
        # Crypto majors — Apewisdom returns "BTC"/"ETH"; map to our "-USD"
        # convention used elsewhere in the app.
        crypto_allow = {
            "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
            "DOGE": "DOGE-USD", "ADA": "ADA-USD",
        }

        # Today's Grade-A alert symbols — for the cross-reference badge.
        today_iso = date.today().isoformat()
        grade_a_rows = session.execute(text("""
            SELECT DISTINCT symbol
            FROM alerts
            WHERE session_date = :d AND grade = 'A'
        """), {"d": today_iso}).all()
        grade_a_today = {r[0].upper() for r in grade_a_rows}

        entries: list[dict] = []
        for row in raw:
            ticker_raw = (row.get("ticker") or "").upper().strip()
            if not ticker_raw:
                continue

            # Normalize: crypto majors mapped to -USD; everything else trusted
            # as-is. Junk filter (_looks_like_valid_ticker) drops ETFs +
            # malformed tickers. Apewisdom already pre-filters the data they
            # ingest, so over-filtering here just kills signal.
            if ticker_raw in crypto_allow:
                symbol = crypto_allow[ticker_raw]
            elif _looks_like_valid_ticker(ticker_raw):
                symbol = ticker_raw
            else:
                continue

            mentions = _to_int(row.get("mentions"))
            mentions_prev = _to_int(row.get("mentions_24h_ago"))
            if mentions < MIN_MENTIONS_24H:
                continue

            # Growth % vs 24h ago — the "is this NEW attention" signal. Require a
            # few prior mentions before trusting it, so a 1→11 blip doesn't read as
            # +1000% and dominate the board.
            growth_pct: Optional[float] = None
            if mentions_prev >= MIN_PREV_FOR_GROWTH:
                growth_pct = round((mentions - mentions_prev) / mentions_prev * 100, 1)

            sentiment = _to_float(row.get("sentiment"))
            sentiment_score = _to_float(row.get("sentiment_score"))

            entries.append({
                "symbol": symbol,
                "name": row.get("name") or "",
                "mentions": mentions,
                "mentions_prev_24h": mentions_prev,
                "growth_pct": growth_pct,
                "upvotes": _to_int(row.get("upvotes")),  # real engagement (Apewisdom sentiment is null)
                "sentiment": sentiment,                  # kept for back-compat; Apewisdom returns null
                "sentiment_score": sentiment_score,
                "rank": _to_int(row.get("rank")),
                "has_grade_a_today": symbol.upper() in grade_a_today,
                "sources": ["apewisdom"],
            })

        # --- Merge StockTwits trending: a 2nd discovery source. Enrich existing
        # Apewisdom names, add StockTwits-only trending names (mentions=0). ---
        by_symbol = {e["symbol"]: e for e in entries}
        for st in _fetch_stocktwits_trending():
            sym = st["symbol"]
            e = by_symbol.get(sym)
            if e is None:
                e = {
                    "symbol": sym, "name": st.get("name") or "", "mentions": 0,
                    "mentions_prev_24h": 0, "growth_pct": None, "upvotes": 0,
                    "sentiment": None, "sentiment_score": None, "rank": 0,
                    "has_grade_a_today": sym.upper() in grade_a_today,
                    "sources": [],
                }
                by_symbol[sym] = e
            if not e.get("name"):
                e["name"] = st.get("name") or ""
            e["sources"] = sorted(set(e.get("sources") or []) | {"stocktwits"})
            e["st_watchers"] = st["watchers"]
            e["st_score"] = st["score"]
            e["st_summary"] = st["summary"]
        summary["fetched"] += sum(1 for e in by_symbol.values() if "stocktwits" in (e.get("sources") or []))

        merged = list(by_symbol.values())
        # Rank for the TOP_N trim: lead with real discussion volume (mentions),
        # then StockTwits trend score (keeps ST-only trending names), then growth.
        merged.sort(key=lambda e: (
            -e["mentions"],
            -(e.get("st_score") or 0),
            -(e["growth_pct"] if e.get("growth_pct") is not None else -1),
        ))
        top = merged[:TOP_N]

        # Real bull/bear sentiment for the DISPLAYED names (parallel, best-effort).
        # StockTwits' own /messages stream — cached 5min, so re-runs are cheap.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as pool:
            sents = list(pool.map(lambda e: _stocktwits_sentiment(e["symbol"]), top))
        for e, sdata in zip(top, sents):
            if sdata:
                e.update(sdata)

        summary["after_filter"] = len(top)
        summary["with_grade_a"] = sum(1 for e in top if e["has_grade_a_today"])
        summary["with_sentiment"] = sum(1 for e in top if e.get("sentiment"))

        # Persist as a new snapshot row (7-day history retained).
        snap = SocialBuzzSnapshot(
            captured_at=datetime.utcnow(),
            source="apewisdom+stocktwits",
            entries=top,
        )
        session.add(snap)
        session.commit()
        session.refresh(snap)
        summary["snapshot_id"] = snap.id

    logger.info("Social buzz refresh: %s", summary)
    return summary


def cleanup_old_snapshots(session_factory, keep_days: int = 7) -> int:
    """Delete snapshots older than `keep_days`. Run weekly. Returns count."""
    from app.models.social_buzz import SocialBuzzSnapshot

    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    with session_factory() as session:
        deleted = session.execute(text(
            "DELETE FROM social_buzz_snapshot WHERE captured_at < :c"
        ), {"c": cutoff}).rowcount or 0
        session.commit()
    if deleted:
        logger.info("Social buzz cleanup: deleted %d snapshots older than %dd",
                    deleted, keep_days)
    return deleted
