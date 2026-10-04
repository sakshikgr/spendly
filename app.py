import math
import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    CATEGORIES,
    create_expense,
    create_user,
    delete_expense as db_delete_expense,
    get_category_totals,
    get_expense_for_user,
    get_expense_stats,
    get_expenses_for_user,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
    update_expense,
)

app = Flask(__name__)
# Fallback key is for local development only — set SECRET_KEY in production.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Profile helpers                                                     #
# ------------------------------------------------------------------ #

def build_expenses(user_id, date_from=None, date_to=None):
    return [
        {
            "id": row["id"],
            "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": row["description"] or row["category"],
            "category": row["category"],
            "amount": row["amount"],
        }
        for row in get_expenses_for_user(user_id, date_from, date_to)
    ]


def build_stats(user_id, date_from=None, date_to=None):
    stats = get_expense_stats(user_id, date_from, date_to)
    return {
        "total_spent": stats["total"],
        "transactions": stats["count"],
        "top_category": stats["top_category"] or "—",
    }


def build_categories(user_id, date_from=None, date_to=None):
    rows = get_category_totals(user_id, date_from, date_to)
    grand_total = sum(row["total"] for row in rows)
    if not grand_total:
        return []
    return [
        {
            "name": row["category"],
            "amount": row["total"],
            "pct": round(row["total"] / grand_total * 100),
        }
        for row in rows
    ]


# ------------------------------------------------------------------ #
# Date filter helpers                                                 #
# ------------------------------------------------------------------ #

def parse_date_filter(args):
    """Return (date_from, date_to, error) as ISO strings or None."""
    bounds, error = [], None
    for key in ("from", "to"):
        value = args.get(key, "").strip()
        if not value:
            bounds.append(None)
            continue
        try:
            bounds.append(datetime.strptime(value, "%Y-%m-%d").date())
        except ValueError:
            # Drop only the invalid bound; a valid one still filters.
            bounds.append(None)
            error = "Invalid date — showing all expenses."

    date_from, date_to = bounds
    if date_from and date_to and date_from > date_to:
        return None, None, "Start date must be before end date."
    return (
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
        error,
    )


def build_presets(today):
    return [
        {"key": "month", "label": "This month",
         "from": today.replace(day=1).isoformat(), "to": today.isoformat()},
        {"key": "30d", "label": "Last 30 days",
         "from": (today - timedelta(days=29)).isoformat(), "to": today.isoformat()},
        {"key": "all", "label": "All time", "from": None, "to": None},
    ]


def format_range_label(date_from, date_to):
    def fmt(value):
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")

    if date_from and date_to:
        return f"Showing {fmt(date_from)} – {fmt(date_to)}"
    if date_from:
        return f"Showing from {fmt(date_from)}"
    if date_to:
        return f"Showing up to {fmt(date_to)}"
    return None


# ------------------------------------------------------------------ #
# Expense form helpers                                                #
# ------------------------------------------------------------------ #

EXPENSE_FIELDS = ("amount", "category", "date", "description")


def validate_expense_form(form):
    """Return (values, None) ready to store, or (None, error message)."""
    try:
        amount = round(float(form["amount"]), 2)
    except ValueError:
        amount = None
    # Rounding first rejects values like 0.001 that would store as 0.
    if amount is None or not math.isfinite(amount) or amount <= 0:
        return None, "Please enter an amount greater than 0."

    if form["category"] not in CATEGORIES:
        return None, "Please choose a valid category."

    try:
        # Store the normalised ISO form: strptime also accepts "2026-1-5",
        # which would break text comparison in the date filter.
        expense_date = datetime.strptime(form["date"], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None, "Please enter a valid date."

    if len(form["description"]) > 200:
        return None, "Description must be 200 characters or fewer."

    return {
        "amount": amount,
        "category": form["category"],
        "date": expense_date,
        "description": form["description"],
    }, None


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    def form_error(message, status):
        return render_template("register.html", error=message, name=name, email=email), status

    local, _, domain = email.partition("@")
    if not name:
        return form_error("Please enter your name.", 400)
    if not local or "." not in domain:
        return form_error("Please enter a valid email address.", 400)
    if len(password) < 8:
        return form_error("Password must be at least 8 characters.", 400)

    duplicate = "An account with that email already exists."
    if get_user_by_email(email):
        return form_error(duplicate, 409)
    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        return form_error(duplicate, 409)

    flash("Account created — please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    def form_error(message, status):
        return render_template("login.html", error=message, email=email), status

    if not email or not password:
        return form_error("Please enter your email and password.", 400)

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return form_error("Invalid email or password.", 401)

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You've been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    row = get_user_by_id(session["user_id"])
    if row is None:
        session.clear()
        return redirect(url_for("login"))

    user_id = row["id"]
    user = {
        "name": row["name"],
        "email": row["email"],
        "initials": "".join(word[0] for word in row["name"].split()[:2]).upper(),
        "member_since": datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").strftime("%B %Y"),
    }
    date_from, date_to, error = parse_date_filter(request.args)
    presets = build_presets(date.today())
    active_preset = next(
        (p["key"] for p in presets if (p["from"], p["to"]) == (date_from, date_to)),
        None,
    )
    date_filter = {
        "date_from": date_from,
        "date_to": date_to,
        "label": format_range_label(date_from, date_to),
        "active_preset": active_preset,
        "error": error,
        "active": bool(date_from or date_to),
    }
    return render_template(
        "profile.html",
        user=user,
        stats=build_stats(user_id, date_from, date_to),
        expenses=build_expenses(user_id, date_from, date_to),
        categories=build_categories(user_id, date_from, date_to),
        date_filter=date_filter,
        presets=presets,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    if get_user_by_id(session["user_id"]) is None:
        session.clear()
        return redirect(url_for("login"))
    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            form={"date": date.today().isoformat()},
        )

    form = {key: request.form.get(key, "").strip() for key in EXPENSE_FIELDS}
    values, error = validate_expense_form(form)
    if error:
        return render_template(
            "add_expense.html", error=error, categories=CATEGORIES, form=form
        ), 400

    create_expense(session["user_id"], **values)
    flash("Expense added.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    if get_user_by_id(session["user_id"]) is None:
        session.clear()
        return redirect(url_for("login"))

    # Filtering by user_id means another user's expense is a plain 404.
    expense = get_expense_for_user(id, session["user_id"])
    if expense is None:
        abort(404)

    if request.method == "GET":
        form = {
            "amount": f"{expense['amount']:.2f}",
            "category": expense["category"],
            "date": expense["date"],
            "description": expense["description"] or "",
        }
        return render_template(
            "edit_expense.html", categories=CATEGORIES, form=form, expense_id=id
        )

    form = {key: request.form.get(key, "").strip() for key in EXPENSE_FIELDS}
    values, error = validate_expense_form(form)
    if error:
        return render_template(
            "edit_expense.html",
            error=error,
            categories=CATEGORIES,
            form=form,
            expense_id=id,
        ), 400

    update_expense(id, session["user_id"], **values)
    flash("Expense updated.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["GET", "POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    if get_user_by_id(session["user_id"]) is None:
        session.clear()
        return redirect(url_for("login"))

    # Filtering by user_id means another user's expense is a plain 404.
    expense = get_expense_for_user(id, session["user_id"])
    if expense is None:
        abort(404)

    if request.method == "GET":
        return render_template("delete_expense.html", expense={
            "id": expense["id"],
            "date": datetime.strptime(expense["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": expense["description"] or expense["category"],
            "category": expense["category"],
            "amount": expense["amount"],
        })

    db_delete_expense(id, session["user_id"])
    flash("Expense deleted.", "success")
    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
