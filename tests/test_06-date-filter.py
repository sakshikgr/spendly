"""Tests for spec 06-date-filter: date-range filter on GET /profile.

Written from .claude/specs/06-date-filter.md. All tests run against a temporary
SQLite file; the real expense_tracker.db is never used by the tests themselves.
"""
import os
import sqlite3
import tempfile
from datetime import date, timedelta

import pytest

import database.db as dbmod

# Point the DB layer at a throwaway file BEFORE importing app (app seeds on import).
_IMPORT_DB = os.path.join(tempfile.mkdtemp(prefix="spendly-import-"), "import.db")
dbmod.DB_PATH = _IMPORT_DB

from app import app as flask_app  # noqa: E402

PASSWORD = "password123"

# (date, amount, category, description) for the primary user. Fixed dates keep
# tests deterministic and independent of today.
EXPENSES = [
    ("2026-03-01", 1000.00, "Shopping", "Boundary-start item"),
    ("2026-03-02", 200.00, "Bills", "Second item"),
    ("2026-03-03", 100.00, "Food", "Third item"),
    ("2026-03-04", 50.00, "Travel", "Boundary-end item"),
    ("2026-03-20", 25.00, "Food", "Late item"),
]

INVALID_MSG = "Invalid date — showing all expenses."
ORDER_MSG = "Start date must be before end date."


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db_file)
    flask_app.config.update(TESTING=True, SECRET_KEY="test-secret")
    dbmod.init_db()
    yield flask_app


def _insert_expenses(user_id, rows):
    conn = sqlite3.connect(dbmod.DB_PATH)
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [(user_id, amt, cat, d, desc) for d, amt, cat, desc in rows],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def user_id(app):
    return dbmod.create_user("Test User", "test@example.com", PASSWORD)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client, user_id):
    _insert_expenses(user_id, EXPENSES)
    resp = client.post("/login", data={"email": "test@example.com", "password": PASSWORD})
    assert resp.status_code == 302
    return client


def _get(client, **params):
    return client.get("/profile", query_string=params)


def _text(resp):
    return resp.get_data(as_text=True)


ALL_DESCS = [e[3] for e in EXPENSES]


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_profile_logged_out_redirects_to_login(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_profile_logged_out_with_filter_params_redirects_to_login(self, client):
        resp = client.get("/profile?from=2026-03-01&to=2026-03-04")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# Unfiltered behaviour unchanged                                      #
# ------------------------------------------------------------------ #

class TestNoFilter:
    def test_no_params_lists_all_expenses(self, auth_client):
        resp = _get(auth_client)
        assert resp.status_code == 200
        body = _text(resp)
        for desc in ALL_DESCS:
            assert desc in body, f"{desc} missing in unfiltered view"

    def test_no_params_shows_no_error_or_range_label(self, auth_client):
        body = _text(_get(auth_client))
        assert INVALID_MSG not in body
        assert ORDER_MSG not in body
        assert "Showing from" not in body and "Showing up to" not in body

    def test_empty_params_treated_as_no_bound(self, auth_client):
        resp = _get(auth_client, **{"from": "", "to": ""})
        body = _text(resp)
        assert resp.status_code == 200
        for desc in ALL_DESCS:
            assert desc in body
        assert INVALID_MSG not in body
        assert ORDER_MSG not in body


# ------------------------------------------------------------------ #
# Filtering behaviour                                                 #
# ------------------------------------------------------------------ #

class TestFiltering:
    def test_both_bounds_filter_inclusive(self, auth_client):
        resp = _get(auth_client, **{"from": "2026-03-01", "to": "2026-03-04"})
        body = _text(resp)
        assert resp.status_code == 200
        for desc in ("Boundary-start item", "Second item", "Third item", "Boundary-end item"):
            assert desc in body, f"{desc} should be inside inclusive range"
        assert "Late item" not in body

    def test_from_bound_is_inclusive(self, auth_client):
        body = _text(_get(auth_client, **{"from": "2026-03-04", "to": "2026-03-04"}))
        assert "Boundary-end item" in body
        assert "Third item" not in body
        assert "Late item" not in body

    def test_to_bound_is_inclusive(self, auth_client):
        body = _text(_get(auth_client, **{"from": "2026-03-01", "to": "2026-03-01"}))
        assert "Boundary-start item" in body
        assert "Second item" not in body

    def test_from_only_means_onward(self, auth_client):
        body = _text(_get(auth_client, **{"from": "2026-03-04"}))
        assert "Boundary-end item" in body
        assert "Late item" in body
        assert "Third item" not in body
        assert "Boundary-start item" not in body

    def test_to_only_means_up_to_and_including(self, auth_client):
        body = _text(_get(auth_client, **{"to": "2026-03-02"}))
        assert "Boundary-start item" in body
        assert "Second item" in body
        assert "Third item" not in body
        assert "Late item" not in body

    def test_stats_respect_range(self, auth_client):
        # 1000 + 200 + 100 + 50 = 1350.00, 4 transactions, top category Shopping
        body = _text(_get(auth_client, **{"from": "2026-03-01", "to": "2026-03-04"}))
        assert "1,350.00" in body, "Total should cover only filtered expenses"
        assert "Shopping" in body

    def test_stats_top_category_changes_with_range(self, auth_client):
        # Range 03-02..03-20: Bills 200 is top, Shopping excluded.
        resp = _get(auth_client, **{"from": "2026-03-02", "to": "2026-03-20"})
        body = _text(resp)
        assert "Boundary-start item" not in body
        assert "1,000.00" not in body

    def test_category_breakdown_limited_to_range(self, auth_client):
        body = _text(_get(auth_client, **{"from": "2026-03-02", "to": "2026-03-03"}))
        assert "Bills" in body and "Food" in body
        assert "Second item" in body and "Third item" in body
        assert "Travel" not in body, "Travel expense is outside the range"
        assert "Shopping" not in body, "Shopping expense is outside the range"

    def test_filtered_expenses_sorted_newest_first(self, auth_client):
        body = _text(_get(auth_client, **{"from": "2026-03-01", "to": "2026-03-04"}))
        assert body.index("Boundary-end item") < body.index("Boundary-start item")


# ------------------------------------------------------------------ #
# Empty range                                                         #
# ------------------------------------------------------------------ #

class TestEmptyRange:
    def test_empty_range_message_and_zero_stats(self, auth_client):
        resp = _get(auth_client, **{"from": "2025-01-01", "to": "2025-01-31"})
        body = _text(resp)
        assert resp.status_code == 200
        assert "No expenses in this date range." in body
        assert "No expenses yet." not in body
        assert "0.00" in body
        assert "—" in body, "Top category placeholder expected"
        for desc in ALL_DESCS:
            assert desc not in body

    def test_no_expenses_at_all_unfiltered_says_no_expenses_yet(self, client, user_id):
        client.post("/login", data={"email": "test@example.com", "password": PASSWORD})
        body = _text(_get(client))
        assert "No expenses yet." in body
        assert "No expenses in this date range." not in body


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

class TestValidation:
    @pytest.mark.parametrize("param", ["from", "to"])
    @pytest.mark.parametrize("bad", ["banana", "2026-13-45", "2026/03/01", "01-03-2026", "2026-02-30"])
    def test_invalid_date_returns_200_with_error_and_all_expenses(self, auth_client, param, bad):
        resp = _get(auth_client, **{param: bad})
        body = _text(resp)
        assert resp.status_code == 200
        assert INVALID_MSG in body
        for desc in ALL_DESCS:
            assert desc in body

    def test_invalid_from_with_valid_to_still_applies_to(self, auth_client):
        resp = _get(auth_client, **{"from": "banana", "to": "2026-03-02"})
        body = _text(resp)
        assert resp.status_code == 200
        assert INVALID_MSG in body
        assert "Second item" in body
        assert "Third item" not in body

    def test_from_after_to_ignores_both_and_shows_error(self, auth_client):
        resp = _get(auth_client, **{"from": "2026-12-31", "to": "2026-01-01"})
        body = _text(resp)
        assert resp.status_code == 200
        assert ORDER_MSG in body
        for desc in ALL_DESCS:
            assert desc in body

    def test_from_equal_to_is_valid(self, auth_client):
        resp = _get(auth_client, **{"from": "2026-03-03", "to": "2026-03-03"})
        body = _text(resp)
        assert ORDER_MSG not in body
        assert "Third item" in body
        assert "Second item" not in body

    @pytest.mark.parametrize("payload", [
        "2026-03-01' OR '1'='1",
        "'; DROP TABLE expenses; --",
        "1 OR 1=1",
    ])
    def test_sql_injection_in_params_is_harmless(self, auth_client, user_id, payload):
        resp = _get(auth_client, **{"from": payload})
        assert resp.status_code == 200
        assert INVALID_MSG in _text(resp)
        conn = sqlite3.connect(dbmod.DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        assert count == len(EXPENSES), "Expenses table must be intact"

    def test_very_long_param_does_not_crash(self, auth_client):
        resp = _get(auth_client, **{"to": "9" * 5000})
        assert resp.status_code == 200
        assert INVALID_MSG in _text(resp)


# ------------------------------------------------------------------ #
# Template: form, label, presets                                      #
# ------------------------------------------------------------------ #

class TestTemplate:
    def test_filter_form_present_with_get_method_and_inputs(self, auth_client):
        body = _text(_get(auth_client))
        assert 'method="get"' in body.lower()
        assert 'type="date"' in body
        assert 'name="from"' in body
        assert 'name="to"' in body
        assert "Apply" in body
        assert "Clear" in body

    def test_inputs_prefilled_from_current_filter(self, auth_client):
        body = _text(_get(auth_client, **{"from": "2026-03-01", "to": "2026-03-04"}))
        assert 'value="2026-03-01"' in body
        assert 'value="2026-03-04"' in body

    def test_range_label_shown_when_filter_active(self, auth_client):
        body = _text(_get(auth_client, **{"from": "2026-03-01", "to": "2026-03-04"}))
        assert "Showing" in body
        assert "01 Mar 2026" in body
        assert "04 Mar 2026" in body

    def test_clear_link_points_to_plain_profile(self, auth_client):
        body = _text(_get(auth_client, **{"from": "2026-03-01"}))
        assert 'href="/profile"' in body

    def test_preset_labels_present(self, auth_client):
        body = _text(_get(auth_client))
        for label in ("This month", "Last 30 days", "All time"):
            assert label in body, f"Preset '{label}' missing"

    def test_this_month_preset_link_dates(self, auth_client):
        today = date.today()
        body = _text(_get(auth_client))
        assert f"from={today.replace(day=1).isoformat()}" in body
        assert f"to={today.isoformat()}" in body

    def test_last_30_days_preset_link_dates(self, auth_client):
        today = date.today()
        body = _text(_get(auth_client))
        assert f"from={(today - timedelta(days=29)).isoformat()}" in body

    def test_this_month_preset_applies_range(self, auth_client, user_id):
        today = date.today()
        first = today.replace(day=1)
        _insert_expenses(user_id, [
            (today.isoformat(), 11.00, "Other", "Today preset item"),
            ((first - timedelta(days=1)).isoformat(), 12.00, "Other", "Prev month preset item"),
        ])
        body = _text(_get(auth_client, **{"from": first.isoformat(), "to": today.isoformat()}))
        assert "Today preset item" in body
        assert "Prev month preset item" not in body

    def test_last_30_days_range_is_inclusive_30_days(self, auth_client, user_id):
        today = date.today()
        start = today - timedelta(days=29)
        _insert_expenses(user_id, [
            (start.isoformat(), 13.00, "Other", "Day 30 item"),
            ((start - timedelta(days=1)).isoformat(), 14.00, "Other", "Day 31 item"),
        ])
        body = _text(_get(auth_client, **{"from": start.isoformat(), "to": today.isoformat()}))
        assert "Day 30 item" in body
        assert "Day 31 item" not in body

    def test_error_message_is_html_escaped_safe(self, auth_client):
        body = _text(_get(auth_client, **{"from": "<script>alert(1)</script>"}))
        assert "<script>alert(1)</script>" not in body


# ------------------------------------------------------------------ #
# User isolation                                                      #
# ------------------------------------------------------------------ #

class TestIsolation:
    def test_filtered_view_never_includes_other_users_expenses(self, app, client):
        uid_a = dbmod.create_user("User A", "a@example.com", PASSWORD)
        uid_b = dbmod.create_user("User B", "b@example.com", PASSWORD)
        _insert_expenses(uid_a, [("2026-03-02", 500.00, "Food", "UserA secret lunch")])
        _insert_expenses(uid_b, [("2026-03-02", 77.00, "Travel", "UserB own taxi")])

        client.post("/login", data={"email": "b@example.com", "password": PASSWORD})
        resp = _get(client, **{"from": "2026-03-01", "to": "2026-03-31"})
        body = _text(resp)
        assert resp.status_code == 200
        assert "UserB own taxi" in body
        assert "UserA secret lunch" not in body


# ------------------------------------------------------------------ #
# DB query functions                                                  #
# ------------------------------------------------------------------ #

class TestDbFunctions:
    @pytest.fixture
    def seeded(self, user_id):
        _insert_expenses(user_id, EXPENSES)
        return user_id

    def test_expenses_no_dates_returns_all(self, seeded):
        assert len(dbmod.get_expenses_for_user(seeded)) == len(EXPENSES)

    def test_expenses_date_from_only(self, seeded):
        rows = dbmod.get_expenses_for_user(seeded, date_from="2026-03-04")
        assert sorted(r["date"] for r in rows) == ["2026-03-04", "2026-03-20"]

    def test_expenses_date_to_only(self, seeded):
        rows = dbmod.get_expenses_for_user(seeded, date_to="2026-03-02")
        assert sorted(r["date"] for r in rows) == ["2026-03-01", "2026-03-02"]

    def test_expenses_both_bounds_inclusive(self, seeded):
        rows = dbmod.get_expenses_for_user(seeded, "2026-03-02", "2026-03-03")
        assert sorted(r["date"] for r in rows) == ["2026-03-02", "2026-03-03"]

    def test_stats_no_dates(self, seeded):
        stats = dbmod.get_expense_stats(seeded)
        assert stats["count"] == 5
        assert stats["total"] == pytest.approx(1375.00)
        assert stats["top_category"] == "Shopping"

    def test_stats_with_range(self, seeded):
        stats = dbmod.get_expense_stats(seeded, "2026-03-01", "2026-03-04")
        assert stats["count"] == 4
        assert stats["total"] == pytest.approx(1350.00)
        assert stats["top_category"] == "Shopping"

    def test_stats_empty_range(self, seeded):
        stats = dbmod.get_expense_stats(seeded, "2025-01-01", "2025-01-31")
        assert stats["count"] == 0
        assert stats["total"] == 0
        assert not stats["top_category"]

    def test_category_totals_with_range_ordered_desc(self, seeded):
        rows = dbmod.get_category_totals(seeded, "2026-03-01", "2026-03-04")
        assert [r["category"] for r in rows] == ["Shopping", "Bills", "Food", "Travel"]
        assert sum(r["total"] for r in rows) == pytest.approx(1350.00)

    def test_category_totals_empty_range(self, seeded):
        assert list(dbmod.get_category_totals(seeded, "2025-01-01", "2025-01-31")) == []

    def test_db_functions_scoped_to_user(self, seeded):
        other = dbmod.create_user("Other", "other@example.com", PASSWORD)
        assert list(dbmod.get_expenses_for_user(other, "2026-03-01", "2026-03-31")) == []
        assert dbmod.get_expense_stats(other, "2026-03-01", "2026-03-31")["count"] == 0
        assert list(dbmod.get_category_totals(other, "2026-03-01", "2026-03-31")) == []

    def test_db_functions_treat_malicious_dates_as_data(self, seeded):
        evil = "2026-03-01' OR '1'='1"
        rows = dbmod.get_expenses_for_user(seeded, date_from=evil)
        assert len(rows) == 0, "Injection string must be compared as a literal, not SQL"


# ------------------------------------------------------------------ #
# Category percentages                                                #
# ------------------------------------------------------------------ #

class TestPercentages:
    def test_percentages_sum_to_about_100_for_filtered_range(self, app, user_id):
        from app import build_categories
        _insert_expenses(user_id, EXPENSES)
        cats = build_categories(user_id, "2026-03-01", "2026-03-04")
        assert [c["name"] for c in cats] == ["Shopping", "Bills", "Food", "Travel"]
        assert abs(sum(c["pct"] for c in cats) - 100) <= 2

    def test_empty_range_returns_empty_breakdown(self, app, user_id):
        from app import build_categories
        _insert_expenses(user_id, EXPENSES)
        assert build_categories(user_id, "2025-01-01", "2025-01-31") == []
