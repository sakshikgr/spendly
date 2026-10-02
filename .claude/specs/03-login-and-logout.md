# Spec: Login and Logout

## Overview
Make the existing `/login` page work and replace the `/logout` placeholder. Right now `GET /login` renders `login.html`, but the form posts to a route that only accepts GET, and `/logout` returns the string "Logout — coming in Step 3". This step adds a POST handler that looks the user up by email and checks the password with werkzeug's `check_password_hash`. On success it stores the user's id and name in Flask's signed `session` cookie. `/logout` clears that session. The navbar changes with login state: logged-out visitors see "Sign in" / "Get started", and logged-in users see their name and "Sign out". This is the first step with a logged-in state. Step 2 created accounts, and the profile page (Step 4) and every expense feature after it need to know who the current user is.

## Depends on
- **Step 1 — Database setup**: the `users` table (`id`, `name`, `email UNIQUE`, `password_hash`) and `get_db()` in `database/db.py`.
- **Step 2 — Registration**: real accounts with `pbkdf2:sha256` password hashes, `get_user_by_email()` in `database/db.py`, `app.secret_key` in `app.py` (required for `session` and `flash`), the flashed-message block in `login.html`, and the `.auth-success` / `.auth-error` styles.

## Routes
- `GET /login` — render the sign-in form (already exists; it now also accepts POST). If the user is already logged in, redirect to `/profile` — public
- `POST /login` — validate the credentials, start a session and redirect to `/profile`. On failure, re-render the form with an error — public
- `GET /logout` — clear the session, flash "You've been signed out." and redirect to `/login` (replaces the placeholder) — public (safe to call when logged out)

`GET /register` also changes: a logged-in user who visits it is redirected to `/profile`. No other new routes. `/profile` stays as its Step 4 placeholder and becomes the post-login landing page.

## Database changes
No database changes. The `users` table already stores everything login needs, and `get_user_by_email(email)` from Step 2 returns the full row, including `password_hash`. No new functions are needed in `database/db.py`.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html`
    - Change `action="/login"` to `action="{{ url_for('login') }}"`.
    - Keep the submitted `email` in the input when the form is re-rendered with an error (`value="{{ email or '' }}"`). Never refill the password field.
    - The flashed-message loop and the `error` block already exist; leave them as they are.
  - `templates/base.html`
    - In `.nav-links`, check `session.user_id`:
      - Logged in: show the user's name (`session.user_name`) in a `<span class="nav-user">` and a "Sign out" link to `url_for('logout')` with class `nav-cta`.
      - Logged out: keep the current "Sign in" and "Get started" links exactly as they are.
  - `static/css/style.css`
    - Add a `.nav-user` style next to the `.nav-links` rules, using only existing CSS variables (e.g. `var(--ink-muted)`).
    - In the existing mobile media query, hide `.nav-user` next to `.nav-links a:not(.nav-cta)`, so only the "Sign out" button stays visible on small screens.

## Files to change
- `app.py` — import `session` and `check_password_hash`. Add POST handling to `login()`. Redirect logged-in users away from `/login` and `/register`. Replace the `/logout` placeholder.
- `templates/login.html` — `url_for` form action and keep the entered email
- `templates/base.html` — navbar that changes with login state
- `static/css/style.css` — `.nav-user` style and its mobile rule

## Files to create
None.

## New dependencies
No new dependencies. Flask's `session` and werkzeug's `check_password_hash` are already available.

## Rules for implementation
- No SQLAlchemy or ORMs. Look users up only with the existing `get_user_by_email()`.
- Parameterised queries only. Never use f-strings, `%` or `.format()` in SQL.
- Check passwords with werkzeug's `check_password_hash(user["password_hash"], password)`. Never compare plain passwords, and never store or log the submitted password.
- Use CSS variables. Never hardcode hex values in new CSS.
- All templates extend `base.html`.
- Use Flask's built-in signed-cookie `session`. Don't add Flask-Login, Flask-Session or any other package.
- Store only `session["user_id"]` and `session["user_name"]`. Never store the password hash or the email in the session.
- Call `session.clear()` before setting the new values on successful login, so nothing from an earlier session carries over. Call it again on logout.
- Validation happens on the server:
  - Strip and lowercase `email` before the lookup, the same way registration does.
  - If email or password is empty, show "Please enter your email and password." with status 400.
  - If the email isn't registered or the password is wrong, show the same message for both: "Invalid email or password." with status 401. Never reveal which part was wrong.
- On a failed login, re-render `login.html` with `error` and `email`.
- On success, `redirect(url_for("profile"))`. This follows the Post/Redirect/Get pattern, so refreshing the page doesn't resubmit the form. Don't flash a welcome message, because the `/profile` placeholder doesn't render templates yet.
- `/logout` stays a GET route, to match the existing placeholder and the navbar link. It must work even when nobody is logged in: it clears the session, flashes "You've been signed out." with the `success` category, and redirects to `/login`.
- Use `session.get("user_id")` for the "already logged in" checks in `/login` and `/register`.
- Don't build the profile page or add `login_required` protection to `/profile` or the expense routes. That's Step 4. Leave the other placeholder routes untouched.
- No new JS libraries and no frontend build step.

## Definition of done
- [ ] `venv/bin/python app.py` starts without errors on http://localhost:5001
- [ ] Visiting `/login` while logged out shows the form exactly as before, and the navbar shows "Sign in" and "Get started"
- [ ] Logging in as `demo@spendly.com` / `demo123` redirects to `/profile`
- [ ] After logging in, the navbar on every page (landing, terms, privacy, login) shows "Demo User" and "Sign out" instead of "Sign in" / "Get started"
- [ ] Logging in with `DEMO@Spendly.com` (different letter case) and the correct password also works
- [ ] A wrong password and an unregistered email both show "Invalid email or password.", and the email field keeps what was typed while the password field is empty
- [ ] Submitting with an empty email or password shows "Please enter your email and password."
- [ ] An account created through `/register` can log in with the password chosen at registration
- [ ] While logged in, visiting `/login` or `/register` redirects to `/profile`
- [ ] Clicking "Sign out" redirects to `/login`, shows "You've been signed out.", and the navbar goes back to "Sign in" / "Get started"
- [ ] Refreshing `/login` after signing out doesn't show the message again
- [ ] Visiting `/logout` while already logged out doesn't error and still lands on `/login`
- [ ] The browser's session cookie doesn't contain the password or the password hash
- [ ] On a narrow (mobile-width) window, the logged-in navbar shows only the "Sign out" button, with no overflow
- [ ] Registration (Step 2) still works end to end, and the landing, terms and privacy pages still render correctly
