"""Tests for spec 08-edit-expense: GET/POST /expenses/<id>/edit.

Written from .claude/specs/08-edit-expense.md. All tests run against a temporary
SQLite file; the real expense_tracker.db is never touched by the tests.
"""
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


def _exec(sql, params=()):
    conn = sqlite3.connect(dbmod.DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _count():
    return _query("SELECT COUNT(*) AS n FROM expenses")[0]["n"]


def _user_id(email):
    return _query("SELECT id FROM users WHERE email = ?", (email,))[0]["id"]


def _row(expense_id):
    rows = _query("SELECT * FROM expenses WHERE id = ?", (expense_id,))
    return dict(rows[0]) if rows else None


def _snapshot():
    return [dict(r) for r in _query("SELECT * FROM expenses ORDER BY id")]


def _demo_expense(description="Electricity bill"):
    rows = _query(
        "SELECT * FROM expenses WHERE user_id = ? AND description = ?",
        (_user_id(DEMO_EMAIL), description),
    )
    assert rows, f"Seed data should contain {description!r}"
    return dict(rows[0])


def _text(resp):
    return resp.get_data(as_text=True)


def _url(expense_id):
    return f"/expenses/{expense_id}/edit"


def _valid(**overrides):
    data = {
        "amount": "250",
        "category": "Food",
        "date": "2025-03-10",
        "description": "Edited",
    }
    data.update(overrides)
    return data


def _post(client, expense_id, **overrides):
    return client.post(_url(expense_id), data=_valid(**overrides))


def _fmt(amount):
    return "₹{:,.2f}".format(amount)


def _user_total(email=DEMO_EMAIL):
    return _query(
        "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses WHERE user_id = ?",
        (_user_id(email),),
    )[0]["t"]


def _category_total(category, email=DEMO_EMAIL):
    return _query(
        "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses WHERE user_id = ? AND category = ?",
        (_user_id(email), category),
    )[0]["t"]


def _breakdown(html):
    """Return {category: amount_text} parsed from the category breakdown list."""
    out = {}
    for m in re.finditer(
        r'<span class="category-name">([^<]+)</span>.*?<span class="category-amount">([^<]+)</span>',
        html,
        re.S,
    ):
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def _stat(html, label):
    m = re.search(
        r'<span class="stat-label">' + re.escape(label) + r'</span>\s*<span class="stat-value">([^<]*)</span>',
        html,
    )
    assert m, f"Stat {label!r} not found"
    return m.group(1).strip()


def _field_value(html, name):
    m = re.search(r'<input[^>]*name="' + name + r'"[^>]*>', html)
    assert m, f"input {name} not found"
    v = re.search(r'value="([^"]*)"', m.group(0))
    return v.group(1) if v else ""


def _textarea_or_input_description(html):
    m = re.search(r'<textarea[^>]*name="description"[^>]*>(.*?)</textarea>', html, re.S)
    if m:
        return m.group(1).strip()
    return _field_value(html, "description")


def _selected_category(html):
    select = re.search(r'<select[^>]*name="category".*?</select>', html, re.S)
    assert select, "Category <select> not found"
    selected = [
        re.search(r'value="([^"]*)"', o).group(1)
        for o in re.findall(r"<option[^>]*>", select.group(0))
        if "selected" in o
    ]
    return selected


# ---------------------------------------------------------------- auth guard
class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client):
        eid = _demo_expense()["id"]
        resp = client.get(_url(eid))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_logged_out_redirects_to_login(self, client):
        eid = _demo_expense()["id"]
        resp = client.post(_url(eid), data=_valid())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_logged_out_leaves_db_unchanged(self, client):
        eid = _demo_expense()["id"]
        before = _snapshot()
        client.post(_url(eid), data=_valid())
        assert _snapshot() == before, "Logged-out POST must not change any row"

    def test_logged_out_nonexistent_id_still_redirects(self, client):
        resp = client.get(_url(99999))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_stale_session_redirects_and_clears(self, client, method):
        eid = _demo_expense()["id"]
        with client.session_transaction() as sess:
            sess["user_id"] = 9999
        before = _snapshot()
        resp = getattr(client, method)(_url(eid), data=_valid())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert _snapshot() == before
        with client.session_transaction() as sess:
            assert "user_id" not in sess, "Stale session should be cleared"


# ----------------------------------------------------------------- ownership
class TestOwnership:
    def test_nonexistent_id_get_returns_404(self, auth_client):
        assert auth_client.get(_url(99999)).status_code == 404

    def test_nonexistent_id_post_returns_404(self, auth_client):
        before = _snapshot()
        assert auth_client.post(_url(99999), data=_valid()).status_code == 404
        assert _snapshot() == before

    def test_other_users_expense_get_returns_404(self, other_client):
        eid = _demo_expense()["id"]
        assert other_client.get(_url(eid)).status_code == 404

    def test_other_users_expense_post_returns_404_and_row_unchanged(self, other_client):
        eid = _demo_expense()["id"]
        before = _row(eid)
        resp = _post(other_client, eid, amount="1", description="Hijacked")
        assert resp.status_code == 404
        assert _row(eid) == before, "Another user's expense must not change"

    def test_other_users_invalid_post_is_404_not_400(self, other_client):
        eid = _demo_expense()["id"]
        resp = _post(other_client, eid, amount="abc")
        assert resp.status_code == 404, "Ownership check precedes validation"

    def test_user_id_in_form_is_ignored(self, auth_client):
        demo_id = _user_id(DEMO_EMAIL)
        eid = _demo_expense()["id"]
        dbmod.create_user("Other User", OTHER_EMAIL, OTHER_PASSWORD)
        other_id = _user_id(OTHER_EMAIL)
        _post(auth_client, eid, user_id=str(other_id))
        assert _row(eid)["user_id"] == demo_id

    def test_404_does_not_leak_expense_details(self, other_client):
        exp = _demo_expense()
        html = _text(other_client.get(_url(exp["id"])))
        assert "Electricity bill" not in html

    def test_only_target_row_is_updated(self, auth_client):
        eid = _demo_expense()["id"]
        before = {r["id"]: r for r in _snapshot()}
        _post(auth_client, eid)
        after = {r["id"]: r for r in _snapshot()}
        for rid, row in before.items():
            if rid != eid:
                assert after[rid] == row, f"Row {rid} must be untouched"

    def test_non_integer_id_returns_404(self, auth_client):
        assert auth_client.get("/expenses/abc/edit").status_code == 404


# ------------------------------------------------------------ GET form + prefill
class TestEditForm:
    def test_get_returns_200(self, auth_client):
        eid = _demo_expense()["id"]
        assert auth_client.get(_url(eid)).status_code == 200

    def test_get_renders_headings_and_buttons(self, auth_client):
        html = _text(auth_client.get(_url(_demo_expense()["id"])))
        assert "Edit expense" in html
        assert "Update the details of this expense" in html
        assert "Save changes" in html
        assert "Cancel" in html

    def test_get_title(self, auth_client):
        html = _text(auth_client.get(_url(_demo_expense()["id"])))
        assert re.search(r"<title>[^<]*Edit expense[^<]*Spendly", html)

    def test_get_renders_all_fields(self, auth_client):
        html = _text(auth_client.get(_url(_demo_expense()["id"])))
        for name in ("amount", "category", "date", "description"):
            assert f'name="{name}"' in html, f"Missing field {name}"

    def test_form_posts_to_same_edit_url(self, auth_client):
        eid = _demo_expense()["id"]
        html = _text(auth_client.get(_url(eid)))
        action = _url(eid)
        assert re.search(rf'<form[^>]*method="POST"[^>]*action="{action}"', html, re.I) \
            or re.search(rf'<form[^>]*action="{action}"[^>]*method="POST"', html, re.I)

    def test_cancel_links_to_profile(self, auth_client):
        html = _text(auth_client.get(_url(_demo_expense()["id"])))
        assert re.search(r'<a[^>]*href="/profile"[^>]*>\s*Cancel', html)

    def test_category_dropdown_lists_exactly_seven_categories(self, auth_client):
        html = _text(auth_client.get(_url(_demo_expense()["id"])))
        select = re.search(r'<select[^>]*name="category".*?</select>', html, re.S)
        assert select
        values = [v for v in re.findall(r'<option[^>]*value="([^"]*)"', select.group(0)) if v]
        assert values == CATEGORIES

    def test_prefill_electricity_bill(self, auth_client):
        exp = _demo_expense("Electricity bill")
        html = _text(auth_client.get(_url(exp["id"])))
        assert _field_value(html, "amount") == "1200.00"
        assert _selected_category(html) == ["Bills"]
        assert _field_value(html, "date") == exp["date"]
        assert _textarea_or_input_description(html) == "Electricity bill"

    def test_prefill_amount_formatted_to_two_decimals(self, auth_client):
        eid = _demo_expense()["id"]
        _exec("UPDATE expenses SET amount = ? WHERE id = ?", (7.5, eid))
        html = _text(auth_client.get(_url(eid)))
        assert _field_value(html, "amount") == "7.50"

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_prefill_selects_stored_category(self, auth_client, category):
        eid = _demo_expense()["id"]
        _exec("UPDATE expenses SET category = ? WHERE id = ?", (category, eid))
        html = _text(auth_client.get(_url(eid)))
        assert _selected_category(html) == [category]

    def test_prefill_null_description_is_empty_not_category(self, auth_client):
        eid = _demo_expense()["id"]
        _exec("UPDATE expenses SET description = NULL, category = ? WHERE id = ?", ("Health", eid))
        html = _text(auth_client.get(_url(eid)))
        assert _textarea_or_input_description(html) == "", \
            "NULL description must show empty, not the category name"

    def test_prefill_raw_description_is_escaped(self, auth_client):
        eid = _demo_expense()["id"]
        _exec("UPDATE expenses SET description = ? WHERE id = ?", ("<script>x</script>", eid))
        html = _text(auth_client.get(_url(eid)))
        assert "<script>x</script>" not in html

    def test_no_error_on_fresh_get(self, auth_client):
        html = _text(auth_client.get(_url(_demo_expense()["id"])))
        for msg in (AMOUNT_MSG, CATEGORY_MSG, DATE_MSG, DESC_MSG):
            assert msg not in html

    def test_get_does_not_modify_db(self, auth_client):
        before = _snapshot()
        auth_client.get(_url(_demo_expense()["id"]))
        assert _snapshot() == before


# -------------------------------------------------------------- happy path
class TestEditSuccess:
    def test_valid_post_redirects_to_profile(self, auth_client):
        resp = _post(auth_client, _demo_expense()["id"])
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_update_persists_all_fields(self, auth_client):
        eid = _demo_expense()["id"]
        before = _count()
        _post(auth_client, eid, amount="1500", category="Health", date="2025-03-10",
              description="Updated desc")
        row = _row(eid)
        assert row["amount"] == 1500.0
        assert row["category"] == "Health"
        assert row["date"] == "2025-03-10"
        assert row["description"] == "Updated desc"
        assert row["user_id"] == _user_id(DEMO_EMAIL)
        assert _count() == before, "Edit must not add or remove rows"

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_category_accepted(self, auth_client, category):
        eid = _demo_expense()["id"]
        resp = _post(auth_client, eid, category=category)
        assert resp.status_code == 302
        assert _row(eid)["category"] == category

    @pytest.mark.parametrize(
        "raw,expected",
        [("10.456", 10.46), ("10.454", 10.45), ("99.999", 100.0), ("0.01", 0.01), ("5", 5.0)],
    )
    def test_amount_rounded_to_two_decimals(self, auth_client, raw, expected):
        eid = _demo_expense()["id"]
        _post(auth_client, eid, amount=raw)
        assert _row(eid)["amount"] == pytest.approx(expected, abs=1e-9)

    @pytest.mark.parametrize("desc", ["", "    "])
    def test_blank_description_stored_as_null(self, auth_client, desc):
        eid = _demo_expense()["id"]
        _post(auth_client, eid, description=desc)
        assert _row(eid)["description"] is None

    def test_missing_description_field_stored_as_null(self, auth_client):
        eid = _demo_expense()["id"]
        data = _valid()
        del data["description"]
        resp = auth_client.post(_url(eid), data=data)
        assert resp.status_code == 302
        assert _row(eid)["description"] is None

    def test_description_is_stripped(self, auth_client):
        eid = _demo_expense()["id"]
        _post(auth_client, eid, description="  Padded  ")
        assert _row(eid)["description"] == "Padded"

    def test_description_of_exactly_200_chars_accepted(self, auth_client):
        eid = _demo_expense()["id"]
        desc = "x" * 200
        resp = _post(auth_client, eid, description=desc)
        assert resp.status_code == 302
        assert _row(eid)["description"] == desc

    def test_unpadded_date_normalised_to_iso(self, auth_client):
        eid = _demo_expense()["id"]
        resp = _post(auth_client, eid, date="2020-1-5")
        assert resp.status_code == 302
        assert _row(eid)["date"] == "2020-01-05"

    def test_sql_injection_in_description_stored_literally(self, auth_client):
        eid = _demo_expense()["id"]
        payload = "'); DROP TABLE expenses; --"
        resp = _post(auth_client, eid, description=payload)
        assert resp.status_code == 302
        assert _row(eid)["description"] == payload

    def test_edit_without_changes_succeeds(self, auth_client):
        exp = _demo_expense()
        resp = _post(
            auth_client, exp["id"], amount=f"{exp['amount']:.2f}", category=exp["category"],
            date=exp["date"], description=exp["description"],
        )
        assert resp.status_code == 302
        assert _row(exp["id"]) == exp


# --------------------------------------------------- redirect, flash, profile
class TestRedirectAndFlash:
    def test_flash_shown_on_profile_after_redirect(self, auth_client):
        resp = _post(auth_client, _demo_expense()["id"])
        follow = auth_client.get(resp.headers["Location"])
        assert follow.status_code == 200
        assert "Expense updated." in _text(follow)

    def test_follow_redirects_shows_flash(self, auth_client):
        eid = _demo_expense()["id"]
        resp = auth_client.post(_url(eid), data=_valid(), follow_redirects=True)
        assert resp.status_code == 200
        assert "Expense updated." in _text(resp)

    def test_flash_disappears_on_second_profile_load(self, auth_client):
        eid = _demo_expense()["id"]
        auth_client.post(_url(eid), data=_valid(), follow_redirects=True)
        assert "Expense updated." not in _text(auth_client.get("/profile"))

    def test_refreshing_profile_does_not_resubmit(self, auth_client):
        eid = _demo_expense()["id"]
        auth_client.post(_url(eid), data=_valid(amount="321"), follow_redirects=True)
        _exec("UPDATE expenses SET amount = ? WHERE id = ?", (11.0, eid))
        auth_client.get("/profile")
        assert _row(eid)["amount"] == 11.0, "GET /profile must not re-apply the edit"

    def test_validation_error_does_not_flash_success(self, auth_client):
        eid = _demo_expense()["id"]
        _post(auth_client, eid, amount="0")
        assert "Expense updated." not in _text(auth_client.get("/profile"))

    def test_updated_row_visible_on_profile(self, auth_client):
        eid = _demo_expense()["id"]
        resp = auth_client.post(
            _url(eid), data=_valid(amount="1500", description="UniqueEditMarker"),
            follow_redirects=True,
        )
        html = _text(resp)
        assert "UniqueEditMarker" in html
        assert "₹1,500.00" in html


class TestProfileEditLinks:
    def test_every_row_has_edit_link(self, auth_client):
        html = _text(auth_client.get("/profile"))
        ids = [r["id"] for r in _query(
            "SELECT id FROM expenses WHERE user_id = ?", (_user_id(DEMO_EMAIL),))]
        assert ids
        for eid in ids:
            assert f'href="{_url(eid)}"' in html, f"Missing Edit link for expense {eid}"
        assert html.count(">Edit</a>") == len(ids)

    def test_profile_has_actions_column(self, auth_client):
        assert "Actions" in _text(auth_client.get("/profile"))

    def test_empty_state_colspan_is_five(self, other_client):
        html = _text(other_client.get("/profile"))
        assert 'colspan="5"' in html
        assert 'colspan="4"' not in html

    def test_empty_filter_state_has_no_edit_links(self, auth_client):
        html = _text(auth_client.get("/profile?from=1990-01-01&to=1990-01-02"))
        assert ">Edit</a>" not in html
        assert 'colspan="5"' in html

    def test_other_users_profile_has_no_link_to_demo_expense(self, other_client):
        eid = _demo_expense()["id"]
        assert _url(eid) not in _text(other_client.get("/profile"))


# ------------------------------------------------------- stats and categories
class TestStatsUpdate:
    def test_total_rises_and_count_unchanged(self, auth_client):
        exp = _demo_expense("Electricity bill")
        total_before = _user_total()
        count_before = _count()
        new_amount = exp["amount"] + 300
        resp = auth_client.post(
            _url(exp["id"]), data=_valid(amount=f"{new_amount:.2f}", category=exp["category"],
                                         date=exp["date"], description=exp["description"]),
            follow_redirects=True,
        )
        html = _text(resp)
        assert _stat(html, "Total spent") == _fmt(total_before + 300)
        assert _stat(html, "Transactions") == str(count_before)
        assert _count() == count_before

    def test_category_total_rises_by_amount_change(self, auth_client):
        exp = _demo_expense("Electricity bill")
        bills_before = _category_total("Bills")
        auth_client.post(
            _url(exp["id"]),
            data=_valid(amount=f"{exp['amount'] + 300:.2f}", category="Bills",
                        date=exp["date"], description=exp["description"]),
        )
        html = _text(auth_client.get("/profile"))
        assert _breakdown(html)["Bills"] == _fmt(bills_before + 300)

    def test_category_change_moves_amount_between_categories(self, auth_client):
        exp = _demo_expense("Electricity bill")
        assert exp["category"] == "Bills"
        bills_before = _category_total("Bills")
        health_before = _category_total("Health")
        auth_client.post(
            _url(exp["id"]),
            data=_valid(amount=f"{exp['amount']:.2f}", category="Health",
                        date=exp["date"], description=exp["description"]),
        )
        html = _text(auth_client.get("/profile"))
        breakdown = _breakdown(html)
        assert breakdown["Health"] == _fmt(health_before + exp["amount"])
        expected_bills = bills_before - exp["amount"]
        if expected_bills > 0:
            assert breakdown["Bills"] == _fmt(expected_bills)
        else:
            assert "Bills" not in breakdown
        assert 'badge badge-health' in html

    def test_row_badge_changes_with_category(self, auth_client):
        exp = _demo_expense("Electricity bill")
        auth_client.post(
            _url(exp["id"]),
            data=_valid(amount="1200", category="Travel", date=exp["date"],
                        description="BadgeRow"),
        )
        html = _text(auth_client.get("/profile"))
        row = re.search(r"<tr>(?:(?!</tr>).)*BadgeRow(?:(?!</tr>).)*</tr>", html, re.S)
        assert row, "Edited row not found"
        assert "badge-travel" in row.group(0)

    def test_blank_description_shows_category_in_table(self, auth_client):
        exp = _demo_expense("Electricity bill")
        auth_client.post(
            _url(exp["id"]),
            data=_valid(amount="1200", category="Entertainment", date=exp["date"],
                        description=""),
        )
        assert _row(exp["id"])["description"] is None
        html = _text(auth_client.get("/profile"))
        row = re.search(r'<tr>(?:(?!</tr>).)*href="' + _url(exp["id"]) + r'"(?:(?!</tr>).)*</tr>',
                        html, re.S)
        assert row, "Edited row not found"
        assert "<td>Entertainment</td>" in row.group(0), \
            "Table should show category name as the description"
        # Reopening the edit form shows an empty description.
        form = _text(auth_client.get(_url(exp["id"])))
        assert _textarea_or_input_description(form) == ""

    def test_other_users_totals_unaffected_by_edit(self, auth_client):
        dbmod.create_user("Other User", OTHER_EMAIL, OTHER_PASSWORD)
        other_id = _user_id(OTHER_EMAIL)
        _exec(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (other_id, 55.0, "Food", "2025-01-01", "Theirs"),
        )
        before = _user_total(OTHER_EMAIL)
        _post(auth_client, _demo_expense()["id"], amount="999")
        assert _user_total(OTHER_EMAIL) == before


# -------------------------------------------------------------- date filter
class TestDateFilterInterplay:
    def test_edited_date_appears_in_matching_range(self, auth_client):
        eid = _demo_expense()["id"]
        _post(auth_client, eid, date="2020-01-15")
        html = _text(auth_client.get("/profile?from=2020-01-01&to=2020-01-31"))
        assert f'href="{_url(eid)}"' in html

    def test_edited_date_hidden_from_non_matching_range(self, auth_client):
        eid = _demo_expense()["id"]
        _post(auth_client, eid, date="2020-01-15")
        html = _text(auth_client.get("/profile?from=2020-02-01&to=2020-02-28"))
        assert f'href="{_url(eid)}"' not in html

    def test_moving_date_outside_this_month_removes_from_month_filter(self, auth_client):
        eid = _demo_expense()["id"]
        today = date.today()
        month_qs = f"/profile?from={today.replace(day=1).isoformat()}&to={today.isoformat()}"
        # Put it inside this month first, then move it out.
        _post(auth_client, eid, date=today.isoformat())
        assert f'href="{_url(eid)}"' in _text(auth_client.get(month_qs))
        _post(auth_client, eid, date="2020-01-15")
        assert f'href="{_url(eid)}"' not in _text(auth_client.get(month_qs))
        assert f'href="{_url(eid)}"' in _text(
            auth_client.get("/profile?from=2020-01-01&to=2020-01-31"))

    def test_filtered_totals_follow_edited_date(self, auth_client):
        eid = _demo_expense()["id"]
        _post(auth_client, eid, amount="123.45", date="2020-01-15")
        html = _text(auth_client.get("/profile?from=2020-01-01&to=2020-01-31"))
        assert _stat(html, "Total spent") == _fmt(123.45)
        assert _stat(html, "Transactions") == "1"


# --------------------------------------------------------------- validation
class TestValidation:
    @pytest.mark.parametrize("bad", ["0", "-5", "abc", "", "   ", "nan", "inf", "0.00"])
    def test_invalid_amount_returns_400_and_row_unchanged(self, auth_client, bad):
        eid = _demo_expense()["id"]
        before = _row(eid)
        resp = _post(auth_client, eid, amount=bad)
        assert resp.status_code == 400
        assert AMOUNT_MSG in _text(resp)
        assert _row(eid) == before

    def test_missing_amount_field_returns_400(self, auth_client):
        eid = _demo_expense()["id"]
        data = _valid()
        del data["amount"]
        resp = auth_client.post(_url(eid), data=data)
        assert resp.status_code == 400
        assert AMOUNT_MSG in _text(resp)

    @pytest.mark.parametrize("bad", ["Crypto", "", "food", "FOOD"])
    def test_invalid_category_returns_400_and_row_unchanged(self, auth_client, bad):
        eid = _demo_expense()["id"]
        before = _row(eid)
        resp = _post(auth_client, eid, category=bad)
        assert resp.status_code == 400
        assert CATEGORY_MSG in _text(resp)
        assert _row(eid) == before

    @pytest.mark.parametrize(
        "bad", ["2026-13-45", "not-a-date", "", "2026/01/01", "01-01-2026", "2026-02-30"]
    )
    def test_invalid_date_returns_400_and_row_unchanged(self, auth_client, bad):
        eid = _demo_expense()["id"]
        before = _row(eid)
        resp = _post(auth_client, eid, date=bad)
        assert resp.status_code == 400
        assert DATE_MSG in _text(resp)
        assert _row(eid) == before

    def test_description_over_200_chars_returns_400_and_row_unchanged(self, auth_client):
        eid = _demo_expense()["id"]
        before = _row(eid)
        resp = _post(auth_client, eid, description="y" * 201)
        assert resp.status_code == 400
        assert DESC_MSG in _text(resp)
        assert _row(eid) == before

    def test_description_whitespace_padding_not_counted(self, auth_client):
        eid = _demo_expense()["id"]
        resp = _post(auth_client, eid, description="  " + "z" * 200 + "  ")
        assert resp.status_code == 302
        assert _row(eid)["description"] == "z" * 200

    def test_validation_order_amount_first(self, auth_client):
        html = _text(_post(auth_client, _demo_expense()["id"],
                           amount="0", category="Crypto", date="bad"))
        assert AMOUNT_MSG in html
        assert CATEGORY_MSG not in html and DATE_MSG not in html

    def test_validation_order_category_before_date(self, auth_client):
        html = _text(_post(auth_client, _demo_expense()["id"], category="Crypto", date="bad"))
        assert CATEGORY_MSG in html
        assert DATE_MSG not in html

    def test_validation_order_date_before_description(self, auth_client):
        html = _text(_post(auth_client, _demo_expense()["id"],
                           date="bad", description="w" * 201))
        assert DATE_MSG in html
        assert DESC_MSG not in html

    def test_error_message_not_flashed_to_profile(self, auth_client):
        _post(auth_client, _demo_expense()["id"], amount="0")
        assert AMOUNT_MSG not in _text(auth_client.get("/profile"))


# ------------------------------------------------- preserved values on error
class TestPreservedValues:
    def test_amount_error_preserves_other_fields(self, auth_client):
        eid = _demo_expense()["id"]
        resp = _post(auth_client, eid, amount="abc", category="Travel",
                     date="2025-05-05", description="Keep me")
        html = _text(resp)
        assert resp.status_code == 400
        assert _field_value(html, "amount") == "abc"
        assert _field_value(html, "date") == "2025-05-05"
        assert _textarea_or_input_description(html) == "Keep me"
        assert _selected_category(html) == ["Travel"]

    def test_category_error_preserves_values(self, auth_client):
        html = _text(_post(auth_client, _demo_expense()["id"], amount="33", category="Crypto",
                           date="2025-06-06", description="Stay put"))
        assert _field_value(html, "amount") == "33"
        assert _field_value(html, "date") == "2025-06-06"
        assert _textarea_or_input_description(html) == "Stay put"

    def test_date_error_preserves_values(self, auth_client):
        html = _text(_post(auth_client, _demo_expense()["id"], amount="44", category="Bills",
                           date="2026-13-45", description="Date keep"))
        assert _field_value(html, "date") == "2026-13-45"
        assert _textarea_or_input_description(html) == "Date keep"
        assert _selected_category(html) == ["Bills"]

    def test_description_error_preserves_values(self, auth_client):
        long_desc = "L" * 201
        html = _text(_post(auth_client, _demo_expense()["id"], amount="55",
                           category="Health", description=long_desc))
        assert long_desc in html
        assert _selected_category(html) == ["Health"]

    def test_error_form_still_posts_to_edit_url_and_lists_categories(self, auth_client):
        eid = _demo_expense()["id"]
        html = _text(_post(auth_client, eid, amount="0"))
        assert _url(eid) in html
        for cat in CATEGORIES:
            assert f'value="{cat}"' in html
        assert "Save changes" in html

    def test_error_shows_in_auth_error_element(self, auth_client):
        html = _text(_post(auth_client, _demo_expense()["id"], amount="0"))
        assert re.search(r'class="auth-error"[^>]*>\s*' + re.escape(AMOUNT_MSG), html)

    def test_error_form_shows_submitted_not_stored_values(self, auth_client):
        eid = _demo_expense()["id"]
        html = _text(_post(auth_client, eid, amount="0", description="SubmittedDesc"))
        assert "SubmittedDesc" in html
        assert _textarea_or_input_description(html) != "Electricity bill"

    def test_html_in_description_is_escaped_on_error(self, auth_client):
        payload = "<script>alert(1)</script>" + "a" * 201
        html = _text(_post(auth_client, _demo_expense()["id"], description=payload))
        assert "<script>alert(1)</script>" not in html


# ------------------------------------------------------ neighbouring features
class TestRegression:
    def test_add_expense_get_still_works(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200
        html = _text(resp)
        assert "Add an expense" in html
        assert "Save expense" in html
        assert date.today().isoformat() in html

    def test_add_expense_post_still_works(self, auth_client):
        before = _count()
        resp = auth_client.post(
            "/expenses/add",
            data={"amount": "250", "category": "Food", "date": "2025-03-10",
                  "description": "AddStillWorks"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Expense added." in _text(resp)
        assert _count() == before + 1

    def test_add_expense_validation_still_works(self, auth_client):
        before = _count()
        resp = auth_client.post(
            "/expenses/add",
            data={"amount": "0", "category": "Food", "date": "2025-03-10", "description": ""},
        )
        assert resp.status_code == 400
        assert AMOUNT_MSG in _text(resp)
        assert _count() == before

    def test_delete_route_still_placeholder(self, auth_client):
        eid = _demo_expense()["id"]
        before = _snapshot()
        resp = auth_client.get(f"/expenses/{eid}/delete")
        assert resp.status_code == 200
        assert "Step 9" in _text(resp)
        assert _snapshot() == before, "Delete placeholder must not delete anything"

    def test_edit_placeholder_text_is_gone(self, auth_client):
        html = _text(auth_client.get(_url(_demo_expense()["id"])))
        assert "coming in Step 8" not in html

    def test_edit_template_has_no_hardcoded_hex_colours(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "templates", "edit_expense.html")
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", content), \
            "edit_expense.html must not hardcode hex colours"
