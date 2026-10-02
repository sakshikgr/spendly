import os
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_user_by_email, init_db, seed_db

app = Flask(__name__)
# Fallback key is for local development only — set SECRET_KEY in production.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

with app.app_context():
    init_db()
    seed_db()


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

    # Hardcoded sample data — replaced with real queries in Step 5.
    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "January 2026",
    }
    expenses = [
        {"date": "08 Oct 2026", "description": "Mobile recharge", "category": "Bills", "amount": 899.00},
        {"date": "07 Oct 2026", "description": "Movie tickets", "category": "Entertainment", "amount": 499.00},
        {"date": "06 Oct 2026", "description": "Dinner with friends", "category": "Food", "amount": 320.00},
        {"date": "05 Oct 2026", "description": "Pharmacy", "category": "Health", "amount": 650.00},
        {"date": "04 Oct 2026", "description": "Running shoes", "category": "Shopping", "amount": 2499.00},
        {"date": "03 Oct 2026", "description": "Metro card recharge", "category": "Travel", "amount": 180.00},
        {"date": "02 Oct 2026", "description": "Groceries", "category": "Food", "amount": 450.50},
        {"date": "01 Oct 2026", "description": "Electricity bill", "category": "Bills", "amount": 1200.00},
    ]
    stats = {"total_spent": 6697.50, "transactions": 8, "top_category": "Shopping"}
    categories = [
        {"name": "Shopping", "amount": 2499.00, "pct": 37},
        {"name": "Bills", "amount": 2099.00, "pct": 31},
        {"name": "Food", "amount": 770.50, "pct": 12},
        {"name": "Health", "amount": 650.00, "pct": 10},
        {"name": "Entertainment", "amount": 499.00, "pct": 7},
        {"name": "Travel", "amount": 180.00, "pct": 3},
    ]
    return render_template(
        "profile.html", user=user, stats=stats, expenses=expenses, categories=categories
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
