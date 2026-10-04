# Spec: Edit Expense

## Overview
Step 7 lets a user add expenses, but a mistake (wrong amount, category or date) can't be fixed. The `/expenses/<int:id>/edit` route is still a placeholder that returns "Edit expense — coming in Step 8". This step replaces it with a real edit form. On `/profile`, each row in the transaction table gets an "Edit" link that opens a form pre-filled with that expense's current values. On submit, the server validates the input with the same rules as Step 7, updates the row only if it belongs to the logged-in user, flashes "Expense updated." and redirects to `/profile`. Step 9 (delete) builds on the per-row actions and ownership checks added here.

## Depends on
- **Step 1 — Database setup**: the `expenses` table and `CATEGORIES` in `database/db.py`.
- **Step 3 — Login and Logout**: `session["user_id"]` and the login-guard pattern.
- **Step 5 — Profile backend routes**: `build_expenses()` and the transaction table on `/profile`.
- **Step 6 — Date filter**: the filter must still work, and an edited date must move the expense in or out of a filtered range.
- **Step 7 — Add expense**: the validation rules, the `add_expense.html` form layout and the flash messages on `/profile`.

## Routes
- `GET /expenses/<int:id>/edit` — render the edit form pre-filled with the expense's current amount, category, date and description — logged-in (redirect to `/login` if not authenticated; 404 if the expense doesn't exist or belongs to another user)
- `POST /expenses/<int:id>/edit` — validate the form, update the expense, flash "Expense updated." and redirect to `/profile`. On a validation error, re-render the form with the error and the submitted values, returning status 400 — logged-in (same auth and 404 rules as GET)

Both are served by the existing `edit_expense` view, which changes to `methods=["GET", "POST"]`. Keep the endpoint name `edit_expense` and the `<int:id>` converter.

## Database changes
No database changes. The existing `expenses` table already has every column needed.

Add two helpers to `database/db.py` in the "Expenses" section, following the `create_expense` pattern (`get_db()`, `try`/`finally` close):
- `get_expense_for_user(expense_id, user_id)`: `SELECT id, amount, category, date, description FROM expenses WHERE id = ? AND user_id = ?`, returns the row or `None`.
- `update_expense(expense_id, user_id, amount, category, date, description)`: `UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? WHERE id = ? AND user_id = ?`, commits and returns `cursor.rowcount`. Store an empty description as `NULL`, same as `create_expense`.

Both helpers filter on `user_id` as well as `id`, so one user can never read or change another user's expense.

## Templates
- **Create:** `templates/edit_expense.html`
  - Extends `base.html` and sets `{% block title %}Edit expense — Spendly{% endblock %}`.
  - Same layout and fields as `add_expense.html` (`auth-section`, `auth-card`, `form-group`, `form-input`, `btn-submit`), with the header "Edit expense" and the subtitle "Update the details of this expense".
  - Shows `{{ error }}` in an `auth-error` element when present.
  - `<form method="POST" action="{{ url_for('edit_expense', id=expense_id) }}">` with `amount`, `category`, `date` and `description` fields, filled from `form` (the stored values on GET, the submitted values after an error).
  - A "Save changes" submit button and a "Cancel" link back to `url_for('profile')`.
  - Option: if the two templates end up nearly identical, extract the fields into a shared partial (e.g. `templates/_expense_form_fields.html`) included by both. Only do this if `add_expense.html` keeps rendering exactly as before.
- **Modify:** `templates/profile.html`
  - Add an Actions column (empty `<th>` or "Actions") to the transaction table, with an "Edit" link per row to `url_for('edit_expense', id=e.id)`.
  - Update the empty-state row's `colspan` from 4 to 5.

## Files to change
- `app.py`:
  - Replace the `edit_expense` placeholder with the GET/POST view described above.
  - Import `get_expense_for_user` and `update_expense` from `database.db`.
  - Add `"id": row["id"]` to each dict in `build_expenses()` so the template can build the edit link.
  - Optional: move the shared amount/category/date/description validation from `add_expense()` into a helper (e.g. `validate_expense_form(form)` returning `(values, error)`) that both views use. `add_expense` must behave exactly as before.
- `database/db.py`: add `get_expense_for_user()` and `update_expense()`.
- `templates/profile.html`: Edit link per row and the extra column.
- `static/css/profile.css`: style for the Edit link in the table (e.g. `.txn-actions`, `.txn-edit`), using existing CSS variables only.

## Files to create
- `templates/edit_expense.html`
- `templates/_expense_form_fields.html` (only if the shared-partial option is used)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()`.
- Parameterised queries only. Never use f-strings, `%` or `.format()` to build SQL.
- Passwords hashed with werkzeug (auth isn't changed in this step).
- Use CSS variables. Never hardcode hex values.
- All templates extend `base.html`.
- `user_id` always comes from `session["user_id"]`, never from the form or the URL.
- Ownership: look up the expense with `get_expense_for_user(id, session["user_id"])` on both GET and POST. If it returns `None`, `abort(404)`. Don't reveal whether the expense exists for another user.
- Guard order, matching `add_expense()`: not logged in → redirect to `/login`; session user missing from the DB → `session.clear()` and redirect to `/login`; then the ownership check.
- Pre-fill on GET from the stored row: `amount` formatted to 2 decimals, `category`, `date` (ISO `YYYY-MM-DD`) and `description` as stored, with `NULL` shown as an empty field. Use the raw description, not the category fallback that `build_expenses()` shows on the profile.
- Server-side validation is identical to Step 7, in the same order and with the same messages, each re-rendering the form with status 400 and the submitted values:
  - `amount`: `float()`, finite, rounded to 2 places, greater than 0 → "Please enter an amount greater than 0."
  - `category`: in `CATEGORIES` → "Please choose a valid category."
  - `date`: parses with `datetime.strptime(value, "%Y-%m-%d")` and is stored in normalised ISO form → "Please enter a valid date."
  - `description`: stripped, optional, at most 200 characters → "Description must be 200 characters or fewer."
- On success: `flash("Expense updated.", "success")` and `redirect(url_for("profile"))` (post/redirect/get).
- Follow the existing view style (a local `form_error()` helper, early returns).
- No JavaScript and no new libraries. The form works with a plain POST.
- No inline styles.
- Leave the delete placeholder route (Step 9) untouched.

## Definition of done
- [ ] `venv/bin/python app.py` starts without errors on http://localhost:5001
- [ ] Visiting `/expenses/1/edit` while logged out redirects to `/login`, and so does a POST while logged out (the row is unchanged)
- [ ] Logged in as `demo@spendly.com` / `demo123`, every row in the transaction table on `/profile` has an "Edit" link, and the empty state still spans the full table width
- [ ] Clicking "Edit" on "Electricity bill" opens a form pre-filled with 1200.00, Bills, that expense's date and "Electricity bill"
- [ ] Changing the amount to `1500` and saving redirects to `/profile`, shows "Expense updated.", and the row shows ₹1,500.00. The total rises by ₹300, the count stays the same, and the Bills total in the category breakdown rises by ₹300
- [ ] Changing the category from Bills to Health moves that amount from Bills to Health in the category breakdown, and the badge on the row changes
- [ ] Changing the date to one outside the current month removes the expense from "This month" and shows it under an `/profile?from=...&to=...` range that includes the new date
- [ ] Clearing the description saves it, and the table shows the category name as the description. Reopening Edit shows an empty description field, not the category name
- [ ] Refreshing `/profile` after the redirect doesn't resubmit the edit
- [ ] Amount `0`, `-5`, `abc` or empty returns 400 with "Please enter an amount greater than 0.", the other fields keep their submitted values, and the database row is unchanged
- [ ] A tampered category (e.g. `Crypto`) returns 400 with "Please choose a valid category."
- [ ] A tampered date (e.g. `2026-13-45`) returns 400 with "Please enter a valid date."
- [ ] A description longer than 200 characters returns 400 with the length error
- [ ] `/expenses/99999/edit` returns 404
- [ ] Logged in as a second user, GET and POST to `/expenses/<demo expense id>/edit` both return 404, and the demo user's expense is unchanged
- [ ] "Cancel" goes back to `/profile` without saving anything
- [ ] Adding an expense through `/expenses/add` still works exactly as in Step 7
- [ ] `/expenses/<id>/delete` still returns the Step 9 placeholder
- [ ] `grep -n "#[0-9a-fA-F]\{3,6\}" templates/edit_expense.html` finds nothing, and any new CSS uses only `var(--...)` colours
