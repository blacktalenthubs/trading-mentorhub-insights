"""One-shot state check — run locally against Railway Postgres.

Usage:
    DATABASE_URL="postgresql://..." python3 scripts/check_state.py
"""
import os
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
cur = conn.cursor()

print("=== users (uid=3 / vbolofinde) ===")
cur.execute(
    "SELECT id, email, tier FROM users WHERE id = 3 OR email = 'vbolofinde@gmail.com'"
)
for row in cur.fetchall():
    print(" ", row)

print("\n=== vbolofinde's watchlist ===")
cur.execute("SELECT symbol FROM watchlist_items WHERE user_id = 3 ORDER BY symbol")
for row in cur.fetchall():
    print(" ", row[0])

print("\n=== ALL open real_trades ===")
cur.execute(
    """
    SELECT rt.user_id, u.email, rt.symbol, rt.direction,
           rt.entry_price, rt.opened_at, rt.status
    FROM real_trades rt
    LEFT JOIN users u ON u.id = rt.user_id
    WHERE rt.status = 'open'
    ORDER BY rt.opened_at DESC
    """
)
for row in cur.fetchall():
    print(" ", row)

print("\n=== user count by tier ===")
cur.execute("SELECT tier, COUNT(*) FROM users GROUP BY tier ORDER BY 2 DESC")
for row in cur.fetchall():
    print(" ", row)

cur.close()
conn.close()
