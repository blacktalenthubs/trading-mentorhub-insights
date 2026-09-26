"""Today-tab integration: writes the scan into ``market_reports``.

The Today tab (web/src/pages/TodayPage.tsx) renders one section per
``market_reports.kind`` — each a JSON body keyed on ``(kind, session_date)`` and
served by ``GET /api/v1/intel/market-report/latest``. This module is the
scanner's producer into that same pipeline under ``kind = "breakout_patterns"``.

Idempotency: the row for a session date is UPSERTed, so a re-run replaces that
day's rows wholesale. Within the body, rows are unique on ``(ticker, pattern)``
(highest score wins), which together with the session_date key gives the
``(ticker, pattern, scan_date)`` uniqueness the spec asks for.

Empty state: when nothing qualifies the body is still written with
``empty: true`` and a ``message`` so the tab shows "No qualified setups today"
instead of yesterday's rows.

DB access goes through the root ``db.get_db()`` wrapper, which is SQLite locally
and Postgres when ``DATABASE_URL`` is set (``?`` params are translated).
"""

from __future__ import annotations

import csv
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterable, Optional

from patterns.common import STAGE_BREAKOUT, STAGE_FORMING

logger = logging.getLogger("patterns.today_writer")

REPORT_KIND = "breakout_patterns"
EMPTY_MESSAGE = "No qualified setups today"

ROW_COLUMNS = (
    "ticker", "pattern", "stage", "buy_point", "last_close", "pct_to_buy",
    "suggested_stop", "risk_pct", "rvol", "volume_ok", "base_depth_pct",
    "base_length_days", "rsi14", "dist_from_200sma_pct", "score", "reason",
    "scanned_at", "days_to_earnings", "chart_path",
)

_CREATE_SQL = (
    "CREATE TABLE IF NOT EXISTS market_reports ("
    " kind TEXT NOT NULL,"
    " session_date TEXT NOT NULL,"
    " body TEXT NOT NULL,"
    " created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " PRIMARY KEY (kind, session_date))"
)
_UPSERT_SQL = (
    "INSERT INTO market_reports (kind, session_date, body, created_at) "
    "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
    "ON CONFLICT (kind, session_date) DO UPDATE "
    "SET body = excluded.body, created_at = CURRENT_TIMESTAMP"
)

DbFactory = Callable[[], "contextmanager"]


def _default_db() -> DbFactory:
    import db as _db  # root db.py — dual SQLite/Postgres
    return _db.get_db


def order_rows(rows: Iterable[dict]) -> list[dict]:
    """Breakout rows first, then forming, each sorted by score descending."""
    rank = {STAGE_BREAKOUT: 0, STAGE_FORMING: 1}
    return sorted(rows, key=lambda r: (rank.get(r.get("stage"), 9), -float(r.get("score") or 0.0), r.get("ticker", "")))


def dedupe_rows(rows: Iterable[dict]) -> list[dict]:
    """One row per (ticker, pattern); the highest score wins."""
    best: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["ticker"], r["pattern"])
        if key not in best or float(r.get("score") or 0) > float(best[key].get("score") or 0):
            best[key] = r
    return list(best.values())


def build_body(
    rows: Iterable[dict], *, session_date: str, scanned_at: str, scanned: int,
    funnel: Optional[dict] = None, skipped: Optional[dict] = None, universe: str = "",
) -> dict:
    """The JSON payload the Today tab renders."""
    ordered = order_rows(dedupe_rows(rows))
    return {
        "rows": ordered,
        "scanned": scanned,
        "candidates": (funnel or {}).get("passed", 0),
        "funnel": funnel or {},
        "skipped": skipped or {},
        "universe": universe,
        "session_date": session_date,
        "scanned_at": scanned_at,
        "empty": len(ordered) == 0,
        "message": EMPTY_MESSAGE if not ordered else "",
        "breakouts": sum(1 for r in ordered if r["stage"] == STAGE_BREAKOUT),
        "forming": sum(1 for r in ordered if r["stage"] == STAGE_FORMING),
    }


def write_today(body: dict, session_date: str, db_factory: Optional[DbFactory] = None) -> None:
    """UPSERT ``body`` as the ``breakout_patterns`` report for ``session_date``."""
    get_db = db_factory or _default_db()
    payload = json.dumps(body, default=str)
    with get_db() as conn:
        conn.execute(_CREATE_SQL)
        conn.execute(_UPSERT_SQL, (REPORT_KIND, session_date, payload))
    logger.info("breakout_patterns: wrote %d row(s) for %s (%s)", len(body.get("rows", [])),
                session_date, "empty" if body.get("empty") else "ok")


def read_today(session_date: str, db_factory: Optional[DbFactory] = None) -> Optional[dict]:
    """Read back the report body for ``session_date`` (None if absent)."""
    get_db = db_factory or _default_db()
    with get_db() as conn:
        cur = conn.execute(
            "SELECT body FROM market_reports WHERE kind = ? AND session_date = ?",
            (REPORT_KIND, session_date),
        )
        row = cur.fetchone()
    if not row:
        return None
    raw = row[0] if not hasattr(row, "keys") else row["body"]
    return json.loads(raw)


def count_rows_for_date(session_date: str, db_factory: Optional[DbFactory] = None) -> int:
    """How many market_reports rows exist for this kind + date (idempotency check)."""
    get_db = db_factory or _default_db()
    with get_db() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM market_reports WHERE kind = ? AND session_date = ?",
            (REPORT_KIND, session_date),
        )
        row = cur.fetchone()
    return int(row[0])


def write_csv(rows: Iterable[dict], path: str | Path) -> Path:
    """Secondary output: a flat CSV of the ordered rows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ROW_COLUMNS), extrasaction="ignore")
        w.writeheader()
        for r in order_rows(rows):
            w.writerow(r)
    return path
