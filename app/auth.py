from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .db import get_db
from .security import is_safe_next

bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped


@bp.before_app_request
def load_user():
    user_id = session.get("user_id")
    g.user = (
        get_db().execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if user_id
        else None
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Usuário ou senha incorretos.", "error")
        else:
            session.clear()  # sessão nova após o login, contra fixation
            session["user_id"] = user["id"]
            target = request.args.get("next", "")
            return redirect(target if is_safe_next(target) else url_for("inventory.products"))

    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
