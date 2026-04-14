"""One-off Alpaca auth test — run locally, no deploy needed.

Usage:
    export ALPACA_API_KEY="PKKSP2DXRKKMVV6BNQDJDTUWHU"
    export ALPACA_SECRET_KEY="<your new secret>"
    python3 scripts/test_alpaca.py

Exits 0 if both stocks + crypto auth work, 1 otherwise.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import requests


def main() -> int:
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not key or not secret:
        print("❌ ALPACA_API_KEY or ALPACA_SECRET_KEY not set in env")
        return 1

    print(f"Key:    {key[:6]}...{key[-4:]}")
    print(f"Secret: {secret[:4]}...{secret[-4:]}")
    print("-" * 60)

    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }

    # Use a known past date for stock bars (weekend-safe).
    end = datetime.now(timezone.utc) - timedelta(hours=1)
    start = end - timedelta(days=5)
    start_iso = start.isoformat().replace("+00:00", "Z")
    end_iso = end.isoformat().replace("+00:00", "Z")

    all_ok = True

    # Test 1: Stock bars (SPY daily)
    print("\n▶ TEST 1 — Stocks (SPY daily bars)")
    try:
        r = requests.get(
            "https://data.alpaca.markets/v2/stocks/SPY/bars",
            headers=headers,
            params={
                "timeframe": "1Day",
                "start": start_iso,
                "end": end_iso,
                "limit": 10,
                "feed": "iex",
            },
            timeout=10,
        )
        print(f"  status={r.status_code}")
        if r.status_code == 200:
            bars = r.json().get("bars", [])
            print(f"  ✅ returned {len(bars)} bars")
            if bars:
                b = bars[-1]
                print(f"  last bar: t={b.get('t')} close=${b.get('c')}")
        else:
            print(f"  ❌ {r.text[:300]}")
            all_ok = False
    except Exception as e:
        print(f"  ❌ exception: {e}")
        all_ok = False

    # Test 2: Crypto bars (BTC/USD)
    print("\n▶ TEST 2 — Crypto (BTC/USD 1-hour bars)")
    try:
        r = requests.get(
            "https://data.alpaca.markets/v1beta3/crypto/us/bars",
            headers=headers,
            params={
                "symbols": "BTC/USD",
                "timeframe": "1Hour",
                "start": start_iso,
                "end": end_iso,
                "limit": 10,
            },
            timeout=10,
        )
        print(f"  status={r.status_code}")
        if r.status_code == 200:
            data = r.json().get("bars", {})
            bars = data.get("BTC/USD", [])
            print(f"  ✅ returned {len(bars)} bars")
            if bars:
                b = bars[-1]
                print(f"  last bar: t={b.get('t')} close=${b.get('c')}")
        else:
            print(f"  ❌ {r.text[:300]}")
            all_ok = False
    except Exception as e:
        print(f"  ❌ exception: {e}")
        all_ok = False

    # Test 3: Crypto latest bar (BCH/USD — the ambiguous one)
    print("\n▶ TEST 3 — Crypto ambiguity check (BCH/USD latest bar)")
    try:
        r = requests.get(
            "https://data.alpaca.markets/v1beta3/crypto/us/latest/bars",
            headers=headers,
            params={"symbols": "BCH/USD"},
            timeout=10,
        )
        print(f"  status={r.status_code}")
        if r.status_code == 200:
            data = r.json().get("bars", {})
            bar = data.get("BCH/USD")
            if bar:
                print(f"  ✅ Bitcoin Cash price = ${bar.get('c')}")
            else:
                print("  ⚠ no bar returned for BCH/USD")
        else:
            print(f"  ❌ {r.text[:200]}")
    except Exception as e:
        print(f"  ❌ exception: {e}")

    # Test 4: Equity BCH (to confirm collision — Banco de Chile)
    print("\n▶ TEST 4 — Equity ambiguity check (BCH = Banco de Chile)")
    try:
        r = requests.get(
            "https://data.alpaca.markets/v2/stocks/BCH/bars/latest",
            headers=headers,
            params={"feed": "iex"},
            timeout=10,
        )
        print(f"  status={r.status_code}")
        if r.status_code == 200:
            bar = r.json().get("bar")
            if bar:
                print(f"  ✅ Banco de Chile price = ${bar.get('c')}")
        else:
            print(f"  ⚠ {r.text[:200]}")
    except Exception as e:
        print(f"  ❌ exception: {e}")

    print("\n" + "=" * 60)
    if all_ok:
        print("✅ AUTH WORKS — safe to migrate data source to Alpaca")
    else:
        print("❌ AUTH FAILED — check keys in Alpaca dashboard + env vars")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
