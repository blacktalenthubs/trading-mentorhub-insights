"""Dump recent AI UPDATE (WAIT) reasons from production DB.

Usage: DATABASE_URL=<url> python3 scripts/dump_wait_reasons.py
"""
import os, sys
import psycopg2

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("Set DATABASE_URL first")
    sys.exit(1)

conn = psycopg2.connect(db_url, connect_timeout=10)
cur = conn.cursor()
cur.execute("""
    SELECT symbol, price, message, created_at
    FROM alerts
    WHERE direction = 'WAIT'
      AND created_at >= NOW() - INTERVAL '48 hours'
    ORDER BY created_at DESC
    LIMIT 50
""")
for sym, price, msg, ts in cur.fetchall():
    print(f"{ts} | {sym:8s} | ${price:>9.2f} | {(msg or '')[:120]}")
conn.close()
