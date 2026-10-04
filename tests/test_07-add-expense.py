"""Tests for spec 07-add-expense: GET/POST /expenses/add.

Written from .claude/specs/07-add-expense.md. All tests run against a temporary
SQLite file; the real expense_tracker.db is never touched by the tests.
"""
import math
import os
import re
import sqlite3
import tempfile
from datetime import date

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

CATEGORIES = ["Food", "Travel", "Bills", "Shopping", "Health", "Entertainment", "Other"]

AMOUNT_MSG = "Please enter an amount greater than 0."
CATEGORY_MSG = "Please choose a valid category."
DATE_MSG = "Please enter a valid date."
DESC_MSG = "Description must be 200 characters or fewer."


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "test.db"))
    flask_app.config.update(TESTING=True, SECRET_KEY="test-secret")
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


def _count():
    return _query("SELECT COUNT(*) AS n FROM expenses")[0]["n"]


def _user_id(email):
    return _query("SELECT id FROM users WHERE email = ?", (email,))[0]["id"]


def _text(resp):
    return resp.get_data(as_text=True)


def _valid(**overrides):
    data = {
        "amount": "250",
        "category": "Food",
        "date": date.today().isoformat(),
        "description": "Lunch",
    }
    data.update(overrides)
    return data


def _post(client, **overrides):
    return client.post("/expenses/add", data=_valid(**overrides))


# ---------------------------------------------------------------- auth guard
class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_logged_out_redirects_to_login(self, client):
        resp = client.post("/expenses/add", data=_valid())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_logged_out_inserts_nothing(self, client):
        before = _count()
        client.post("/expenses/add", data=_valid())
        assert _count() == before, "Logged-out POST must not insert a row"

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_stale_session_redirects_to_login(self, client, method):
        # Session points at a user that no longer exists (e.g. DB was reset).
        with client.session_transaction() as sess:
            sess["user_id"] = 9999
        before = _count()
        resp = getattr(client, method)("/expenses/add", data=_valid())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert _count() == before, "Stale session must not insert a row"
        with client.session_transaction() as sess:
            assert "user_id" not in sess, "Stale session should be cleared"


# ------------------------------------------------------------------ GET form
class TestForm:
    def test_get_returns_200(self, auth_client):
        assert auth_client.get("/expenses/add").status_code == 200

    def test_get_renders_form_fields(self, auth_client):
        html = _text(auth_client.get("/expenses/add"))
        for name in ("amount", "category", "date", "description"):
            assert f'name="{name}"' in html, f"Missing field {name}"
        assert "Add an expense" in html
        assert "Save expense" in html
        assert "Cancel" in html

    def test_get_form_posts_to_add_expense(self, auth_client):
        html = _text(auth_client.get("/expenses/add"))
        assert re.search(r'<form[^>]*method="POST"[^>]*action="/expenses/add"', html, re.I) \
            or re.search(r'<form[^>]*action="/expenses/add"[^>]*method="POST"', html, re.I)

    def test_get_date_prefilled_with_today(self, auth_client):
        html = _text(auth_client.get("/expenses/add"))
        assert date.today().isoformat() in html, "Date should default to today"

    def test_get_title(self, auth_client):
        assert "Add expense" in _text(auth_client.get("/expenses/add"))

    def test_category_dropdown_lists_exactly_seven_categories(self, auth_client):
        html = _text(auth_client.get("/expenses/add"))
        select = re.search(r'<select[^>]*name="category".*?</select>', html, re.S)
        assert select, "Category <select> not found"
        values = re.findall(r'<option[^>]*value="([^"]*)"', select.group(0))
        values = [v for v in values if v]  # ignore any empty placeholder
        assert values == CATEGORIES

    def test_cancel_links_to_profile(self, auth_client):
        html = _text(auth_client.get("/expenses/add"))
        assert re.search(r'<a[^>]*href="/profile"[^>]*>\s*Cancel', html), \
            "Cancel should link to /profile"

    def test_no_error_shown_on_fresh_get(self, auth_client):
        html = _text(auth_client.get("/expenses/add"))
        for msg in (AMOUNT_MSG, CATEGORY_MSG, DATE_MSG, DESC_MSG):
            assert msg not in html


# -------------------------------------------------------------- happy path
class TestAddSuccess:
    def test_valid_post_redirects_to_profile(self, auth_client):
        resp = _post(auth_client)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_valid_post_inserts_row_with_correct_values(self, auth_client):
        uid = _user_id(DEMO_EMAIL)
        before = _count()
        _post(auth_client, amount="250", category="Food", description="Lunch")
        assert _count() == before + 1
        row = _query(
            "SELECT * FROM expenses WHERE user_id = ? AND description = ?",
            (uid, "Lunch"),
        )
        assert len(row) == 1
        assert row[0]["user_id"] == uid
        assert row[0]["amount"] == 250.0
        assert row[0]["category"] == "Food"
        assert row[0]["date"] == date.today().isoformat()

    def test_user_id_comes_from_session_not_form(self, auth_client, other_client):
        demo_id = _user_id(DEMO_EMAIL)
        other_id = _user_id(OTHER_EMAIL)
        other_client.post("/expenses/add", data=_valid(description="Sneaky", user_id=str(demo_id)))
        row = _query("SELECT user_id FROM expenses WHERE description = ?", ("Sneaky",))
        assert len(row) == 1
        assert row[0]["user_id"] == other_id

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_category_is_accepted(self, auth_client, category):
        resp = _post(auth_client, category=category, description=f"cat-{category}")
        assert resp.status_code == 302
        rows = _query("SELECT category FROM expenses WHERE description = ?", (f"cat-{category}",))
        assert [r["category"] for r in rows] == [category]

    def test_blank_description_stored_as_null(self, auth_client):
        _post(auth_client, description="", amount="11.11")
        rows = _query("SELECT description FROM expenses WHERE amount = ?", (11.11,))
        assert len(rows) == 1
        assert rows[0]["description"] is None

    def test_whitespace_description_stored_as_null(self, auth_client):
        _post(auth_client, description="    ", amount="12.12")
        rows = _query("SELECT description FROM expenses WHERE amount = ?", (12.12,))
        assert len(rows) == 1
        assert rows[0]["description"] is None

    def test_missing_description_field_is_allowed(self, auth_client):
        data = _valid(amount="13.13")
        del data["description"]
        resp = auth_client.post("/expenses/add", data=data)
        assert resp.status_code == 302
        rows = _query("SELECT description FROM expenses WHERE amount = ?", (13.13,))
        assert len(rows) == 1 and rows[0]["description"] is None

    def test_description_is_stripped(self, auth_client):
        _post(auth_client, description="  Padded  ")
        rows = _query("SELECT description FROM expenses WHERE description = ?", ("Padded",))
        assert len(rows) == 1

    def test_description_of_exactly_200_chars_accepted(self, auth_client):
        desc = "x" * 200
        resp = _post(auth_client, description=desc)
        assert resp.status_code == 302
        assert len(_query("SELECT id FROM expenses WHERE description = ?", (desc,))) == 1

    @pytest.mark.parametrize(
        "raw,expected",
        [("10.456", 10.46), ("10.454", 10.45), ("99.999", 100.0), ("0.01", 0.01), ("5", 5.0)],
    )
    def test_amount_rounded_to_two_decimals(self, auth_client, raw, expected):
        _post(auth_client, amount=raw, description="rounding")
        rows = _query("SELECT amount FROM expenses WHERE description = ?", ("rounding",))
        assert len(rows) == 1
        assert rows[0]["amount"] == pytest.approx(expected, abs=1e-9)

    def test_past_date_is_stored(self, auth_client):
        _post(auth_client, date="2020-01-15", description="Old one")
        rows = _query("SELECT date FROM expenses WHERE description = ?", ("Old one",))
        assert rows[0]["date"] == "2020-01-15"

    def test_unpadded_date_stored_as_iso(self, auth_client):
        resp = _post(auth_client, date="2020-1-5", description="Unpadded")
        assert resp.status_code == 302
        rows = _query("SELECT date FROM expenses WHERE description = ?", ("Unpadded",))
        assert rows[0]["date"] == "2020-01-05"

    def test_unpadded_date_visible_in_date_filter(self, auth_client):
        _post(auth_client, date="2020-1-5", description="Unpadded")
        html = _text(auth_client.get("/profile?from=2020-01-01&to=2020-01-31"))
        assert "Unpadded" in html

    def test_sql_injection_in_description_stored_literally(self, auth_client):
        payload = "'); DROP TABLE expenses; --"
        resp = _post(auth_client, description=payload)
        assert resp.status_code == 302
        rows = _query("SELECT description FROM expenses WHERE description = ?", (payload,))
        assert len(rows) == 1, "Payload should be stored verbatim and table must survive"


# -------------------------------------------------- post/redirect/get + flash
class TestRedirectAndFlash:
    def test_flash_shown_on_profile_after_redirect(self, auth_client):
        resp = _post(auth_client)
        follow = auth_client.get(resp.headers["Location"])
        assert follow.status_code == 200
        assert "Expense added." in _text(follow)

    def test_follow_redirects_shows_flash(self, auth_client):
        resp = auth_client.post("/expenses/add", data=_valid(), follow_redirects=True)
        assert resp.status_code == 200
        assert "Expense added." in _text(resp)

    def test_flash_disappears_on_second_profile_load(self, auth_client):
        auth_client.post("/expenses/add", data=_valid(), follow_redirects=True)
        again = auth_client.get("/profile")
        assert "Expense added." not in _text(again)

    def test_refreshing_profile_does_not_duplicate_expense(self, auth_client):
        before = _count()
        auth_client.post("/expenses/add", data=_valid(), follow_redirects=True)
        auth_client.get("/profile")
        auth_client.get("/profile")
        assert _count() == before + 1

    def test_new_expense_appears_on_profile(self, auth_client):
        resp = auth_client.post(
            "/expenses/add", data=_valid(description="UniqueLunchMarker"), follow_redirects=True
        )
        html = _text(resp)
        assert "UniqueLunchMarker" in html
        assert "250.00" in html

    def test_total_rises_to_6947_50_on_profile(self, auth_client):
        resp = auth_client.post("/expenses/add", data=_valid(), follow_redirects=True)
        html = _text(resp)
        assert "6,947.50" in html, "Total should rise from 6,697.50 by 250"

    def test_total_before_add_is_6697_50(self, auth_client):
        assert "6,697.50" in _text(auth_client.get("/profile"))

    def test_blank_description_shows_category_in_table(self, auth_client):
        resp = auth_client.post(
            "/expenses/add",
            data=_valid(description="", category="Health", amount="77.77"),
            follow_redirects=True,
        )
        html = _text(resp)
        assert "77.77" in html
        assert "Health" in html


# --------------------------------------------------------- date filter interplay
class TestDateFilterInterplay:
    def test_past_expense_visible_in_range_including_it(self, auth_client):
        _post(auth_client, date="2020-01-15", description="PastMarkerIn")
        resp = auth_client.get("/profile", query_string={"from": "2020-01-01", "to": "2020-01-31"})
        assert "PastMarkerIn" in _text(resp)

    def test_past_expense_hidden_in_range_excluding_it(self, auth_client):
        _post(auth_client, date="2020-01-15", description="PastMarkerOut")
        resp = auth_client.get("/profile", query_string={"from": "2020-02-01", "to": "2020-02-28"})
        assert "PastMarkerOut" not in _text(resp)


# ------------------------------------------------------------- user isolation
class TestUserIsolation:
    def test_other_users_expense_not_on_demo_profile(self, auth_client, other_client):
        other_client.post("/expenses/add", data=_valid(description="OtherUserSecretItem"))
        assert "OtherUserSecretItem" not in _text(auth_client.get("/profile"))

    def test_other_users_expense_stored_under_their_id(self, other_client):
        _post(other_client, description="OtherOwned")
        rows = _query("SELECT user_id FROM expenses WHERE description = ?", ("OtherOwned",))
        assert rows[0]["user_id"] == _user_id(OTHER_EMAIL)

    def test_other_users_expense_does_not_change_demo_total(self, auth_client, other_client):
        other_client.post("/expenses/add", data=_valid(amount="999"))
        assert "6,697.50" in _text(auth_client.get("/profile"))

    def test_other_user_sees_own_expense_on_profile(self, other_client):
        resp = other_client.post(
            "/expenses/add", data=_valid(description="MineOnly"), follow_redirects=True
        )
        assert "MineOnly" in _text(resp)


# --------------------------------------------------------------- validation
class TestValidation:
    @pytest.mark.parametrize("bad", ["0", "-5", "abc", "", "   ", "nan", "inf", "-inf", "0.00"])
    def test_invalid_amount_returns_400_with_message(self, auth_client, bad):
        resp = _post(auth_client, amount=bad)
        assert resp.status_code == 400
        assert AMOUNT_MSG in _text(resp)

    def test_missing_amount_field_returns_400(self, auth_client):
        data = _valid()
        del data["amount"]
        resp = auth_client.post("/expenses/add", data=data)
        assert resp.status_code == 400
        assert AMOUNT_MSG in _text(resp)

    def test_amount_that_rounds_to_zero_not_stored_as_zero(self, auth_client):
        before = _count()
        resp = _post(auth_client, amount="0.001", description="tiny")
        # Either rejected (400) or, if accepted, never stored as a non-positive amount.
        if resp.status_code == 400:
            assert _count() == before
        else:
            rows = _query("SELECT amount FROM expenses WHERE description = ?", ("tiny",))
            assert all(r["amount"] > 0 for r in rows)

    @pytest.mark.parametrize("bad", ["Crypto", "", "food", "FOOD", "Food; DROP TABLE expenses"])
    def test_invalid_category_returns_400_with_message(self, auth_client, bad):
        resp = _post(auth_client, category=bad)
        assert resp.status_code == 400
        assert CATEGORY_MSG in _text(resp)

    def test_missing_category_field_returns_400(self, auth_client):
        data = _valid()
        del data["category"]
        resp = auth_client.post("/expenses/add", data=data)
        assert resp.status_code == 400
        assert CATEGORY_MSG in _text(resp)

    @pytest.mark.parametrize(
        "bad", ["2026-13-45", "not-a-date", "", "2026/01/01", "01-01-2026", "2026-02-30"]
    )
    def test_invalid_date_returns_400_with_message(self, auth_client, bad):
        resp = _post(auth_client, date=bad)
        assert resp.status_code == 400
        assert DATE_MSG in _text(resp)

    def test_missing_date_field_returns_400(self, auth_client):
        data = _valid()
        del data["date"]
        resp = auth_client.post("/expenses/add", data=data)
        assert resp.status_code == 400
        assert DATE_MSG in _text(resp)

    def test_description_over_200_chars_returns_400(self, auth_client):
        resp = _post(auth_client, description="y" * 201)
        assert resp.status_code == 400
        assert DESC_MSG in _text(resp)

    def test_description_whitespace_padding_not_counted(self, auth_client):
        # 200 real chars plus padding: stripped before the length check.
        resp = _post(auth_client, description="  " + "z" * 200 + "  ")
        assert resp.status_code == 302

    @pytest.mark.parametrize(
        "overrides",
        [
            {"amount": "0"},
            {"amount": "abc"},
            {"category": "Crypto"},
            {"date": "2026-13-45"},
            {"description": "q" * 201},
        ],
    )
    def test_validation_failure_inserts_nothing(self, auth_client, overrides):
        before = _count()
        resp = _post(auth_client, **overrides)
        assert resp.status_code == 400
        assert _count() == before

    def test_validation_order_amount_checked_first(self, auth_client):
        resp = _post(auth_client, amount="0", category="Crypto", date="bad")
        html = _text(resp)
        assert resp.status_code == 400
        assert AMOUNT_MSG in html
        assert CATEGORY_MSG not in html and DATE_MSG not in html

    def test_validation_order_category_before_date(self, auth_client):
        resp = _post(auth_client, category="Crypto", date="bad")
        html = _text(resp)
        assert CATEGORY_MSG in html
        assert DATE_MSG not in html

    def test_validation_order_date_before_description(self, auth_client):
        resp = _post(auth_client, date="bad", description="w" * 201)
        html = _text(resp)
        assert DATE_MSG in html
        assert DESC_MSG not in html


# ------------------------------------------------- preserved values on error
class TestPreservedValues:
    def test_amount_error_preserves_other_fields(self, auth_client):
        resp = _post(auth_client, amount="abc", category="Travel", date="2025-05-05",
                     description="Keep me")
        html = _text(resp)
        assert resp.status_code == 400
        assert "2025-05-05" in html
        assert "Keep me" in html
        assert re.search(r'<option[^>]*value="Travel"[^>]*selected', html), \
            "Submitted category should stay selected"

    def test_amount_value_preserved_on_other_error(self, auth_client):
        resp = _post(auth_client, amount="42.50", category="Crypto")
        html = _text(resp)
        assert resp.status_code == 400
        assert "42.50" in html

    def test_category_error_preserves_values(self, auth_client):
        resp = _post(auth_client, amount="33", category="Crypto", date="2025-06-06",
                     description="Stay put")
        html = _text(resp)
        assert "33" in html
        assert "2025-06-06" in html
        assert "Stay put" in html

    def test_date_error_preserves_values(self, auth_client):
        resp = _post(auth_client, amount="44", category="Bills", date="2026-13-45",
                     description="Date keep")
        html = _text(resp)
        assert "2026-13-45" in html
        assert "Date keep" in html
        assert re.search(r'<option[^>]*value="Bills"[^>]*selected', html)

    def test_description_error_preserves_values(self, auth_client):
        long_desc = "L" * 201
        resp = _post(auth_client, amount="55", category="Health", description=long_desc)
        html = _text(resp)
        assert long_desc in html
        assert re.search(r'<option[^>]*value="Health"[^>]*selected', html)

    def test_error_response_still_lists_all_categories(self, auth_client):
        html = _text(_post(auth_client, amount="0"))
        for cat in CATEGORIES:
            assert f'value="{cat}"' in html

    def test_html_in_description_is_escaped_on_error(self, auth_client):
        payload = "<script>alert(1)</script>" + "a" * 201
        html = _text(_post(auth_client, description=payload))
        assert "<script>alert(1)</script>" not in html


# ---------------------------------------------------- profile button/link
class TestProfileLink:
    def test_profile_has_add_expense_link(self, auth_client):
        html = _text(auth_client.get("/profile"))
        assert "/expenses/add" in html
