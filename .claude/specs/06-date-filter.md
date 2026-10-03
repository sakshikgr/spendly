# Spec: Date Filter

## Overview
Step 5 connected `/profile` to the database, so it now shows all of the logged-in user's expenses, stats and category breakdown. As expenses pile up, users need to look at a specific period, such as this month or last quarter. This step adds a date-range filter to the profile page. A small form above the stats takes a "From" and a "To" date and submits them as query-string parameters (`/profile?from=YYYY-MM-DD&to=YYYY-MM-DD`). The transaction table, the summary stats and the category breakdown are then all limited to that range. Quick preset links ("This month", "Last 30 days", "All time") cover the common cases. Filtering happens on the server with plain GET requests, so no JavaScript is needed, and a filtered view can be bookmarked or shared as a URL.

## Depends on
- **Step 1 — Database setup**: `expenses.date` stored as ISO `YYYY-MM-DD` text, so string comparison in SQL sorts and compares correctly.
- **Step 3 — Login and Logout**: `session["user_id"]` and the login guard on `/profile`.
- **Step 4 — Profile page design**: `templates/profile.html` and `static/css/profile.css`.
- **Step 5 — Profile backend routes**: `get_expenses_for_user()`, `get_expense_stats()`, `get_category_totals()` and the `build_*` helpers in `app.py`.

## Routes
No new routes.

- `GET /profile` — changes: it accepts the optional query parameters `from` and `to` (ISO dates) and filters expenses, stats and categories to that inclusive range — logged-in (redirect to `/login` if not authenticated)

## Database changes
No database changes. The existing `expenses.date` column is enough.

Changes to the query functions in `database/db.py`:
- `get_expenses_for_user(user_id, date_from=None, date_to=None)`
- `get_expense_stats(user_id, date_from=None, date_to=None)`
- `get_category_totals(user_id, date_from=None, date_to=None)`

When `date_from` is given, add `AND date >= ?`. When `date_to` is given, add `AND date <= ?`. Both bounds are inclusive. Build the extra conditions with a small shared helper (e.g. `_date_range_clause(date_from, date_to)` that returns a SQL fragment of fixed text plus a params tuple). Values must always go in as `?` parameters. Called with no dates, each function must behave exactly as it does now, so existing callers keep working.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a filter card between the user card and the stats row. It holds a `<form method="get" action="{{ url_for('profile') }}">` with two `<input type="date">` fields named `from` and `to`, pre-filled from the current filter, an "Apply" submit button (`btn-primary`) and a "Clear" link to `url_for('profile')`.
  - Add preset links ("This month", "Last 30 days", "All time") built with `url_for('profile', from=..., to=...)` using dates computed in `app.py`. Highlight the active preset with a modifier class.
  - When a filter is active, show a short line such as "Showing 01 Oct 2026 – 31 Oct 2026" in the stats/table area.
  - Show the filter error message (see rules) in an existing-style error/flash element when one is passed.
  - When a filter is active and nothing matches, the table's empty row reads "No expenses in this date range." instead of "No expenses yet."

## Files to change
- `database/db.py` — add the optional `date_from`/`date_to` parameters and the shared range-clause helper.
- `app.py` — in `profile()`, read and validate `request.args["from"]` / `request.args["to"]`, pass them to the `build_*` helpers (which pass them on to the DB functions), compute the preset ranges, and pass `filter` context (`date_from`, `date_to`, `label`, `active_preset`, `error`) to the template.
- `templates/profile.html` — filter form, presets, range label, error and empty-state text, as described above.
- `static/css/profile.css` — styles for the filter card, date inputs, preset links (including the active state) and range label. Use only existing CSS variables.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()`.
- Parameterised queries only. Never use f-strings, `%` or `.format()` to put values into SQL. Only fixed SQL text (such as `" AND date >= ?"`) may be joined into the query.
- Passwords hashed with werkzeug (auth isn't changed in this step).
- Use CSS variables. Never hardcode hex values.
- All templates extend `base.html`.
- Every expense query must still filter with `WHERE user_id = ?` on the session's user.
- Aggregation (total, count, per-category sums) stays in SQL and respects the same date range as the table.
- Validation, done in `app.py`:
  - Parse each parameter with `datetime.strptime(value, "%Y-%m-%d")`. Treat an empty or missing value as "no bound".
  - An invalid date (e.g. `?from=banana`) is ignored. That bound is dropped, the page still returns 200, and an error message is shown: "Invalid date — showing all expenses."
  - If `from` is later than `to`, ignore both bounds, show "Start date must be before end date.", and return 200.
  - Only one bound is fine: `from` alone means "from this date onward", and `to` alone means "up to and including this date".
- Presets, computed from `date.today()` in `app.py`:
  - **This month**: the 1st of the current month to today.
  - **Last 30 days**: `today - 29 days` to today (inclusive, 30 days).
  - **All time**: no parameters (`url_for('profile')`).
- Keep the `stats`, `expenses` and `categories` context shapes from Step 5 unchanged.
- `categories[].pct` is still computed against the filtered total, and an empty range returns `[]` without dividing by zero.
- No JavaScript and no new libraries. The form works with a plain GET submit.
- No inline styles.
- Leave the placeholder routes for adding, editing and deleting expenses untouched.

## Definition of done
- [ ] `venv/bin/python app.py` starts without errors on http://localhost:5001
- [ ] Visiting `/profile` while logged out redirects to `/login`, including with `?from=...&to=...`
- [ ] Logged in as `demo@spendly.com` / `demo123`, `/profile` with no parameters shows all 8 expenses, a ₹6,697.50 total and "Shopping" as top category (unchanged from Step 5)
- [ ] The filter form shows two date inputs, Apply and Clear, plus "This month", "Last 30 days" and "All time" presets
- [ ] `/profile?from=<YYYY-MM>-01&to=<YYYY-MM>-04` (the current month) shows only the 4 expenses dated the 1st–4th: total ₹4,329.50, 4 transactions, top category "Shopping"
- [ ] The category breakdown for that range lists only Shopping, Bills, Food and Travel, in that order, and the percentages add up to about 100
- [ ] Submitting the form fills the URL with `from`/`to`, and the inputs stay filled with those dates after reload
- [ ] `?from=<date>` alone and `?to=<date>` alone each filter by a single bound, and both bounds are inclusive (an expense dated exactly on `from` or `to` is shown)
- [ ] A range with no expenses shows ₹0.00, 0 transactions, "—" top category, "No expenses in this date range." and an empty breakdown, with no errors
- [ ] `?from=banana` returns 200, shows "Invalid date — showing all expenses." and lists all expenses
- [ ] `?from=2026-12-31&to=2026-01-01` returns 200, shows "Start date must be before end date." and lists all expenses
- [ ] Clicking "This month" or "Last 30 days" applies the correct range and highlights that preset; "All time" and "Clear" go back to `/profile` with no parameters
- [ ] A second user's filtered view never includes the demo user's expenses
- [ ] `grep -n "#[0-9a-fA-F]\{3,6\}" templates/profile.html` finds nothing, and the new CSS in `profile.css` uses only `var(--...)` colours
