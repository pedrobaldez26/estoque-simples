import os

import click
from flask import Flask

from . import auth, inventory
from .db import close_db, get_db, init_db
from .money import format_brl
from .security import check_csrf, csrf_token, hash_password


def create_app(config=None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-troque-em-producao"),
        DATABASE=os.environ.get("DATABASE", "estoque.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if config:
        app.config.update(config)

    if not app.debug and not app.testing and app.config["SECRET_KEY"].startswith("dev-only"):
        app.logger.warning("SECRET_KEY de desenvolvimento em uso. Defina SECRET_KEY antes de publicar.")

    app.teardown_appcontext(close_db)
    app.before_request(check_csrf)
    app.jinja_env.filters["brl"] = format_brl
    app.jinja_env.globals["csrf_token"] = csrf_token

    app.register_blueprint(auth.bp)
    app.register_blueprint(inventory.bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy", "default-src 'self'")
        return resp

    with app.app_context():
        init_db()

    @app.cli.command("create-user")
    @click.argument("username")
    @click.password_option()
    def create_user(username: str, password: str):
        """Cria um usuário: flask --app app create-user maria"""
        get_db().execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password)),
        )
        click.echo(f"Usuário {username} criado.")

    return app
