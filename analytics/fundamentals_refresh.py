"""On-demand fundamentals refresh for the Watchlist > Details tab.

No nightly cron (unlike earnings_refresh) — these functions run synchronously
inside a thread-pool executor when the user taps Refresh in the UI. Each one:

  1. fetch_fundamentals() — Finnhub profile/metric/recommendation + (maybe) yfinance
  2. generate_views()     — Anthropic short/long-term paragraphs
  3. upsert the symbol_fundamentals row (get-or-create, preserving a cached
     description when the new fetch returns None)

Mirrors the get-or-add upsert style of analytics/earnings_refresh.py and uses
the same sync session factory wired into app.state.sync_session_factory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from analytics.fundamentals_fetcher import fetch_fundamentals
from analytics.fundamentals_view import generate_brief

logger = logging.getLogger(__name__)


def _distinct_watchlist_symbols(session) -> list[str]:
    from sqlalchemy import select
    from app.models.watchlist import WatchlistItem

    rows = session.execute(select(WatchlistItem.symbol).distinct()).all()
    return sorted({r[0].upper() for r in rows if r[0]})


def refresh_symbol(session, symbol: str, *, with_ai: bool = False) -> bool:
    """Fetch + upsert one symbol's numbers. Returns True if a row was written.

    ``with_ai=True`` ALSO (re)generates the structured AI brief (Sonnet) — this
    is the expensive, admin-gated path. Numbers-only (``with_ai=False``) refreshes
    EPS/analysts/metrics for any user without spending LLM budget. A prior brief is
    always preserved when not regenerated or when generation fails.

    Skips the rate-limited yfinance description call when the existing row already
    has one (the description is static).
    """
    from app.models.fundamentals import SymbolFundamentals

    symbol = symbol.upper()
    existing = session.get(SymbolFundamentals, symbol)
    include_description = existing is None or not existing.description

    data = fetch_fundamentals(symbol, include_description=include_description)
    if data is None:
        logger.info("Fundamentals refresh: no data for %s, skipping", symbol)
        return False

    if existing is None:
        existing = SymbolFundamentals(symbol=symbol)
        session.add(existing)

    existing.company_name = data.company_name or existing.company_name
    # Description only re-fetched when missing — preserve the cached one otherwise.
    if data.description:
        existing.description = data.description
    existing.sector = data.sector or existing.sector
    existing.industry = data.industry or existing.industry
    existing.market_cap = data.market_cap
    existing.trailing_eps = data.trailing_eps
    existing.forward_eps = data.forward_eps
    existing.eps_growth_pct = data.eps_growth_pct
    existing.pe_ratio = data.pe_ratio
    existing.rec_strong_buy = data.rec_strong_buy
    existing.rec_buy = data.rec_buy
    existing.rec_hold = data.rec_hold
    existing.rec_sell = data.rec_sell
    existing.rec_strong_sell = data.rec_strong_sell
    existing.consensus = data.consensus
    existing.rec_period = data.rec_period
    existing.metrics_json = json.dumps(data.metrics_dict())

    if with_ai:
        brief = generate_brief(data)
        if brief:  # preserve the prior brief if generation failed/disabled
            existing.ai_brief = json.dumps(brief)
            existing.ai_generated_at = datetime.utcnow()
            existing.short_term_view = brief.get("short_term") or existing.short_term_view
            existing.long_term_view = brief.get("long_term") or existing.long_term_view

    existing.fetched_at = datetime.utcnow()
    return True


def refresh_one(session_factory, symbol: str, *, with_ai: bool = False) -> dict:
    """Refresh a single symbol in its own session. Returns a summary dict."""
    with session_factory() as session:
        try:
            written = refresh_symbol(session, symbol, with_ai=with_ai)
            session.commit()
            return {"symbol": symbol.upper(), "refreshed": int(written), "failures": 0}
        except Exception:
            session.rollback()
            logger.exception("Fundamentals refresh failed for %s", symbol)
            return {"symbol": symbol.upper(), "refreshed": 0, "failures": 1}


def generate_brief_if_missing(session_factory, symbol: str) -> dict:
    """Auto-run path for newly added symbols: generate the AI brief ONLY if the
    symbol has none yet (so a re-add doesn't re-spend LLM budget). Numbers are
    always refreshed. Safe to call in a background task."""
    from app.models.fundamentals import SymbolFundamentals
    with session_factory() as session:
        existing = session.get(SymbolFundamentals, symbol.upper())
        needs_ai = existing is None or not existing.ai_brief
    return refresh_one(session_factory, symbol, with_ai=needs_ai)


def refresh_all(session_factory, *, with_ai: bool = False) -> dict:
    """Refresh every distinct watchlist symbol. Slow (throttled by the shared
    Finnhub token bucket + per-symbol Anthropic call when ``with_ai``) — intended
    as an explicit user action, not a background job.
    """
    summary = {"symbols": 0, "refreshed": 0, "failures": 0}
    with session_factory() as session:
        symbols = _distinct_watchlist_symbols(session)
        summary["symbols"] = len(symbols)
        for symbol in symbols:
            try:
                if refresh_symbol(session, symbol, with_ai=with_ai):
                    summary["refreshed"] += 1
                session.commit()
            except Exception:
                session.rollback()
                summary["failures"] += 1
                logger.exception("Fundamentals refresh failed for %s — continuing", symbol)
    logger.info(
        "Fundamentals refresh complete: %d symbols, %d refreshed, %d failures",
        summary["symbols"], summary["refreshed"], summary["failures"],
    )
    return summary
