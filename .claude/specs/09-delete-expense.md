# Spec: Delete Expense

## Overview
Step 8 lets a user fix a wrong expense, but there's no way to remove one entered by mistake or twice. The `/expenses/<int:id>/delete` route is still a placeholder that returns "Delete expense — coming in Step 9". This step replaces it with a two-step delete. On `/profile`, each row in the transaction table gets a "Delete" link next to "Edit". The link opens a confirmation page that shows the expense's date, description, category and amount. Submitting that page's form sends a POST that deletes the row only if it belongs to the logged-in user, flashes "Expense deleted." and redirects to `/profile`. Deleting only on POST means a link preview, prefetch or crawler hitting the URL can never delete data. This completes create, edit and delete for expenses.

## Depends on
- **Step 1 — Database setup**: the `expenses` table in `database/db.py`.
- **Step 3 — Login and Logout**: `session["user_id"]` and the login-guard pattern.
- **Step 5 — Profile backend routes**: the transaction table and stats/category breakdown on `/profile`.
- **Step 6 — Date filter**: totals for a filtered range must reflect the deletion.
- **Step 8 — Edit expense**: `get_expense_for_user()`, the `id` in `build_expenses()`, the Actions column (`.txn-actions`, `.txn-edit`) and the guard/404 ownership pattern.

## Routes
- `GET /expenses/<int:id>/delete` — render a confirmation page showing the expense's date, description, category and amount, with a "Delete expense" button and a "Cancel" link — logged-in (redirect to `/login` if not authenticated; 404 if the expense doesn't exist or belongs to another user)
- `POST /expenses/<int:id>/delete` — delete the expense, flash "Expense deleted." and redirect to `/profile` — logged-in (same auth and 404 rules as GET)

Both are served by the existing `delete_expense` view, which changes to `methods=["GET", "POST"]`. Keep the endpoint name `delete_expense` and the `<int:id>` converter.

## Database changes
No database changes. Deleting an expense needs no schema change, and no other table references `expenses`.

Add one helper to `database/db.py` in the "Expenses" section, following the `update_expense` pattern (`get_db()`, `try`/`finally` close):
- `delete_expense(expense_id, user_id)`: `DELETE FROM expenses WHERE id = ? AND user_id = ?`, commits and returns `cursor.rowcount`.

The helper filters on `user_id` as well as `id`, so one user can never delete another user's expense. Since the view is also named `delete_expense`, import the helper under an alias (e.g. `from database.db import delete_expense as db_delete_expense`) or name the helper differently (e.g. `remove_expense`) to avoid the name clash in `app.py`.

## Templates
- **Create:** `templates/delete_expense.html`
  - Extends `base.html` and sets `{% block title %}Delete expense — Spendly{% endblock %}`.
  - Uses the same card layout as `edit_expense.html` (`auth-section`, `auth-card`), with the header "Delete expense" and the subtitle "This can't be undone."
  - Shows a read-only summary of the expense: date (formatted like the profile table, e.g. `05 Oct 2026`), description (or the category name if empty, matching the profile table), category badge and amount as `₹{:,.2f}`.
  - `<form method="POST" action="{{ url_for('delete_expense', id=expense.id) }}">` with a single "Delete expense" submit button styled as a danger action.
  - A "Cancel" link back to `url_for('profile')`.
- **Modify:** `templates/profile.html`
  - In each row's `txn-actions` cell, add a "Delete" link to `url_for('delete_expense', id=e.id)` after the existing "Edit" link.
  - No change to the column count or the empty-state `colspan`.

## Files to change
- `app.py`:
  - Replace the `delete_expense` placeholder with the GET/POST view described above, and move it out of the "Placeholder routes" section (remove the now-empty section header).
  - Import the new delete helper from `database.db` (aliased if needed, see above).
- `database/db.py`: add the delete helper.
- `templates/profile.html`: Delete link per row.
- `static/css/profile.css`: style for the Delete link (e.g. `.txn-delete`) using `var(--danger)`, with spacing next to `.txn-edit`.
- `static/css/style.css`: a danger button variant (e.g. `.btn-danger`, using `var(--danger)` / `var(--danger-light)`) and any styles for the expense summary on the confirmation page, if no existing class fits.

## Files to create
- `templates/delete_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs. Use raw `sqlite3` through `get_db()`.
- Parameterised queries only. Never use f-strings, `%` or `.format()` to build SQL.
- Passwords hashed with werkzeug (auth isn't changed in this step).
- Use CSS variables. Never hardcode hex values.
- All templates extend `base.html`.
- `user_id` always comes from `session["user_id"]`, never from the form or the URL.
- Never delete on GET. GET only renders the confirmation page; only POST deletes.
- Guard order, matching `edit_expense()`: not logged in → redirect to `/login`; session user missing from the DB → `session.clear()` and redirect to `/login`; then look up the expense with `get_expense_for_user(id, session["user_id"])` and `abort(404)` if it returns `None`. Do this on both GET and POST, and don't reveal whether the expense exists for another user.
- On success: `flash("Expense deleted.", "success")` and `redirect(url_for("profile"))` (post/redirect/get).
- A second POST for an already-deleted expense returns 404, not an error page or a 500.
- No JavaScript (no `confirm()` dialog) and no new libraries. The confirmation is a plain page and form.
- No inline styles.
- Don't change the add or edit flows.

## Definition of done
- [ ] `venv/bin/python app.py` starts without errors on http://localhost:5001
- [ ] Visiting `/expenses/1/delete` while logged out redirects to `/login`, and so does a POST while logged out (the row still exists)
- [ ] Logged in as `demo@spendly.com` / `demo123`, every row in the transaction table on `/profile` has both "Edit" and "Delete" links, and "Delete" is styled in the danger colour
- [ ] Clicking "Delete" on "Electricity bill" opens a confirmation page showing its date, "Electricity bill", the Bills badge and ₹1,200.00, and the expense is still in the database
- [ ] Clicking "Cancel" returns to `/profile` with the expense still listed
- [ ] Clicking "Delete expense" redirects to `/profile`, shows "Expense deleted.", and the row is gone. The total drops by ₹1,200, the transaction count drops by 1, and the Bills total in the category breakdown drops by ₹1,200
- [ ] Deleting the only expense in a category removes that category from the breakdown, and "Top category" updates if needed
- [ ] With a date filter active (e.g. "This month"), deleting an expense in that range updates the filtered totals
- [ ] Deleting every expense shows the "No expenses yet." empty state and a ₹0.00 total
- [ ] Refreshing `/profile` after the redirect doesn't resubmit the delete
- [ ] POSTing to the same `/expenses/<id>/delete` again after it's deleted returns 404
- [ ] `/expenses/99999/delete` returns 404 for both GET and POST
- [ ] Logged in as a second user, GET and POST to `/expenses/<demo expense id>/delete` both return 404, and the demo user's expense still exists
- [ ] Adding an expense through `/expenses/add` and editing one through `/expenses/<id>/edit` still work as in Steps 7 and 8
- [ ] `grep -n "#[0-9a-fA-F]\{3,6\}" templates/delete_expense.html` finds nothing, and any new CSS uses only `var(--...)` colours
