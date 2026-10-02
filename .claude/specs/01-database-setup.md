# Spec: Step 1 — Database Setup

## Overview

Implement the SQLite data layer for Spendly in `database/db.py`, replacing the
"Students will write this file in Step 1" stub. This step only builds the
database foundation (connection helper, schema, seed data) and wires
initialisation into app startup. No routes or templates change behaviour yet —
registration, login and expense CRUD come in later steps and will build on this.

## Depends on

- Nothing (first step). Uses only the Python standard library (`sqlite3`) and
  `werkzeug.security`, which is already installed via `requirements.txt`.

## Files

| File | Change |
|---|---|
| `database/db.py` | Replace stub with `get_db()`, `init_db()`, `seed_db()` |
| `app.py` | Call `init_db()` and `seed_db()` once at startup |

No new dependencies. No changes to templates, CSS or JS.

## Database

- File: `expense_tracker.db` in the project root (already gitignored).
- Build the path from the project root (e.g. relative to `database/db.py`),
  not the current working directory, so `pytest` and `python app.py` hit the
  same file.

### Schema

**`users`**

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `name` | TEXT | NOT NULL |
| `email` | TEXT | NOT NULL, UNIQUE |
| `password_hash` | TEXT | NOT NULL |
| `created_at` | TEXT | NOT NULL, DEFAULT `datetime('now')` |

**`expenses`**

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `user_id` | INTEGER | NOT NULL, FOREIGN KEY → `users(id)` ON DELETE CASCADE |
| `amount` | REAL | NOT NULL, CHECK (`amount > 0`) |
| `category` | TEXT | NOT NULL |
| `date` | TEXT | NOT NULL — ISO format `YYYY-MM-DD` |
| `description` | TEXT | nullable |
| `created_at` | TEXT | NOT NULL, DEFAULT `datetime('now')` |

Fields match the register form (`name`, `email`, `password`) and the landing
page copy ("Category, amount, date, description"). Amounts are in rupees (₹).

### Categories

Store category as plain text. Allowed values (keep as a module-level constant
`CATEGORIES` in `db.py` so later steps can reuse it for form dropdowns):

`Food`, `Travel`, `Bills`, `Shopping`, `Health`, `Entertainment`, `Other`

## Functions

### `get_db()`

- Opens a connection to `expense_tracker.db`.
- Sets `conn.row_factory = sqlite3.Row` so rows can be accessed by column name.
- Runs `PRAGMA foreign_keys = ON` (SQLite has it off by default).
- Returns the connection. Callers are responsible for closing it.

### `init_db()`

- Creates both tables with `CREATE TABLE IF NOT EXISTS`, so it is safe to call
  on every startup.
- Commits and closes the connection.

### `seed_db()`

- Inserts sample data for development **only if the `users` table is empty**,
  so restarting the dev server doesn't duplicate rows.
- One demo user:
  - name: `Demo User`
  - email: `demo@spendly.com`
  - password: `demo123`, stored as `generate_password_hash("demo123")` — never
    plain text.
- 8 sample expenses for that user, spread across the current month and at least
  5 different categories, with realistic rupee amounts and short descriptions.
- Commits and closes the connection.

## App wiring

In `app.py`, import from `database.db` and run initialisation once when the app
starts:

```python
from database.db import init_db, seed_db

with app.app_context():
    init_db()
    seed_db()
```

Do not modify any existing routes.

## Rules

- Use parameterised queries (`?` placeholders) everywhere — no string
  formatting / f-strings in SQL.
- Hash passwords with `werkzeug.security`; never store plain text.
- Standard library + existing dependencies only; no ORM (no SQLAlchemy).
- Keep the comment/style conventions of the existing code (section-divider
  comments like in `app.py`).

## Definition of done

- [ ] `venv/bin/python app.py` starts on port 5001 without errors and creates
      `expense_tracker.db` in the project root.
- [ ] The database contains `users` and `expenses` tables with the columns
      above.
- [ ] Restarting the app does not error and does not duplicate seed data
      (still 1 user, 8 expenses).
- [ ] The demo user's `password_hash` is a werkzeug hash, not `demo123`.
- [ ] Foreign keys are enforced: inserting an expense with a non-existent
      `user_id` raises `sqlite3.IntegrityError`.
- [ ] Inserting an expense with `amount <= 0` raises `sqlite3.IntegrityError`.
- [ ] Existing pages (`/`, `/login`, `/register`, `/terms`, `/privacy`) still
      return 200.

## Suggested commit

```
database: add sqlite schema, connection helper and seed data
```
