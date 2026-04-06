"""Rapid price feed — polls latest quotes every 15 seconds.

Pushes price updates to connected frontends via SSE.
Uses yfinance fast_info for lightweight quotes (~200ms/symbol).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger("price_feed")

_price_cache: Dict[str, dict] = {}  # {symbol: {price, change_pct, updated_at}}
_symbols_cache: list[str] = []
_symbols_updated: str = ""


def get_watchlist_symbols(sync_session_factory) -> list[str]:
    """Get union of all user watchlist symbols (cached 60s)."""
    global _symbols_cache, _symbols_updated
    now = datetime.utcnow().isoformat()[:16]  # minute precision
    if _symbols_updated == now and _symbols_cache:
        return _symbols_cache

    try:
        from sqlalchemy import select
        from app.models.watchlist import WatchlistItem
        with sync_session_factory() as db:
            rows = db.execute(select(WatchlistItem.symbol).distinct()).scalars().all()
            _symbols_cache = list(rows) if rows else []
            _symbols_updated = now
    except Exception:
        logger.exception("Failed to get watchlist symbols")
    return _symbols_cache


def poll_prices(sync_session_factory) -> dict:
    """Fetch latest prices for all watchlist symbols. Returns price dict."""
    symbols = get_watchlist_symbols(sync_session_factory)
    if not symbols:
        return {}

    import yfinance as yf

    prices = {}
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            info = t.fast_info
            price = round(float(info.last_price), 2)
            prev = float(info.previous_close) if hasattr(info, "previous_close") and info.previous_close else price
            change_pct = round(((price - prev) / prev) * 100, 2) if prev > 0 else 0

            prices[sym] = {
                "price": price,
                "change_pct": change_pct,
            }
            _price_cache[sym] = prices[sym]
        except Exception:
            # Use cached value if fetch fails
            if sym in _price_cache:
                prices[sym] = _price_cache[sym]

    logger.debug("Price feed: updated %d/%d symbols", len(prices), len(symbols))
    return prices


def get_cached_prices() -> dict:
    """Return latest cached prices."""
    return dict(_price_cache)
