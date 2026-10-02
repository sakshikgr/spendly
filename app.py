import os
import sqlite3

from flask import Flask, flash, redirect, render_template, request, url_for

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


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
