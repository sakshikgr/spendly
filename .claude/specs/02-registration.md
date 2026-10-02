# Spec: Registration

## Overview
Make the existing `/register` page work. Right now `GET /register` renders `register.html`, but the form posts to a route that only accepts GET, so nothing is saved. This step adds the POST handler. It validates the name, email and password, hashes the password with werkzeug, inserts a row into the `users` table created in Step 1, and redirects to the login page with a success message. Registration is the first feature that writes user data. Login and logout (Step 3) and every logged-in page after that depend on real accounts existing, so registration comes first. This step does not log the user in or start a session; that is Step 3's job.

## Depends on
- **Step 1 — Database setup**: `get_db()`, `init_db()` and the `users` table (`id`, `name`, `email UNIQUE`, `password_hash`, `created_at`) in `database/db.py`.

## Routes
- `GET /register` — render the registration form (already exists; it now also accepts POST) — public
- `POST /register` — validate the form, create the user and redirect to `/login` with a success flash message; on error, re-render the form with an error message — public

## Database changes
No database changes. The `users` table in `database/db.py` already has everything this step needs: `name`, `email` (with a `UNIQUE` constraint), `password_hash`, and `created_at` (which defaults to `datetime('now')`).

Two helper functions are added to `database/db.py`. They are new functions, not schema changes:
- `get_user_by_email(email)` — returns the matching `users` row, or `None`
- `create_user(name, email, password)` — hashes the password with `generate_password_hash(password, method="pbkdf2:sha256")` (the same method `seed_db()` uses), inserts the row and returns the new user's `id`

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html`
    - Keep the submitted `name` and `email` in the inputs when the form is re-rendered with an error (`value="{{ name or '' }}"`). Never refill the password field.
    - Add `minlength="8"` to the password input, matching its placeholder.
    - Change `action="/register"` to `action="{{ url_for('register') }}"` to match the project's linking convention.
  - `templates/login.html`
    - Show flashed messages above the form so the "Account created" message appears after the redirect. Use `get_flashed_messages(with_categories=true)`.
  - `static/css/style.css`
    - Add an `.auth-success` style next to `.auth-error`, built only from existing CSS variables. Add a new token in `:root` if no suitable success colour exists.

## Files to change
- `app.py` — import `request`, `redirect`, `url_for` and `flash`; set `app.secret_key` (needed by `flash`); add POST handling to `register()`
- `database/db.py` — add `get_user_by_email()` and `create_user()`
- `templates/register.html` — keep entered values, add `minlength`, use `url_for` in the form action
- `templates/login.html` — render flashed messages
- `static/css/style.css` — add the `.auth-success` style (plus a token if needed)

## Files to create
None.

## New dependencies
No new dependencies. Flask, werkzeug and sqlite3 are already available.

## Rules for implementation
- No SQLAlchemy or ORMs. Use `sqlite3` through `get_db()` only.
- Parameterised queries only. Never use f-strings, `%` or `.format()` in SQL.
- Hash passwords with werkzeug's `generate_password_hash`. Never store or log the plain password.
- Use CSS variables. Never hardcode hex values in new CSS.
- All templates extend `base.html`.
- Validation happens on the server. The HTML attributes (`required`, `type="email"`, `minlength`) are only a convenience.
  - Strip leading and trailing spaces from `name` and `email`, and lowercase `email` before checking and storing it.
  - `name` is required.
  - `email` must be present and look like an email address (contains `@` and a `.` after it).
  - `password` must be at least 8 characters.
  - If the email is already registered, show "An account with that email already exists." Check with `get_user_by_email()` before inserting. Also catch `sqlite3.IntegrityError` from the insert as a backstop.
- On a validation error, re-render `register.html` with `error`, `name` and `email`. Return a 400 for bad input and a 409 for a duplicate email.
- On success, `flash("Account created — please sign in.", "success")` and `redirect(url_for("login"))`. This follows the Post/Redirect/Get pattern, so refreshing the page does not resubmit the form.
- Close every connection opened with `get_db()`. Use `try/finally` or a context manager.
- `app.secret_key` is read from the `SECRET_KEY` environment variable, with a clearly marked dev fallback for local use.
- Do not add sessions or a logged-in state. That is Step 3. Leave the `/logout` and other placeholder routes untouched.
- No new JS libraries and no frontend build step.

## Definition of done
- [ ] `venv/bin/python app.py` starts without errors on http://localhost:5001
- [ ] Visiting `/register` shows the form exactly as before
- [ ] Submitting a valid name, email and password (8+ characters) redirects to `/login`, which shows "Account created — please sign in."
- [ ] The new user appears in `expense_tracker.db` → `users`, with the email stored in lowercase and a `password_hash` starting with `pbkdf2:sha256:`, never the plain password
- [ ] Registering again with the same email, including in different letter case (e.g. `Demo@Spendly.com`), shows "An account with that email already exists." and adds no new row
- [ ] Submitting with an empty name, an invalid email, or a password shorter than 8 characters shows a clear error. The name and email fields keep what was typed, and the password field is empty.
- [ ] Refreshing `/login` after the redirect does not show the success message a second time and does not create another user
- [ ] The success and error messages use only CSS variables and look correct in the existing auth card
- [ ] The landing, login, terms and privacy pages still render correctly
