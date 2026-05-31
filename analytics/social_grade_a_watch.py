"""Social + Grade-A push notifier.

Sibling to the in-play screener. Every 5 min during market hours:
  1. Read the latest social_buzz_snapshot (top trending symbols).
  2. For each symbol, pull intraday 5m bars from Alpaca.
  3. Compute volume_ratio + vwap_slope_pct.
  4. Run compute_grade() — same function the TV alerts + in-play screener use.
  5. If grade == 'A' AND we haven't already pushed for this (symbol, today),
     fire the special push: "🔥 SYM trending + Grade A".
  6. Mark the (symbol, today) row in ScreenerAlertLog with kind='social_a'
     so we never push twice for the same symbol same day.

Why this is the right shape (rather than gating on TV chart presence):
The whole point is to catch setups on stocks the user ISN'T watching but
that are trending. Server-side scan is the only way to do this without
requiring users to maintain TV setups for every popular ticker.

Dedup key (ScreenerAlertLog kind='social_a') makes the push idempotent:
re-running the cron mid-day doesn't re-fire for a symbol already pushed.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import desc, select, text
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# How many of the top buzz symbols to scan each cycle. Hardcoded vs config
# because the social_buzz_snapshot table only ever stores top 25, and
# pushing on rank 20+ tickers means very thin retail attention — not the
# "everyone is talking about this" signal we want.
TOP_BUZZ_TO_SCAN = 10


def _is_market_open() -> bool:
    """Mon-Fri 09:30-16:00 ET. Conservative — skips holidays via the cron's
    misfire grace, not a calendar check, which is fine for this best-effort job.
    """
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return t >= datetime.strptime("09:30", "%H:%M").time() and t <= datetime.strptime("16:00", "%H:%M").time()


def _load_top_buzz_symbols(session) -> list[str]:
    """Read the latest snapshot's top N entries. Return symbols newest-first."""
    from app.models.social_buzz import SocialBuzzSnapshot

    row = session.execute(
        select(SocialBuzzSnapshot)
        .order_by(desc(SocialBuzzSnapshot.captured_at))
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return []
    entries = row.entries or []
    return [e.get("symbol") for e in entries[:TOP_BUZZ_TO_SCAN] if e.get("symbol")]


def _score_symbol(symbol: str) -> Optional[tuple[str, float, float]]:
    """Fetch intraday bars + compute (grade, vol_ratio, vwap_slope_pct).
    Returns None if data is unavailable. Crypto symbols skipped — the
    grade function is calibrated for equities (different vol distributions).
    """
    if symbol.endswith("-USD"):
        return None

    from analytics.intraday_data import fetch_intraday
    from analytics.alert_grade import compute_grade

    try:
        intraday = fetch_intraday(symbol, period="1d", interval="5m")
    except Exception:
        logger.debug("social_a: fetch_intraday failed for %s", symbol, exc_info=True)
        return None
    if intraday is None or intraday.empty or len(intraday) < 7:
        return None

    # Volume ratio — today's cumulative session volume vs 20-day average.
    # Use the same lookback the existing screener uses for consistency.
    try:
        today_vol = float(intraday["Volume"].sum())
        # No clean way to get 20-day avg from a 1-day intraday pull, so fall
        # back to a recent-period mean from longer pull. Cheap second call.
        wider = fetch_intraday(symbol, period="20d", interval="1d")
        if wider is None or wider.empty:
            avg_daily = today_vol  # forces vol_ratio = 1.0 (neutral)
        else:
            avg_daily = float(wider["Volume"].tail(20).mean())
        vol_ratio = today_vol / avg_daily if avg_daily > 0 else 1.0
    except Exception:
        logger.debug("social_a: vol ratio compute failed for %s", symbol, exc_info=True)
        return None

    # Session VWAP slope (% change over last ~30 min = 6 × 5m bars).
    try:
        vwap_series = (intraday["Close"] * intraday["Volume"]).cumsum() / intraday["Volume"].cumsum()
        if len(vwap_series) < 7 or float(vwap_series.iloc[-7]) == 0:
            slope = 0.0
        else:
            slope = ((float(vwap_series.iloc[-1]) - float(vwap_series.iloc[-7])) / float(vwap_series.iloc[-7])) * 100
    except Exception:
        slope = 0.0

    grade = compute_grade(vol_ratio, slope)
    return grade, vol_ratio, slope


def _already_pushed(session, symbol: str, today_iso: str) -> bool:
    from app.models.screener import ScreenerAlertLog

    row = session.get(ScreenerAlertLog, (symbol, "social_a", today_iso))
    return row is not None


def _record_push(session, symbol: str, today_iso: str) -> None:
    from app.models.screener import ScreenerAlertLog

    session.add(ScreenerAlertLog(
        symbol=symbol, kind="social_a", session_date=today_iso,
    ))


def _push_to_all_users(session, symbol: str, vol_ratio: float, slope: float) -> int:
    """Fire push to every user with push_enabled + active device tokens.
    Mirrors the pattern in earnings_refresh._send_t7_notifications.
    Returns count of devices pushed.
    """
    from app.models.user import User
    from app.models.device_token import DeviceToken
    from app.services.push_service import send_push_sync

    users = session.execute(
        select(User).where(User.push_enabled == True)  # noqa: E712
    ).scalars().all()
    if not users:
        return 0

    sign = "+" if slope >= 0 else ""
    title = f"🔥 {symbol} — Social + Grade A"
    body = (
        f"Trending on retail social AND just fired Grade A. "
        f"Vol {vol_ratio:.1f}× · VWAP slope {sign}{slope:.2f}%."
    )

    sent = 0
    for u in users:
        tokens = [t.token for t in session.execute(
            select(DeviceToken).where(
                DeviceToken.user_id == u.id,
                DeviceToken.is_active == True,  # noqa: E712
            )
        ).scalars().all()]
        if not tokens:
            continue
        try:
            send_push_sync(
                tokens, title, body,
                data={"symbol": symbol, "kind": "social_grade_a"},
                thread_id="social_grade_a",
            )
            sent += len(tokens)
        except Exception:
            logger.exception("social_a push failed for user %d / %s", u.id, symbol)
    return sent


def check_social_grade_a(session_factory) -> dict:
    """Entrypoint for the APScheduler cron. Returns summary dict for logging."""
    summary = {"scanned": 0, "graded_a": 0, "pushed": 0, "devices_sent": 0,
               "skipped_market_closed": False, "skipped_no_buzz": False}

    if not _is_market_open():
        summary["skipped_market_closed"] = True
        return summary

    today_iso = date.today().isoformat()

    with session_factory() as session:
        symbols = _load_top_buzz_symbols(session)
        if not symbols:
            summary["skipped_no_buzz"] = True
            return summary
        summary["scanned"] = len(symbols)

        for sym in symbols:
            scored = _score_symbol(sym)
            if scored is None:
                continue
            grade, vol_ratio, slope = scored
            if grade != "A":
                continue
            summary["graded_a"] += 1

            if _already_pushed(session, sym, today_iso):
                continue

            devices = _push_to_all_users(session, sym, vol_ratio, slope)
            if devices > 0:
                summary["devices_sent"] += devices
            summary["pushed"] += 1
            _record_push(session, sym, today_iso)

        session.commit()

    logger.info("social_a check: %s", summary)
    return summary
