# Spec: Add Expense

## Overview
The profile page shows a user's expenses and offers date filtering, but the only data in the database is the demo seed. The "Add expense" button on `/profile` points to a placeholder route that returns "Add expense — coming in Step 7". This step replaces that placeholder with a real form for recording a new expense. A logged-in user enters an amount, picks a category, sets the date (defaulting to today) and can add an optional description. On submit, the server validates the input, inserts a row into `expenses` for the session's user, flashes a success message and redirects to `/profile`. The new expense then appears in the transaction table, the stats and the category breakdown. This is the first write path for expenses, and Steps 8 and 9 (edit and delete) build on it.

## Depends on
- **Step 1 — Database setup**: `expenses` table (`amount REAL CHECK (amount > 0)`, `category`, `date` as ISO `YYYY-MM-DD`, `description`), `get_db()` and the `CATEGORIES` list in `database/db.py`.
- **Step 3 — Login and Logout**: `session["user_id"]` and the login-guard pattern.
- **Step 4 — Profile page design**: the "Add expense" button in `templates/profile.html` that links to `url_for('add_expense')`.
- **Step 5 — Profile backend routes**: `/profile` reads expenses, stats and categories from the database, so a new row shows up straight away.
- **Step 6 — Date filter**: the filter must still work, and a newly added expense must respect it.

## Routes
- `GET /expenses/add` — render the add-expense form, with the date pre-filled to today — logged-in (redirect to `/login` if not authenticated)
- `POST /expenses/add` — validate the form, insert the expense for `session["user_id"]`, flash "Expense added." and redirect to `/profile`. On a validation error, re-render the form with the error and the submitted values, returning status 400 — logged-in (redirect to `/login` if not authenticated)

Both are served by the existing `add_expense` view, which changes to `methods=["GET", "POST"]`. Keep the endpoint name `add_expense` so the existing `url_for('add_expense')` link keeps working.

## Database changes
No database changes. The existing `expenses` table already has every column needed.

Add one helper to `database/db.py` in the "Expenses" section:
- `create_expense(user_id, amount, category, date, description)`: does `INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)`, commits, returns `cursor.lastrowid` and closes the connection in a `finally` (same pattern as `create_user`). Store an empty description as `NULL`.

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html` and sets `{% block title %}Add expense — Spendly{% endblock %}`.
  - Reuses the existing auth card layout (`auth-section`, `auth-container`, `auth-header`, `auth-card`) and form styles (`form-group`, `form-input`, `btn-submit`), with the header "Add an expense".
  - Shows `{{ error }}` in an `auth-error` element when present.
  - `<form method="POST" action="{{ url_for('add_expense') }}">` with these fields:
    - `amount`: `<input type="number" step="0.01" min="0.01" required>`
    - `category`: `<select required>` with one `<option>` per entry in `categories` (passed from `CATEGORIES`), keeping the submitted value selected after an error
    - `date`: `<input type="date" required>`, pre-filled with today on GET or the submitted value after an error
    - `description`: optional text input, `maxlength="200"`
  - A "Save expense" submit button and a "Cancel" link back to `url_for('profile')`.
- **Modify:** `templates/profile.html`
  - Show flashed messages (`get_flashed_messages(with_categories=true)`) at the top of the page content so "Expense added." is visible after the redirect. Reuse the `auth-success` / `auth-error` classes or add a matching profile-scoped class in `profile.css`.

## Files to change
- `app.py`: replace the `add_expense` placeholder with the GET/POST view described above, and import `create_expense` and `CATEGORIES` from `database.db`.
- `database/db.py`: add `create_expense()`.
- `templates/profile.html`: render flashed messages.
- `static/css/style.css` (only if needed): style for the `<select>` so it matches `.form-input` (prefer adding the `form-input` class to the select first), and a style for the Cancel link. Use only existing CSS variables.

## Files to create
- `templates/add_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()`.
- Parameterised queries only. Never use f-strings, `%` or `.format()` to build SQL.
- Passwords hashed with werkzeug (auth isn't changed in this step).
- Use CSS variables. Never hardcode hex values.
- All templates extend `base.html`.
- `user_id` always comes from `session["user_id"]`, never from the form or the URL.
- Server-side validation in `app.py`, in this order, each re-rendering the form with status 400 and the submitted values:
  - `amount`: must parse as a number with `float()`, be finite and be greater than 0 → otherwise "Please enter an amount greater than 0." Round to 2 decimal places before storing.
  - `category`: must be one of `CATEGORIES` → otherwise "Please choose a valid category."
  - `date`: must parse with `datetime.strptime(value, "%Y-%m-%d")` → otherwise "Please enter a valid date."
  - `description`: strip whitespace. It is optional, and anything over 200 characters fails with "Description must be 200 characters or fewer."
- On success: `flash("Expense added.", "success")` and `redirect(url_for("profile"))`. This is the post/redirect/get pattern, so refreshing doesn't resubmit.
- Follow the existing view style in `register()` / `login()` (a local `form_error()` helper, early returns).
- No JavaScript and no new libraries. The form works with a plain POST.
- No inline styles.
- Leave the edit and delete placeholder routes (Steps 8 and 9) untouched.

## Definition of done
- [ ] `venv/bin/python app.py` starts without errors on http://localhost:5001
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`, and so does a POST while logged out (no row is inserted)
- [ ] Logged in as `demo@spendly.com` / `demo123`, clicking "Add expense" on `/profile` opens a form with amount, category, date (pre-filled with today) and description fields
- [ ] The category dropdown lists exactly Food, Travel, Bills, Shopping, Health, Entertainment, Other
- [ ] Submitting amount `250`, category `Food`, today's date and description `Lunch` redirects to `/profile`, shows "Expense added.", and the table now has 9 rows with "Lunch" at the top, ₹250.00, Food
- [ ] After that add, the total rises from ₹6,697.50 to ₹6,947.50, the transaction count is 9, and the Food amount in the category breakdown goes up by ₹250
- [ ] Leaving the description blank saves the expense, and the table shows the category name as its description
- [ ] Refreshing `/profile` after the redirect doesn't add a duplicate expense
- [ ] Amount `0`, `-5`, `abc` or empty returns 400 with "Please enter an amount greater than 0.", and the other fields keep their submitted values
- [ ] A tampered category (e.g. `Crypto` via devtools) returns 400 with "Please choose a valid category."
- [ ] A tampered date (e.g. `2026-13-45`) returns 400 with "Please enter a valid date."
- [ ] A description longer than 200 characters returns 400 with the length error
- [ ] An expense added with a past date only appears under `/profile?from=...&to=...` ranges that include that date
- [ ] An expense added by a second user never appears on the demo user's profile
- [ ] "Cancel" goes back to `/profile` without saving anything
- [ ] `grep -n "#[0-9a-fA-F]\{3,6\}" templates/add_expense.html` finds nothing, and any new CSS uses only `var(--...)` colours
