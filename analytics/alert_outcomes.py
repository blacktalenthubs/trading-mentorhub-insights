"""Compute REAL outcomes for fired alerts from post-fire price action.

The problem this solves: our alerts ship with fixed-percent T1/T2 targets
(entry * 1.005 etc.) that don't reflect actual outcomes. Asking "did
T1 hit" against synthetic targets gives a meaningless win rate.

The fix: for each long alert at fire-time T with entry E and stop S,
fetch the post-fire 5m bars from Alpaca, walk forward bar by bar, and
classify in R-multiples:
  R = (price - E) / (E - S)   for LONG
  MFE  = max R reached         (max favorable excursion)
  MAE  = min R reached         (max adverse excursion — negative number)
  Outcome:
    'worked'        if MFE first reaches +1.0R before MAE reaches -1.0R
    'failed'        if MAE first reaches -1.0R before MFE reaches +1.0R
    'inconclusive'  if neither threshold crossed by 16:00 ET (or last bar)

Run nightly @ 4:30 PM ET as the swing_scan_eod cron's neighbor. Free
to re-run any time — idempotent (only updates rows where real_outcome
is NULL).

API budget: alerts are grouped by symbol, so one Alpaca session-bars call
per (symbol, session_date) regardless of how many alerts fired on that
combo. ~30 symbols × 1 call = 30 calls/day. Well under any quota.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, or_, select, update

from analytics.intraday_data import _fetch_alpaca_bars_for_date


logger = logging.getLogger(__name__)

R_TARGET = 1.0   # MFE must reach +R_TARGET to be "worked"
R_STOP = -1.0    # MAE reaching R_STOP first is "failed"


def _classify_long(bars, entry: float, stop: float, fired_at: datetime) -> dict:
    """Walk bars after fired_at, return outcome dict. `bars` is a pandas
    DataFrame with naive ET index + [Open, High, Low, Close] columns.
    """
    if entry is None or stop is None or entry == stop:
        return {"real_outcome": None, "mfe_r": None, "mae_r": None}

    risk = entry - stop
    if risk <= 0:
        # Risk has to be positive for a long (entry > stop).
        return {"real_outcome": None, "mfe_r": None, "mae_r": None}

    # Naive ET comparison — both bars index and fired_at are ET.
    fired_naive = fired_at.replace(tzinfo=None) if fired_at.tzinfo else fired_at
    forward = bars[bars.index > fired_naive]
    if len(forward) == 0:
        return {"real_outcome": "inconclusive", "mfe_r": 0.0, "mae_r": 0.0}

    mfe_r = 0.0
    mae_r = 0.0
    outcome: Optional[str] = None

    for _, row in forward.iterrows():
        # Per-bar high and low both contribute to MFE/MAE.
        bar_high_r = (row["High"] - entry) / risk
        bar_low_r = (row["Low"] - entry) / risk
        if bar_high_r > mfe_r:
            mfe_r = bar_high_r
        if bar_low_r < mae_r:
            mae_r = bar_low_r

        # First-cross logic: whichever threshold the bar touches first wins.
        # Within the same bar we don't know intra-bar order, so use the rule:
        # if both touched in same bar, "failed" wins (conservative for outcome
        # quality — most stop-outs are real, target hits in the same bar
        # often mean a wick that didn't actually close above).
        if bar_low_r <= R_STOP:
            outcome = "failed"
            break
        if bar_high_r >= R_TARGET:
            outcome = "worked"
            break

    if outcome is None:
        outcome = "inconclusive"

    return {
        "real_outcome": outcome,
        "mfe_r": round(mfe_r, 3),
        "mae_r": round(mae_r, 3),
    }


def compute_outcomes_for_session(session_factory, session_date: date,
                                  symbols_filter: Optional[set[str]] = None) -> dict:
    """Compute real_outcome for every alert fired on `session_date` that
    doesn't already have one. Returns summary dict for logging.

    Strategy:
      1. Pull (symbol, alert_rows) groups from the DB for that date.
      2. For each symbol, fetch Alpaca session bars ONCE.
      3. Walk every alert's window within that bar series.
      4. Bulk-update at end.
    """
    from app.models.alert import Alert

    summary = {
        "session_date": session_date.isoformat(),
        "alerts_seen": 0,
        "alerts_updated": 0,
        "symbols": 0,
        "fetch_failures": 0,
    }

    with session_factory() as session:
        rows = session.execute(
            select(Alert).where(
                Alert.session_date == session_date.isoformat(),
                Alert.real_outcome.is_(None),
                # LONG-only for v1 (entry/stop math assumes entry > stop).
                or_(Alert.direction == "BUY", Alert.direction == "LONG"),
                Alert.entry.isnot(None),
                Alert.stop.isnot(None),
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
                bars = _fetch_alpaca_bars_for_date(symbol, session_date)
            except Exception:
                summary["fetch_failures"] += 1
                logger.exception("Outcome fetch failed for %s on %s", symbol, session_date)
                continue
            if bars is None or len(bars) == 0:
                summary["fetch_failures"] += 1
                continue

            for a in alerts:
                result = _classify_long(bars, a.entry, a.stop, a.created_at)
                if result["real_outcome"] is None:
                    continue
                a.real_outcome = result["real_outcome"]
                a.mfe_r = result["mfe_r"]
                a.mae_r = result["mae_r"]
                a.outcome_computed_at = datetime.utcnow()
                summary["alerts_updated"] += 1

        session.commit()

    logger.info(
        "Outcome compute %s: %d alerts seen, %d updated across %d symbols, %d fetch failures",
        session_date, summary["alerts_seen"], summary["alerts_updated"],
        summary["symbols"], summary["fetch_failures"],
    )
    return summary
