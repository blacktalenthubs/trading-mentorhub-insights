"""Analytics package — V2 surface.

Re-exports the small set of symbols that downstream packages commonly need.
The V1 rule-engine re-exports (enrich_trades, scan_watchlist, match_trades_fifo,
detect_wash_sales) were removed as part of Spec 49 V1 cleanup — the modules
they came from are deleted. Anything that still wants them must import
from the source module directly (but most are now deleted).
"""

from analytics.market_data import classify_day, fetch_ohlc, get_levels

__all__ = ["classify_day", "fetch_ohlc", "get_levels"]
