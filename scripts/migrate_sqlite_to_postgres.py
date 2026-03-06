"""One-time migration: copy data from SQLite → Railway Postgres.

Usage:
    DATABASE_URL="postgresql://..." python scripts/migrate_sqlite_to_postgres.py [path/to/trades.db]

If no path is given, defaults to data/trades.db.

What it migrates (in order):
    1. users                  — login accounts
    2. user_notification_prefs — telegram/email settings
    3. watchlist              — symbol lists
    4. alerts                 — full alert history
    5. active_entries         — active BUY entries (session-scoped)
    6. daily_plans            — scanner plans
    7. paper_trades           — paper trade history
    8. real_trades            — real trade history
    9. real_options_trades    — options trade history
   10. swing_trades           — swing trade history
   11. swing_categories       — swing scanner categories

Skips empty tables automatically. Safe to re-run (uses ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

import os
import sqlite3
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL env var is required.")
        print("Usage: DATABASE_URL='postgresql://...' python scripts/migrate_sqlite_to_postgres.py")
        sys.exit(1)

    sqlite_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "data", "trades.db"
    )

    if not os.path.exists(sqlite_path):
        print(f"ERROR: SQLite DB not found at {sqlite_path}")
        sys.exit(1)

    import psycopg2
    import psycopg2.extras

    # --- Connect to both databases ---
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    dst = psycopg2.connect(database_url)
    dst.autocommit = False
    cur = dst.cursor()

    # --- Ensure Postgres schema exists ---
    print("Ensuring Postgres schema is initialized...")
    os.environ["DATABASE_URL"] = database_url
    from db import init_db
    init_db()

    # --- Tables to migrate (order matters for FK dependencies) ---
    TABLES = [
        {
            "name": "users",
            "columns": "id, email, password_hash, display_name, created_at",
            "conflict": "ON CONFLICT (email) DO NOTHING",
        },
        {
            "name": "user_notification_prefs",
            "columns": "user_id, telegram_chat_id, notification_email, telegram_enabled, email_enabled, anthropic_api_key, created_at, updated_at",
            "conflict": "ON CONFLICT (user_id) DO NOTHING",
        },
        {
            "name": "watchlist",
            "columns": "user_id, symbol, added_at",
            "conflict": "ON CONFLICT (user_id, symbol) DO NOTHING",
        },
        {
            "name": "alerts",
            "columns": "symbol, alert_type, direction, price, entry, stop, target_1, target_2, confidence, message, narrative, score, notified_email, notified_sms, created_at, session_date, user_id",
            "conflict": "",
            "skip_if_exists": True,  # No unique constraint — only insert if table is empty
        },
        {
            "name": "active_entries",
            "columns": "symbol, entry_price, stop_price, target_1, target_2, alert_type, session_date, status, created_at",
            "conflict": "ON CONFLICT (symbol, session_date, alert_type) DO NOTHING",
        },
        {
            "name": "daily_plans",
            "columns": "symbol, session_date, support, support_label, support_status, entry, stop, target_1, target_2, score, score_label, pattern, created_at",
            "conflict": "ON CONFLICT (symbol, session_date) DO NOTHING",
        },
        {
            "name": "paper_trades",
            "columns": "symbol, direction, shares, entry_price, exit_price, stop_price, target_price, pnl, status, alert_type, alert_id, alpaca_order_id, alpaca_close_order_id, session_date, opened_at, closed_at",
            "conflict": "",
            "skip_if_exists": True,
        },
        {
            "name": "real_trades",
            "columns": "symbol, direction, shares, entry_price, exit_price, stop_price, target_price, target_2_price, pnl, status, alert_type, alert_id, notes, session_date, opened_at, closed_at, trade_type, stop_type, target_type, entry_rsi",
            "conflict": "",
            "skip_if_exists": True,
        },
        {
            "name": "real_options_trades",
            "columns": "symbol, option_type, strike, expiration, contracts, premium_per_contract, entry_cost, exit_premium, exit_proceeds, pnl, status, alert_type, alert_id, notes, session_date, opened_at, closed_at",
            "conflict": "",
            "skip_if_exists": True,
        },
        {
            "name": "swing_trades",
            "columns": "symbol, alert_type, direction, entry_price, current_price, stop_type, target_type, entry_rsi, current_rsi, status, pnl_pct, entry_date, closed_date, created_at",
            "conflict": "ON CONFLICT (symbol, entry_date, alert_type) DO NOTHING",
        },
        {
            "name": "swing_categories",
            "columns": "symbol, category, rsi, session_date, created_at",
            "conflict": "ON CONFLICT (symbol, session_date) DO NOTHING",
        },
    ]

    total_migrated = 0

    for table_info in TABLES:
        name = table_info["name"]
        columns = table_info["columns"]
        conflict = table_info["conflict"]
        skip_if_exists = table_info.get("skip_if_exists", False)
        col_list = [c.strip() for c in columns.split(",")]

        # For tables without unique constraints, skip if Postgres already has data
        if skip_if_exists:
            cur.execute(f"SELECT count(*) FROM {name}")
            pg_count = cur.fetchone()[0]
            if pg_count > 0:
                print(f"  {name}: SKIP (already has {pg_count} rows in Postgres)")
                continue

        # Read from SQLite
        try:
            rows = src.execute(f"SELECT {columns} FROM {name}").fetchall()
        except sqlite3.OperationalError as e:
            print(f"  {name}: SKIP (table/column missing in SQLite: {e})")
            continue

        if not rows:
            print(f"  {name}: (empty, skipped)")
            continue

        # Build INSERT statement
        placeholders = ", ".join(["%s"] * len(col_list))
        col_names = ", ".join(col_list)
        insert_sql = f"INSERT INTO {name} ({col_names}) VALUES ({placeholders}) {conflict}"

        inserted = 0
        skipped = 0
        for row in rows:
            values = tuple(row[c] for c in col_list)
            try:
                cur.execute(insert_sql, values)
                inserted += 1
            except psycopg2.IntegrityError:
                dst.rollback()
                skipped += 1
            except Exception as e:
                dst.rollback()
                print(f"  {name}: ERROR on row — {e}")
                skipped += 1

        dst.commit()
        total_migrated += inserted
        skip_msg = f" ({skipped} skipped/duplicates)" if skipped else ""
        print(f"  {name}: {inserted} rows migrated{skip_msg}")

    # Reset Postgres sequences to max(id) + 1 so new INSERTs get correct IDs
    print("\nResetting sequences...")
    SERIAL_TABLES = [
        "users", "alerts", "active_entries", "daily_plans",
        "paper_trades", "real_trades", "real_options_trades",
        "watchlist", "user_notification_prefs",
        "swing_trades", "swing_categories",
    ]
    for tbl in SERIAL_TABLES:
        try:
            cur.execute(f"SELECT MAX(id) FROM {tbl}")
            max_id = cur.fetchone()[0]
            if max_id:
                seq_name = f"{tbl}_id_seq"
                cur.execute(f"SELECT setval('{seq_name}', {max_id})")
        except Exception:
            dst.rollback()
    dst.commit()

    src.close()
    cur.close()
    dst.close()

    print(f"\nDone! {total_migrated} total rows migrated to Postgres.")


if __name__ == "__main__":
    main()
