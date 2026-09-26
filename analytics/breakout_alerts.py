"""Live breakout alerts — fires when a scanner pattern's price crosses its TBA (buy trigger)
during the day, on the DAILY chart. Standalone job (NOT the protected monitor pipeline), same
shape as weekly_vp_alerts: detect fresh crosses over the master watchlist, dedup once per
symbol-pattern-day, send Telegram, and record an alert row for user 3 so it shows in the app's
Breakout feed — just like any other live signal.

The "breakout" event on a daily chart is price closing above the trigger; intraday the daily
bar is forming, so we fire when the live price crosses the TBA (yesterday closed below it).
Volume confirms by the close — carried in the message, not a hard gate (daily volume is partial
mid-session). Only TIGHT setups alert (entry→stop ≤ max_setup_risk_pct).

CLI: python3 -m analytics.breakout_alerts [--dry]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patterns.config import CONFIG  # noqa: E402
from patterns.indicators import add_indicators  # noqa: E402
from patterns.detect_utils import prefilter, compose_score  # noqa: E402
from patterns.screener import run_detectors, _label  # noqa: E402

USER_ID = int(os.environ.get("BREAKOUT_ALERT_USER_ID", "3"))   # the trader's account (feed + telegram)
_SENT_DDL = "CREATE TABLE IF NOT EXISTS breakout_alerts_sent (dedup_key TEXT PRIMARY KEY, sent_at TIMESTAMP NOT NULL DEFAULT NOW())"


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL not set")
    return dsn


def _fetch(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="4y", interval="1d")
    return None if df is None or df.empty else df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])


def detect(df, cfg=CONFIG) -> list[dict]:
    """Fresh TBA crosses on the given (already fetched) df — [] if none. Pure-ish: the cross test
    is `prior daily close ≤ trigger < current`, so it fires the session price crosses the level."""
    if df is None or len(df) < cfg.min_bars:
        return []
    df = add_indicators(df, cfg)
    if prefilter(df, cfg):
        return []
    closes = df["Close"].values
    price, prev = float(closes[-1]), float(closes[-2])
    out = []
    for hit in run_detectors(df, cfg):
        bp, stop = hit["buy_point"], hit["suggested_stop"]
        if not (prev <= bp < price):                 # not a fresh cross today
            continue
        risk = (bp - stop) / bp * 100.0 if bp else 999
        if risk > cfg.max_setup_risk_pct:            # only tight setups
            continue
        day_change = (price - prev) / prev * 100.0 if prev else None
        out.append({
            "pattern": hit["pattern"], "buy_point": round(bp, 2), "stop": round(stop, 2),
            "tight_stop": round(bp * (1 - cfg.tight_stop_pct), 2),
            "price": round(price, 2), "risk_pct": round(risk, 1), "rvol": hit["rvol"],
            "day_change": round(day_change, 1) if day_change is not None else None,
            "big_day": bool(day_change is not None and day_change >= cfg.big_day_pct),
            "score": compose_score(hit["_parts"], df, cfg),
            "reason": ", ".join(hit["reason_bits"]),
        })
    return out


def _unsent(events):  # pragma: no cover - DB
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15); cur = conn.cursor()
    cur.execute(_SENT_DDL)
    keys = [e["key"] for e in events]
    cur.execute("SELECT dedup_key FROM breakout_alerts_sent WHERE dedup_key = ANY(%s)", (keys,))
    seen = {r[0] for r in cur.fetchall()}
    cur.close(); conn.close()
    return [e for e in events if e["key"] not in seen]


def _mark_sent(events):  # pragma: no cover - DB
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15); cur = conn.cursor()
    cur.execute(_SENT_DDL)
    for e in events:
        cur.execute("INSERT INTO breakout_alerts_sent (dedup_key) VALUES (%s) ON CONFLICT DO NOTHING", (e["key"],))
    conn.commit(); cur.close(); conn.close()


def _chat_id():  # pragma: no cover - DB
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15); cur = conn.cursor()
    cur.execute("SELECT telegram_chat_id FROM users WHERE id = %s AND telegram_chat_id IS NOT NULL AND telegram_chat_id <> ''", (USER_ID,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0] if row else None


def _record_alerts(events, session_date):  # pragma: no cover - DB
    """Insert a Breakout-feed alert row per event for user 3 (so it appears in the signal feeds)."""
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15); cur = conn.cursor()
    for e in events:
        cur.execute(
            "INSERT INTO alerts (user_id, symbol, alert_type, direction, price, entry, stop, "
            "target_1, score, message, volume_ratio, session_date, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())",
            (USER_ID, e["sym"], f"breakout_{e['pattern']}", "BUY", e["price"], e["buy_point"],
             e["stop"], None, e["score"], e["msg"], e["rvol"], session_date),
        )
    conn.commit(); cur.close(); conn.close()


def _format(events) -> str:
    lines = ["<b>📈 Breakout signals</b> (TBA crossed)"]
    for e in events:
        extra = []
        if e.get("day_change") is not None:
            extra.append(f"{'🔥 ' if e.get('big_day') else ''}+{e['day_change']:.1f}% day")
        if e.get("earnings_days") is not None:
            extra.append(f"⚠ earnings in {e['earnings_days']}d")
        tail = ("  ·  " + " · ".join(extra)) if extra else ""
        lines.append(f"• <b>{e['sym']}</b> {_label(e['pattern'])} — buy ${e['buy_point']:.2f} · "
                     f"stop ${e['stop']:.2f} (tight ${e['tight_stop']:.2f} · risk {e['risk_pct']:.1f}%) · "
                     f"{e['rvol']}x · score {e['score']}{tail}")
    return "\n".join(lines)


def run(dry: bool = False) -> dict:  # pragma: no cover - network/DB
    from analytics.swing_setups_report import _watchlist
    syms = _watchlist(_dsn())
    date = _dt.date.today().isoformat()
    events = []
    for sym in syms:
        try:
            for ev in detect(_fetch(sym), CONFIG):
                ev["sym"] = sym.upper()
                ev["key"] = f"{ev['sym']}:{ev['pattern']}:{date}"
                ev["msg"] = f"{_label(ev['pattern'])} breakout — crossed TBA {ev['buy_point']:.2f}. {ev['reason']}"
                events.append(ev)
        except Exception:
            pass
    new = _unsent(events) if events else []
    for e in new:                                       # earnings context (few fires → affordable)
        try:
            from analytics.premium_desk_scan import _earnings_days
            e["earnings_days"] = _earnings_days(e["sym"])
        except Exception:
            e["earnings_days"] = None
    if not dry and new:
        _record_alerts(new, date)
        cid = _chat_id()
        if cid:
            from alerting.notifier import _send_telegram_to
            _send_telegram_to(_format(new), cid, parse_mode="HTML")
        _mark_sent(new)
    return {"scanned": len(syms), "fired": len(new), "events": new}


def main():  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    rep = run(dry=a.dry)
    print(f"breakout alerts: scanned {rep['scanned']} · fired {rep['fired']}")
    for e in rep["events"]:
        print(f"  {e['sym']:<6} {e['pattern']:<18} buy {e['buy_point']:.2f} stop {e['stop']:.2f} risk {e['risk_pct']}% score {e['score']}")


if __name__ == "__main__":
    main()
