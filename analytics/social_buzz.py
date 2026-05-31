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
APEWISDOM_URL = "https://apewisdom.io/api/v1.0/filter/stocks/page/1"
APEWISDOM_TIMEOUT = 10

# Filter thresholds — keep the snapshot clean.
MIN_MENTIONS_24H = 10        # noise floor — below this is conversational chaff
TOP_N = 20                   # store top 20, UI typically shows top 10


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
    try:
        r = requests.get(APEWISDOM_URL, timeout=APEWISDOM_TIMEOUT)
    except requests.RequestException as e:
        logger.warning("Apewisdom network error: %s", e)
        return None

    if r.status_code != 200:
        logger.info("Apewisdom returned %d", r.status_code)
        return None

    try:
        data = r.json()
    except ValueError:
        logger.warning("Apewisdom returned non-JSON")
        return None

    results = data.get("results") or []
    if not isinstance(results, list):
        return None
    return results


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


def refresh_social_buzz(session_factory) -> dict:
    """Pull Apewisdom, filter against screener_universe (real US-listed
    equities with known market cap), cross-reference today's Grade-A
    alerts, persist top N as a fresh snapshot.

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
        # Allowlist: symbols our screener already approved (cap + liquidity).
        universe_symbols = {
            row[0] for row in session.execute(
                text("SELECT symbol FROM screener_universe")
            ).all()
        }
        # Crypto majors we always allow (Apewisdom returns "BTC", "ETH"; map
        # to our "BTC-USD" / "ETH-USD" convention used elsewhere in the app).
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

            # Normalize: universe symbols are e.g. "NVDA"; crypto in our app
            # are "BTC-USD".
            if ticker_raw in universe_symbols:
                symbol = ticker_raw
            elif ticker_raw in crypto_allow:
                symbol = crypto_allow[ticker_raw]
            else:
                continue  # not in our tradeable universe — skip

            mentions = _to_int(row.get("mentions"))
            mentions_prev = _to_int(row.get("mentions_24h_ago"))
            if mentions < MIN_MENTIONS_24H:
                continue

            # Growth % vs 24h ago — the "is this NEW attention" signal.
            growth_pct: Optional[float] = None
            if mentions_prev > 0:
                growth_pct = round((mentions - mentions_prev) / mentions_prev * 100, 1)

            sentiment = _to_float(row.get("sentiment"))
            sentiment_score = _to_float(row.get("sentiment_score"))

            entries.append({
                "symbol": symbol,
                "name": row.get("name") or "",
                "mentions": mentions,
                "mentions_prev_24h": mentions_prev,
                "growth_pct": growth_pct,
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "rank": _to_int(row.get("rank")),
                "has_grade_a_today": symbol.upper() in grade_a_today,
            })

        # Sort by growth_pct desc (new attention beats perpetual SPY chatter).
        # Tie-break on raw mentions.
        entries.sort(
            key=lambda e: (
                -(e["growth_pct"] if e["growth_pct"] is not None else -1),
                -e["mentions"],
            ),
        )
        top = entries[:TOP_N]
        summary["after_filter"] = len(top)
        summary["with_grade_a"] = sum(1 for e in top if e["has_grade_a_today"])

        # Persist as a new snapshot row. We keep history for "growth over
        # time" charts later; for now the endpoint serves the latest.
        snap = SocialBuzzSnapshot(
            captured_at=datetime.utcnow(),
            source="apewisdom_stocks",
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
