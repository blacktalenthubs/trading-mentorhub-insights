"""Performance test: Monitor poll throughput with simulated users.

Creates N test users with watchlists, runs one poll cycle, measures duration.
Uses the V2 SQLAlchemy monitor against the dev database.

Usage:
    python3 tests/perf/test_monitor_load.py --users 20 --symbols-per-user 8
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
_root = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, _root)
sys.path.insert(0, str(Path(_root) / "api"))


def setup_test_users(db, num_users: int, symbols_per_user: int):
    """Create test users with subscriptions and watchlists."""
    from app.models.user import Subscription, User
    from app.models.watchlist import WatchlistItem

    ALL_SYMBOLS = [
        "SPY", "QQQ", "AAPL", "NVDA", "TSLA", "META", "MSFT", "AMZN",
        "GOOGL", "AMD", "BTC-USD", "ETH-USD", "NFLX", "JPM", "V",
        "DIS", "BA", "INTC", "COIN", "SQ",
    ]

    created_ids = []
    for i in range(num_users):
        email = f"perftest_{i}@test.com"
        # Check if already exists
        existing = db.execute(
            db.bind.dialect.identifier_preparer.__class__  # hack - just use raw SQL
        ) if False else None

        from sqlalchemy import select, text
        row = db.execute(select(User.id).where(User.email == email)).scalar_one_or_none()
        if row:
            created_ids.append(row)
            continue

        user = User(email=email, password_hash="$2b$12$test", display_name=f"PerfTest {i}")
        db.add(user)
        db.flush()

        db.add(Subscription(user_id=user.id, tier="pro", status="active"))

        # Assign symbols round-robin
        for j in range(symbols_per_user):
            sym = ALL_SYMBOLS[(i * symbols_per_user + j) % len(ALL_SYMBOLS)]
            db.add(WatchlistItem(user_id=user.id, symbol=sym))

        created_ids.append(user.id)

    db.commit()
    return created_ids


def cleanup_test_users(db):
    """Remove perf test users."""
    from sqlalchemy import text
    db.execute(text("DELETE FROM watchlist WHERE user_id IN (SELECT id FROM users WHERE email LIKE 'perftest_%')"))
    db.execute(text("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email LIKE 'perftest_%')"))
    db.execute(text("DELETE FROM alerts WHERE user_id IN (SELECT id FROM users WHERE email LIKE 'perftest_%')"))
    db.execute(text("DELETE FROM users WHERE email LIKE 'perftest_%'"))
    db.commit()


def run_test(num_users: int, symbols_per_user: int):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config import get_settings

    settings = get_settings()
    sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)

    print(f"\n{'='*60}")
    print(f"MONITOR LOAD TEST")
    print(f"  Users: {num_users}")
    print(f"  Symbols per user: {symbols_per_user}")
    print(f"  Max unique symbols: ~{min(num_users * symbols_per_user, 20)}")
    print(f"{'='*60}\n")

    # Setup
    print("Setting up test users...")
    with Session() as db:
        user_ids = setup_test_users(db, num_users, symbols_per_user)
    print(f"  Created/found {len(user_ids)} users")

    # Run poll cycle
    print("\nRunning poll cycle...")
    from app.background.monitor import poll_all_users

    start = time.time()
    total_alerts = poll_all_users(Session)
    duration = time.time() - start

    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"  Poll duration: {duration:.1f}s")
    print(f"  Alerts fired: {total_alerts}")
    print(f"  Users polled: {num_users}")
    print(f"{'='*60}")

    # Evaluate
    if duration < 90:
        print(f"\n  PASS — {duration:.1f}s < 90s threshold")
    elif duration < 120:
        print(f"\n  WARNING — {duration:.1f}s approaching 120s limit")
    else:
        print(f"\n  FAIL — {duration:.1f}s exceeds 120s limit")

    # Cleanup
    print("\nCleaning up test users...")
    with Session() as db:
        cleanup_test_users(db)
    print("  Done")

    engine.dispose()
    return duration


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--symbols-per-user", type=int, default=8)
    args = parser.parse_args()

    run_test(args.users, args.symbols_per_user)
