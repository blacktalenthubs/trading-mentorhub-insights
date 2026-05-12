#!/usr/bin/env python3
"""List all alerts that fired today (ET) for a given user.

Usage:
    DATABASE_URL=postgresql://...  TRIAGE_USER_ID=3  python3 scripts/today_alerts.py
    railway run -- python3 scripts/today_alerts.py

The alerts table doesn't have a `notified_telegram` column — Telegram
delivery is tracked separately in the triage-agent audit log. This
script lists everything ingested today, which is the upper bound on
what got sent. To filter to "actually delivered" only, check the
audit log at /data/.triage-audit.jsonl on the triage-agent service.
"""
import os
import sys
import psycopg2
import psycopg2.extras
from zoneinfo import ZoneInfo

DB = os.environ.get("DATABASE_URL")
USER_ID = int(os.environ.get("TRIAGE_USER_ID", "3"))

if not DB:
    sys.exit("DATABASE_URL not set — run via `railway run` or export it explicitly.")
if DB.startswith("sqlite"):
    sys.exit("DATABASE_URL points to SQLite — needs the prod Postgres URL to query live alerts.")

con = psycopg2.connect(DB)
cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
cur.execute("""
    SELECT id, symbol, alert_type, direction, price, entry, stop,
           target_1, target_2, score, confidence, created_at
      FROM alerts
     WHERE user_id = %s
       AND DATE(created_at AT TIME ZONE 'America/New_York')
         = (NOW() AT TIME ZONE 'America/New_York')::date
     ORDER BY created_at DESC
""", (USER_ID,))
rows = cur.fetchall()
ET = ZoneInfo("America/New_York")

print(f"\n{len(rows)} alerts for user_id={USER_ID} today (ET)\n")
print(f"{'ID':>7}  {'TIME (ET)':<19}  {'SYMBOL':<10} {'DIR':<6} "
      f"{'RULE':<36}  {'PRICE':>10}  {'SCORE':>5}")
print("-" * 115)
for r in rows:
    t = r["created_at"].astimezone(ET).strftime("%Y-%m-%d %H:%M:%S")
    rule = (r["alert_type"] or "")[:36]
    price = r["price"] or 0.0
    score = r["score"] or 0
    print(f"{r['id']:>7}  {t:<19}  {r['symbol']:<10} {r['direction']:<6} "
          f"{rule:<36}  ${price:>9.2f}  {score:>5}")

# Quick breakdown by alert type
if rows:
    from collections import Counter
    by_type = Counter(r["alert_type"] for r in rows)
    by_symbol = Counter(r["symbol"] for r in rows)
    by_direction = Counter(r["direction"] for r in rows)
    print(f"\nBreakdown by rule:")
    for t, c in by_type.most_common():
        print(f"  {c:>4}  {t}")
    print(f"\nBreakdown by symbol:")
    for s, c in by_symbol.most_common():
        print(f"  {c:>4}  {s}")
    print(f"\nBreakdown by direction:")
    for d, c in by_direction.most_common():
        print(f"  {c:>4}  {d}")

con.close()
