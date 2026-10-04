import os
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)

CATEGORIES = ["Food", "Travel", "Bills", "Shopping", "Health", "Entertainment", "Other"]


# ------------------------------------------------------------------ #
# Connection                                                          #
# ------------------------------------------------------------------ #

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ------------------------------------------------------------------ #
# Schema                                                              #
# ------------------------------------------------------------------ #

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            amount      REAL NOT NULL CHECK (amount > 0),
            category    TEXT NOT NULL,
            date        TEXT NOT NULL,
            description TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Seed data                                                           #
# ------------------------------------------------------------------ #

def seed_db():
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        conn.close()
        return

    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123", method="pbkdf2:sha256")),
    )
    user_id = cursor.lastrowid

    today = date.today()
    samples = [
        (1, 1200.00, "Bills", "Electricity bill"),
        (2, 450.50, "Food", "Groceries"),
        (3, 180.00, "Travel", "Metro card recharge"),
        (4, 2499.00, "Shopping", "Running shoes"),
        (5, 650.00, "Health", "Pharmacy"),
        (6, 320.00, "Food", "Dinner with friends"),
        (7, 499.00, "Entertainment", "Movie tickets"),
        (8, 899.00, "Bills", "Mobile recharge"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (user_id, amount, category, today.replace(day=day).isoformat(), description)
            for day, amount, category, description in samples
        ],
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Users                                                               #
# ------------------------------------------------------------------ #

def get_user_by_email(email):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    finally:
        conn.close()


def create_user(name, email, password):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password, method="pbkdf2:sha256")),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Expenses                                                            #
# ------------------------------------------------------------------ #

def _date_range_clause(date_from, date_to):
    clause, params = "", []
    if date_from:
        clause += " AND date >= ?"
        params.append(date_from)
    if date_to:
        clause += " AND date <= ?"
        params.append(date_to)
    return clause, tuple(params)


def create_expense(user_id, amount, category, date, description):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description or None),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_expenses_for_user(user_id, date_from=None, date_to=None):
    clause, params = _date_range_clause(date_from, date_to)
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE user_id = ?" + clause + " ORDER BY date DESC, id DESC",
            (user_id, *params),
        ).fetchall()
    finally:
        conn.close()


def get_expense_stats(user_id, date_from=None, date_to=None):
    clause, params = _date_range_clause(date_from, date_to)
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count "
            "FROM expenses WHERE user_id = ?" + clause,
            (user_id, *params),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + clause + " "
            "GROUP BY category ORDER BY SUM(amount) DESC, category LIMIT 1",
            (user_id, *params),
        ).fetchone()
        return {
            "total": float(totals["total"]),
            "count": int(totals["count"]),
            "top_category": top["category"] if top else None,
        }
    finally:
        conn.close()


def get_category_totals(user_id, date_from=None, date_to=None):
    clause, params = _date_range_clause(date_from, date_to)
    conn = get_db()
    try:
        return conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + clause + " GROUP BY category ORDER BY total DESC, category",
            (user_id, *params),
        ).fetchall()
    finally:
        conn.close()
