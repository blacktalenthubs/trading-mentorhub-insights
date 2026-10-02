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

# The account whose FOCUS drives the gate = the trader's live/telegram account. Its OWN
# env (not ADMIN_EMAIL, which is the admin login) so the two can't collide.
_FOCUS_EMAIL = os.environ.get("FOCUS_ACCOUNT_EMAIL", "vbolofinde@gmail.com")
_TTL_SEC = 300.0
_cache: dict = {"at": 0.0, "syms": None}
_tier_cache: dict = {"at": 0.0, "tiers": None}


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
                (_FOCUS_EMAIL,),
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


def focus_tiers(force: bool = False) -> dict[str, int]:
    """{UPPER(symbol): tier} for the admin's focus names — tier 1 = A (core, Telegram),
    2 = B (watch, app feed only). A focus row with a NULL focus_tier is treated as A (1)
    so a half-migrated DB still delivers. 5-min cached. On any DB issue returns {} — the
    caller then treats every focus symbol as A (safe default: keep delivering to Telegram)."""
    now = time.time()
    if not force and _tier_cache["tiers"] is not None and (now - _tier_cache["at"]) < _TTL_SEC:
        return _tier_cache["tiers"]
    tiers: dict[str, int] | None = None
    try:
        dsn = os.environ.get("DATABASE_URL")
        if dsn:
            import psycopg2
            conn = psycopg2.connect(dsn, connect_timeout=8)
            cur = conn.cursor()
            cur.execute(
                "SELECT UPPER(w.symbol), COALESCE(w.focus_tier, 1) "
                "FROM watchlist w JOIN users u ON u.id = w.user_id "
                "WHERE w.focus AND u.email = %s",
                (_FOCUS_EMAIL,),
            )
            tiers = {r[0]: int(r[1]) for r in cur.fetchall()}
            cur.close(); conn.close()
    except Exception:
        tiers = None
    if tiers is None:
        tiers = {}
    _tier_cache["tiers"] = tiers
    _tier_cache["at"] = now
    return tiers


def focus_tier_of(symbol: str) -> int | None:
    """Tier for ONE symbol: 1 (A), 2 (B), or None (not in focus). A not-in-focus name is
    scanned (canary/universe) but should NOT be delivered. On a DB miss (tiers == {}) a focus
    symbol isn't known, so fall back to focus_symbols(): in-focus → A (1), else None — this
    keeps Telegram delivery alive for focus names even if the tier read failed."""
    s = symbol.upper()
    tiers = focus_tiers()
    if s in tiers:
        return tiers[s]
    if not tiers:                      # tier read failed → lean on focus membership, default A
        return 1 if s in focus_symbols() else None
    return None                        # tiers known and symbol absent → genuinely not in focus
