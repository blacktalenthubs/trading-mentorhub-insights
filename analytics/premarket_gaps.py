"""Premarket Gap Board — Stage 1 (pre-bell prep).

Scans the user watchlists ∪ the curated screener universes for stocks gapping
in the premarket session (4:00–9:29 ET), so the trader can build a plan before
the open instead of chasing extended intraday moves.

Two buckets (the curated list a symbol belongs to IS its bucket):
  - "clean"    — large/mega caps (MEGA_CAP_UNIVERSE + STATIC_UNIVERSE)
  - "momentum" — curated liquid small/mid + momentum names (SMALL_CAP_UNIVERSE)

Stability gate: the board should be SOLID, liquid names, so a market-cap floor
(default ≥ $3B, env PM_GAP_MARKET_CAP_MIN) drops the sub-$3B small/penny gappers
that leak in via the market-wide movers broadening. Curated mega/large-cap lists
are trusted (no lookup); everything else is verified via Finnhub /stock/profile2
(cloud-safe — yfinance is IP-blocked in prod), which also tags sector + whether
the name is in the AI / tech space (the user's preferred focus).

Per symbol it reuses the existing premarket pipeline:
  fetch_premarket_bars() + fetch_prior_day() + compute_premarket_brief()
and adds the key liquidity gate — premarket $-volume — plus the gap, premarket
high/low, and the prior-day/-week levels (PDH/PDL/PWH/PWL) so the plan is set.

The top gappers are enriched with a news catalyst (Finnhub /company-news).
Persisted as a PremarketGapSnapshot (mirrors SocialBuzzSnapshot). Pure helpers
(bucket / filter / $-volume) are unit-testable without pandas or the DB.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Filters — premarket is thin, so the liquidity floor is modest but non-zero
# (a big gap on no premarket volume is an untradeable trap).
GAP_MIN_PCT = 2.0            # |gap%| from prior close
PM_DOLLAR_VOL_MIN = 100_000.0   # premarket $-volume floor (liquidity gate)
PRICE_MIN = 2.0             # skip sub-$2 penny pumps
TOP_N = 40                  # cap the board
TOP_ENRICH_NEWS = 15        # only fetch a catalyst for the top N gappers

# Market-cap floor — the board should be STABLE, liquid names, not sub-$3B small
# caps / penny gappers that leak in via the market-wide movers broadening. The
# curated mega/large-cap universes are TRUSTED (no lookup); everything else
# (movers, most-actives, watchlist adds) must clear this floor or it's dropped.
# Tunable via env; a value of 0 disables the gate.
MARKET_CAP_MIN = float(os.getenv("PM_GAP_MARKET_CAP_MIN") or 3_000_000_000.0)


# ── Pure helpers (no pandas / no DB — unit-testable) ─────────────────
def bucket_for(symbol: str, momentum_symbols: set[str]) -> str:
    """A symbol's bucket = the curated list it belongs to."""
    return "momentum" if symbol.upper() in momentum_symbols else "clean"


def pm_dollar_volume(closes: list[float], volumes: list[float]) -> float:
    """Premarket traded dollar-volume = Σ close*volume across PM bars."""
    return float(sum((c or 0) * (v or 0) for c, v in zip(closes, volumes)))


def passes_gap_filters(gap_pct: Optional[float], pm_dollar_vol: float, price: Optional[float],
                       gap_min: float = GAP_MIN_PCT, vol_min: float = PM_DOLLAR_VOL_MIN,
                       price_min: float = PRICE_MIN) -> bool:
    if gap_pct is None or price is None:
        return False
    return abs(gap_pct) >= gap_min and pm_dollar_vol >= vol_min and price >= price_min


# ── Market-cap + sector gate (Finnhub /stock/profile2 — cloud-safe) ──
# The AI / tech space the user wants to focus on, matched on Finnhub industry.
_AI_INDUSTRIES = ("semiconductor", "technology", "software", "communications",
                  "electronic", "hardware", "internet", "media")


def passes_market_cap(symbol: str, market_cap: Optional[float], trusted: set[str],
                      floor: float = MARKET_CAP_MIN) -> bool:
    """Trusted curated large caps always pass; everything else must clear the
    floor. Unknown market cap on a non-trusted name = drop (fail-closed — we
    want stable, verified names, not maybes)."""
    if floor <= 0 or symbol.upper() in trusted:
        return True
    return market_cap is not None and market_cap >= floor


def is_ai_space(industry: Optional[str]) -> bool:
    """True if the Finnhub industry is in the AI / tech-and-business space."""
    ind = (industry or "").lower()
    return any(k in ind for k in _AI_INDUSTRIES)


def _finnhub_profile(symbol: str) -> tuple[Optional[float], Optional[str]]:
    """(market_cap_usd, industry) from Finnhub /stock/profile2. (None, None) on miss.
    marketCapitalization is reported in MILLIONS of USD."""
    from analytics.earnings_fetcher import _get

    data = _get("/stock/profile2", {"symbol": symbol})
    if not isinstance(data, dict):
        return None, None
    mc = data.get("marketCapitalization")
    industry = data.get("finnhubIndustry") or None
    return (float(mc) * 1e6 if mc else None), industry


# ── News catalyst (Finnhub, shared token bucket) ─────────────────────
def _latest_headline(symbol: str) -> Optional[str]:
    """Most-recent company-news headline (last ~3 days). None on miss/failure."""
    from analytics.earnings_fetcher import _get

    today = date.today()
    data = _get("/company-news", {
        "symbol": symbol,
        "from": (today - timedelta(days=3)).isoformat(),
        "to": today.isoformat(),
    })
    if not isinstance(data, list) or not data:
        return None
    # Finnhub returns newest-first-ish; pick the max by datetime to be safe.
    try:
        newest = max(data, key=lambda a: a.get("datetime") or 0)
    except (TypeError, ValueError):
        newest = data[0]
    headline = (newest.get("headline") or "").strip()
    return headline[:160] or None


# ── Orchestrator (mirrors analytics/social_buzz.refresh_social_buzz) ──
def refresh_premarket_gaps(session_factory) -> dict:
    """Scan watchlist ∪ universe for premarket gappers, persist a snapshot.
    Returns a summary dict for cron logging.
    """
    from sqlalchemy import select
    from app.models.premarket_gap import PremarketGapSnapshot
    from app.models.watchlist import WatchlistItem
    from analytics.intraday_data import (
        fetch_premarket_bars, fetch_prior_day, compute_premarket_brief, _fetch_prior_levels_alpaca,
    )
    from analytics.screener import MEGA_CAP_UNIVERSE, STATIC_UNIVERSE, SMALL_CAP_UNIVERSE

    summary = {"scanned": 0, "gappers": 0, "enriched": 0, "fetch_failures": 0,
               "empty_pm": 0, "no_prior": 0, "no_gap": 0, "small_cap": 0, "snapshot_id": None}

    momentum_symbols = {s.upper() for s in SMALL_CAP_UNIVERSE}

    with session_factory() as session:
        wl_rows = session.execute(select(WatchlistItem.symbol).distinct()).all()
        watchlist = {r[0].upper() for r in wl_rows if r[0]}

        universe = set(MEGA_CAP_UNIVERSE) | set(STATIC_UNIVERSE) | momentum_symbols
        # Broaden the board beyond the curated lists with Alpaca's LIVE movers +
        # most-actives — the day's biggest gappers market-wide (which is exactly
        # what a gap board should surface). Defensive: each returns [] if the
        # endpoint is unavailable, so we degrade to the curated universe.
        try:
            from app.services.screener_service import _fetch_most_actives, _fetch_market_movers
        except ImportError:  # path differs depending on how the worker is launched
            from api.app.services.screener_service import _fetch_most_actives, _fetch_market_movers
        try:
            universe |= {s.upper() for s in (_fetch_market_movers(top=50) or [])}
            universe |= {s.upper() for s in (_fetch_most_actives(top=100) or [])}
        except Exception:
            pass  # screener helpers failed → curated universe only

        symbols = sorted(watchlist | universe)
        summary["scanned"] = len(symbols)

        entries: list[dict] = []
        for sym in symbols:
            if sym.endswith("-USD"):
                continue  # crypto has no premarket gap concept here
            try:
                pm_bars = fetch_premarket_bars(sym)
                if pm_bars is None or pm_bars.empty:
                    summary["empty_pm"] += 1  # #271 diag: empty fetch is a silent skip
                    continue
                # Alpaca levels first (cloud-safe); yfinance fetch_prior_day is a
                # local-dev fallback (IP-blocked on cloud → blank board).
                prior = _fetch_prior_levels_alpaca(sym) or fetch_prior_day(sym)
                if not prior:
                    summary["no_prior"] += 1
                    continue
                brief = compute_premarket_brief(sym, pm_bars, prior)
                if not brief:
                    continue
            except Exception:
                summary["fetch_failures"] += 1
                logger.debug("premarket gap scan failed for %s", sym, exc_info=True)
                continue

            closes = [float(x) for x in pm_bars["Close"].tolist()]
            vols = [float(x) for x in pm_bars["Volume"].tolist()]
            pm_vol = float(sum(vols))
            pm_dvol = pm_dollar_volume(closes, vols)

            if not passes_gap_filters(brief.get("gap_pct"), pm_dvol, brief.get("pm_last")):
                summary["no_gap"] += 1  # had data but gap%/$-vol below the floor
                continue

            entries.append({
                "symbol": sym,
                "bucket": bucket_for(sym, momentum_symbols),
                "on_watchlist": sym in watchlist,
                "gap_pct": brief.get("gap_pct"),
                "gap_type": brief.get("gap_type"),
                "pm_last": brief.get("pm_last"),
                "pm_high": brief.get("pm_high"),
                "pm_low": brief.get("pm_low"),
                "pm_change_pct": brief.get("pm_change_pct"),
                "pm_volume": int(pm_vol),
                "pm_dollar_vol": round(pm_dvol, 0),
                "prior_close": round(float(prior.get("close") or 0), 2) or None,
                "pdh": round(float(prior["high"]), 2) if prior.get("high") else None,
                "pdl": round(float(prior["low"]), 2) if prior.get("low") else None,
                "pwh": round(float(prior["prior_week_high"]), 2) if prior.get("prior_week_high") else None,
                "pwl": round(float(prior["prior_week_low"]), 2) if prior.get("prior_week_low") else None,
                "flags": brief.get("flags") or [],
                "catalyst": None,   # filled for the top N below
                "market_cap": None,  # filled during the market-cap gate below
                "sector": None,      # Finnhub industry
                "is_ai": False,      # AI / tech-and-business space (user focus)
            })

        # Rank by gap magnitude, then apply the market-cap floor + sector/AI tag.
        # Trusted curated large caps skip the Finnhub lookup and always qualify;
        # everything else (movers, most-actives, watchlist) must clear ≥ $3B or
        # it's dropped as a small cap. Walk the ranked list so we only hit
        # Finnhub until the board is full (bounded by LOOKUP_BUDGET).
        entries.sort(key=lambda e: abs(e.get("gap_pct") or 0), reverse=True)
        trusted = {s.upper() for s in MEGA_CAP_UNIVERSE} | {s.upper() for s in STATIC_UNIVERSE}
        LOOKUP_BUDGET = 80
        kept: list[dict] = []
        lookups = 0
        for e in entries:
            if len(kept) >= TOP_N or lookups >= LOOKUP_BUDGET:
                break
            sym = e["symbol"]
            mc, industry = None, None
            if MARKET_CAP_MIN > 0:
                try:
                    mc, industry = _finnhub_profile(sym)
                    lookups += 1
                except Exception:
                    logger.debug("profile fetch failed for %s", sym, exc_info=True)
            if not passes_market_cap(sym, mc, trusted):
                summary["small_cap"] += 1
                continue
            e["market_cap"] = mc
            e["sector"] = industry
            e["is_ai"] = is_ai_space(industry)
            kept.append(e)
        # AI / tech space first (user focus), then by gap magnitude.
        kept.sort(key=lambda e: (1 if e.get("is_ai") else 0, abs(e.get("gap_pct") or 0)), reverse=True)
        entries = kept
        summary["gappers"] = len(entries)

        # Catalyst enrichment — only the top N (one Finnhub call each, throttled).
        for e in entries[:TOP_ENRICH_NEWS]:
            try:
                e["catalyst"] = _latest_headline(e["symbol"])
                if e["catalyst"]:
                    summary["enriched"] += 1
            except Exception:
                logger.debug("catalyst fetch failed for %s", e["symbol"], exc_info=True)

        snap = PremarketGapSnapshot(captured_at=datetime.utcnow(), entries=entries)
        session.add(snap)
        session.commit()
        session.refresh(snap)
        summary["snapshot_id"] = snap.id

    logger.info("Premarket gaps refresh: %s", summary)
    return summary
