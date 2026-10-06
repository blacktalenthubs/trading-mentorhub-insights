"""Audit 4h SMA support/reject alerts: how many fired, how many were DELIVERED
(suppressed_reason IS NULL) vs suppressed, and why. Run against prod:

    DATABASE_URL="<prod postgres url>" python3 scripts/audit_4h_signals.py [days]

Default window: 14 days. Without DATABASE_URL it reads the local SQLite, which may
have an older schema (no suppressed_reason) — then it just reports totals.
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_db

days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat()


def _has_suppressed_col() -> bool:
    try:
        with get_db() as db:
            db.execute("SELECT suppressed_reason FROM alerts LIMIT 1").fetchone()
        return True
    except Exception:
        return False


has_sup = _has_suppressed_col()
print(f"=== 4h alerts in the last {days} days ===")

with get_db() as db:
    if has_sup:
        rows = db.execute(
            """
            SELECT alert_type,
                   COUNT(*) AS total,
                   SUM(CASE WHEN suppressed_reason IS NULL THEN 1 ELSE 0 END) AS delivered,
                   MAX(created_at) AS last_seen
            FROM alerts
            WHERE alert_type LIKE ? AND created_at > ?
            GROUP BY alert_type ORDER BY alert_type
            """,
            ("%4h", cutoff),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT alert_type, COUNT(*) AS total, MAX(created_at) AS last_seen
            FROM alerts
            WHERE alert_type LIKE ? AND created_at > ?
            GROUP BY alert_type ORDER BY alert_type
            """,
            ("%4h", cutoff),
        ).fetchall()

if not rows:
    print("  (none fired at all in this window — 4h rules enabled but no touches recorded)")
elif has_sup:
    print(f"  {'alert_type':22} {'total':>6} {'delivered':>10}   last_seen")
    for at, total, delivered, last_seen in rows:
        print(f"  {at:22} {total:>6} {delivered:>10}   {last_seen}")
else:
    print("  (local schema has no suppressed_reason — totals only)")
    print(f"  {'alert_type':22} {'total':>6}   last_seen")
    for at, total, last_seen in rows:
        print(f"  {at:22} {total:>6}   {last_seen}")

if has_sup:
    with get_db() as db:
        br = db.execute(
            """
            SELECT COALESCE(suppressed_reason, '(delivered)') AS reason, COUNT(*) AS n
            FROM alerts
            WHERE alert_type LIKE ? AND created_at > ?
            GROUP BY reason ORDER BY n DESC
            """,
            ("%4h", cutoff),
        ).fetchall()
    print("\n  suppression breakdown:")
    for reason, n in br:
        print(f"    {reason:28} {n}")
