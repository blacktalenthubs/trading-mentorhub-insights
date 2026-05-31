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


def _gap_pct(q: Optional[dict]) -> Optional[float]:
    if not q or q.get("last") is None or not q.get("prev_close"):
        return None
    prev = q["prev_close"]
    if prev <= 0:
        return None
    return (q["last"] - prev) / prev * 100


def _index_focus_line(macro_quotes: dict[str, dict]) -> Optional[str]:
    """One-line tape characterization + dominant index recommendation.

    Reads SPY/QQQ/IWM/DIA gaps + VIX + leading sector SPDR. Returns something
    like 'Lead: QQQ +1.0% (tech tape) · Sector: XLK +1.5%'.
    """
    spy = _gap_pct(macro_quotes.get("SPY"))
    qqq = _gap_pct(macro_quotes.get("QQQ"))
    iwm = _gap_pct(macro_quotes.get("IWM"))
    dia = _gap_pct(macro_quotes.get("DIA"))
    vix_q = macro_quotes.get("^VIX")
    vix_level = vix_q["last"] if vix_q and vix_q.get("last") is not None else None

    indexes = [
        ("SPY", spy, "S&P broad"),
        ("QQQ", qqq, "tech tape"),
        ("IWM", iwm, "small-cap risk-on"),
        ("DIA", dia, "blue-chip"),
    ]
    indexes_with_data = [(s, g, lbl) for s, g, lbl in indexes if g is not None]
    if not indexes_with_data:
        return None

    # Tape character — risk-off if everything red, otherwise leader.
    all_red = all(g < -0.1 for _, g, _ in indexes_with_data)
    all_green = all(g > 0.1 for _, g, _ in indexes_with_data)
    leader = max(indexes_with_data, key=lambda x: abs(x[1]))
    sym, gap, label = leader

    if all_red:
        char = "risk-off (broad weakness)"
    elif all_green:
        char = f"{label}, broad green"
    elif gap > 0:
        # Special case: SPY leads but QQQ lags = defensive mega-cap day
        if sym == "SPY" and qqq is not None and qqq < spy - 0.3:
            char = "mega-cap defensive (QQQ lags)"
        else:
            char = label
    else:
        char = f"{label} weakening"

    sign = "+" if gap >= 0 else ""
    parts = [f"Lead: {sym} {sign}{gap:.1f}% ({char})"]

    # Sector ETF leader if meaningful.
    sec_gaps = [
        (sym, _gap_pct(macro_quotes.get(sym)))
        for sym in MACRO_SECTORS
    ]
    sec_with_data = [(s, g) for s, g in sec_gaps if g is not None]
    if sec_with_data:
        sec_leader = max(sec_with_data, key=lambda x: abs(x[1]))
        ssym, sgap = sec_leader
        if abs(sgap) > 0.5:
            ssign = "+" if sgap >= 0 else ""
            parts.append(f"Sector: {ssym} {ssign}{sgap:.1f}%")

    # VIX caveat.
    if vix_level is not None:
        if vix_level >= 20:
            parts.append(f"VIX {vix_level:.1f} (elevated fear)")
        elif vix_level <= 12:
            parts.append(f"VIX {vix_level:.1f} (complacent)")

    return " · ".join(parts)


def _format_tape_section(macro_quotes: dict[str, dict]) -> list[str]:
    """Macro tape: indexes (row 1), sector ETFs (row 2), focus call (row 3)."""
    if not macro_quotes:
        return []
    idx_tokens = [_format_macro_token(s, macro_quotes.get(s)) for s in MACRO_INDEXES]
    sec_tokens = [_format_macro_token(s, macro_quotes.get(s)) for s in MACRO_SECTORS]
    lines = [
        f"Tape:  {'  '.join(idx_tokens)}",
        f"       {'  '.join(sec_tokens)}",
    ]
    focus = _index_focus_line(macro_quotes)
    if focus:
        lines.append(f"       {focus}")
    return lines


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


async def _build_top_of_day_lines(user_id: int, db: AsyncSession) -> list[str]:
    """Build the TOP OF DAY header section for the morning brief (Feature 4
    of the spec 61 follow-up batch). Prepended above the existing per-group
    premarket heat lines.

    Three lines, all optional — only added when data exists:
      1. SPY regime: bias label + price + slope %
      2. Earnings today on this user's watchlist
      3. Top 3 AI Best Setups from the user's most recent FocusList run
    """
    from app.models.earnings import Earnings
    from app.models.focus_list import FocusList
    from app.models.watchlist import WatchlistItem
    from app.routers.market import _compute_spy_regime
    from datetime import date as _date, timedelta as _td

    lines: list[str] = []
    today = _date.today()

    # 1. SPY regime — single call to the same compute used by the live strip.
    # Cached server-side 30s so this is cheap even with many users.
    try:
        import asyncio as _aio
        loop = _aio.get_event_loop()
        regime = await loop.run_in_executor(None, _compute_spy_regime)
        if regime and regime.get("status") == "ok":
            bias = regime.get("bias", "NEUTRAL").replace("_", " ")
            slope = regime.get("vwap_slope_pct", 0.0)
            sign = "+" if slope >= 0 else ""
            extra = ""
            if regime.get("inside_day"):
                extra = f" · inside day (PDH {regime.get('pdh'):.2f} / PDL {regime.get('pdl'):.2f})"
            lines.append(
                f"SPY <b>{bias}</b> · ${regime.get('price'):.2f} · "
                f"VWAP {sign}{slope:.2f}%{extra}"
            )
    except Exception:
        logger.exception("Morning brief: SPY regime failed")

    # 2. Earnings today on this user's watchlist.
    try:
        rows = (await db.execute(
            select(Earnings.symbol, Earnings.time_of_day, Earnings.eps_estimate)
            .join(WatchlistItem, WatchlistItem.symbol == Earnings.symbol)
            .where(WatchlistItem.user_id == user_id, Earnings.next_earnings_date == today)
        )).all()
        if rows:
            parts = []
            for sym, tod, eps in rows:
                tod_str = f" ({tod})" if tod else ""
                parts.append(f"<b>{sym}</b>{tod_str}")
            lines.append("Earnings today: " + ", ".join(parts))
    except Exception:
        logger.exception("Morning brief: earnings lookup failed")

    # 3. Top 3 AI Best Setups from the most recent FocusList run (< 24h old).
    try:
        cutoff = today - _td(days=1)
        latest = (await db.execute(
            select(FocusList)
            .where(
                FocusList.user_id == user_id,
                FocusList.session_date >= cutoff.isoformat(),
                FocusList.status == "has_setups",
            )
            .order_by(FocusList.generated_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if latest and isinstance(latest.recommendations, list) and latest.recommendations:
            picks = latest.recommendations[:3]
            parts = []
            for p in picks:
                sym = p.get("symbol") or "?"
                tf = (p.get("timeframe") or "day").lower()
                tf_short = "swing" if tf.startswith("swing") else "day"
                parts.append(f"<b>{sym}</b> ({tf_short})")
            lines.append("AI Best Setups: " + ", ".join(parts))
    except Exception:
        logger.exception("Morning brief: focus list lookup failed")

    # 4. Top 5 swing setups from the latest swing-screener snapshot (mega-cap).
    # Universe-wide — gives the user trade ideas BEYOND their hand-picked
    # watchlist. Pull from screener_snapshot kind='swing'.
    try:
        from app.models.screener import ScreenerSnapshot
        from sqlalchemy import desc as _desc
        swing_row = (await db.execute(
            select(ScreenerSnapshot)
            .where(ScreenerSnapshot.kind == "swing")
            .order_by(_desc(ScreenerSnapshot.captured_at))
            .limit(1)
        )).scalar_one_or_none()
        if swing_row and isinstance(swing_row.entries, list) and swing_row.entries:
            with_setup = [e for e in swing_row.entries if e.get("setup")][:5]
            if with_setup:
                parts = []
                for e in with_setup:
                    sym = e.get("symbol") or "?"
                    grade = e.get("grade") or "C"
                    parts.append(f"<b>{sym}</b>({grade})")
                lines.append("Swing picks: " + ", ".join(parts))
    except Exception:
        logger.exception("Morning brief: swing snapshot lookup failed")

    # 5. Top 5 social-trending symbols from the latest social_buzz_snapshot.
    # Cross-watchlist signal — what retail is actually discussing right now.
    try:
        from app.models.social_buzz import SocialBuzzSnapshot
        from sqlalchemy import desc as _desc2
        buzz_row = (await db.execute(
            select(SocialBuzzSnapshot)
            .order_by(_desc2(SocialBuzzSnapshot.captured_at))
            .limit(1)
        )).scalar_one_or_none()
        if buzz_row and isinstance(buzz_row.entries, list) and buzz_row.entries:
            top5 = buzz_row.entries[:5]
            parts = []
            for e in top5:
                sym = e.get("symbol") or "?"
                growth = e.get("growth_pct")
                growth_str = ""
                if growth is not None and growth > 0:
                    growth_str = f" +{int(growth)}%"
                parts.append(f"<b>{sym}</b>{growth_str}")
            lines.append("Social trending: " + ", ".join(parts))
    except Exception:
        logger.exception("Morning brief: social buzz lookup failed")

    return lines


def _format_brief_with_header(
    top_lines: list[str],
    summaries: list[dict],
    macro_quotes: Optional[dict[str, dict]] = None,
) -> Optional[str]:
    """Wrap format_brief with the TOP OF DAY prefix section. If neither
    the top section nor the per-group section has data, returns None.
    """
    inner = format_brief(summaries, macro_quotes=macro_quotes)
    has_summaries = inner is not None
    if not top_lines and not has_summaries:
        return None

    if top_lines:
        header_block = (
            "🔥 <b>TOP OF DAY</b>\n"
            + "\n".join(top_lines)
            + "\n──────────────"
        )
        if has_summaries:
            # Inner is wrapped in <pre> for column alignment — splice header
            # ABOVE the <pre> block so the header renders as rich text.
            return f"{header_block}\n{inner}"
        return header_block
    return inner


async def build_user_sector_brief(user_id: int) -> Optional[str]:
    """Build the formatted Telegram message for a single user. None if no data."""
    async with async_session_factory() as db:
        top_lines = await _build_top_of_day_lines(user_id, db)
        summaries, macro_quotes = await _user_summaries(user_id, db)
    return _format_brief_with_header(top_lines, summaries, macro_quotes=macro_quotes)


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
