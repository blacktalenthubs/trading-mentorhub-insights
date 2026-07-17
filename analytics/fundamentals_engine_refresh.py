"""Fundamentals Engine nightly orchestrator.

For each distinct watchlist symbol:
  1. EDGAR: ticker → CIK → companyfacts → normalised periods (cached/throttled).
  2. Upsert the per-period financials (idempotent on symbol+period_end+form).
  3. Compute metrics + score + flags (pure engine).
  4. Upsert metrics / score / flags.
  5. Detect flags that are NEW vs the previous run and fire a red-flag alert
     (reuses the notifier's low-level Telegram sender — does NOT modify the
     protected notifier business logic).

Idempotent: re-running the same night updates rows in place and re-notifies
nothing (a flag already recorded for a prior as-of date is not "new"). Any
single symbol that fails is logged and skipped so the batch continues.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from sqlalchemy import select

from analytics.edgar_client import load_financials, ticker_to_cik
from analytics.fundamentals_metrics import PeriodFinancials, compute_metrics
from analytics.fundamentals_scoring import CRITICAL, WARN, Flag, ScoreResult, score_company
from fundamentals_config import get_config

logger = logging.getLogger(__name__)

# Concept columns copied straight from PeriodFinancials → FundFinancials.
_LINE_ITEMS = (
    "revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income",
    "interest_expense", "operating_cash_flow", "capex", "inventory", "receivables",
    "total_current_assets", "total_current_liabilities", "total_assets",
    "total_liabilities", "cash", "short_term_debt", "long_term_debt",
    "stockholders_equity", "shares_diluted",
)


def _distinct_watchlist_symbols(session) -> List[str]:
    from app.models.watchlist import WatchlistItem

    rows = session.execute(select(WatchlistItem.symbol).distinct()).all()
    return sorted({r[0].upper() for r in rows if r[0]})


def _upsert_company(session, symbol: str, cik: Optional[int], has_data: bool) -> None:
    from app.models.fundamentals_engine import FundCompany

    row = session.get(FundCompany, symbol)
    if row is None:
        row = FundCompany(symbol=symbol)
        session.add(row)
    row.cik = cik
    row.no_edgar_data = not has_data
    from datetime import datetime as _dt
    row.updated_at = _dt.utcnow()


def _upsert_financials(session, periods: List[PeriodFinancials]) -> int:
    from app.models.fundamentals_engine import FundFinancials

    written = 0
    for p in periods:
        row = session.execute(
            select(FundFinancials).where(
                FundFinancials.symbol == p.symbol,
                FundFinancials.period_end == p.period_end,
                FundFinancials.form == p.form,
            )
        ).scalar_one_or_none()
        if row is None:
            row = FundFinancials(symbol=p.symbol, period_end=p.period_end, form=p.form)
            session.add(row)
        row.fiscal_year = p.fiscal_year
        row.fiscal_period = p.fiscal_period
        row.filed_date = p.filed_date
        row.period_days = p.period_days
        row.accession = p.accession
        row.source_url = p.source_url
        for col in _LINE_ITEMS:
            setattr(row, col, getattr(p, col))
        written += 1
    return written


def _upsert_metrics(session, ms, as_of: date) -> None:
    from app.models.fundamentals_engine import FundMetric

    for name, mv in ms.latest.items():
        row = session.execute(
            select(FundMetric).where(
                FundMetric.symbol == ms.symbol,
                FundMetric.period_end == (mv.period_end or as_of),
                FundMetric.name == name,
            )
        ).scalar_one_or_none()
        if row is None:
            row = FundMetric(symbol=ms.symbol, period_end=mv.period_end or as_of, name=name)
            session.add(row)
        row.value = mv.value
        row.unit = mv.unit
        row.source_url = mv.source_url


def _upsert_score(session, result: ScoreResult, as_of: date, latest_period: Optional[date]) -> None:
    from app.models.fundamentals_engine import FundScore

    row = session.execute(
        select(FundScore).where(FundScore.symbol == result.symbol, FundScore.as_of_date == as_of)
    ).scalar_one_or_none()
    if row is None:
        row = FundScore(symbol=result.symbol, as_of_date=as_of)
        session.add(row)
    row.quality_score = result.quality_score
    row.risk_score = result.risk_score
    row.profitable = result.profitable
    row.quality_coverage = result.quality_coverage
    row.risk_coverage = result.risk_coverage
    row.latest_period_end = latest_period


def _persist_flags_and_find_new(session, result: ScoreResult, as_of: date) -> List[Flag]:
    """Insert today's flags; return the ones NOT present on the most recent
    PRIOR as-of date (genuinely new red flags worth an alert)."""
    from app.models.fundamentals_engine import FundFlag

    prior_codes = set(
        session.execute(
            select(FundFlag.code)
            .where(FundFlag.symbol == result.symbol, FundFlag.as_of_date < as_of)
            .order_by(FundFlag.as_of_date.desc())
            .limit(50)
        ).scalars().all()
    )

    new_flags: List[Flag] = []
    for f in result.flags:
        existing = session.execute(
            select(FundFlag).where(
                FundFlag.symbol == result.symbol,
                FundFlag.code == f.code,
                FundFlag.as_of_date == as_of,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(FundFlag(
                symbol=result.symbol, code=f.code, severity=f.severity,
                label=f.label, detail=f.detail, metric=f.metric, as_of_date=as_of,
            ))
        if f.code not in prior_codes and f.severity in (WARN, CRITICAL):
            new_flags.append(f)
    return new_flags


def _alert_new_flags(symbol: str, new_flags: List[Flag]) -> None:
    """Fire a Telegram digest for newly-appeared red flags.

    Reuses the notifier's low-level default-chat sender rather than touching the
    protected per-user notify pipeline. Best-effort: any failure is logged, not
    raised, so a notification problem never breaks the batch.
    """
    if not new_flags:
        return
    try:
        from alerting.notifier import _send_telegram
    except Exception:  # pragma: no cover - notifier optional in some contexts
        logger.info("notifier unavailable; skipping fundamentals alert for %s", symbol)
        return

    lines = [f"🔎 New fundamental red flag — {symbol}"]
    for f in new_flags:
        icon = "🚩" if f.severity == CRITICAL else "⚠️"
        lines.append(f"{icon} {f.label}" + (f" — {f.detail}" if f.detail else ""))
    lines.append("\nEducation only, not financial advice.")
    try:
        _send_telegram("\n".join(lines))
    except Exception:
        logger.exception("Failed to send fundamentals alert for %s", symbol)


def refresh_symbol(
    session,
    symbol: str,
    as_of: date,
    *,
    market_cap: Optional[float] = None,
    price: Optional[float] = None,
    notify: bool = True,
) -> Optional[ScoreResult]:
    """Full pipeline for one symbol. Returns the ScoreResult, or None if there
    was no EDGAR data to work with."""
    symbol = symbol.upper()
    cfg = get_config()

    periods = load_financials(symbol, max_periods=cfg.red_flags.trend_lookback_quarters + 4)
    if not periods:
        _upsert_company(session, symbol, ticker_to_cik(symbol), has_data=False)
        return None

    _upsert_company(session, symbol, ticker_to_cik(symbol), has_data=True)
    _upsert_financials(session, periods)

    ms = compute_metrics(
        periods, market_cap=market_cap, price=price,
        pe_multiple=cfg.value.intrinsic_pe_multiple,
    )
    result = score_company(ms, cfg)

    _upsert_metrics(session, ms, as_of)
    _upsert_score(session, result, as_of, ms.as_of)
    new_flags = _persist_flags_and_find_new(session, result, as_of)

    if notify:
        _alert_new_flags(symbol, new_flags)
    return result


def refresh_all(session_factory, *, as_of: Optional[date] = None, notify: bool = True) -> dict:
    """Nightly entry point. Refreshes every distinct watchlist symbol.

    ``as_of`` defaults to the caller-provided run date; callers pass
    ``date.today()`` (kept as a param so the engine core stays clock-free and
    testable).
    """
    if as_of is None:
        from datetime import datetime as _dt
        as_of = _dt.utcnow().date()

    summary = {"symbols": 0, "scored": 0, "no_data": 0, "failures": 0, "new_flags": 0}
    with session_factory() as session:
        symbols = _distinct_watchlist_symbols(session)
        summary["symbols"] = len(symbols)
        for symbol in symbols:
            try:
                result = refresh_symbol(session, symbol, as_of, notify=notify)
                if result is None:
                    summary["no_data"] += 1
                else:
                    summary["scored"] += 1
                session.commit()
            except Exception:
                session.rollback()
                summary["failures"] += 1
                logger.exception("Fundamentals engine failed for %s — continuing", symbol)
    logger.info(
        "Fundamentals engine complete: %d symbols, %d scored, %d no-data, %d failures",
        summary["symbols"], summary["scored"], summary["no_data"], summary["failures"],
    )
    return summary
