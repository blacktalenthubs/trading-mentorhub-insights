"""Today-tab writer for the breakout scanner. Same pipeline as every other producer: upsert
one row per (kind, session_date) into market_reports; the app's /market-report/latest bundle
picks it up. Idempotent by construction — re-running the same date REPLACES the body (never
appends), and an empty result still writes a marker so the tab shows "no setups", not yesterday.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

KIND = "breakout_setups"


def build_body(rep: dict) -> dict:
    """The stored body. Dedups rows by (ticker, pattern) keeping the best score, so a re-run or
    an overlapping detector can never double a name."""
    seen: dict[tuple, dict] = {}
    for r in rep.get("rows", []):
        key = (r["ticker"], r["pattern"])
        if key not in seen or r["score"] > seen[key]["score"]:
            seen[key] = r
    rows = sorted(seen.values(),
                  key=lambda r: ({"breakout": 0, "forming": 1}.get(r["stage"], 9), -r["score"]))
    return {
        "rows": rows,
        "scanned": rep.get("scanned", 0),
        "funnel": rep.get("funnel", {}),
        "empty": len(rows) == 0,
        "generated_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def publish(rep: dict, session_date: str, dsn: str | None = None) -> dict:  # pragma: no cover - DB
    body = build_body(rep)
    import psycopg2
    conn = psycopg2.connect(dsn or os.environ["DATABASE_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_reports (
        kind TEXT NOT NULL, session_date TEXT NOT NULL, body TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), PRIMARY KEY (kind, session_date))""")
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body, created_at) VALUES (%s, %s, %s, NOW()) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (KIND, session_date, json.dumps(body)),
    )
    conn.commit(); cur.close(); conn.close()
    return body
