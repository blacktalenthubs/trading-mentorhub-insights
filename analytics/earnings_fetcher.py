"""Finnhub earnings fetcher with token-bucket throttling.

Free tier = 60 req/min. The token-bucket lets us burst up to the bucket
capacity, then steady-state at 60/min. Avoids raw `time.sleep(1)` between
every call which would serialize a 150-symbol refresh into ~5 wasted
minutes of pure waiting.

Two endpoints:
  /calendar/earnings?symbol=NVDA&from=YYYY-MM-DD&to=YYYY-MM-DD
  /stock/earnings?symbol=NVDA&limit=N

Both return JSON. Errors return None and log — the caller (refresh job)
is responsible for skipping symbols that fail without aborting the whole
run.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import requests


logger = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

# Free tier ceiling. Conservative — they advertise 60/min but rate-limit
# headers sometimes lag, so we target 55 to leave margin for retries.
_RATE_PER_MIN = int(os.environ.get("FINNHUB_RATE_PER_MIN", "55"))


@dataclass
class UpcomingEarnings:
    symbol: str
    next_earnings_date: Optional[date]
    time_of_day: Optional[str]   # BMO / AMC / DMH / None
    eps_estimate: Optional[float]
    revenue_estimate: Optional[float]
    confirmed: bool


@dataclass
class HistoricalEarnings:
    symbol: str
    quarter_label: str           # e.g. "2026Q1"
    eps_actual: Optional[float]
    eps_estimate: Optional[float]
    surprise_pct: Optional[float]
    reported_at: Optional[date]


# ── Token bucket ────────────────────────────────────────────────────
class _TokenBucket:
    """Simple thread-safe token bucket. Tokens refill at `rate_per_min`/60
    per second up to `capacity`. `take()` blocks until a token is
    available. Single shared instance across all fetcher calls.
    """

    def __init__(self, rate_per_min: int, capacity: Optional[int] = None) -> None:
        self.rate_per_sec = rate_per_min / 60.0
        self.capacity = capacity or rate_per_min
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def take(self) -> None:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
            self.last_refill = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            # Need to wait — release the lock while sleeping.
            wait = (1.0 - self.tokens) / self.rate_per_sec
        time.sleep(wait)
        self.take()


_bucket = _TokenBucket(_RATE_PER_MIN)


# ── HTTP ────────────────────────────────────────────────────────────
def _get(endpoint: str, params: dict) -> Optional[dict]:
    """One Finnhub GET. Respects the token bucket. Returns parsed JSON
    on 200, None on any other status / network error.
    """
    if not FINNHUB_API_KEY:
        logger.warning("FINNHUB_API_KEY not set — earnings fetcher disabled")
        return None

    _bucket.take()
    params = {**params, "token": FINNHUB_API_KEY}
    try:
        r = requests.get(f"{FINNHUB_BASE}{endpoint}", params=params, timeout=10)
    except requests.RequestException as e:
        logger.warning("Finnhub %s network error: %s", endpoint, e)
        return None

    if r.status_code == 429:
        # Rate-limited despite the bucket — back off and retry once.
        logger.warning("Finnhub 429 on %s — backing off 30s", endpoint)
        time.sleep(30)
        _bucket.take()
        try:
            r = requests.get(f"{FINNHUB_BASE}{endpoint}", params=params, timeout=10)
        except requests.RequestException as e:
            logger.warning("Finnhub %s retry network error: %s", endpoint, e)
            return None

    if r.status_code != 200:
        logger.info("Finnhub %s returned %d for %s", endpoint, r.status_code, params.get("symbol"))
        return None

    try:
        return r.json()
    except ValueError:
        return None


# ── Parse helpers ───────────────────────────────────────────────────
def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_time_of_day(raw: Optional[str]) -> Optional[str]:
    """Finnhub uses 'bmo' / 'amc' / 'dmt' lowercase. Normalize to uppercase
    per spec FR-001. Anything unrecognized → None (don't guess).
    """
    if not raw:
        return None
    raw = raw.strip().lower()
    if raw == "bmo":
        return "BMO"
    if raw == "amc":
        return "AMC"
    if raw == "dmt":
        return "DMH"
    return None


def _quarter_label(year: Optional[int], quarter: Optional[int]) -> Optional[str]:
    if year is None or quarter is None:
        return None
    if quarter < 1 or quarter > 4:
        return None
    return f"{year}Q{quarter}"


# ── Public fetch fns ────────────────────────────────────────────────
def fetch_upcoming_earnings(symbol: str, days_ahead: int = 90) -> Optional[UpcomingEarnings]:
    """Returns the next upcoming earnings event within `days_ahead`, or None
    if the symbol has nothing scheduled in that window.

    Finnhub returns the calendar as a list under "earningsCalendar"; we
    pick the FIRST entry (closest upcoming) since we sorted from=today.
    """
    today = date.today()
    end = today + timedelta(days=days_ahead)
    data = _get("/calendar/earnings", {
        "symbol": symbol,
        "from": today.isoformat(),
        "to": end.isoformat(),
    })
    if not data:
        return None

    entries = data.get("earningsCalendar") or []
    if not entries:
        return None

    # Sort by date asc (defensive — Finnhub usually returns sorted).
    entries.sort(key=lambda e: e.get("date", ""))
    e = entries[0]

    return UpcomingEarnings(
        symbol=symbol,
        next_earnings_date=_parse_date(e.get("date")),
        time_of_day=_parse_time_of_day(e.get("hour")),
        eps_estimate=e.get("epsEstimate"),
        revenue_estimate=e.get("revenueEstimate"),
        # Finnhub doesn't expose a "confirmed" flag directly. Treat any
        # entry with a time_of_day set as confirmed. Estimate-only entries
        # without BMO/AMC are typically analyst projections.
        confirmed=bool(_parse_time_of_day(e.get("hour"))),
    )


def fetch_historical_earnings(symbol: str, limit: int = 4) -> list[HistoricalEarnings]:
    """Returns the last `limit` reported quarters, newest first. Empty
    list if the symbol has no history at Finnhub.
    """
    data = _get("/stock/earnings", {"symbol": symbol, "limit": limit})
    if not isinstance(data, list):
        return []

    out: list[HistoricalEarnings] = []
    for row in data:
        ql = _quarter_label(row.get("year"), row.get("quarter"))
        if ql is None:
            continue
        actual = row.get("actual")
        est = row.get("estimate")
        surprise_pct = row.get("surprisePercent")
        # If Finnhub didn't supply the surprise % directly, compute it.
        if surprise_pct is None and actual is not None and est not in (None, 0):
            try:
                surprise_pct = round((actual - est) / abs(est) * 100, 2)
            except (TypeError, ZeroDivisionError):
                surprise_pct = None
        out.append(HistoricalEarnings(
            symbol=symbol,
            quarter_label=ql,
            eps_actual=actual,
            eps_estimate=est,
            surprise_pct=surprise_pct,
            reported_at=_parse_date(row.get("period")),
        ))
    return out
