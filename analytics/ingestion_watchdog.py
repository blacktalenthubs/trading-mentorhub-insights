#!/usr/bin/env python3
"""Ingestion watchdog — detect a SILENT alert-ingestion outage.

The TV webhook swallows background errors: TradingView gets a 200, zero rows save,
nothing surfaces (bit us twice — #355 ~20h, #476 ~11h). The only reliable signal is
the DB: during RTH, max(alerts.id) and max(created_at) must keep ADVANCING. If they're
frozen while the market is open, ingestion is down.

This prints a JSON verdict the watchdog skill acts on — it does NOT page on its own.

    DATABASE_URL=postgresql://... python3 analytics/ingestion_watchdog.py [--stale-min 25]

Verdict JSON: {"status":"ok|stale|quiet|closed|error", "max_id":.., "last_alert_utc":..,
"age_min":.., "recent_count":.., "rth": true/false, "detail":".."}.
  ok     — RTH and a fresh alert within the window (ingestion flowing)
  stale  — RTH, market active, but NO alert in --stale-min  → LIKELY OUTAGE, investigate
  quiet  — RTH but legitimately could be a slow tape (low confidence; widen window/confirm)
  closed — outside RTH, nothing expected
"""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timezone


def _rth() -> bool:
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from analytics.market_hours import is_market_hours
        return bool(is_market_hours())
    except Exception:
        # Fallback: rough US RTH in UTC (13:30–20:00) Mon–Fri.
        now = datetime.now(timezone.utc)
        if now.weekday() >= 5:
            return False
        mins = now.hour * 60 + now.minute
        return 13 * 60 + 30 <= mins <= 20 * 60


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale-min", type=int, default=25,
                    help="RTH minutes with no new alert before flagging an outage")
    args = ap.parse_args()

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print(json.dumps({"status": "error", "detail": "DATABASE_URL not set"}))
        return

    try:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=15)
        cur = conn.cursor()
        cur.execute("SELECT MAX(id), MAX(created_at) FROM alerts")
        max_id, last_ts = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM alerts WHERE created_at >= NOW() - INTERVAL '%s minutes'"
                    % int(args.stale_min))
        recent = cur.fetchone()[0]
        cur.close()
        conn.close()
    except Exception as e:
        print(json.dumps({"status": "error", "detail": str(e)[:160]}))
        return

    rth = _rth()
    age_min = None
    if last_ts is not None:
        ref = last_ts if last_ts.tzinfo else last_ts.replace(tzinfo=timezone.utc)
        age_min = round((datetime.now(timezone.utc) - ref).total_seconds() / 60.0, 1)

    if not rth:
        status, detail = "closed", "outside RTH — no ingestion expected"
    elif recent and recent > 0:
        status, detail = "ok", f"{recent} alert(s) in the last {args.stale_min}m — flowing"
    elif age_min is not None and age_min > args.stale_min:
        status, detail = "stale", (f"NO alert in {args.stale_min}m during RTH "
                                   f"(last was {age_min}m ago) — likely a silent ingestion outage")
    else:
        status, detail = "quiet", "RTH but window inconclusive — widen --stale-min or confirm"

    print(json.dumps({
        "status": status, "max_id": max_id,
        "last_alert_utc": last_ts.isoformat() if last_ts else None,
        "age_min": age_min, "recent_count": recent, "rth": rth, "detail": detail,
    }))


if __name__ == "__main__":
    main()
