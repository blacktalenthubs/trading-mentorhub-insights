"""Premarket sector heat brief — concise actionable Telegram message.

Aggregates per-watchlist-group movement from yfinance, formats into a tight
glanceable message, and sends to each user with telegram_chat_id + groups.

No AI. Deterministic rules:
  - avg_gap > +0.5% AND breadth >= 75% green → "longs focus"
  - avg_gap < -0.5% AND breadth <= 25% green → "avoid / shorts on rejects"
  - everything else → mixed (skip from focus / avoid lists)

Schedule (cron registered in api/app/main.py lifespan): 9:00 AM ET mon-fri.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.user import User
from app.models.watchlist import WatchlistGroup, WatchlistItem

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Threshold tuning — calibrated so a typical sector with ±0.3% intra-day chop
# isn't flagged as "focus". Tighten/widen based on real Telegram noise.
STRONG_MOVE_PCT = 0.5
STRONG_BREADTH_RATIO = 0.75

# Macro tape — broad indexes + sector SPDRs + fear gauge. Fetched in the same
# yfinance batch as the user's watchlist symbols (one HTTP round-trip).
MACRO_INDEXES = ["SPY", "QQQ", "IWM", "DIA", "^VIX"]
MACRO_SECTORS = ["XLK", "XLE", "XLF", "XLV", "XLY", "XLI"]


def _bucket_label(avg_gap: Optional[float]) -> str:
    """Triangle / dash glyph based on average gap %."""
    if avg_gap is None:
        return "·"
    if avg_gap > STRONG_MOVE_PCT:
        return "▲"
    if avg_gap < -STRONG_MOVE_PCT:
        return "▼"
    return "─"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _format_summary_line(s: dict) -> str:
    """One sector line.

    Example: '▲ Optics  +6.7%  3/3  AAOI +11.7%'
    """
    bucket = _bucket_label(s["avg_gap_pct"])
    name = s["name"][:12].ljust(12)
    avg = _fmt_pct(s["avg_gap_pct"]).ljust(7)
    breadth = (
        f"{s['breadth_green']}/{s['breadth_total']}"
        if s["breadth_total"] > 0
        else "—"
    ).ljust(4)

    # Anchor symbol: top mover if up, bottom mover if down, none if flat.
    anchor = ""
    if s["avg_gap_pct"] is not None and s["avg_gap_pct"] > STRONG_MOVE_PCT and s["top_mover"]:
        anchor = f"{s['top_mover']['symbol']} {_fmt_pct(s['top_mover']['gap_pct'])}"
    elif s["avg_gap_pct"] is not None and s["avg_gap_pct"] < -STRONG_MOVE_PCT and s["bottom_mover"]:
        anchor = f"{s['bottom_mover']['symbol']} {_fmt_pct(s['bottom_mover']['gap_pct'])}"

    return f"{bucket} {name} {avg} {breadth}  {anchor}".rstrip()


def _focus_lines(summaries: list[dict]) -> tuple[list[str], list[str]]:
    """Split summaries into (focus_longs, avoid) groups using deterministic rules."""
    longs: list[str] = []
    avoid: list[str] = []
    for s in summaries:
        avg = s["avg_gap_pct"]
        total = s["breadth_total"]
        green = s["breadth_green"]
        if avg is None or total == 0:
            continue
        breadth_ratio = green / total
        if avg > STRONG_MOVE_PCT and breadth_ratio >= STRONG_BREADTH_RATIO:
            longs.append(s["name"])
        elif avg < -STRONG_MOVE_PCT and breadth_ratio <= (1 - STRONG_BREADTH_RATIO):
            avoid.append(s["name"])
    return longs, avoid


def _format_macro_token(symbol: str, q: Optional[dict]) -> str:
    """One symbol on the macro tape line: 'SPY +0.3%' or 'VIX 14.2'."""
    display = "VIX" if symbol == "^VIX" else symbol
    if not q or q.get("last") is None:
        return f"{display} —"
    last = q["last"]
    prev = q.get("prev_close")
    # VIX shown as absolute level (it's already a %); equities shown as gap %.
    if symbol == "^VIX":
        return f"{display} {last:.1f}"
    if prev and prev > 0:
        gap_pct = (last - prev) / prev * 100
        sign = "+" if gap_pct >= 0 else ""
        return f"{display} {sign}{gap_pct:.1f}%"
    return f"{display} {last:.1f}"


def _format_tape_section(macro_quotes: dict[str, dict]) -> list[str]:
    """Two-line macro tape: indexes on row 1, sector ETFs on row 2."""
    if not macro_quotes:
        return []
    idx_tokens = [_format_macro_token(s, macro_quotes.get(s)) for s in MACRO_INDEXES]
    sec_tokens = [_format_macro_token(s, macro_quotes.get(s)) for s in MACRO_SECTORS]
    return [
        f"Tape:  {'  '.join(idx_tokens)}",
        f"       {'  '.join(sec_tokens)}",
    ]


def format_brief(
    summaries: list[dict],
    macro_quotes: Optional[dict[str, dict]] = None,
    now_et: Optional[datetime] = None,
) -> Optional[str]:
    """Build the concise Telegram message string. Returns None if no data.

    *summaries* — list of dicts in the same shape as GroupPremarketSummary,
    sorted by abs(avg_gap_pct) DESC.
    *macro_quotes* — {symbol: {last, prev_close, volume}} for indexes + sector ETFs.
    """
    if not summaries:
        return None
    has_data = any(s["avg_gap_pct"] is not None for s in summaries)
    if not has_data:
        return None

    now = now_et or datetime.now(ET)
    header = f"📊 Premarket Heat — {now.strftime('%a %-I:%M %p')} ET"

    body_lines = [_format_summary_line(s) for s in summaries]
    longs, avoid = _focus_lines(summaries)

    parts = [header, ""]
    if macro_quotes:
        parts.extend(_format_tape_section(macro_quotes))
        parts.append("")
    parts.extend(body_lines)
    parts.append("")

    if longs:
        parts.append(f"Focus: {', '.join(longs)} (longs)")
    if avoid:
        parts.append(f"Avoid: {', '.join(avoid)} (red breadth)")
    if not longs and not avoid:
        parts.append("Mixed tape — wait for first 30 min")

    # Wrap in <pre> so Telegram preserves the column alignment.
    body = "\n".join(parts)
    return f"<pre>{body}</pre>"


async def _user_summaries(
    user_id: int, db: AsyncSession
) -> tuple[list[dict], dict[str, dict]]:
    """Compute per-group premarket summaries + macro tape quotes for a user.

    Macro symbols (SPY/QQQ/IWM/DIA/VIX + sector SPDRs) are fetched in the
    SAME yfinance batch as the user's watchlist — one HTTP round-trip total.
    """
    from app.routers.market import _fetch_quotes_batch, _summarize_group

    groups_result = await db.execute(
        select(WatchlistGroup)
        .where(WatchlistGroup.user_id == user_id)
        .order_by(WatchlistGroup.sort_order, WatchlistGroup.id)
    )
    groups = list(groups_result.scalars().all())
    if not groups:
        return [], {}

    items_result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user_id)
        .where(WatchlistItem.group_id.is_not(None))
    )
    all_items = list(items_result.scalars().all())
    items_by_group: dict[int, list] = {}
    for it in all_items:
        items_by_group.setdefault(it.group_id, []).append(it)

    user_symbols = {it.symbol for it in all_items}
    macro_symbols = set(MACRO_INDEXES) | set(MACRO_SECTORS)
    all_symbols = sorted(user_symbols | macro_symbols)

    import asyncio as _aio
    from functools import partial as _partial

    loop = _aio.get_event_loop()
    quotes = await loop.run_in_executor(None, _partial(_fetch_quotes_batch, all_symbols))

    summaries = [
        _summarize_group(g, items_by_group.get(g.id, []), quotes).model_dump()
        for g in groups
    ]
    summaries.sort(
        key=lambda s: abs(s["avg_gap_pct"]) if s["avg_gap_pct"] is not None else -1,
        reverse=True,
    )

    macro_quotes = {sym: quotes[sym] for sym in macro_symbols if sym in quotes}
    return summaries, macro_quotes


async def build_user_sector_brief(user_id: int) -> Optional[str]:
    """Build the formatted Telegram message for a single user. None if no data."""
    async with async_session_factory() as db:
        summaries, macro_quotes = await _user_summaries(user_id, db)
    return format_brief(summaries, macro_quotes=macro_quotes)


async def send_sector_briefs() -> tuple[int, int]:
    """Send the brief to every user who has telegram_chat_id + watchlist groups.

    Returns (sent_count, attempted_count). Idempotent within a run; the cron
    schedules this once per day so day-level dedup is implicit.
    """
    from alerting.notifier import _send_telegram_to

    sent = 0
    attempted = 0
    async with async_session_factory() as db:
        users_result = await db.execute(
            select(User).where(
                User.telegram_chat_id.is_not(None),
                User.telegram_chat_id != "",
            )
        )
        users = list(users_result.scalars().all())

    for u in users:
        # Build outside the iteration's session to avoid holding it open across
        # network I/O.
        attempted += 1
        try:
            body = await build_user_sector_brief(u.id)
        except Exception:
            logger.exception("Sector brief build failed for user %d", u.id)
            continue
        if not body:
            logger.info("Sector brief: skip user %d (no groups or no data)", u.id)
            continue
        try:
            ok = _send_telegram_to(body, u.telegram_chat_id, parse_mode="HTML")
            if ok:
                sent += 1
                logger.info("Sector brief: sent to user %d", u.id)
            else:
                logger.warning("Sector brief: telegram send failed for user %d", u.id)
        except Exception:
            logger.exception("Sector brief: telegram exception for user %d", u.id)

    logger.info("Sector brief done: sent=%d/%d", sent, attempted)
    return sent, attempted
