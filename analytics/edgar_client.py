"""SEC EDGAR client — ticker→CIK, companyfacts XBRL, throttle + cache.

The ONLY network module of the Fundamentals Engine. Everything downstream
(metrics, scoring) is pure and fed by :func:`get_period_financials`, which this
module builds from EDGAR's structured XBRL ``companyfacts`` API.

EDGAR etiquette (hard requirements):
  * a descriptive User-Agent (``SEC_USER_AGENT`` in fundamentals_config),
  * a request-rate cap (token bucket, ``SEC_RATE_PER_MIN``),
  * aggressive caching (companyfacts only changes on a new filing).

Every value we surface carries provenance — the accession + filing URL of the
report it came from — so numbers are auditable. Missing concepts stay ``None``;
we never invent data.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime
from typing import Dict, List, Optional

import requests

from analytics.fundamentals_metrics import PeriodFinancials
from fundamentals_config import (
    SEC_CACHE_TTL_HOURS,
    SEC_RATE_PER_MIN,
    SEC_USER_AGENT,
)

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_FILING_INDEX_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}"

_CACHE_DIR = os.environ.get(
    "SEC_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "edgar_cache"),
)


# ── throttle ─────────────────────────────────────────────────────────────
class _TokenBucket:
    """Thread-safe token bucket. Mirrors analytics/earnings_fetcher so the
    whole app throttles external feeds the same way."""

    def __init__(self, rate_per_min: int) -> None:
        self.rate_per_sec = rate_per_min / 60.0
        self.capacity = float(rate_per_min)
        self.tokens = float(rate_per_min)
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def take(self) -> None:
        with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate_per_sec)
            self.updated = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            wait = (1.0 - self.tokens) / self.rate_per_sec
        time.sleep(wait)
        with self._lock:
            self.tokens = max(0.0, self.tokens - 1.0)


_bucket = _TokenBucket(SEC_RATE_PER_MIN)
_HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def _get_json(url: str) -> Optional[dict]:
    _bucket.take()
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
    except requests.RequestException as e:
        logger.warning("EDGAR GET failed %s: %s", url, e)
        return None
    if r.status_code == 429:
        logger.warning("EDGAR 429 rate-limited; backing off 5s")
        time.sleep(5)
        _bucket.take()
        try:
            r = requests.get(url, headers=_HEADERS, timeout=20)
        except requests.RequestException as e:
            logger.warning("EDGAR retry failed %s: %s", url, e)
            return None
    if r.status_code != 200:
        logger.info("EDGAR %s → HTTP %s", url, r.status_code)
        return None
    try:
        return r.json()
    except ValueError:
        logger.warning("EDGAR %s returned non-JSON", url)
        return None


# ── ticker → CIK ─────────────────────────────────────────────────────────
_cik_map: Optional[Dict[str, int]] = None
_cik_lock = threading.Lock()


def _load_cik_map() -> Dict[str, int]:
    global _cik_map
    with _cik_lock:
        if _cik_map is not None:
            return _cik_map
        cached = _read_cache("company_tickers.json", ttl_hours=24 * 7)
        data = cached or _get_json(_TICKERS_URL)
        if data and not cached:
            _write_cache("company_tickers.json", data)
        mapping: Dict[str, int] = {}
        if data:
            # EDGAR shape: {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
            for row in data.values():
                tkr = str(row.get("ticker", "")).upper()
                cik = row.get("cik_str")
                if tkr and cik is not None:
                    mapping[tkr] = int(cik)
        _cik_map = mapping
        return mapping


def ticker_to_cik(symbol: str) -> Optional[int]:
    """Resolve a ticker to its EDGAR CIK, or ``None`` if unknown (ETFs,
    foreign issuers without XBRL, crypto tickers all legitimately miss)."""
    if not symbol:
        return None
    return _load_cik_map().get(symbol.upper())


# ── disk cache ───────────────────────────────────────────────────────────
def _cache_path(name: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    safe = name.replace("/", "_")
    return os.path.join(_CACHE_DIR, safe)


def _read_cache(name: str, ttl_hours: float) -> Optional[dict]:
    path = _cache_path(name)
    try:
        st = os.stat(path)
    except OSError:
        return None
    age_hours = (time.time() - st.st_mtime) / 3600.0
    if age_hours > ttl_hours:
        return None
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_cache(name: str, data: dict) -> None:
    try:
        with open(_cache_path(name), "w") as fh:
            json.dump(data, fh)
    except OSError as e:
        logger.debug("EDGAR cache write failed for %s: %s", name, e)


def fetch_company_facts(cik: int, *, use_cache: bool = True) -> Optional[dict]:
    """Fetch the full companyfacts XBRL payload for a CIK (cached ~a day)."""
    name = f"companyfacts_CIK{cik:010d}.json"
    if use_cache:
        cached = _read_cache(name, ttl_hours=SEC_CACHE_TTL_HOURS)
        if cached is not None:
            return cached
    data = _get_json(_FACTS_URL.format(cik=cik))
    if data is not None:
        _write_cache(name, data)
    return data


# ── XBRL normalisation ───────────────────────────────────────────────────
# Curated concept → candidate US-GAAP tags, in priority order. First tag with a
# value for the period wins. Keeps the engine robust to filer tag choices.
_CONCEPT_TAGS: Dict[str, List[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt", "InterestAndDebtExpense"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities",
                             "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"],
    "inventory": ["InventoryNet"],
    "receivables": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "total_current_assets": ["AssetsCurrent"],
    "total_current_liabilities": ["LiabilitiesCurrent"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "short_term_debt": ["DebtCurrent", "ShortTermBorrowings", "LongTermDebtCurrent"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "stockholders_equity": ["StockholdersEquity",
                             "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding",
                       "WeightedAverageNumberOfSharesOutstandingBasic"],
}

# Instant (balance-sheet) concepts have no start date; the rest are durations.
_INSTANT = {
    "inventory", "receivables", "total_current_assets", "total_current_liabilities",
    "total_assets", "total_liabilities", "cash", "short_term_debt", "long_term_debt",
    "stockholders_equity",
}

_SHARE_UNITS = {"shares"}


def _parse_d(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _duration_days(start: Optional[date], end: Optional[date]) -> Optional[int]:
    if start is None or end is None:
        return None
    return (end - start).days


def _facts_for(company_facts: dict, concept: str) -> List[dict]:
    """All USGAAP facts (any unit) for the first matching tag of ``concept``."""
    gaap = company_facts.get("facts", {}).get("us-gaap", {})
    for tag in _CONCEPT_TAGS.get(concept, []):
        node = gaap.get(tag)
        if not node:
            continue
        units = node.get("units", {})
        for unit_key, arr in units.items():
            if arr:
                return arr
    return []


def _is_annual(days: Optional[int]) -> bool:
    return days is not None and 340 <= days <= 380


def _is_quarter(days: Optional[int]) -> bool:
    return days is not None and 75 <= days <= 105


def get_period_financials(
    company_facts: dict,
    symbol: str,
    *,
    max_periods: int = 12,
) -> List[PeriodFinancials]:
    """Normalise companyfacts XBRL into an oldest→newest list of periods.

    We anchor periods on the ``net_income`` concept (present in every issuer's
    income statement), collecting one period per distinct filing context, then
    attach each other concept by matching period-end (instant) or period
    end + duration class (flow). Prefer 10-Q granularity for trend analysis;
    fall back to 10-K when quarterly is unavailable.
    """
    anchor = _facts_for(company_facts, "net_income")
    if not anchor:
        return []

    # Build the anchor period skeletons keyed by (end, form). Keep the fact with
    # the latest 'filed' date for each context (restatements supersede).
    skeletons: Dict[tuple, dict] = {}
    for fact in anchor:
        end = _parse_d(fact.get("end"))
        start = _parse_d(fact.get("start"))
        form = fact.get("form", "")
        if end is None or form not in ("10-K", "10-Q"):
            continue
        days = _duration_days(start, end)
        if form == "10-Q" and not _is_quarter(days):
            continue
        if form == "10-K" and not _is_annual(days):
            continue
        key = (end, form)
        prev = skeletons.get(key)
        if prev is None or (fact.get("filed", "") > prev.get("filed", "")):
            skeletons[key] = {
                "end": end, "start": start, "form": form, "days": days or (90 if form == "10-Q" else 365),
                "fy": fact.get("fy"), "fp": fact.get("fp"),
                "filed": fact.get("filed"), "accn": fact.get("accn"),
            }

    if not skeletons:
        return []

    # Newest first, then trim, then flip to oldest→newest for the engine.
    ordered = sorted(skeletons.values(), key=lambda s: s["end"], reverse=True)[:max_periods]
    ordered.reverse()

    periods: List[PeriodFinancials] = []
    for sk in ordered:
        p = PeriodFinancials(
            symbol=symbol.upper(),
            period_end=sk["end"],
            form=sk["form"],
            fiscal_year=sk["fy"],
            fiscal_period=sk["fp"],
            filed_date=_parse_d(sk["filed"]),
            accession=sk["accn"],
            period_days=int(sk["days"]),
            source_url=_filing_url(company_facts.get("cik"), sk["accn"]),
        )
        for concept in _CONCEPT_TAGS:
            val = _resolve_value(company_facts, concept, sk)
            if val is not None:
                setattr(p, concept, val)
        periods.append(p)
    return periods


def _resolve_value(company_facts: dict, concept: str, sk: dict) -> Optional[float]:
    facts = _facts_for(company_facts, concept)
    if not facts:
        return None
    end = sk["end"]
    if concept in _INSTANT:
        # Match the balance-sheet snapshot at period end; latest filed wins.
        best = None
        for f in facts:
            if _parse_d(f.get("end")) == end and f.get("form") in ("10-K", "10-Q"):
                if best is None or f.get("filed", "") > best.get("filed", ""):
                    best = f
        return _num(best.get("val")) if best else None
    # Flow concept: match end + same duration class as the anchor.
    want_annual = sk["form"] == "10-K"
    best = None
    for f in facts:
        if _parse_d(f.get("end")) != end:
            continue
        days = _duration_days(_parse_d(f.get("start")), end)
        if want_annual and not _is_annual(days):
            continue
        if not want_annual and not _is_quarter(days):
            continue
        if best is None or f.get("filed", "") > best.get("filed", ""):
            best = f
    return _num(best.get("val")) if best else None


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _filing_url(cik, accn: Optional[str]) -> Optional[str]:
    if not cik or not accn:
        return None
    acc_nodash = str(accn).replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/"


def load_financials(symbol: str, *, use_cache: bool = True,
                    max_periods: int = 12) -> List[PeriodFinancials]:
    """End-to-end: ticker → CIK → companyfacts → normalised periods.

    Returns ``[]`` (never raises) for anything without XBRL fundamentals so the
    nightly batch can skip-and-continue on ETFs, ADRs, and fresh IPOs.
    """
    cik = ticker_to_cik(symbol)
    if cik is None:
        logger.info("EDGAR: no CIK for %s (ETF/ADR/unknown) — skipping", symbol)
        return []
    facts = fetch_company_facts(cik, use_cache=use_cache)
    if not facts:
        return []
    return get_period_financials(facts, symbol, max_periods=max_periods)
