#!/usr/bin/env python3
"""Format + persist the daily TV-watchlist-sync report. The agentic flow pipes the
reconcile result in as JSON; this writes a markdown report into `market_reports`
(kind='watchlist_sync') — the same in-app store as the premarket/EOD reports — and
echoes it to stdout (so the cron run's output also carries it).

    echo '<diff json>' | DATABASE_URL=postgresql://... python3 analytics/tv_sync_report.py --date 2026-06-28

Input JSON (all keys optional, sensible defaults):
  { "before": 39, "after": 151,
    "added":   ["AMD","COHR",...],     # symbols pushed into the master this run
    "extras":  ["NKE","IYT",...],      # in TV, on no platform watchlist (left alone)
    "new_from_ibd": ["TVTX","HUT",...],# brand-new IBD discovery names
    "failures": ["BADSYM"],            # adds that didn't resolve
    "sections": [["IBD 50",46],...],   # section -> count
    "mode": "sectioned-import" }       # or "flat-add"
"""
from __future__ import annotations
import json, os, sys, argparse
from datetime import datetime


def _md(d: dict, date: str) -> str:
    before, after = d.get("before"), d.get("after")
    added = d.get("added") or []
    extras = d.get("extras") or []
    new_ibd = d.get("new_from_ibd") or []
    fails = d.get("failures") or []
    mode = d.get("mode", "sectioned-import")
    # NEW USER PICKS = symbols added this run that came from a user's watchlist (not IBD).
    # These are the names users started tracking that we didn't already cover — the most
    # interesting line of the report (what the crowd is onto). Derive if not passed.
    new_users = d.get("new_from_users")
    if new_users is None:
        new_users = sorted(set(added) - set(new_ibd))
    L = [f"# TV Watchlist Sync — {date}", ""]
    delta = "" if before is None or after is None else f" ({before} → {after}, {after-before:+d})"
    L.append(f"**all_sectors reconciled to the platform**{delta} · mode: `{mode}`")
    L.append("")
    if new_users:
        L.append(f"- ⭐ **NEW user picks we didn't cover ({len(new_users)})** — what users started tracking: "
                 + ", ".join(new_users[:40]) + (" …" if len(new_users) > 40 else ""))
    L.append(f"- ✅ **Added {len(added)}**" + (": " + ", ".join(added[:40]) + (" …" if len(added) > 40 else "") if added else " — none (already in sync)"))
    if new_ibd:
        L.append(f"- 🆕 **New IBD discovery {len(new_ibd)}**: " + ", ".join(new_ibd[:40]) + (" …" if len(new_ibd) > 40 else ""))
    if fails:
        L.append(f"- ⚠️ **Failed to resolve {len(fails)}**: " + ", ".join(fails))
    if extras:
        L.append(f"- ℹ️ **Extras in TV, not on any watchlist {len(extras)}** (left as-is): " + ", ".join(extras[:30]))
    if d.get("sections"):
        L.append("")
        L.append("**Sections:** " + " · ".join(f"{n} {c}" for n, c in d["sections"]))
    if not added and not fails:
        L.append("")
        L.append("_No change — TV already matches the platform._")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.utcnow().strftime("%Y-%m-%d"))
    ap.add_argument("--no-persist", action="store_true", help="format + print only, don't write DB")
    args = ap.parse_args()

    raw = sys.stdin.read().strip()
    try:
        diff = json.loads(raw) if raw else {}
    except Exception as e:
        sys.exit(f"bad diff JSON on stdin: {str(e)[:120]}")

    body = _md(diff, args.date)
    print(body)

    if args.no_persist:
        return
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("Set DATABASE_URL to persist the report (or pass --no-persist).")
    import psycopg2
    conn = psycopg2.connect(dsn, connect_timeout=15)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO market_reports (kind, session_date, body, created_at) "
            "VALUES ('watchlist_sync', %s, %s, NOW())",
            (args.date, body),
        )
        conn.commit()
        cur.close()
        print(f"\n[persisted to market_reports kind=watchlist_sync session_date={args.date}]")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
