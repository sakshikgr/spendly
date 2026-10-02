# Plan: Step 1 — Database Setup

Implements `.claude/specs/01-database-setup.md`.

## Current state

- `database/db.py` — 5-line comment stub, no code.
- `database/__init__.py` — empty (package already importable as `database.db`).
- `app.py` — Flask app, only imports `Flask, render_template`; no DB usage.
  Real routes: `/`, `/register`, `/login`, `/privacy`, `/terms`.
  Placeholder routes return strings. Runs on port 5001.
- `expense_tracker.db` and `__pycache__/` already in `.gitignore`.
- `werkzeug` is already in `requirements.txt` → `werkzeug.security` available.

## Steps

### 1. `database/db.py` — module setup

Replace the stub comment entirely.

```python
import os
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "expense_tracker.db")

CATEGORIES = ["Food", "Travel", "Bills", "Shopping", "Health", "Entertainment", "Other"]
```

- `DB_PATH` resolves to the project root regardless of the working directory.
- Use the same `# ---- #` section-divider comment style as `app.py`
  (sections: Connection, Schema, Seed data).

### 2. `get_db()`

```python
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

### 3. `init_db()`

Single `executescript` with both `CREATE TABLE IF NOT EXISTS` statements:

- `users`: `id INTEGER PRIMARY KEY AUTOINCREMENT`, `name TEXT NOT NULL`,
  `email TEXT NOT NULL UNIQUE`, `password_hash TEXT NOT NULL`,
  `created_at TEXT NOT NULL DEFAULT (datetime('now'))`.
- `expenses`: `id INTEGER PRIMARY KEY AUTOINCREMENT`,
  `user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE`,
  `amount REAL NOT NULL CHECK (amount > 0)`, `category TEXT NOT NULL`,
  `date TEXT NOT NULL`, `description TEXT`,
  `created_at TEXT NOT NULL DEFAULT (datetime('now'))`.

Commit, close.

Note: `DEFAULT (datetime('now'))` needs the parentheses — SQLite only accepts
function-call defaults as parenthesised expressions.

### 4. `seed_db()`

1. `get_db()`; `SELECT COUNT(*) FROM users` → if > 0, close and return.
2. Insert demo user with `?` placeholders:
   `("Demo User", "demo@spendly.com", generate_password_hash("demo123"))`;
   take `cursor.lastrowid` as `user_id`.
3. Build 8 expenses dated in the current month. Use day numbers 1–8 so dates
   are always valid regardless of month length or today's date:
   `date.today().replace(day=d).isoformat()`.

   | day | amount | category | description |
   |---|---|---|---|
   | 1 | 1200.00 | Bills | Electricity bill |
   | 2 | 450.50 | Food | Groceries |
   | 3 | 180.00 | Travel | Metro card recharge |
   | 4 | 2499.00 | Shopping | Running shoes |
   | 5 | 650.00 | Health | Pharmacy |
   | 6 | 320.00 | Food | Dinner with friends |
   | 7 | 499.00 | Entertainment | Movie tickets |
   | 8 | 899.00 | Bills | Mobile recharge |

   (6 distinct categories, satisfies "at least 5".)
4. `executemany` the insert with `?` placeholders. Commit, close.

### 5. `app.py` — wire up initialisation

- Add `from database.db import init_db, seed_db` under the Flask import.
- After `app = Flask(__name__)`, add:

  ```python
  with app.app_context():
      init_db()
      seed_db()
  ```

- No route changes.

## Verification

Run from the project root with the venv:

1. `venv/bin/python -c "import app"` — imports cleanly, creates
   `expense_tracker.db` in the project root.
2. Schema check:
   `sqlite3 expense_tracker.db ".schema"` → both tables with expected columns.
3. Idempotency: import app twice, then
   `SELECT COUNT(*) FROM users` → 1, `SELECT COUNT(*) FROM expenses` → 8.
4. Password hashed: `SELECT password_hash FROM users` starts with a werkzeug
   scheme prefix (e.g. `scrypt:`), not `demo123`.
5. Constraints (via a short Python snippet using `get_db()`):
   - insert expense with `user_id = 999` → `sqlite3.IntegrityError`
   - insert expense with `amount = 0` → `sqlite3.IntegrityError`
6. Routes: `app.test_client()` GET `/`, `/login`, `/register`, `/terms`,
   `/privacy` → all 200.
7. Clean up any test rows (constraint tests shouldn't insert anything since
   they fail); optionally delete `expense_tracker.db` so the next run re-seeds
   fresh.

## Commit

```
database: add sqlite schema, connection helper and seed data
```

Files: `database/db.py`, `app.py`. (Decide separately whether to commit
`CLAUDE.md` and `.claude/specs`/`.claude/plan`.)
