"""Compute REAL forward returns for fired alerts — close-to-close.

The problem: alerts ship with fixed-percent T1/T2 targets that don't reflect
real outcomes, and the intraday outcome (analytics/alert_outcomes.py) ends at
16:00 ET the same day. To decide which PATTERNS actually work, we need to know
whether the move HELD — measured by the stock's real closing price at end of
day and end of week ("a big rally at EOD/EOW protects the gains").

For each long alert fired on session_date D with fire price P:
  ret_eod_pct = (close(D)            - P) / P * 100
  ret_eow_pct = (close(last bar <= Friday-of-D's-week) - P) / P * 100
Win = the stock closed higher than the fire price (ret > 0).

Mirrors analytics/alert_outcomes.py: batches alerts by symbol (one daily fetch
per symbol), idempotent per-column (only fills NULLs), and only computes a
horizon once it has matured (the week's Friday must have closed for EOW).

The price math lives in pure helpers that take a {date: close} dict — NOT a
DataFrame — so the logic is unit-testable without pandas.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Synthetic outcome alert types are not real setups — never grade them.
_SYNTHETIC_TYPES = (
    "target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out",
    "vwap_loss", "vwap_reclaim",
)


# ── Pure helpers (no pandas / no DB — unit-testable) ─────────────────
def week_friday(session_date: date) -> date:
    """Friday of the alert's Mon-Fri week (mirrors performance._week_bounds)."""
    monday = session_date - timedelta(days=session_date.weekday())  # Mon=0
    return monday + timedelta(days=4)


def is_eow_matured(session_date: date, today: date) -> bool:
    """End-of-week return is only valid once that week's Friday has closed.
    Strictly-after so the Friday daily bar exists; a Friday-fired alert
    matures the next session.
    """
    return today > week_friday(session_date)


def pick_close_on_or_before(closes: dict[date, float], target: date,
                            floor: Optional[date] = None) -> Optional[float]:
    """Close on `target`, else the most recent prior trading day's close
    (handles holidays/half-days). Won't look back past `floor` if given.
    Returns None when no bar <= target (>= floor) exists in the window.
    """
    d = target
    # Don't scan forever — a week of calendar days covers any holiday run.
    limit = floor if floor is not None else (target - timedelta(days=7))
    while d >= limit:
        c = closes.get(d)
        if c is not None:
            return c
        d -= timedelta(days=1)
    return None


def forward_pct(fire_price: float, close_price: Optional[float]) -> Optional[float]:
    """% change from the fire price to a later close. None on bad input."""
    if not fire_price or fire_price <= 0 or close_price is None:
        return None
    return round((close_price / fire_price - 1.0) * 100.0, 3)


def _closes_from_df(df) -> dict[date, float]:
    """Collapse a daily OHLC DataFrame (naive-ET index, Close column) into a
    {date: close} map. Empty dict on empty/missing input.
    """
    if df is None or len(df) == 0 or "Close" not in df.columns:
        return {}
    out: dict[date, float] = {}
    for idx, close in zip(df.index, df["Close"]):
        try:
            out[idx.date()] = float(close)
        except (AttributeError, TypeError, ValueError):
            continue
    return out


# ── Orchestrator (mirrors compute_outcomes_for_session) ──────────────
def compute_forward_returns(session_factory, today: Optional[date] = None,
                            lookback_days: int = 14,
                            symbols_filter: Optional[set[str]] = None) -> dict:
    """Fill ret_eod_pct / ret_eow_pct for long alerts in the lookback window
    that don't yet have them and whose horizon has matured. Idempotent per
    column. Returns a summary dict for logging.

    Each daily run fills today's EOD immediately and backfills any now-matured
    EOW from the prior week, so a single ~14-day lookback catches both.
    """
    from sqlalchemy import or_, select

    from analytics.market_data import fetch_ohlc
    from app.models.alert import Alert

    today = today or date.today()
    window_start = today - timedelta(days=lookback_days)
    summary = {
        "alerts_seen": 0, "eod_filled": 0, "eow_filled": 0,
        "symbols": 0, "fetch_failures": 0,
    }

    with session_factory() as session:
        rows = session.execute(
            select(Alert).where(
                Alert.session_date >= window_start.isoformat(),
                Alert.session_date <= today.isoformat(),
                or_(Alert.ret_eod_pct.is_(None), Alert.ret_eow_pct.is_(None)),
                or_(Alert.direction == "BUY", Alert.direction == "LONG"),
                Alert.price.isnot(None),
                Alert.alert_type.notin_(_SYNTHETIC_TYPES),
            )
        ).scalars().all()
        summary["alerts_seen"] = len(rows)
        if not rows:
            return summary

        by_symbol: dict[str, list] = {}
        for a in rows:
            if symbols_filter and a.symbol not in symbols_filter:
                continue
            by_symbol.setdefault(a.symbol, []).append(a)
        summary["symbols"] = len(by_symbol)

        for symbol, alerts in by_symbol.items():
            try:
                df = fetch_ohlc(symbol, period="3mo", interval="1d")
            except Exception:
                summary["fetch_failures"] += 1
                logger.exception("Forward-return fetch failed for %s", symbol)
                continue
            closes = _closes_from_df(df)
            if not closes:
                summary["fetch_failures"] += 1
                continue

            for a in alerts:
                try:
                    sd = datetime.strptime(a.session_date, "%Y-%m-%d").date()
                except (TypeError, ValueError):
                    continue
                wrote = False

                # EOD — the exact close on the alert's session date (once closed).
                if a.ret_eod_pct is None and sd < today:
                    eod_close = closes.get(sd)
                    pct = forward_pct(a.price, eod_close)
                    if pct is not None:
                        a.ret_eod_pct = pct
                        summary["eod_filled"] += 1
                        wrote = True

                # EOW — close on the last trading day <= that week's Friday,
                # only once the week has closed.
                if a.ret_eow_pct is None and is_eow_matured(sd, today):
                    eow_close = pick_close_on_or_before(closes, week_friday(sd), floor=sd)
                    pct = forward_pct(a.price, eow_close)
                    if pct is not None:
                        a.ret_eow_pct = pct
                        summary["eow_filled"] += 1
                        wrote = True

                if wrote:
                    a.fwd_returns_computed_at = datetime.utcnow()

        session.commit()

    logger.info(
        "Forward returns %s: %d seen, %d EOD, %d EOW across %d symbols, %d fetch failures",
        today, summary["alerts_seen"], summary["eod_filled"],
        summary["eow_filled"], summary["symbols"], summary["fetch_failures"],
    )
    return summary
