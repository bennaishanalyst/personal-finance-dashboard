"""SQLite storage layer. The database file lives under data/ which is
gitignored -- only this schema/code is version controlled, never your
actual financial data."""

import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "finance.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN ('checking', 'savings', 'credit_card', 'investment', 'loan', 'other')),
    institution TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL DEFAULT 'Uncategorized',
    source_file TEXT,
    hash TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    balance REAL NOT NULL,
    source_file TEXT,
    UNIQUE(account_id, date)
);

-- Remembers manual category corrections by exact description, so the next
-- import of the same merchant (and every past transaction with that same
-- description) gets categorized correctly without re-editing categories.yaml.
CREATE TABLE IF NOT EXISTS category_overrides (
    description TEXT PRIMARY KEY COLLATE NOCASE,
    category TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_balances_account_date ON balances(account_id, date);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def transaction_hash(account_id: int, date: str, description: str, amount: float) -> str:
    key = f"{account_id}|{date}|{description.strip().lower()}|{amount:.2f}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def get_accounts() -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM accounts ORDER BY name").fetchall()
    finally:
        conn.close()


def get_or_create_account(name: str, acc_type: str, institution: str = "") -> int:
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            "INSERT INTO accounts (name, type, institution) VALUES (?, ?, ?)",
            (name, acc_type, institution),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def delete_account(account_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
    finally:
        conn.close()


def clear_account_transactions(account_id: int) -> tuple[int, int]:
    """Delete all transactions and balances for an account, keeping the
    account itself -- useful for wiping out a bad import (e.g. wrong sign
    convention) and re-uploading cleanly. Returns (transactions_deleted,
    balances_deleted)."""
    conn = get_connection()
    try:
        t_count = conn.execute("DELETE FROM transactions WHERE account_id = ?", (account_id,)).rowcount
        b_count = conn.execute("DELETE FROM balances WHERE account_id = ?", (account_id,)).rowcount
        conn.commit()
        return t_count, b_count
    finally:
        conn.close()


def insert_transactions(account_id: int, rows: list[dict], source_file: str) -> tuple[int, int]:
    """Insert transactions, skipping duplicates. Returns (inserted, skipped)."""
    conn = get_connection()
    inserted = skipped = 0
    try:
        for r in rows:
            h = transaction_hash(account_id, r["date"], r["description"], r["amount"])
            try:
                conn.execute(
                    """INSERT INTO transactions
                       (account_id, date, description, amount, category, source_file, hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (account_id, r["date"], r["description"], r["amount"],
                     r.get("category", "Uncategorized"), source_file, h),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    finally:
        conn.close()
    return inserted, skipped


def insert_balance(account_id: int, date: str, balance: float, source_file: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO balances (account_id, date, balance, source_file)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(account_id, date) DO UPDATE SET balance = excluded.balance""",
            (account_id, date, balance, source_file),
        )
        conn.commit()
    finally:
        conn.close()


def get_transactions(account_id: int | None = None, start: str | None = None,
                      end: str | None = None, category: str | None = None,
                      search: str | None = None) -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        query = """
            SELECT t.*, a.name AS account_name, a.type AS account_type
            FROM transactions t JOIN accounts a ON a.id = t.account_id
            WHERE 1=1
        """
        params: list = []
        if account_id:
            query += " AND t.account_id = ?"
            params.append(account_id)
        if start:
            query += " AND t.date >= ?"
            params.append(start)
        if end:
            query += " AND t.date <= ?"
            params.append(end)
        if category:
            query += " AND t.category = ?"
            params.append(category)
        if search:
            query += " AND t.description LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY t.date DESC"
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def get_category_overrides() -> dict[str, str]:
    """description (lowercased) -> category, for every manual correction made so far."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT description, category FROM category_overrides").fetchall()
        return {r["description"].lower(): r["category"] for r in rows}
    finally:
        conn.close()


def recategorize_transaction(transaction_id: int, description: str, category: str) -> int:
    """Correct one transaction's category, remember the correction for future
    imports, and retroactively apply it to every other transaction that has
    the exact same description. Returns how many rows were updated."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE transactions SET category = ? WHERE description = ? COLLATE NOCASE",
            (category, description),
        )
        updated = cur.rowcount
        conn.execute(
            """INSERT INTO category_overrides (description, category) VALUES (?, ?)
               ON CONFLICT(description) DO UPDATE SET category = excluded.category, updated_at = datetime('now')""",
            (description.strip(), category),
        )
        conn.commit()
        return updated
    finally:
        conn.close()


def get_latest_balances() -> list[sqlite3.Row]:
    conn = get_connection()
    try:
        return conn.execute("""
            SELECT a.id AS account_id, a.name, a.type, b.date, b.balance
            FROM accounts a
            LEFT JOIN balances b ON b.account_id = a.id
            AND b.date = (SELECT MAX(date) FROM balances WHERE account_id = a.id)
            ORDER BY a.name
        """).fetchall()
    finally:
        conn.close()


def get_net_worth_history() -> list[sqlite3.Row]:
    """Daily net worth = sum of each account's most-recent balance as-of that date,
    with liability account types (credit_card, loan) subtracted rather than added."""
    conn = get_connection()
    try:
        return conn.execute("""
            SELECT b.account_id, a.type, b.date, b.balance
            FROM balances b JOIN accounts a ON a.id = b.account_id
            ORDER BY b.date
        """).fetchall()
    finally:
        conn.close()
