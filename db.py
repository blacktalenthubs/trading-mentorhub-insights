"""SQLite database schema and CRUD operations."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Optional

import pandas as pd

from config import DB_PATH
from models import Trade1099, TradeMonthly, MatchedTrade, AccountSummary, ImportRecord


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist, then run migrations."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                period TEXT NOT NULL,
                records_imported INTEGER DEFAULT 0,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(filename, file_type)
            );

            CREATE TABLE IF NOT EXISTS trades_1099 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id INTEGER REFERENCES imports(id),
                user_id INTEGER REFERENCES users(id),
                account TEXT NOT NULL,
                description TEXT NOT NULL,
                symbol TEXT NOT NULL,
                cusip TEXT,
                date_sold TEXT NOT NULL,
                date_acquired TEXT,
                date_acquired_raw TEXT,
                quantity REAL NOT NULL,
                proceeds REAL NOT NULL,
                cost_basis REAL NOT NULL,
                wash_sale_disallowed REAL DEFAULT 0,
                gain_loss REAL NOT NULL,
                term TEXT NOT NULL,
                covered INTEGER NOT NULL,
                form_type TEXT NOT NULL,
                trade_type TEXT,
                asset_type TEXT,
                category TEXT,
                holding_days INTEGER,
                holding_period_type TEXT,
                underlying_symbol TEXT
            );

            CREATE TABLE IF NOT EXISTS trades_monthly (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id INTEGER REFERENCES imports(id),
                user_id INTEGER REFERENCES users(id),
                account TEXT NOT NULL,
                description TEXT NOT NULL,
                symbol TEXT NOT NULL,
                cusip TEXT,
                acct_type TEXT,
                transaction_type TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                is_option INTEGER DEFAULT 0,
                option_detail TEXT,
                is_recurring INTEGER DEFAULT 0,
                asset_type TEXT,
                category TEXT,
                underlying_symbol TEXT
            );

            CREATE TABLE IF NOT EXISTS matched_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                account TEXT NOT NULL,
                symbol TEXT NOT NULL,
                buy_date TEXT NOT NULL,
                sell_date TEXT NOT NULL,
                quantity REAL NOT NULL,
                buy_price REAL NOT NULL,
                sell_price REAL NOT NULL,
                buy_amount REAL NOT NULL,
                sell_amount REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                holding_days INTEGER NOT NULL,
                asset_type TEXT,
                category TEXT,
                holding_period_type TEXT,
                underlying_symbol TEXT
            );

            CREATE TABLE IF NOT EXISTS account_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id INTEGER REFERENCES imports(id),
                user_id INTEGER REFERENCES users(id),
                account TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                opening_balance REAL NOT NULL,
                closing_balance REAL NOT NULL,
                UNIQUE(account, period_start, period_end)
            );

            CREATE TABLE IF NOT EXISTS trade_annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                source TEXT NOT NULL,
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                quantity REAL,
                strategy_tag TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, symbol, trade_date, quantity)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                price REAL NOT NULL,
                entry REAL,
                stop REAL,
                target_1 REAL,
                target_2 REAL,
                confidence TEXT,
                message TEXT,
                notified_email INTEGER DEFAULT 0,
                notified_sms INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS active_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_price REAL,
                stop_price REAL,
                target_1 REAL,
                target_2 REAL,
                alert_type TEXT,
                session_date TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, session_date, alert_type)
            );

            CREATE TABLE IF NOT EXISTS monitor_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_poll_at TIMESTAMP,
                symbols_checked INTEGER DEFAULT 0,
                alerts_fired INTEGER DEFAULT 0,
                status TEXT DEFAULT 'idle'
            );

            CREATE INDEX IF NOT EXISTS idx_trades_1099_symbol ON trades_1099(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_1099_account ON trades_1099(account);
            CREATE INDEX IF NOT EXISTS idx_trades_1099_date_sold ON trades_1099(date_sold);
            CREATE INDEX IF NOT EXISTS idx_trades_monthly_symbol ON trades_monthly(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_monthly_date ON trades_monthly(trade_date);
            CREATE INDEX IF NOT EXISTS idx_matched_trades_symbol ON matched_trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trade_annotations_lookup
                ON trade_annotations(source, symbol, trade_date);
            CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol);
            CREATE INDEX IF NOT EXISTS idx_alerts_session ON alerts(session_date);
            CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type, session_date);
            CREATE INDEX IF NOT EXISTS idx_active_entries_symbol
                ON active_entries(symbol, session_date);
        """)
    _migrate_add_user_id()


def _migrate_add_user_id():
    """Add user_id column to existing tables if missing (handles DB upgrades)."""
    from config import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD

    tables = [
        "imports", "trades_1099", "trades_monthly",
        "matched_trades", "account_summaries", "trade_annotations",
    ]
    with get_db() as conn:
        for table in tables:
            try:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Create user_id indexes for query performance
        for table in tables:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)"
            )

        # If data exists but no users, create default admin for migration
        has_data = conn.execute("SELECT 1 FROM imports LIMIT 1").fetchone()
        has_users = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if has_data and not has_users:
            import bcrypt
            pw_hash = bcrypt.hashpw(
                DEFAULT_ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            conn.execute(
                "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
                (DEFAULT_ADMIN_EMAIL, pw_hash, "Admin"),
            )

        # Assign orphan rows (NULL user_id) to the first registered user
        admin = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        if admin:
            admin_id = admin["id"]
            for table in tables:
                conn.execute(
                    f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL",
                    (admin_id,),
                )


# ---------------------------------------------------------------------------
# Import tracking
# ---------------------------------------------------------------------------

def check_import_exists(filename: str, file_type: str, user_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM imports WHERE filename=? AND file_type=? AND user_id=?",
            (filename, file_type, user_id),
        ).fetchone()
        return row is not None


def create_import(record: ImportRecord, user_id: int) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO imports (filename, file_type, period, records_imported, user_id)
               VALUES (?, ?, ?, ?, ?)""",
            (record.filename, record.file_type, record.period, record.records_imported, user_id),
        )
        return cur.lastrowid


def update_import_count(import_id: int, count: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE imports SET records_imported=? WHERE id=?",
            (count, import_id),
        )


def get_imports(user_id: int) -> pd.DataFrame:
    with get_db() as conn:
        return pd.read_sql_query(
            "SELECT * FROM imports WHERE user_id=? ORDER BY imported_at DESC",
            conn,
            params=[user_id],
        )


def delete_import(import_id: int, user_id: int):
    """Delete an import and all associated records (scoped to user)."""
    with get_db() as conn:
        conn.execute("DELETE FROM trades_1099 WHERE import_id=? AND user_id=?", (import_id, user_id))
        conn.execute("DELETE FROM trades_monthly WHERE import_id=? AND user_id=?", (import_id, user_id))
        conn.execute("DELETE FROM account_summaries WHERE import_id=? AND user_id=?", (import_id, user_id))
        conn.execute("DELETE FROM imports WHERE id=? AND user_id=?", (import_id, user_id))


# ---------------------------------------------------------------------------
# Trade 1099
# ---------------------------------------------------------------------------

def insert_trades_1099(trades: list[Trade1099], import_id: int, user_id: int):
    with get_db() as conn:
        conn.executemany(
            """INSERT INTO trades_1099
               (import_id, user_id, account, description, symbol, cusip, date_sold, date_acquired,
                date_acquired_raw, quantity, proceeds, cost_basis, wash_sale_disallowed,
                gain_loss, term, covered, form_type, trade_type, asset_type, category,
                holding_days, holding_period_type, underlying_symbol)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(import_id, user_id, t.account, t.description, t.symbol, t.cusip,
              t.date_sold.isoformat(), t.date_acquired.isoformat() if t.date_acquired else None,
              t.date_acquired_raw, t.quantity, t.proceeds, t.cost_basis,
              t.wash_sale_disallowed, t.gain_loss, t.term, int(t.covered),
              t.form_type, t.trade_type, t.asset_type, t.category,
              t.holding_days, t.holding_period_type, t.underlying_symbol)
             for t in trades],
        )


def get_trades_1099(user_id: int, account: Optional[str] = None) -> pd.DataFrame:
    with get_db() as conn:
        query = "SELECT * FROM trades_1099 WHERE user_id=?"
        params: list = [user_id]
        if account:
            query += " AND account=?"
            params.append(account)
        query += " ORDER BY date_sold"
        df = pd.read_sql_query(query, conn, params=params)
        if not df.empty:
            df["date_sold"] = pd.to_datetime(df["date_sold"])
            df["date_acquired"] = pd.to_datetime(df["date_acquired"])
        return df


# ---------------------------------------------------------------------------
# Trade Monthly
# ---------------------------------------------------------------------------

def insert_trades_monthly(trades: list[TradeMonthly], import_id: int, user_id: int):
    with get_db() as conn:
        conn.executemany(
            """INSERT INTO trades_monthly
               (import_id, user_id, account, description, symbol, cusip, acct_type,
                transaction_type, trade_date, quantity, price, amount,
                is_option, option_detail, is_recurring, asset_type, category, underlying_symbol)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(import_id, user_id, t.account, t.description, t.symbol, t.cusip, t.acct_type,
              t.transaction_type, t.trade_date.isoformat(), t.quantity, t.price, t.amount,
              int(t.is_option), t.option_detail, int(t.is_recurring),
              t.asset_type, t.category, t.underlying_symbol)
             for t in trades],
        )


def get_trades_monthly(user_id: int, account: Optional[str] = None) -> pd.DataFrame:
    with get_db() as conn:
        query = "SELECT * FROM trades_monthly WHERE user_id=?"
        params: list = [user_id]
        if account:
            query += " AND account=?"
            params.append(account)
        query += " ORDER BY trade_date"
        df = pd.read_sql_query(query, conn, params=params)
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df


# ---------------------------------------------------------------------------
# Matched Trades
# ---------------------------------------------------------------------------

def insert_matched_trades(trades: list[MatchedTrade], user_id: int):
    with get_db() as conn:
        conn.executemany(
            """INSERT INTO matched_trades
               (user_id, account, symbol, buy_date, sell_date, quantity, buy_price, sell_price,
                buy_amount, sell_amount, realized_pnl, holding_days,
                asset_type, category, holding_period_type, underlying_symbol)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(user_id, t.account, t.symbol, t.buy_date.isoformat(), t.sell_date.isoformat(),
              t.quantity, t.buy_price, t.sell_price, t.buy_amount, t.sell_amount,
              t.realized_pnl, t.holding_days, t.asset_type, t.category,
              t.holding_period_type, t.underlying_symbol)
             for t in trades],
        )


def get_matched_trades(user_id: int) -> pd.DataFrame:
    with get_db() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM matched_trades WHERE user_id=? ORDER BY sell_date",
            conn,
            params=[user_id],
        )
        if not df.empty:
            df["buy_date"] = pd.to_datetime(df["buy_date"])
            df["sell_date"] = pd.to_datetime(df["sell_date"])
        return df


# ---------------------------------------------------------------------------
# Account Summaries
# ---------------------------------------------------------------------------

def insert_account_summary(summary: AccountSummary, import_id: int, user_id: int):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO account_summaries
               (import_id, user_id, account, period_start, period_end, opening_balance, closing_balance)
               VALUES (?,?,?,?,?,?,?)""",
            (import_id, user_id, summary.account, summary.period_start.isoformat(),
             summary.period_end.isoformat(), summary.opening_balance, summary.closing_balance),
        )


def get_account_summaries(user_id: int) -> pd.DataFrame:
    with get_db() as conn:
        return pd.read_sql_query(
            "SELECT * FROM account_summaries WHERE user_id=? ORDER BY period_end DESC",
            conn,
            params=[user_id],
        )


# ---------------------------------------------------------------------------
# Aggregation queries
# ---------------------------------------------------------------------------

def get_all_trades_combined(user_id: int) -> pd.DataFrame:
    """Get 1099 trades + matched trades in a unified format for analytics."""
    with get_db() as conn:
        df = pd.read_sql_query("""
            SELECT
                symbol, date_sold as trade_date, proceeds, cost_basis,
                gain_loss as realized_pnl, wash_sale_disallowed,
                asset_type, category, holding_days, holding_period_type,
                underlying_symbol, account, term, '1099' as source
            FROM trades_1099
            WHERE user_id = ?

            UNION ALL

            SELECT
                symbol, sell_date as trade_date, sell_amount as proceeds,
                buy_amount as cost_basis,
                realized_pnl, 0 as wash_sale_disallowed,
                asset_type, category, holding_days, holding_period_type,
                underlying_symbol, account, 'short' as term, 'monthly' as source
            FROM matched_trades
            WHERE user_id = ?
        """, conn, params=[user_id, user_id])
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df


def get_user_trades(user_id: int) -> pd.DataFrame:
    """Get trades for a user's accounts (stocks + ETFs, no options)."""
    with get_db() as conn:
        df = pd.read_sql_query("""
            SELECT
                symbol, date_sold as trade_date, date_acquired,
                proceeds, cost_basis,
                gain_loss as realized_pnl, wash_sale_disallowed,
                quantity, asset_type, category,
                holding_days, holding_period_type,
                underlying_symbol, account, term, trade_type,
                '1099' as source
            FROM trades_1099
            WHERE user_id = ?
              AND asset_type IN ('stock', 'etf')

            UNION ALL

            SELECT
                symbol, sell_date as trade_date, buy_date as date_acquired,
                sell_amount as proceeds, buy_amount as cost_basis,
                realized_pnl, 0 as wash_sale_disallowed,
                quantity, asset_type, category,
                holding_days, holding_period_type,
                underlying_symbol, account, 'short' as term, '' as trade_type,
                'monthly' as source
            FROM matched_trades
            WHERE user_id = ?
              AND asset_type IN ('stock', 'etf')

            ORDER BY trade_date
        """, conn, params=[user_id, user_id])
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df["date_acquired"] = pd.to_datetime(df["date_acquired"])
        return df


def get_user_options(user_id: int) -> pd.DataFrame:
    """Get option trades for a user."""
    with get_db() as conn:
        df = pd.read_sql_query("""
            SELECT
                symbol, date_sold as trade_date,
                proceeds, cost_basis,
                gain_loss as realized_pnl, wash_sale_disallowed,
                quantity, asset_type, category,
                holding_days, holding_period_type,
                underlying_symbol, account
            FROM trades_1099
            WHERE user_id = ?
              AND asset_type = 'option'
            ORDER BY date_sold
        """, conn, params=[user_id])
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df


# ---------------------------------------------------------------------------
# Trade Annotations
# ---------------------------------------------------------------------------

STRATEGY_TAGS = [
    "support_bounce",
    "ma_bounce",
    "key_level",
    "breakout",
    "pullback_buy",
    "gap_play",
    "momentum",
    "earnings",
    "other",
]


def upsert_annotation(source: str, symbol: str, trade_date: str,
                       quantity: float, user_id: int,
                       strategy_tag: str = None, notes: str = None):
    """Insert or update a trade annotation."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO trade_annotations (source, symbol, trade_date, quantity, strategy_tag, notes, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, symbol, trade_date, quantity)
            DO UPDATE SET strategy_tag=excluded.strategy_tag, notes=excluded.notes
        """, (source, symbol, trade_date, quantity, strategy_tag, notes, user_id))


def get_annotations(user_id: int) -> pd.DataFrame:
    """Get all trade annotations for a user."""
    with get_db() as conn:
        return pd.read_sql_query(
            "SELECT * FROM trade_annotations WHERE user_id=?",
            conn,
            params=[user_id],
        )
