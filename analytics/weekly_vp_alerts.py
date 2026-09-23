"""Weekly volume-profile ALERTS — live Telegram alerts on weekly POC / VWAP / VAL.

A dedicated intraday job (NOT the protected monitor loop): it reads the weekly levels the
daily weekly_vp_scan cached (weekly_vp_levels), checks the LIVE price against them, and
fires three event types — once per symbol/level/week (deduped):

  🛡 SUPPORT   price is AT the level (±tol) and this week OPENED ABOVE it → holding as support
  🌟 RECLAIM   prior day closed at/below the level and price is now just above it → regained value
  ⚠️ LOSS      this week opened above the level but price has now dropped below it → lost support

Full master watchlist (levels are cached daily for every name); most names sit far from their
weekly value area, so this stays quiet. Read-only; sends to the alert recipient's Telegram.
Educational, not financial advice.

CLI:  python3 -m analytics.weekly_vp_alerts [--dry]
"""
from __future__ import annotations

import datetime as _dt
import logging
import os

logger = logging.getLogger(__name__)

TOL = 0.015            # "at the level" band
RECLAIM_BAND = 0.03    # a reclaim only fires while price is still within this of the level
ALERT_EMAIL = os.environ.get("WEEKLY_VP_ALERT_EMAIL", "vbolofinde@gmail.com")

_EVENT = {
    "support": ("🛡", "SUPPORT", "opened above · holding it as support"),
    "reclaim": ("🌟", "RECLAIM", "reclaimed from below — first move back above"),
    "loss":    ("⚠️", "LOSS", "opened above but has lost the level"),
}
_SENT_DDL = "CREATE TABLE IF NOT EXISTS weekly_vp_alerts_sent (dedup_key TEXT PRIMARY KEY, sent_at TIMESTAMP NOT NULL DEFAULT NOW())"


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL required for weekly VP alerts")
    return dsn


def _read_levels():  # pragma: no cover - DB
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS weekly_vp_levels (symbol TEXT PRIMARY KEY, poc REAL, vwap REAL, val REAL, week_open REAL, prior_close REAL, session_date TEXT, updated_at TIMESTAMP)")
    cur.execute("SELECT symbol, poc, vwap, val, week_open, prior_close FROM weekly_vp_levels")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{"symbol": r[0], "poc": r[1], "vwap": r[2], "val": r[3],
             "week_open": r[4], "prior_close": r[5]} for r in rows]


def _live_prices(symbols):  # pragma: no cover - network
    from analytics.weekly_vp_scan import _ensure_rh
    rh = _ensure_rh()
    out: dict[str, float] = {}
    try:
        lp = rh.stocks.get_latest_price(symbols) or []      # batch, aligned to input order
        for s, p in zip(symbols, lp):
            try:
                if p:
                    out[s] = float(p)
            except Exception:
                pass
    except Exception:
        logger.exception("live price fetch failed")
    return out


def detect(levels, prices, monday: str, tol: float = TOL) -> list[dict]:
    """Pure event detection (unit-testable). One event per symbol/level, keyed for dedup."""
    events = []
    for lv in levels:
        price = prices.get(lv["symbol"])
        if not price or price <= 0:
            continue
        wo = lv.get("week_open") or 0.0
        pc = lv.get("prior_close")
        for name in ("POC", "VWAP", "VAL"):
            level = lv.get(name.lower())
            if not level or level <= 0:
                continue
            if wo >= level and price < level * (1 - tol):
                ev = "loss"
            elif pc is not None and pc <= level < price and (price - level) / level <= RECLAIM_BAND:
                ev = "reclaim"
            elif abs(price - level) / price <= tol and wo >= level:
                ev = "support"
            else:
                continue
            events.append({
                "symbol": lv["symbol"], "event": ev, "level_name": name, "level": round(level, 2),
                "price": round(price, 2), "key": f"{lv['symbol']}:{ev}:{name}:{monday}",
            })
    return events


def _unsent(events):  # pragma: no cover - DB
    if not events:
        return []
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15)
    cur = conn.cursor()
    cur.execute(_SENT_DDL)
    keys = [e["key"] for e in events]
    cur.execute("SELECT dedup_key FROM weekly_vp_alerts_sent WHERE dedup_key = ANY(%s)", (keys,))
    seen = {r[0] for r in cur.fetchall()}
    cur.close(); conn.close()
    return [e for e in events if e["key"] not in seen]


def _mark_sent(events):  # pragma: no cover - DB
    if not events:
        return
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15)
    cur = conn.cursor()
    cur.execute(_SENT_DDL)
    for e in events:
        cur.execute("INSERT INTO weekly_vp_alerts_sent (dedup_key) VALUES (%s) ON CONFLICT DO NOTHING", (e["key"],))
    conn.commit(); cur.close(); conn.close()


def _chat_ids():  # pragma: no cover - DB
    """Telegram chat ids for the alert recipient(s)."""
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15)
    cur = conn.cursor()
    cur.execute("SELECT telegram_chat_id FROM users WHERE LOWER(email) = LOWER(%s) AND telegram_chat_id IS NOT NULL AND telegram_chat_id <> ''", (ALERT_EMAIL,))
    ids = [str(r[0]) for r in cur.fetchall()]
    cur.close(); conn.close()
    return ids


def _format(events) -> str:
    order = {"reclaim": 0, "support": 1, "loss": 2}
    events = sorted(events, key=lambda e: (order.get(e["event"], 9), e["symbol"]))
    lines = ["<b>WEEKLY VALUE · alerts</b>"]
    for e in events:
        icon, word, _ = _EVENT[e["event"]]
        lines.append(f"{icon} <b>{e['symbol']}</b> {word} — weekly {e['level_name']} {e['level']:.2f} · now {e['price']:.2f}")
    lines.append("<i>Weekly volume profile · verify on your chart · not financial advice.</i>")
    return "\n".join(lines)


def run(dry: bool = False) -> dict:  # pragma: no cover - network/DB
    levels = _read_levels()
    if not levels:
        logger.info("weekly-vp alerts: no cached levels yet")
        return {"events": 0, "sent": 0}
    prices = _live_prices([lv["symbol"] for lv in levels])
    today = _dt.date.today()
    monday = (today - _dt.timedelta(days=today.weekday())).isoformat()
    events = detect(levels, prices, monday)
    new = _unsent(events)
    if not new:
        return {"events": len(events), "sent": 0}
    body = _format(new)
    if dry:
        print(body)
        return {"events": len(events), "sent": 0, "dry": True}
    try:
        from alerting.notifier import _send_telegram_to
        chat_ids = _chat_ids()
        for cid in chat_ids:
            _send_telegram_to(body, cid, parse_mode="HTML")
        _mark_sent(new)
        logger.info("weekly-vp alerts: sent %d event(s) to %d chat(s)", len(new), len(chat_ids))
        return {"events": len(events), "sent": len(new), "chats": len(chat_ids)}
    except Exception:
        logger.exception("weekly-vp alert send failed")
        return {"events": len(events), "sent": 0, "error": True}


def main():  # pragma: no cover
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Weekly VP alerts (POC/VWAP/VAL support/reclaim/loss)")
    ap.add_argument("--dry", action="store_true", help="detect + print, don't send or mark")
    args = ap.parse_args()
    print(run(dry=args.dry))


if __name__ == "__main__":
    main()
