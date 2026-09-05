"""Verify APNs actually reaches the phone.

Run on a machine that has the Railway env (DATABASE_URL + APNS_* + the .p8 key):

    python3 scripts/test_apns.py                       # vbolofinde@gmail.com
    python3 scripts/test_apns.py --email you@x.com

It (1) checks the APNs client config, (2) pulls that user's registered iOS
tokens from the DB, and (3) sends a REAL test push to each — printing per-token
success or the exact failure reason (BadDeviceToken / Unregistered / config
missing / sandbox-vs-production mismatch). Logging is on so aioapns' own
response.description prints.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _clean_dsn(url: str) -> str:
    for suffix in ("+asyncpg", "+psycopg2", "+psycopg", "+aiosqlite"):
        url = url.replace(suffix, "")
    return url


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="vbolofinde@gmail.com")
    args = ap.parse_args()

    from app.services.push_service import _get_client, send_push

    # 1) config
    client = _get_client()
    print("\n── APNs config ──")
    for v in ("APNS_KEY_ID", "APNS_TEAM_ID", "APNS_KEY_PATH", "APNS_TOPIC", "APNS_USE_SANDBOX"):
        print(f"   {v} = {os.environ.get(v) or '(unset)'}")
    if client is None:
        print("\n❌ APNs client NOT configured — the Monitor's send_push_sync returns 0 silently.")
        print("   Set APNS_KEY_ID / APNS_TEAM_ID / APNS_KEY_PATH (and place the .p8) on the worker.")
        return
    sandbox = os.environ.get("APNS_USE_SANDBOX", "0") == "1"
    print(f"\n✅ APNs client initialized (sandbox={sandbox}). "
          f"Note: TestFlight build ⇒ sandbox=1, App Store build ⇒ sandbox=0. A mismatch fails silently as BadDeviceToken.")

    # 2) tokens
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("\n❌ DATABASE_URL not set — can't look up device tokens.")
        return
    import psycopg2
    con = psycopg2.connect(_clean_dsn(dsn)); con.set_session(readonly=True); cur = con.cursor()
    cur.execute("""select dt.token, dt.created_at::timestamp(0)
                   from device_tokens dt join users u on u.id = dt.user_id
                   where lower(u.email) = %s and dt.platform = 'ios'
                   order by dt.created_at desc""", (args.email.lower(),))
    tokens = cur.fetchall(); con.close()
    print(f"\n── {args.email}: {len(tokens)} iOS token(s) ──")
    if not tokens:
        print("   ❌ No iOS tokens registered — the app must register one (open it, grant notifications).")
        return

    # 3) send a real test push to each
    async def run() -> None:
        for tok, created in tokens:
            ok = await send_push(tok, "Scanner test",
                                 "APNs works ✅ — you can receive scanner pushes.",
                                 data={"test": "1"})
            print(f"   {'✅ delivered' if ok else '❌ FAILED'}  token={tok[:14]}…  registered={created}")
    asyncio.run(run())
    print("\nIf any say ✅ delivered, check your phone. If all ❌, the WARNING line above names the APNs reason.")


if __name__ == "__main__":
    main()
