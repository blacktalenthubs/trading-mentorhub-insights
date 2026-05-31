"""StockTwits message stream fetcher — provides the 'what's actually
being said' context for symbols surfaced in Social Buzz.

Free public API, no auth required. Anonymous rate limit ~200/hour per IP;
server-side 5-min cache per symbol keeps us well under for any realistic
load (typical user expands 1-3 rows per session).

Maps each StockTwits message to a normalized SocialMessage dict the
frontend can render directly. Computes a net-sentiment summary from
the opt-in poster sentiment tags (not all posters tag — only ones who
do contribute to the count).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests


logger = logging.getLogger(__name__)

STOCKTWITS_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
STOCKTWITS_TIMEOUT = 8

# Cache: per-symbol with TTL. Keeps StockTwits API calls well below the
# anonymous 200/hour limit even if every user expands every row.
_CACHE_TTL_SEC = 300  # 5 min
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


@dataclass
class SocialMessage:
    id: int
    body: str
    created_at: str         # ISO timestamp string
    age_min: int            # minutes since post
    user: str               # @username
    user_followers: int
    sentiment: Optional[str]  # "bullish" | "bearish" | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "body": self.body,
            "created_at": self.created_at,
            "age_min": self.age_min,
            "user": self.user,
            "user_followers": self.user_followers,
            "sentiment": self.sentiment,
        }


@dataclass
class SocialContext:
    symbol: str
    messages: list[SocialMessage] = field(default_factory=list)
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    total_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "messages": [m.to_dict() for m in self.messages],
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "neutral_count": self.neutral_count,
            "total_count": self.total_count,
            "bullish_pct": round(self.bullish_count / self.total_count * 100, 0) if self.total_count else 0,
            "bearish_pct": round(self.bearish_count / self.total_count * 100, 0) if self.total_count else 0,
            "neutral_pct": round(self.neutral_count / self.total_count * 100, 0) if self.total_count else 0,
            "error": self.error,
        }


def _normalize_symbol(symbol: str) -> Optional[str]:
    """Map our internal symbol convention to StockTwits cashtag.
    - Equities: same symbol (NVDA → NVDA)
    - Crypto:   BTC-USD → BTC.X  (StockTwits uses .X suffix for crypto)
    Returns None for symbols StockTwits can't resolve (skip the context fetch).
    """
    s = (symbol or "").upper().strip()
    if not s:
        return None
    if s.endswith("-USD"):
        base = s[:-4]
        # StockTwits crypto coverage is spotty — only common majors work reliably.
        if base in {"BTC", "ETH", "SOL", "DOGE", "ADA", "AVAX", "MATIC", "LINK"}:
            return f"{base}.X"
        return None
    return s


def _parse_message(raw: dict) -> Optional[SocialMessage]:
    """Convert one raw StockTwits message JSON into our normalized shape."""
    try:
        msg_id = int(raw["id"])
        body = (raw.get("body") or "").strip()
        if not body:
            return None
        created_at = raw.get("created_at") or ""
        user = raw.get("user") or {}
        username = user.get("username") or "anonymous"
        followers = int(user.get("followers") or 0)
        entities = raw.get("entities") or {}
        sentiment_block = entities.get("sentiment") or {}
        basic_sent = (sentiment_block.get("basic") or "").lower() or None
        sentiment: Optional[str] = None
        if basic_sent == "bullish":
            sentiment = "bullish"
        elif basic_sent == "bearish":
            sentiment = "bearish"

        # Compute age in minutes — handles ISO 8601 string from StockTwits.
        from datetime import datetime, timezone
        age_min = 0
        if created_at:
            try:
                ts = created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_min = max(0, int((datetime.now(timezone.utc) - dt).total_seconds() / 60))
            except ValueError:
                age_min = 0

        return SocialMessage(
            id=msg_id,
            body=body,
            created_at=created_at,
            age_min=age_min,
            user=username,
            user_followers=followers,
            sentiment=sentiment,
        )
    except (KeyError, ValueError, TypeError):
        return None


def _fetch_raw(symbol: str) -> Optional[list[dict]]:
    """One HTTP call to StockTwits. Returns raw messages list or None on failure."""
    url = STOCKTWITS_URL.format(symbol=symbol)
    try:
        r = requests.get(url, timeout=STOCKTWITS_TIMEOUT)
    except requests.RequestException as e:
        logger.info("StockTwits network error for %s: %s", symbol, e)
        return None

    if r.status_code == 429:
        logger.warning("StockTwits 429 rate limit hit for %s", symbol)
        return None
    if r.status_code == 404:
        # Symbol not on StockTwits — fine, return empty.
        return []
    if r.status_code != 200:
        logger.info("StockTwits returned %d for %s", r.status_code, symbol)
        return None

    try:
        data = r.json()
    except ValueError:
        return None

    messages = data.get("messages") or []
    if not isinstance(messages, list):
        return []
    return messages


def get_social_context(symbol: str, limit: int = 8) -> SocialContext:
    """Fetch + cache + summarize StockTwits context for one symbol.

    Returns a SocialContext with messages (up to `limit`) sorted newest
    first + sentiment counts across the entire fetched stream (typically
    30 messages, which is what StockTwits returns per call).
    """
    st_symbol = _normalize_symbol(symbol)
    if st_symbol is None:
        return SocialContext(symbol=symbol, error="not_supported")

    cache_key = st_symbol
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and (now - cached[0]) < _CACHE_TTL_SEC:
            return SocialContext(**cached[1])

    raw_messages = _fetch_raw(st_symbol)
    if raw_messages is None:
        return SocialContext(symbol=symbol, error="fetch_failed")

    # Parse + filter empty.
    parsed: list[SocialMessage] = []
    for raw in raw_messages:
        m = _parse_message(raw)
        if m is not None:
            parsed.append(m)

    # Sentiment summary from ALL fetched messages (not just the limit slice).
    bull = sum(1 for m in parsed if m.sentiment == "bullish")
    bear = sum(1 for m in parsed if m.sentiment == "bearish")
    neut = sum(1 for m in parsed if m.sentiment is None)

    # Trim to `limit` for the displayed stream, newest first (already sorted
    # by StockTwits API).
    display = parsed[:limit]

    ctx = SocialContext(
        symbol=symbol,
        messages=display,
        bullish_count=bull,
        bearish_count=bear,
        neutral_count=neut,
        total_count=len(parsed),
    )

    # Cache the dict form (cheaper to round-trip than the dataclass).
    with _cache_lock:
        _cache[cache_key] = (now, {
            "symbol": symbol,
            "messages": ctx.messages,
            "bullish_count": ctx.bullish_count,
            "bearish_count": ctx.bearish_count,
            "neutral_count": ctx.neutral_count,
            "total_count": ctx.total_count,
            "error": None,
        })

    return ctx
