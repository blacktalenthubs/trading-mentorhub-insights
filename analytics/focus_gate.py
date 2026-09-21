"""Focus-driven alert gate — the names that get the curated 1h SMA, weekly/monthly level,
and hourly volume-profile (POC/VAL/VWAP/VAH) alerts are the trader's FOCUS watchlist, so
the gate is managed by starring names in the app (no code edit to add a name).

Reads the admin user's `watchlist.focus = true` symbols, cached with a short TTL. Falls
back to the static LEVEL_ALERT_SYMBOLS when the DB is unavailable — and in tests, which
never hit the DB, so the gate there is exactly the static set (deterministic).
"""
from __future__ import annotations

import os
import time

from alert_config import LEVEL_ALERT_SYMBOLS

_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "mentorhubnetworks@gmail.com")
_TTL_SEC = 300.0
_cache: dict = {"at": 0.0, "syms": None}


def _fallback() -> set[str]:
    return {s.upper() for s in LEVEL_ALERT_SYMBOLS}


def focus_symbols(force: bool = False) -> set[str]:
    """The uppercase set of the admin's focus symbols (5-min cached). Static-set fallback
    on any DB issue or empty focus, so the gate is never accidentally empty."""
    now = time.time()
    if not force and _cache["syms"] is not None and (now - _cache["at"]) < _TTL_SEC:
        return _cache["syms"]
    syms: set[str] | None = None
    try:
        dsn = os.environ.get("DATABASE_URL")
        if dsn:
            import psycopg2
            conn = psycopg2.connect(dsn, connect_timeout=8)
            cur = conn.cursor()
            cur.execute(
                "SELECT UPPER(w.symbol) FROM watchlist w JOIN users u ON u.id = w.user_id "
                "WHERE w.focus AND u.email = %s",
                (_ADMIN_EMAIL,),
            )
            syms = {r[0] for r in cur.fetchall()}
            cur.close(); conn.close()
    except Exception:
        syms = None
    if not syms:                       # DB down, no rows, or misconfig → never empty
        syms = _fallback()
    _cache["syms"] = syms
    _cache["at"] = now
    return syms
