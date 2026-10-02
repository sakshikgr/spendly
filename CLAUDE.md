# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Spendly — a personal expense tracker built with Flask, Jinja templates, plain CSS and vanilla JS (no JS framework or frontend build step; don't add libraries). It is a step-by-step learning project: placeholder routes in `app.py` and stub files (e.g. `database/db.py`, `static/js/main.js`) are marked "coming in Step N" / "students will implement", so check those markers before assuming a feature exists.

## Commands

Always use the project virtualenv (`venv/`); the system Python does not have Flask.

```bash
venv/bin/pip install -r requirements.txt   # install deps
venv/bin/python app.py                      # dev server with reload → http://localhost:5001
venv/bin/pytest                             # run tests (pytest + pytest-flask are installed)
venv/bin/pytest path/to/test_file.py::test_name   # single test
```

The app runs on **port 5001**, not 5000 — on macOS port 5000 is taken by AirPlay Receiver. There are no tests yet; quick route checks can use `app.test_client()`.

## Architecture

- `app.py` — all routes in one file. Real pages (`/`, `/login`, `/register`, `/privacy`, `/terms`) render templates; the expense/profile/logout routes are string-returning placeholders.
- `database/db.py` — empty stub; intended to hold `get_db()`, `init_db()`, `seed_db()` over SQLite (`expense_tracker.db`, gitignored).
- `templates/base.html` — shared layout (navbar, footer with Terms/Privacy links). Pages extend it and can fill `title`, `head` (page-specific stylesheets), `content` and `scripts` blocks. Link with `url_for(...)`, matching existing templates.

### Styling

- `static/css/style.css` — global stylesheet: design tokens as CSS variables in `:root` (ink/paper/accent palette, DM Serif Display + DM Sans fonts, radii), plus navbar, buttons, auth, legal (`legal-*`) and footer styles. Reuse the variables rather than hard-coding colours.
- `static/css/landing.css` — loaded only by `landing.html` via `{% block head %}`. It overrides the shared `.hero*` rules for the landing page's centred hero, app preview and video modal. The Terms/Privacy pages also reuse `.hero-badge`/`.hero-title`/`.hero-subtitle` from `style.css`, so change landing-only hero styling in `landing.css`, not `style.css`.
- Page-specific JS goes inline in the template's `{% block scripts %}` (e.g. the "See how it works" YouTube modal in `landing.html`).

## Notes

- `file.txt` at the repo root is the user's scratch file of prompts and commit messages, not app code.
- Commit messages follow a `area: description` style (e.g. `landing: add privacy policy page and route`).
