"""Performance test: Concurrent API load simulation.

Simulates N users hitting key endpoints simultaneously.

Usage:
    python3 tests/perf/test_api_load.py --users 20 --duration 30
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, _root)

# Use aiohttp for async HTTP
try:
    import aiohttp
except ImportError:
    print("Install aiohttp: pip3 install aiohttp")
    sys.exit(1)


API_BASE = "http://localhost:8000/api/v1"

ENDPOINTS = [
    ("GET", "/alerts/today"),
    ("GET", "/watchlist"),
    ("GET", "/market/status"),
]


async def get_token(session: aiohttp.ClientSession, email: str, password: str) -> str:
    """Login and get access token."""
    async with session.post(f"{API_BASE}/auth/login", json={"email": email, "password": password}) as resp:
        if resp.status != 200:
            return ""
        data = await resp.json()
        return data.get("access_token", "")


async def hit_endpoint(session: aiohttp.ClientSession, token: str, method: str, path: str) -> dict:
    """Hit an endpoint and measure latency."""
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    try:
        async with session.request(method, f"{API_BASE}{path}", headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            await resp.read()
            latency = time.time() - start
            return {"path": path, "status": resp.status, "latency": latency, "error": None}
    except Exception as e:
        return {"path": path, "status": 0, "latency": time.time() - start, "error": str(e)}


async def user_loop(session: aiohttp.ClientSession, token: str, duration: int, results: list):
    """Simulate one user hitting endpoints in a loop."""
    end_time = time.time() + duration
    while time.time() < end_time:
        for method, path in ENDPOINTS:
            result = await hit_endpoint(session, token, method, path)
            results.append(result)
        await asyncio.sleep(0.5)  # Brief pause between cycles


async def run_test(num_users: int, duration: int):
    print(f"\n{'='*60}")
    print(f"API LOAD TEST")
    print(f"  Concurrent users: {num_users}")
    print(f"  Duration: {duration}s")
    print(f"  Endpoints: {len(ENDPOINTS)}")
    print(f"{'='*60}\n")

    # Login with the main test user
    async with aiohttp.ClientSession() as session:
        print("Authenticating...")
        token = await get_token(session, "vbolofinde@gmail.com", "test1234")
        if not token:
            print("  FAIL — could not authenticate. Is the API running?")
            return

        print(f"  Token obtained. Starting {num_users} concurrent users...\n")

        results = []
        start = time.time()

        # Launch N concurrent user loops (all share the same token for simplicity)
        tasks = [user_loop(session, token, duration, results) for _ in range(num_users)]
        await asyncio.gather(*tasks)

        total_time = time.time() - start

    # Analyze results
    print(f"\n{'='*60}")
    print(f"RESULTS ({len(results)} requests in {total_time:.1f}s)")
    print(f"{'='*60}")

    errors = [r for r in results if r["error"] or r["status"] >= 400]
    success = [r for r in results if not r["error"] and r["status"] < 400]

    if success:
        latencies = [r["latency"] for r in success]
        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print(f"\n  Successful: {len(success)}")
        print(f"  Errors: {len(errors)}")
        print(f"  Error rate: {len(errors) / len(results) * 100:.1f}%")
        print(f"\n  Latency:")
        print(f"    p50: {p50*1000:.0f}ms")
        print(f"    p95: {p95*1000:.0f}ms")
        print(f"    p99: {p99*1000:.0f}ms")
        print(f"    max: {max(latencies)*1000:.0f}ms")
        print(f"\n  Throughput: {len(results)/total_time:.1f} req/s")

        # Per-endpoint breakdown
        print(f"\n  Per-endpoint p95:")
        for _, path in ENDPOINTS:
            ep_latencies = sorted([r["latency"] for r in success if r["path"] == path])
            if ep_latencies:
                ep_p95 = ep_latencies[int(len(ep_latencies) * 0.95)]
                print(f"    {path}: {ep_p95*1000:.0f}ms ({len(ep_latencies)} reqs)")

        # Evaluate
        print(f"\n{'='*60}")
        if p95 < 2.0 and len(errors) / len(results) < 0.01:
            print(f"  PASS — p95 {p95*1000:.0f}ms < 2000ms, error rate {len(errors)/len(results)*100:.1f}% < 1%")
        else:
            if p95 >= 2.0:
                print(f"  FAIL — p95 {p95*1000:.0f}ms >= 2000ms")
            if len(errors) / len(results) >= 0.01:
                print(f"  FAIL — error rate {len(errors)/len(results)*100:.1f}% >= 1%")
    else:
        print(f"\n  ALL REQUESTS FAILED ({len(errors)} errors)")
        for e in errors[:5]:
            print(f"    {e['path']}: {e['error']}")

    if errors:
        print(f"\n  Sample errors:")
        for e in errors[:3]:
            print(f"    {e['path']}: status={e['status']} error={e['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--duration", type=int, default=30)
    args = parser.parse_args()

    asyncio.run(run_test(args.users, args.duration))
