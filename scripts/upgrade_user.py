#!/usr/bin/env python3
"""Admin CLI to manually set a user's subscription tier.

Usage:
    python scripts/upgrade_user.py user@email.com pro
    python scripts/upgrade_user.py user@email.com elite
    python scripts/upgrade_user.py user@email.com free
"""

from __future__ import annotations

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db, init_db, upsert_subscription, get_subscription

VALID_TIERS = ("free", "pro", "elite")


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <email> <tier>")
        print(f"  Valid tiers: {', '.join(VALID_TIERS)}")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    tier = sys.argv[2].strip().lower()

    if tier not in VALID_TIERS:
        print(f"Error: Invalid tier '{tier}'. Must be one of: {', '.join(VALID_TIERS)}")
        sys.exit(1)

    init_db()

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, email, display_name FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not row:
        print(f"Error: No user found with email '{email}'")
        sys.exit(1)

    user_id = row["id"]
    old_sub = get_subscription(user_id)
    old_tier = old_sub["tier"] if old_sub else "none"

    upsert_subscription(user_id, tier)

    print(f"Updated: {email} (id={user_id})")
    print(f"  {old_tier} -> {tier}")


if __name__ == "__main__":
    main()
