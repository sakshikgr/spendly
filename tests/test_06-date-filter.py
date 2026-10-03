"""Tests for Step 06 - Date filter on /profile (spec: .claude/specs/06-date-filter.md).

All tests run against a temporary SQLite file; the real expense_tracker.db is
never touched.
"""
import sqlite3
from datetime import date, timedelta

import pytest

import database.db as db


# ------------------------------------------------------------------ #
# Fixtures / helpers                                                  #
# ------------------------------------------------------------------ #

@pytest.fixture(scope="session")
def flask_app(tmp_path_factory):
    """Import app.py once, with DB_PATH pointed at a throwaway file, because
    app.py runs init_db()/seed_db() at import time."""
    mp = pytest.MonkeyPatch()
    mp.setattr(db, "DB_PATH", str(tmp_path_factory.mktemp("import") / "import.db"))
    from app import app as the_app
    mp.undo()
    return the_app


@pytest.fixture
def app(flask_app, tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    flask_app.config["TESTING"] = True
    db.init_db()
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def insert_expense(user_id, amount, category, on, description):
    conn = sqlite3.connect(db.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, on, description),
        )
        conn.commit()
    finally:
        conn.close()


def snapshot_expenses():
    conn = sqlite3.connect(db.DB_PATH)
    try:
        return conn.execute(
            "SELECT id, user_id, amount, category, date, description "
            "FROM expenses ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


@pytest.fixture
def user_a(app):
    db.create_user("Alice Tester", "alice@example.com", "password123")
    uid = db.get_user_by_email("alice@example.com")["id"]
    # Fixed dates, deliberately straddling boundaries.
    insert_expense(uid, 100.00, "Food", "2026-09-30", "ALICE-SEP-END")
    insert_expense(uid, 1000.00, "Shopping", "2026-10-01", "ALICE-OCT-01")
    insert_expense(uid, 500.00, "Bills", "2026-10-02", "ALICE-OCT-02")
    insert_expense(uid, 200.00, "Food", "2026-10-04", "ALICE-OCT-04")
    insert_expense(uid, 300.00, "Travel", "2026-10-10", "ALICE-OCT-10")
    insert_expense(uid, 50.00, "Food", "2026-11-01", "ALICE-NOV-01")
    return uid


@pytest.fixture
def user_b(app):
    db.create_user("Bob Other", "bob@example.com", "password123")
    uid = db.get_user_by_email("bob@example.com")["id"]
    insert_expense(uid, 9999.00, "Shopping", "2026-10-02", "BOB-SECRET-OCT-02")
    insert_expense(uid, 7777.00, "Health", "2026-10-03", "BOB-SECRET-OCT-03")
    return uid


def login(client, email, password="password123"):
    resp = client.post("/login", data={"email": email, "password": password})
    assert resp.status_code == 302, "login should redirect on success"


@pytest.fixture
def alice(client, user_a):
    login(client, "alice@example.com")
    return client


ALL_ALICE = [
    "ALICE-SEP-END", "ALICE-OCT-01", "ALICE-OCT-02",
    "ALICE-OCT-04", "ALICE-OCT-10", "ALICE-NOV-01",
]


def get_profile(client, query=""):
    return client.get("/profile" + query)


def assert_shown(html, labels):
    for label in labels:
        assert label in html, f"Expected {label} to be listed"


def assert_hidden(html, labels):
    for label in labels:
        assert label not in html, f"Expected {label} NOT to be listed"


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    @pytest.mark.parametrize("query", [
        "",
        "?from=2026-10-01&to=2026-10-31",
        "?from=banana",
        "?from=2026-12-31&to=2026-01-01",
    ])
    def test_profile_logged_out_redirects_to_login(self, client, user_a, query):
        resp = get_profile(client, query)
        assert resp.status_code == 302, "logged-out access must redirect"
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# No filter: unchanged behaviour                                      #
# ------------------------------------------------------------------ #

class TestNoFilter:
    def test_no_params_lists_all_expenses_and_total(self, alice):
        resp = get_profile(alice)
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert_shown(html, ALL_ALICE)
        assert "₹2,150.00" in html, "total of all expenses expected"

    def test_empty_params_treated_as_no_bound(self, alice):
        resp = get_profile(alice, "?from=&to=")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert_shown(html, ALL_ALICE)
        assert "Invalid date" not in html, "empty value is not an error"

    def test_user_with_no_expenses_shows_original_empty_text(self, client, app):
        db.create_user("Empty Eve", "eve@example.com", "password123")
        login(client, "eve@example.com")
        html = get_profile(client).get_data(as_text=True)
        assert "No expenses yet." in html
        assert "No expenses in this date range." not in html


# ------------------------------------------------------------------ #
# Filter form and presets rendering                                   #
# ------------------------------------------------------------------ #

class TestFilterUI:
    def test_form_has_get_method_date_inputs_and_apply(self, alice):
        html = get_profile(alice).get_data(as_text=True)
        assert 'method="get"' in html.lower()
        assert 'type="date"' in html
        assert 'name="from"' in html
        assert 'name="to"' in html
        assert "Apply" in html
        assert "Clear" in html

    def test_preset_labels_present(self, alice):
        html = get_profile(alice).get_data(as_text=True)
        for label in ("This month", "Last 30 days", "All time"):
            assert label in html, f"missing preset {label}"

    def test_inputs_prefilled_from_current_filter(self, alice):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-04").get_data(as_text=True)
        assert 'value="2026-10-01"' in html, "from input should be pre-filled"
        assert 'value="2026-10-04"' in html, "to input should be pre-filled"

    def test_range_label_shown_when_filter_active(self, alice):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-04").get_data(as_text=True)
        assert "01 Oct 2026" in html
        assert "04 Oct 2026" in html
        assert "Showing" in html

    def test_range_label_absent_without_filter(self, alice):
        html = get_profile(alice).get_data(as_text=True)
        assert "Showing 30 Sep 2026" not in html, "no range label without a filter"
        assert "Showing 01 Oct 2026" not in html, "no range label without a filter"


# ------------------------------------------------------------------ #
# Filtering behaviour                                                 #
# ------------------------------------------------------------------ #

class TestFiltering:
    def test_both_bounds_inclusive(self, alice):
        resp = get_profile(alice, "?from=2026-10-01&to=2026-10-04")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert_shown(html, ["ALICE-OCT-01", "ALICE-OCT-02", "ALICE-OCT-04"])
        assert_hidden(html, ["ALICE-SEP-END", "ALICE-OCT-10", "ALICE-NOV-01"])

    def test_stats_total_matches_filtered_range(self, alice):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-04").get_data(as_text=True)
        assert "₹1,700.00" in html, "1000 + 500 + 200 expected"
        assert "₹2,150.00" not in html, "unfiltered total must not appear"

    def test_top_category_follows_filter(self, alice):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-04").get_data(as_text=True)
        assert "Shopping" in html

    def test_from_only_means_onward(self, alice):
        html = get_profile(alice, "?from=2026-10-04").get_data(as_text=True)
        assert_shown(html, ["ALICE-OCT-04", "ALICE-OCT-10", "ALICE-NOV-01"])
        assert_hidden(html, ["ALICE-SEP-END", "ALICE-OCT-01", "ALICE-OCT-02"])

    def test_to_only_means_up_to_and_including(self, alice):
        html = get_profile(alice, "?to=2026-10-02").get_data(as_text=True)
        assert_shown(html, ["ALICE-SEP-END", "ALICE-OCT-01", "ALICE-OCT-02"])
        assert_hidden(html, ["ALICE-OCT-04", "ALICE-OCT-10", "ALICE-NOV-01"])

    def test_single_day_range_from_equals_to(self, alice):
        resp = get_profile(alice, "?from=2026-10-02&to=2026-10-02")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Start date must be before end date." not in html
        assert_shown(html, ["ALICE-OCT-02"])
        assert_hidden(html, ["ALICE-OCT-01", "ALICE-OCT-04"])

    def test_from_boundary_expense_included(self, alice):
        html = get_profile(alice, "?from=2026-10-10").get_data(as_text=True)
        assert "ALICE-OCT-10" in html

    def test_to_boundary_expense_included(self, alice):
        html = get_profile(alice, "?to=2026-09-30").get_data(as_text=True)
        assert "ALICE-SEP-END" in html
        assert_hidden(html, ["ALICE-OCT-01"])

    def test_category_breakdown_limited_to_range(self, alice):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-02").get_data(as_text=True)
        assert "Shopping" in html and "Bills" in html
        assert "Travel" not in html, "Travel expense is outside the range"

    def test_category_breakdown_order_by_amount_desc(self, alice):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-04").get_data(as_text=True)
        # Shopping 1000, Bills 500, Food 200 in the range.
        assert html.index("Shopping") < html.index("Bills") < html.rindex("Food")

    def test_empty_range_shows_zero_state(self, alice):
        resp = get_profile(alice, "?from=2030-01-01&to=2030-01-31")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "₹0.00" in html
        assert "—" in html, "top category placeholder expected"
        assert "No expenses in this date range." in html
        assert "No expenses yet." not in html
        assert_hidden(html, ALL_ALICE)

    def test_filtered_page_without_error_has_no_error_text(self, alice):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-04").get_data(as_text=True)
        assert "Invalid date" not in html
        assert "Start date must be before end date." not in html


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

class TestValidation:
    @pytest.mark.parametrize("query", [
        "?from=banana",
        "?to=banana",
        "?from=2026-13-45",
        "?from=2026-02-30",
        "?from=10/01/2026",
        "?from=2026-10-01T00:00:00",
        "?from=%27%20OR%201%3D1%20--",
        "?from=2026-10-01%27%3B%20DROP%20TABLE%20expenses%3B--",
    ])
    def test_invalid_single_bound_returns_200_with_error_and_all_rows(self, alice, query):
        resp = get_profile(alice, query)
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Invalid date — showing all expenses." in html
        assert_shown(html, ALL_ALICE)

    def test_invalid_from_with_valid_to_drops_only_invalid_bound(self, alice):
        resp = get_profile(alice, "?from=banana&to=2026-10-02")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Invalid date — showing all expenses." in html
        assert_shown(html, ["ALICE-SEP-END", "ALICE-OCT-01", "ALICE-OCT-02"])
        assert_hidden(html, ["ALICE-OCT-04", "ALICE-NOV-01"])

    def test_invalid_to_with_valid_from_drops_only_invalid_bound(self, alice):
        resp = get_profile(alice, "?from=2026-10-04&to=banana")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Invalid date — showing all expenses." in html
        assert_shown(html, ["ALICE-OCT-04", "ALICE-NOV-01"])
        assert_hidden(html, ["ALICE-SEP-END", "ALICE-OCT-01"])

    def test_from_after_to_ignores_both_with_error(self, alice):
        resp = get_profile(alice, "?from=2026-12-31&to=2026-01-01")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Start date must be before end date." in html
        assert_shown(html, ALL_ALICE)
        assert "₹2,150.00" in html

    def test_sql_injection_attempt_does_not_modify_data(self, alice):
        before = snapshot_expenses()
        get_profile(alice, "?from=2026-10-01%27%3B%20DROP%20TABLE%20expenses%3B--")
        get_profile(alice, "?to=%27%20OR%20%271%27%3D%271")
        assert snapshot_expenses() == before, "expenses must be unchanged"


# ------------------------------------------------------------------ #
# Presets                                                             #
# ------------------------------------------------------------------ #

class TestPresets:
    def test_this_month_link_uses_first_of_month_to_today(self, alice):
        today = date.today()
        html = get_profile(alice).get_data(as_text=True)
        assert f"from={today.replace(day=1).isoformat()}" in html
        assert f"to={today.isoformat()}" in html

    def test_last_30_days_link_is_today_minus_29_to_today(self, alice):
        today = date.today()
        html = get_profile(alice).get_data(as_text=True)
        assert f"from={(today - timedelta(days=29)).isoformat()}" in html
        assert f"to={today.isoformat()}" in html

    def test_this_month_range_filters_correctly(self, alice, user_a):
        today = date.today()
        first = today.replace(day=1)
        insert_expense(user_a, 11.0, "Food", first.isoformat(), "PRESET-MONTH-FIRST")
        insert_expense(user_a, 12.0, "Food", today.isoformat(), "PRESET-MONTH-TODAY")
        insert_expense(user_a, 13.0, "Food",
                       (first - timedelta(days=1)).isoformat(), "PRESET-BEFORE-MONTH")
        html = get_profile(
            alice, f"?from={first.isoformat()}&to={today.isoformat()}"
        ).get_data(as_text=True)
        assert_shown(html, ["PRESET-MONTH-FIRST", "PRESET-MONTH-TODAY"])
        assert_hidden(html, ["PRESET-BEFORE-MONTH"])

    def test_last_30_days_range_is_inclusive_of_30_days(self, alice, user_a):
        today = date.today()
        start = today - timedelta(days=29)
        insert_expense(user_a, 11.0, "Food", start.isoformat(), "L30-EDGE-IN")
        insert_expense(user_a, 12.0, "Food",
                       (start - timedelta(days=1)).isoformat(), "L30-EDGE-OUT")
        insert_expense(user_a, 13.0, "Food", today.isoformat(), "L30-TODAY")
        html = get_profile(
            alice, f"?from={start.isoformat()}&to={today.isoformat()}"
        ).get_data(as_text=True)
        assert_shown(html, ["L30-EDGE-IN", "L30-TODAY"])
        assert_hidden(html, ["L30-EDGE-OUT"])

    def test_all_time_and_clear_link_to_plain_profile(self, alice):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-04").get_data(as_text=True)
        assert 'href="/profile"' in html, "All time / Clear must link to bare /profile"


# ------------------------------------------------------------------ #
# User isolation                                                      #
# ------------------------------------------------------------------ #

class TestUserIsolation:
    @pytest.mark.parametrize("query", [
        "",
        "?from=2026-10-01&to=2026-10-31",
        "?from=2026-10-02",
        "?to=2026-10-03",
        "?from=2026-10-03&to=2026-10-03",
    ])
    def test_other_users_rows_never_appear(self, alice, user_b, query):
        html = get_profile(alice, query).get_data(as_text=True)
        assert "BOB-SECRET" not in html
        assert "₹9,999.00" not in html
        assert "₹7,777.00" not in html

    def test_filtered_totals_exclude_other_users(self, alice, user_b):
        html = get_profile(alice, "?from=2026-10-01&to=2026-10-04").get_data(as_text=True)
        assert "₹1,700.00" in html, "Alice's total must not include Bob's expenses"

    def test_range_where_only_other_user_has_expenses_is_empty_for_alice(self, alice, user_b):
        html = get_profile(alice, "?from=2026-10-03&to=2026-10-03").get_data(as_text=True)
        assert "No expenses in this date range." in html
        assert "₹0.00" in html

    def test_other_user_sees_only_own_filtered_rows(self, client, user_a, user_b):
        login(client, "bob@example.com")
        html = get_profile(client, "?from=2026-10-01&to=2026-10-02").get_data(as_text=True)
        assert "BOB-SECRET-OCT-02" in html
        assert_hidden(html, ["BOB-SECRET-OCT-03"] + ALL_ALICE)


# ------------------------------------------------------------------ #
# No side effects                                                     #
# ------------------------------------------------------------------ #

class TestNoSideEffects:
    @pytest.mark.parametrize("query", [
        "",
        "?from=2026-10-01&to=2026-10-04",
        "?from=banana",
        "?from=2026-12-31&to=2026-01-01",
        "?from=2030-01-01&to=2030-01-31",
    ])
    def test_filtering_never_modifies_expenses(self, alice, user_b, query):
        before = snapshot_expenses()
        resp = get_profile(alice, query)
        assert resp.status_code == 200
        assert snapshot_expenses() == before, "GET /profile must be read-only"


# ------------------------------------------------------------------ #
# DB query functions (optional date_from / date_to)                   #
# ------------------------------------------------------------------ #

class TestDbFunctions:
    def test_expenses_no_dates_returns_all_for_user_only(self, user_a, user_b):
        rows = db.get_expenses_for_user(user_a)
        assert len(rows) == 6
        assert {r["description"] for r in rows} == set(ALL_ALICE)

    def test_expenses_inclusive_both_bounds(self, user_a):
        rows = db.get_expenses_for_user(user_a, "2026-10-01", "2026-10-04")
        assert {r["description"] for r in rows} == {
            "ALICE-OCT-01", "ALICE-OCT-02", "ALICE-OCT-04"}

    def test_expenses_keyword_arguments(self, user_a):
        rows = db.get_expenses_for_user(user_a, date_from="2026-10-10", date_to="2026-10-10")
        assert [r["description"] for r in rows] == ["ALICE-OCT-10"]

    def test_expenses_from_only(self, user_a):
        rows = db.get_expenses_for_user(user_a, date_from="2026-10-10")
        assert {r["description"] for r in rows} == {"ALICE-OCT-10", "ALICE-NOV-01"}

    def test_expenses_to_only(self, user_a):
        rows = db.get_expenses_for_user(user_a, date_to="2026-09-30")
        assert [r["description"] for r in rows] == ["ALICE-SEP-END"]

    def test_expenses_scoped_to_user_with_range(self, user_a, user_b):
        rows = db.get_expenses_for_user(user_a, "2026-10-02", "2026-10-03")
        descs = {r["description"] for r in rows}
        assert descs == {"ALICE-OCT-02"}

    def test_stats_no_dates_unchanged(self, user_a):
        stats = db.get_expense_stats(user_a)
        assert stats["total"] == pytest.approx(2150.00)
        assert stats["count"] == 6

    def test_stats_with_range(self, user_a):
        stats = db.get_expense_stats(user_a, "2026-10-01", "2026-10-04")
        assert stats["total"] == pytest.approx(1700.00)
        assert stats["count"] == 3
        assert stats["top_category"] == "Shopping"

    def test_stats_empty_range(self, user_a):
        stats = db.get_expense_stats(user_a, "2030-01-01", "2030-12-31")
        assert not stats["total"]
        assert stats["count"] == 0
        assert not stats["top_category"]

    def test_stats_exclude_other_users(self, user_a, user_b):
        stats = db.get_expense_stats(user_a, "2026-10-02", "2026-10-03")
        assert stats["total"] == pytest.approx(500.00)
        assert stats["count"] == 1

    def test_category_totals_with_range(self, user_a):
        rows = db.get_category_totals(user_a, "2026-10-01", "2026-10-04")
        totals = {r["category"]: r["total"] for r in rows}
        assert totals == {"Shopping": pytest.approx(1000.0),
                          "Bills": pytest.approx(500.0),
                          "Food": pytest.approx(200.0)}

    def test_category_totals_no_dates_unchanged(self, user_a):
        rows = db.get_category_totals(user_a)
        totals = {r["category"]: r["total"] for r in rows}
        assert totals["Food"] == pytest.approx(350.0)
        assert set(totals) == {"Food", "Shopping", "Bills", "Travel"}

    def test_category_totals_empty_range_returns_empty(self, user_a):
        assert list(db.get_category_totals(user_a, "2030-01-01", "2030-12-31")) == []

    def test_malicious_date_value_is_parameterised(self, user_a):
        before = snapshot_expenses()
        payload = "2026-10-01'; DROP TABLE expenses; --"
        db.get_expenses_for_user(user_a, payload, None)
        db.get_expense_stats(user_a, None, payload)
        db.get_category_totals(user_a, payload, payload)
        assert snapshot_expenses() == before, "table must survive injection payload"
