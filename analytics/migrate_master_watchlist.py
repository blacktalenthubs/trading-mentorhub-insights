#!/usr/bin/env python3
"""One-off migration: create a dedicated MASTER watchlist account and COPY the admin's
(vbolofinde, id 3) groups + watchlist into it. Idempotent — safe to re-run.

After this, the master account holds the platform universe (sectors template + scanner
universe), decoupled from vbolofinde's PERSONAL watchlist. vbolofinde keeps its current
list untouched (no alert-behaviour change) and can curate it down via the UI.
"""
import os, sys, psycopg2

MASTER_EMAIL = "master@busytradersdesk"
SRC_EMAIL = "vbolofinde@gmail.com"

dsn = os.environ.get("DATABASE_URL")
if not dsn:
    sys.exit("set DATABASE_URL")
conn = psycopg2.connect(dsn, connect_timeout=20)
conn.autocommit = False
cur = conn.cursor()
try:
    cur.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (SRC_EMAIL,))
    row = cur.fetchone()
    if not row:
        sys.exit(f"source {SRC_EMAIL} not found")
    src_id = row[0]

    cur.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (MASTER_EMAIL,))
    row = cur.fetchone()
    if row:
        master_id = row[0]
        print(f"master account exists: id={master_id}")
    else:
        cur.execute("INSERT INTO users (email, display_name, swing_alerts_enabled) "
                    "VALUES (%s, %s, false) RETURNING id", (MASTER_EMAIL, "Master Watchlist"))
        master_id = cur.fetchone()[0]
        print(f"created master account id={master_id}")

    cur.execute("SELECT COUNT(*) FROM watchlist WHERE user_id=%s", (master_id,))
    if cur.fetchone()[0] > 0:
        print("master already has watchlist rows — skipping copy (idempotent).")
        conn.commit()
        sys.exit(0)

    # copy groups, mapping old_gid -> new_gid
    cur.execute("SELECT id, name, sort_order, color FROM watchlist_group WHERE user_id=%s ORDER BY id", (src_id,))
    gmap = {}
    for gid, name, sort_order, color in cur.fetchall():
        cur.execute("INSERT INTO watchlist_group (user_id, name, sort_order, color) "
                    "VALUES (%s,%s,%s,%s) RETURNING id", (master_id, name, sort_order, color))
        gmap[gid] = cur.fetchone()[0]
    print(f"copied {len(gmap)} groups")

    # copy watchlist rows with mapped group_id
    cur.execute("SELECT symbol, group_id, focus FROM watchlist WHERE user_id=%s", (src_id,))
    n = 0
    for symbol, group_id, focus in cur.fetchall():
        cur.execute("INSERT INTO watchlist (user_id, symbol, group_id, focus) VALUES (%s,%s,%s,%s)",
                    (master_id, symbol, gmap.get(group_id), focus))
        n += 1
    print(f"copied {n} watchlist symbols")

    conn.commit()
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT symbol) FROM watchlist WHERE user_id=%s", (master_id,))
    print("master now:", cur.fetchone())
    cur.execute("SELECT COUNT(*) FROM watchlist WHERE user_id=%s", (src_id,))
    print("vbolofinde unchanged:", cur.fetchone()[0])
finally:
    cur.close(); conn.close()
