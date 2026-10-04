"""Tests for spec 09-delete-expense: GET/POST /expenses/<id>/delete.

Written from .claude/specs/09-delete-expense.md. All tests run against a temporary
SQLite file; the real expense_tracker.db is never touched by the tests.
"""
import os
import re
import sqlite3
import tempfile

import pytest

import database.db as dbmod

# Point the DB layer at a throwaway file BEFORE importing app (app seeds on import).
_IMPORT_DB = os.path.join(tempfile.mkdtemp(prefix="spendly-import-"), "import.db")
dbmod.DB_PATH = _IMPORT_DB

from app import app as flask_app  # noqa: E402

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
OTHER_EMAIL = "other@example.com"
OTHER_PASSWORD = "password123"


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "test.db"))
    flask_app.config.update(TESTING=True)
    dbmod.init_db()
    dbmod.seed_db()
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    resp = client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert resp.status_code == 302, "Demo login should succeed"
    return client


@pytest.fixture
def other_client(app):
    dbmod.create_user("Other User", OTHER_EMAIL, OTHER_PASSWORD)
    c = app.test_client()
    resp = c.post("/login", data={"email": OTHER_EMAIL, "password": OTHER_PASSWORD})
    assert resp.status_code == 302, "Second user login should succeed"
    return c


# ------------------------------------------------------------------- helpers
def _query(sql, params=()):
    conn = sqlite3.connect(dbmod.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _expense_id(description="Electricity bill"):
    return _query("SELECT id FROM expenses WHERE description = ?", (description,))[0]["id"]


def _exists(expense_id):
    return bool(_query("SELECT 1 FROM expenses WHERE id = ?", (expense_id,)))


def _count():
    return _query("SELECT COUNT(*) AS n FROM expenses")[0]["n"]


def _url(expense_id):
    return f"/expenses/{expense_id}/delete"


def _text(resp):
    return resp.get_data(as_text=True)


# --------------------------------------------------------------------- auth
class TestAuth:
    def test_get_logged_out_redirects_to_login(self, client):
        resp = client.get(_url(_expense_id()))
        assert resp.status_code == 302
        assert "/login" in resp.location

    def test_post_logged_out_redirects_and_keeps_row(self, client):
        eid = _expense_id()
        resp = client.post(_url(eid))
        assert resp.status_code == 302
        assert "/login" in resp.location
        assert _exists(eid)

    def test_stale_session_user_is_logged_out(self, auth_client):
        eid = _expense_id()
        with auth_client.session_transaction() as sess:
            sess["user_id"] = 99999
        resp = auth_client.post(_url(eid))
        assert resp.status_code == 302
        assert "/login" in resp.location
        assert _exists(eid)


# ------------------------------------------------------------- confirmation
class TestConfirmationPage:
    def test_shows_expense_summary(self, auth_client):
        eid = _expense_id()
        resp = auth_client.get(_url(eid))
        html = _text(resp)
        assert resp.status_code == 200
        assert "Electricity bill" in html
        assert "badge-bills" in html
        assert "₹1,200.00" in html
        assert "This can&#39;t be undone." in html or "This can't be undone." in html

    def test_get_does_not_delete(self, auth_client):
        eid = _expense_id()
        auth_client.get(_url(eid))
        assert _exists(eid)

    def test_form_posts_to_delete_route(self, auth_client):
        eid = _expense_id()
        html = _text(auth_client.get(_url(eid)))
        assert re.search(r'<form[^>]*method="POST"[^>]*action="/expenses/%d/delete"' % eid, html)

    def test_cancel_links_to_profile(self, auth_client):
        html = _text(auth_client.get(_url(_expense_id())))
        assert 'href="/profile"' in html

    def test_empty_description_shows_category(self, auth_client):
        eid = dbmod.create_expense(1, 50, "Food", "2026-01-05", "")
        html = _text(auth_client.get(_url(eid)))
        assert "05 Jan 2026" in html
        assert re.search(r"<dd>\s*Food\s*</dd>", html)


# ------------------------------------------------------------------- delete
class TestDelete:
    def test_post_deletes_and_redirects_with_flash(self, auth_client):
        eid = _expense_id()
        before = _count()
        resp = auth_client.post(_url(eid))
        assert resp.status_code == 302
        assert resp.location.endswith("/profile")
        assert not _exists(eid)
        assert _count() == before - 1
        html = _text(auth_client.get("/profile"))
        assert "Expense deleted." in html
        assert "Electricity bill" not in html

    def test_profile_totals_update(self, auth_client):
        auth_client.post(_url(_expense_id()))
        html = _text(auth_client.get("/profile"))
        # Seed total 6,697.50 minus the 1,200.00 electricity bill.
        assert "₹5,497.50" in html
        assert re.search(r'stat-value">\s*7\s*<', html)

    def test_last_in_category_leaves_breakdown(self, auth_client):
        auth_client.post(_url(_expense_id("Running shoes")))
        html = _text(auth_client.get("/profile"))
        assert "category-bar-shopping" not in html

    def test_delete_everything_shows_empty_state(self, auth_client):
        for row in _query("SELECT id FROM expenses"):
            auth_client.post(_url(row["id"]))
        html = _text(auth_client.get("/profile"))
        assert "No expenses yet." in html
        assert "₹0.00" in html

    def test_second_post_is_404(self, auth_client):
        eid = _expense_id()
        auth_client.post(_url(eid))
        assert auth_client.post(_url(eid)).status_code == 404

    def test_missing_expense_is_404(self, auth_client):
        assert auth_client.get(_url(99999)).status_code == 404
        assert auth_client.post(_url(99999)).status_code == 404

    def test_other_users_expense_is_404(self, auth_client, other_client):
        eid = _expense_id()
        assert other_client.get(_url(eid)).status_code == 404
        assert other_client.post(_url(eid)).status_code == 404
        assert _exists(eid)


# --------------------------------------------------------------- profile UI
class TestProfileLinks:
    def test_every_row_has_edit_and_delete(self, auth_client):
        html = _text(auth_client.get("/profile"))
        n = _count()
        assert html.count('class="txn-edit"') == n
        assert html.count('class="txn-delete"') == n

    def test_delete_template_has_no_hardcoded_hex_colours(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "templates", "delete_expense.html")
        with open(path, encoding="utf-8") as fh:
            assert not re.search(r"#[0-9a-fA-F]{3,6}\b", fh.read())


# ------------------------------------------------------------------- navbar
class TestNavbar:
    def test_logged_in_nav_links_to_profile(self, auth_client):
        html = _text(auth_client.get("/analytics"))
        assert 'href="/profile"' in html

    def test_logged_out_nav_has_no_profile_link(self, client):
        html = _text(client.get("/"))
        assert 'class="nav-profile' not in html
