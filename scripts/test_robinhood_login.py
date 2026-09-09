"""One-off Robinhood auth + import test — run locally, no deploy needed.

Verifies the credentials and the TOTP seed BEFORE they go on Railway, so a
scheduled 16:45 ET job does not turn out to be the first login attempt.

Usage:
    export ROBINHOOD_USERNAME="you@example.com"
    export ROBINHOOD_PASSWORD="..."
    export ROBINHOOD_TOTP_SECRET="JBSWY3DPEHPK3PXP"   # the setup key, not a 6-digit code
    python3 scripts/test_robinhood_login.py

Read-only: it logs in, prints today's filled orders, and writes NOTHING to the
database. Exits 0 when login and fetch both work.

Stage 1 runs with no network at all — if the seed is malformed you find out
before an authentication attempt is ever made against the account.
"""
from __future__ import annotations

import os
import sys
from datetime import date


def main() -> int:
    username = os.environ.get("ROBINHOOD_USERNAME", "")
    password = os.environ.get("ROBINHOOD_PASSWORD", "")
    secret = os.environ.get("ROBINHOOD_TOTP_SECRET", "")

    if not username or not password:
        print("FAIL: ROBINHOOD_USERNAME / ROBINHOOD_PASSWORD not set")
        return 1
    if not secret:
        print("FAIL: ROBINHOOD_TOTP_SECRET not set — unattended login needs the")
        print("      authenticator SETUP KEY (base32), not a 6-digit code.")
        return 1

    # ── Stage 1: the seed itself, offline ────────────────────────────
    try:
        import pyotp
    except ImportError:
        print("FAIL: pyotp not installed — pip install pyotp")
        return 1

    try:
        code = pyotp.TOTP(secret).now()
    except Exception as exc:
        print(f"FAIL: TOTP secret is not valid base32 ({type(exc).__name__}).")
        print("      Copy the setup key from Robinhood's 'Can't scan it?' screen —")
        print("      letters A-Z and digits 2-7 only, no spaces.")
        return 1

    print(f"TOTP secret parses. Current code: {code}")
    print("  -> Compare this against your phone's authenticator RIGHT NOW.")
    print("     If they differ, the seed is from a different account or was mistyped,")
    print("     and every unattended login will fail.\n")

    # ── Stage 2: live login ──────────────────────────────────────────
    try:
        import robin_stocks.robinhood as rh
    except ImportError:
        print("FAIL: robin_stocks not installed — pip install robin_stocks")
        return 1

    try:
        rh.login(username=username, password=password, mfa_code=code, store_session=True)
    except Exception as exc:
        # Never echo the exception body — it can carry request details.
        print(f"FAIL: login rejected ({type(exc).__name__})")
        print("      Common causes: 2FA still set to SMS rather than an authenticator app;")
        print("      a device-approval prompt waiting in the Robinhood app or your email.")
        return 1

    print("Login OK. Session stored — later runs will usually skip the MFA round-trip.\n")

    # ── Stage 3: read today's fills ──────────────────────────────────
    try:
        stock_orders = rh.get_all_stock_orders() or []
    except Exception as exc:
        print(f"FAIL: could not fetch stock orders ({type(exc).__name__})")
        return 1

    try:
        option_orders = rh.get_all_option_orders() or []
    except Exception:
        print("WARN: option order fetch failed — stocks-only import would still work")
        option_orders = []

    print(f"Fetched {len(stock_orders)} stock orders, {len(option_orders)} option orders.")

    # Run the real normalizers so this exercises the code the job will run.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from brokers.robinhood import normalize_orders

    client_cache: dict[str, str] = {}

    def _symbol(url: str) -> str:
        if url not in client_cache:
            try:
                client_cache[url] = (rh.get_symbol_by_url(url) or "").upper()
            except Exception:
                client_cache[url] = ""
        return client_cache[url]

    fills = normalize_orders(stock_orders, option_orders, _symbol)
    today = [(ext, t) for ext, t in fills if t.trade_date == date.today()]

    print(f"Normalized {len(fills)} total fills, {len(today)} dated today.\n")
    for ext, t in today:
        print(f"  {t.trade_date}  {t.transaction_type:4}  {t.symbol:24} "
              f"qty {t.quantity:g} @ ${t.price:.4f}  [{ext}]")

    if not today:
        print("  (no fills today — expected on a day you did not trade)")

    print("\nPASS: credentials and import path both work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
