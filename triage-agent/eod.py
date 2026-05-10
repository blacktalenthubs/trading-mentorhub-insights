"""End-of-day recap.

Runs daily at 4:05 PM ET. Reads this morning's premarket picks (persisted by
premarket.py) and grades them against today's close. Identifies tomorrow's
setups. Sends a recap to Telegram.

Output format:

    📊 EOD Recap — Fri 4:05 PM ET

    Tape:  SPY +0.8%  QQQ +1.4%  IWM +0.2%  DIA +0.1%  VIX 16.3 (-4%)
           XLK +2.0%  XLE -0.5%  ...

    Morning Brief Verdict:
    ✓ Focus delivered: Optics +8.2%, Memory +7.1%, BTC +5.4%, Cloud +4.8%
    ✗ Avoid call missed: Power +0.3% (we said red)

    Top picks performance:
      🟢 AAOI +14.3% (entry hit, T1 cleared)
      🟢 SNDK +9.8%
      🟡 MSTR +5.4%
      🔴 ORCL -0.5% (rejected at PDH)

    Tomorrow watch:
      • AVGO breaking out late session — pdh_break setup primed
      • XLK strong close → tech setups higher conviction tomorrow

    🤖 [LLM commentary on what worked, why, what to take into tomorrow]
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # picks up .env when running standalone; harmless on Railway

import psycopg2
from psycopg2.extras import RealDictCursor
import yfinance as yf
from anthropic import Anthropic

import premarket  # reuse data fetch + helpers

logger = logging.getLogger("triage.eod")

DATABASE_URL    = os.environ.get("DATABASE_URL")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TRIAGE_USER_ID  = int(os.environ.get("TRIAGE_USER_ID", "3"))
PICKS_FILE      = Path(os.environ.get("PREMARKET_PICKS_FILE", "/data/premarket-picks.json"))
LLM_TIER        = os.environ.get("PREMARKET_LLM_TIER", "heavy")


# ──────────────────────────────────────────────────────────────────
# LOAD MORNING'S PICKS
# ──────────────────────────────────────────────────────────────────

def load_morning_picks() -> Optional[dict]:
    """Read what the morning brief said. Returns None if no brief was generated today."""
    if not PICKS_FILE.exists():
        return None
    try:
        record = json.loads(PICKS_FILE.read_text())
        ts = datetime.fromisoformat(record["timestamp"]) if "timestamp" in record else None
        # Sanity check: must be from today
        if ts and (datetime.now(ts.tzinfo) - ts) > timedelta(hours=12):
            logger.info("eod: morning picks file is stale (>12h old), skipping recap of picks")
            return None
        return record
    except Exception:
        logger.exception("eod: failed to read picks file")
        return None


# ──────────────────────────────────────────────────────────────────
# GRADE THE MORNING'S CALLS
# ──────────────────────────────────────────────────────────────────

def grade_picks(picks: list[dict], close_quotes: dict[str, premarket.PriceMove]) -> list[dict]:
    """For each morning pick, grade by full-day move (premarket → close)."""
    graded = []
    for p in picks:
        sym = p["symbol"]
        if sym not in close_quotes:
            graded.append({**p, "close_pct_full_day": None, "verdict": "no_data"})
            continue
        close = close_quotes[sym]
        # Full-day pct: premarket price → today's last regular close
        pre = p["premarket_price"]
        full_day_pct = (close.last_close - pre) / pre * 100.0 if pre else 0.0
        # Note: close.last_close is yesterday's close in PriceMove convention.
        # For EOD we want today's close. Recompute below using close.premarket_price
        # (which at EOD will be close-of-day or post-market price).
        # Better: compute pct from morning premarket price → end-of-day current price
        eod_price = close.premarket_price  # at 4:05pm this is essentially the close
        full_day_pct = (eod_price - pre) / pre * 100.0 if pre else 0.0

        if full_day_pct >= 1.5:
            verdict = "win"
        elif full_day_pct >= 0:
            verdict = "flat"
        else:
            verdict = "miss"
        graded.append({
            **p,
            "eod_price": eod_price,
            "full_day_pct": full_day_pct,
            "verdict": verdict,
        })
    return graded


def grade_sectors(
    sectors: list[dict],
    close_quotes: dict[str, premarket.PriceMove],
    groups: dict[str, list[str]],
) -> list[dict]:
    """For each focus/avoid sector, grade by today's avg move."""
    graded = []
    for s in sectors:
        gname = s["name"]
        syms = groups.get(gname, [])
        moves = [close_quotes[sym] for sym in syms if sym in close_quotes]
        if not moves:
            graded.append({**s, "eod_avg_pct": None})
            continue
        # For EOD, we need today's % change (close vs yesterday close)
        # PriceMove.pct_change at EOD is now the day's pct
        avg = sum(m.pct_change for m in moves) / len(moves)
        graded.append({**s, "eod_avg_pct": avg})
    return graded


# ──────────────────────────────────────────────────────────────────
# TOMORROW WATCH — recent alerts that look like setups for tomorrow
# ──────────────────────────────────────────────────────────────────

def find_tomorrow_setups(user_id: int, lookback_hours: int = 4) -> list[dict]:
    """Find recent alerts (last N hours) that suggest setups for tomorrow.
    Heuristics:
      - Late-session alerts (after 14:00 ET) — fresh signal for tomorrow
      - High-volume + cvd_diverging — institutional accumulation
    """
    out = []
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT ON (symbol)
                    symbol, alert_type, direction, entry, stop, target_1,
                    confidence, volume_ratio, cvd_diverging, created_at
                FROM alerts
                WHERE user_id = %s
                  AND created_at > NOW() - INTERVAL '%s hours'
                  AND direction IN ('BUY', 'SHORT')
                  AND (volume_ratio >= 2.0 OR cvd_diverging = 1)
                ORDER BY symbol, created_at DESC
                LIMIT 8
            """, (user_id, lookback_hours))
            rows = cur.fetchall()
            for r in rows:
                out.append(dict(r))
    return out


# ──────────────────────────────────────────────────────────────────
# FORMATTING
# ──────────────────────────────────────────────────────────────────

def _verdict_emoji(v: str) -> str:
    return {"win": "🟢", "flat": "🟡", "miss": "🔴", "no_data": "⚪"}.get(v, "⚪")


def format_eod_recap(
    quotes: dict[str, premarket.PriceMove],
    morning: Optional[dict],
    graded_picks: list[dict],
    graded_focus: list[dict],
    graded_avoid: list[dict],
    tomorrow: list[dict],
    polish: Optional[str],
    now: datetime,
) -> str:
    et_str = now.strftime("%a %-I:%M %p ET") if hasattr(now, "strftime") else str(now)
    parts = [f"📊 <b>EOD Recap</b> — {et_str}", ""]
    parts.append(premarket.format_tape_line(quotes))
    parts.append("")

    if morning is None:
        parts.append("<i>No morning brief was generated today; skipping picks recap.</i>")
    else:
        parts.append("<b>Morning Brief Verdict:</b>")
        # Focus sectors
        if graded_focus:
            wins = [f"{s['name']} {s['eod_avg_pct']:+.1f}%"
                    for s in graded_focus if s.get("eod_avg_pct") is not None]
            if wins:
                parts.append("✓ Focus delivered: " + ", ".join(wins))
            else:
                parts.append("✓ Focus sectors: data missing")
        # Avoid sectors — did the call hold?
        if graded_avoid:
            for s in graded_avoid:
                pct = s.get("eod_avg_pct")
                if pct is None:
                    continue
                if pct < 0:
                    parts.append(f"✓ Avoid held: {s['name']} {pct:+.1f}%")
                else:
                    parts.append(f"✗ Avoid call missed: {s['name']} {pct:+.1f}% (we said red)")

        # Picks
        if graded_picks:
            parts.append("")
            parts.append("<b>Top picks performance:</b>")
            for p in graded_picks:
                em = _verdict_emoji(p["verdict"])
                pct = p.get("full_day_pct")
                pct_str = f"{pct:+.1f}%" if pct is not None else "n/a"
                eod_price = p.get("eod_price")
                price_str = f"${eod_price:.2f}" if eod_price else ""
                parts.append(f"  {em} {p['symbol']} {pct_str}  {price_str}")

    # Tomorrow watch
    if tomorrow:
        parts.append("")
        parts.append("<b>Tomorrow watch:</b>")
        for t in tomorrow[:5]:
            sym = t["symbol"]
            atype = t["alert_type"]
            direction = t.get("direction", "")
            note_parts = []
            if t.get("volume_ratio") and t["volume_ratio"] >= 2.0:
                note_parts.append(f"vr={t['volume_ratio']:.1f}×")
            if t.get("cvd_diverging"):
                note_parts.append("cvd!")
            note = " · ".join(note_parts)
            parts.append(f"  • {sym} {direction} — {atype}{(' (' + note + ')') if note else ''}")

    if polish:
        parts.append("")
        parts.append("🤖 " + polish)

    return "\n".join(parts)[:4000]


# ──────────────────────────────────────────────────────────────────
# LLM POLISH (heavy)
# ──────────────────────────────────────────────────────────────────

POLISH_PROMPT = """You are a trading-desk analyst writing a 2-3 sentence end-of-day recap.
You'll be given:
- Today's index moves
- Morning brief verdict (focus / avoid sectors and how they performed)
- Top picks performance (won, flat, missed)
- Tomorrow's potential setups from late-session alerts

Write a tight 2-3 sentence reflection: what worked, what didn't, and one thing
to carry into tomorrow. Don't restate the numbers — they're above. Add insight.
"""


def polish_with_llm_eod(
    quotes: dict[str, premarket.PriceMove],
    morning: Optional[dict],
    graded_picks: list[dict],
    graded_focus: list[dict],
    graded_avoid: list[dict],
    tomorrow: list[dict],
) -> Optional[str]:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        ctx = []
        ctx.append("INDICES TODAY:")
        for s in premarket.INDICES:
            if s in quotes:
                ctx.append(f"  {s} {quotes[s].pct_change:+.1f}%")
        ctx.append("")
        if morning:
            ctx.append("MORNING SAID:")
            ctx.append(f"  Focus: {[s['name'] for s in graded_focus]}")
            ctx.append(f"  Avoid: {[s['name'] for s in graded_avoid]}")
            ctx.append("")
            ctx.append("FOCUS PERFORMANCE:")
            for s in graded_focus:
                ctx.append(f"  {s['name']}: {s.get('eod_avg_pct', 'n/a')}")
            ctx.append("AVOID PERFORMANCE:")
            for s in graded_avoid:
                ctx.append(f"  {s['name']}: {s.get('eod_avg_pct', 'n/a')}")
            ctx.append("")
            ctx.append("PICKS PERFORMANCE:")
            for p in graded_picks:
                pct = p.get("full_day_pct")
                pct_str = f"{pct:+.1f}%" if pct is not None else "n/a"
                ctx.append(f"  {p['symbol']} ({p['sector']}): {pct_str} → {p['verdict']}")
        ctx.append("")
        ctx.append("TOMORROW'S POTENTIAL SETUPS (late-session alerts with strong signals):")
        for t in tomorrow[:5]:
            ctx.append(f"  {t['symbol']} {t.get('direction')} {t['alert_type']}")

        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            system=POLISH_PROMPT,
            messages=[{"role": "user", "content": "\n".join(ctx)}],
        )
        return resp.content[0].text.strip() if resp.content else None
    except Exception:
        logger.exception("polish_with_llm_eod failed")
        return None


# ──────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────

def run_eod_recap(send: bool = True) -> dict:
    import telegram_post
    from datetime import datetime
    try:
        import pytz
        et = datetime.now(pytz.timezone("America/New_York"))
    except Exception:
        et = datetime.now()

    logger.info("eod: starting recap at %s", et.isoformat())

    morning = load_morning_picks()

    # Build symbol set: indices + ETFs + watchlist + morning picks
    groups = premarket.load_watchlist_groups(TRIAGE_USER_ID)
    watchlist_syms = sorted({s for syms in groups.values() for s in syms})
    pick_syms = [p["symbol"] for p in (morning or {}).get("picks", [])]
    all_syms = list(set(premarket.INDICES + [premarket.VIX_SYMBOL] +
                        premarket.SECTOR_ETFS + watchlist_syms + pick_syms))

    quotes = premarket.fetch_premarket(all_syms)
    logger.info("eod: fetched %d/%d symbols", len(quotes), len(all_syms))

    # Grade morning's calls
    graded_picks = []
    graded_focus = []
    graded_avoid = []
    if morning:
        graded_picks = grade_picks(morning.get("picks", []), quotes)
        graded_focus = grade_sectors(morning.get("focus_sectors", []), quotes, groups)
        graded_avoid = grade_sectors(morning.get("avoid_sectors", []), quotes, groups)

    # Tomorrow watch
    tomorrow = find_tomorrow_setups(TRIAGE_USER_ID, lookback_hours=4)

    # LLM polish
    polish = None
    if LLM_TIER in ("standard", "heavy"):
        polish = polish_with_llm_eod(quotes, morning, graded_picks,
                                     graded_focus, graded_avoid, tomorrow)

    recap = format_eod_recap(quotes, morning, graded_picks, graded_focus,
                             graded_avoid, tomorrow, polish, et)

    if send:
        try:
            telegram_post._send(recap)
            logger.info("eod: recap sent to Telegram")
        except Exception:
            logger.exception("eod: telegram send failed")

    return {
        "recap": recap,
        "n_picks_graded": len(graded_picks),
        "n_tomorrow": len(tomorrow),
    }


if __name__ == "__main__":
    import sys
    send = "--no-send" not in sys.argv
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-7s %(name)s | %(message)s")
    result = run_eod_recap(send=send)
    print(result["recap"])
