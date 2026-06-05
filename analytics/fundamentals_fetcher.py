"""Fundamentals + analyst ratings fetcher for the Watchlist > Details tab.

Combines three Finnhub free-tier endpoints with one yfinance call:

  Finnhub /stock/profile2      → company name, industry, market cap
  Finnhub /stock/metric        → trailing EPS, forward EPS, P/E
  Finnhub /stock/recommendation → analyst buy/hold/sell distribution
  yfinance longBusinessSummary → "what the company does" description

Reuses the shared token-bucket + HTTP helper from earnings_fetcher so a
Details refresh and the nightly earnings job share ONE 55/min Finnhub budget
(duplicating the bucket would let each burst to 55 → 110/min → 429s).

Every helper is graceful: a failing source returns None for its fields rather
than raising, so a partial card still renders. `/stock/price-target` is NOT
used — it is a Finnhub premium endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

# Reuse the throttled GET + shared token bucket from the earnings fetcher.
from analytics.earnings_fetcher import _get

logger = logging.getLogger(__name__)


@dataclass
class SymbolFundamentalsData:
    symbol: str
    company_name: Optional[str] = None
    description: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    trailing_eps: Optional[float] = None
    forward_eps: Optional[float] = None
    eps_growth_pct: Optional[float] = None
    pe_ratio: Optional[float] = None
    rec_strong_buy: Optional[int] = None
    rec_buy: Optional[int] = None
    rec_hold: Optional[int] = None
    rec_sell: Optional[int] = None
    rec_strong_sell: Optional[int] = None
    consensus: Optional[str] = None
    rec_period: Optional[str] = None
    # Extra decision metrics (Finnhub /metric + yfinance fast_info).
    revenue_growth_pct: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    last_price: Optional[float] = None
    ma50: Optional[float] = None
    ma200: Optional[float] = None

    def metrics_dict(self) -> dict:
        """The extra metrics as a JSON-serializable dict for storage (metrics_json)."""
        return {
            "revenue_growth_pct": self.revenue_growth_pct,
            "gross_margin_pct": self.gross_margin_pct,
            "net_margin_pct": self.net_margin_pct,
            "week52_high": self.week52_high,
            "week52_low": self.week52_low,
            "last_price": self.last_price,
            "ma50": self.ma50,
            "ma200": self.ma200,
        }


# ── Finnhub profile ──────────────────────────────────────────────────
def _fetch_profile(symbol: str) -> dict:
    """name, industry, market cap from /stock/profile2. Returns {} on failure."""
    data = _get("/stock/profile2", {"symbol": symbol})
    if not isinstance(data, dict) or not data:
        return {}
    return {
        "company_name": data.get("name"),
        "industry": data.get("finnhubIndustry"),
        # Finnhub returns market cap in millions of USD.
        "market_cap": (data["marketCapitalization"] * 1e6)
        if data.get("marketCapitalization") else None,
    }


# ── Finnhub metrics ──────────────────────────────────────────────────
def _to_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _fetch_metrics(symbol: str) -> dict:
    """trailing/forward EPS + P/E from /stock/metric?metric=all. {} on failure."""
    data = _get("/stock/metric", {"symbol": symbol, "metric": "all"})
    if not isinstance(data, dict):
        return {}
    metric = data.get("metric") or {}

    trailing_eps = _to_float(metric.get("epsTTM"))
    # Finnhub free tier exposes forward EPS inconsistently; try the common keys.
    forward_eps = _to_float(
        metric.get("epsForward")
        or metric.get("epsEstimateNextYear")
        or metric.get("epsNormalizedAnnual")
    )
    pe_ratio = _to_float(metric.get("peTTM") or metric.get("peNormalizedAnnual"))

    eps_growth_pct = None
    if trailing_eps not in (None, 0) and forward_eps is not None:
        eps_growth_pct = round((forward_eps - trailing_eps) / abs(trailing_eps) * 100, 1)

    return {
        "trailing_eps": trailing_eps,
        "forward_eps": forward_eps,
        "pe_ratio": pe_ratio,
        "eps_growth_pct": eps_growth_pct,
        # Extra decision metrics — same /metric payload (Finnhub returns these in %).
        "revenue_growth_pct": _to_float(metric.get("revenueGrowthTTMYoy")),
        "gross_margin_pct": _to_float(metric.get("grossMarginTTM")),
        "net_margin_pct": _to_float(metric.get("netProfitMarginTTM")),
        "week52_high": _to_float(metric.get("52WeekHigh")),
        "week52_low": _to_float(metric.get("52WeekLow")),
    }


# ── yfinance price trend (light fast_info call) ──────────────────────
def _fetch_price_trend(symbol: str) -> dict:
    """Last price + 50/200-day moving averages from yfinance fast_info (lighter
    than .info). {} on failure. Needed fresh each refresh (changes daily)."""
    try:
        import yfinance as yf

        fi = yf.Ticker(symbol).fast_info

        def g(attr: str) -> Optional[float]:
            try:
                v = getattr(fi, attr, None)
                return float(v) if v else None
            except Exception:
                return None

        return {
            "last_price": g("last_price"),
            "ma50": g("fifty_day_average"),
            "ma200": g("two_hundred_day_average"),
        }
    except Exception:
        logger.warning("yfinance price trend failed for %s", symbol)
        return {}


# ── Finnhub recommendation ───────────────────────────────────────────
def _derive_consensus(sb: int, b: int, h: int, s: int, ss: int) -> Optional[str]:
    """Weighted score → Buy / Hold / Sell. None when there are no ratings."""
    total = sb + b + h + s + ss
    if total == 0:
        return None
    score = (sb * 2 + b * 1 + h * 0 + s * -1 + ss * -2) / total
    if score > 0.5:
        return "Buy"
    if score < -0.5:
        return "Sell"
    return "Hold"


def _fetch_recommendation(symbol: str) -> dict:
    """Most recent analyst rating distribution from /stock/recommendation.

    Returns a LIST newest-first; we take [0]. {} on failure / no coverage.
    """
    data = _get("/stock/recommendation", {"symbol": symbol})
    if not isinstance(data, list) or not data:
        return {}
    row = data[0]
    sb = int(row.get("strongBuy") or 0)
    b = int(row.get("buy") or 0)
    h = int(row.get("hold") or 0)
    s = int(row.get("sell") or 0)
    ss = int(row.get("strongSell") or 0)
    return {
        "rec_strong_buy": sb,
        "rec_buy": b,
        "rec_hold": h,
        "rec_sell": s,
        "rec_strong_sell": ss,
        "consensus": _derive_consensus(sb, b, h, s, ss),
        "rec_period": row.get("period"),
    }


# ── yfinance description ─────────────────────────────────────────────
def _fetch_description(symbol: str) -> dict:
    """Company business summary + sector from yfinance. {} on failure.

    This is the rate-limited call (Yahoo throttles the server IP), so callers
    should skip it when a cached description already exists. The description is
    static, so caching it long-term is safe.
    """
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        return {
            "description": info.get("longBusinessSummary"),
            "sector": info.get("sector"),
            # yfinance industry is more specific than Finnhub's; prefer it.
            "industry": info.get("industry"),
        }
    except Exception:
        logger.warning("yfinance description failed for %s", symbol)
        return {}


# ── Public orchestrator ──────────────────────────────────────────────
def fetch_fundamentals(
    symbol: str, *, include_description: bool = True,
) -> Optional[SymbolFundamentalsData]:
    """Fetch and merge all sources for `symbol`.

    Returns None only if EVERY source failed (nothing to store). Otherwise
    returns a dataclass with whatever resolved; missing fields stay None.

    Set `include_description=False` to skip the rate-limited yfinance call when
    a cached description already exists.
    """
    merged: dict = {}
    merged.update(_fetch_profile(symbol))
    merged.update(_fetch_metrics(symbol))
    merged.update(_fetch_recommendation(symbol))
    # Price + MAs change daily, so fetch fresh every refresh (light fast_info call).
    merged.update({k: v for k, v in _fetch_price_trend(symbol).items() if v is not None})
    if include_description:
        # yfinance industry overrides Finnhub's when present; merge last.
        desc = _fetch_description(symbol)
        merged.update({k: v for k, v in desc.items() if v is not None})

    if not merged:
        return None
    return SymbolFundamentalsData(symbol=symbol, **merged)
