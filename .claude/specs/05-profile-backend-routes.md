# Spec: Profile Backend Routes

## Overview
Step 4 built the profile page UI, but `profile()` in `app.py` still passes hardcoded sample data (marked "replaced with real queries in Step 5"). This step connects the page to the database. The view loads the logged-in user's row and their expenses from SQLite, then computes the summary stats and the category breakdown from that data. Every logged-in user now sees their own name, email, join date and spending, and a new account sees an empty state. `profile.html` stays as it is: the route keeps passing the same `user`, `stats`, `expenses` and `categories` context shape, so only the data source changes. This is the first step that reads expenses, and later steps (add, edit and delete expense) will show their results on this page.

## Depends on
- **Step 1 — Database setup**: the `users` table (`created_at`) and the `expenses` table (`user_id`, `amount`, `category`, `date`, `description`), `get_db()`, and the seeded demo user with 8 expenses.
- **Step 2 — Registration**: real accounts created through `create_user()`.
- **Step 3 — Login and Logout**: `session["user_id"]` is set on login.
- **Step 4 — Profile page design**: `templates/profile.html`, `static/css/profile.css`, and the login guard on `/profile`.

## Routes
No new routes.

- `GET /profile` — changes: it now loads real data for `session["user_id"]` instead of hardcoded data — logged-in (redirect to `/login` if not authenticated)

## Database changes
No database changes. The existing `users` and `expenses` tables hold everything the page needs.

New query functions in `database/db.py`, in the same style as `get_user_by_email()` (open a connection, `try`/`finally` close it):
- `get_user_by_id(user_id)` — returns the `users` row, or `None`.
- `get_expenses_for_user(user_id)` — returns all of that user's expenses, ordered by `date DESC, id DESC`.
- `get_expense_stats(user_id)` — returns the total amount (`COALESCE(SUM(amount), 0)`) and the expense count.
- `get_category_totals(user_id)` — returns `category` and `SUM(amount)` per category with `GROUP BY category`, ordered by total descending, then category name.

## Templates
- **Create:** none
- **Modify:** none. `templates/profile.html` already reads `user.initials`, `user.name`, `user.email`, `user.member_since`, `stats.total_spent`, `stats.transactions`, `stats.top_category`, `e.date`, `e.description`, `e.category`, `e.amount`, `c.name`, `c.amount` and `c.pct`, and already has the "No expenses yet." empty row. The route has to provide exactly these keys.

## Files to change
- `database/db.py` — add the four query functions listed above under a new `Expenses` section, and add `get_user_by_id()` to the `Users` section.
- `app.py` — replace the hardcoded data in `profile()` with calls to the new functions, plus small formatting helpers in Python (initials, dates, percentages). Remove the "Hardcoded sample data" comment.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()`.
- Parameterised queries only. Never use f-strings, `%` or `.format()` in SQL.
- Passwords hashed with werkzeug (auth isn't changed in this step).
- Use CSS variables. Never hardcode hex values (no CSS changes are expected in this step).
- All templates extend `base.html`.
- Every expense query must filter with `WHERE user_id = ?` on the session's user id. A user must never see another user's data.
- Do the aggregation (total, count, per-category sums) in SQL, not by looping in Python.
- If `session["user_id"]` points to a user that no longer exists (for example, after the DB file was deleted), call `session.clear()` and redirect to `/login`. Don't crash.
- Context formatting, done in `app.py`:
  - `user.initials`: the first letter of the first two words of the name, uppercased (`"Demo User"` → `"DU"`, `"Sakshi"` → `"S"`).
  - `user.member_since`: `created_at` (`YYYY-MM-DD HH:MM:SS`) formatted as `"%B %Y"` (e.g. `"October 2026"`).
  - `expenses[].date`: the stored ISO `YYYY-MM-DD` formatted as `"%d %b %Y"` (e.g. `"08 Oct 2026"`).
  - `expenses[].description`: fall back to the category name when it is `NULL` or empty.
  - `stats.top_category`: the first row of `get_category_totals()`, or `"—"` when the user has no expenses.
  - `categories[].pct`: `round(amount / total * 100)` as an int. Return an empty list when the total is 0, and never divide by zero.
- Keep the template unchanged. If a change looks necessary, keep it to the minimum and use existing classes.
- Leave the placeholder routes for adding, editing and deleting expenses untouched.
- No new JS and no new libraries.

## Definition of done
- [ ] `venv/bin/python app.py` starts without errors on http://localhost:5001
- [ ] Visiting `/profile` while logged out redirects to `/login`
- [ ] Logged in as `demo@spendly.com` / `demo123`, `/profile` shows "Demo User", `demo@spendly.com`, initials "DU" and a "Member since" month that matches the user's `created_at`
- [ ] The demo user's stats show total ₹6,697.50, 8 transactions and top category "Shopping", all read from the DB
- [ ] The transaction table lists the demo user's 8 seeded expenses, newest first, with dates like "08 Oct 2026"
- [ ] The category breakdown lists the categories in order of total amount, and the percentages add up to about 100
- [ ] Changing an expense amount directly in SQLite and reloading `/profile` updates the table, stats and breakdown, which proves the data isn't hardcoded
- [ ] A newly registered user who logs in sees their own name, email and initials, ₹0.00 total, 0 transactions, "—" as top category, "No expenses yet." in the table, an empty category breakdown, and no errors
- [ ] A second user never sees the demo user's expenses
- [ ] Logged in as a registered (non-demo) user, deleting that user's row from SQLite and then reloading `/profile` clears the session and redirects to `/login`, without raising an error
- [ ] No hardcoded sample data is left in `profile()` in `app.py`
