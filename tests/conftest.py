import re

import pytest

from app import create_app
from app.db import get_db
from werkzeug.security import generate_password_hash


@pytest.fixture()
def app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db"), "SECRET_KEY": "teste"})
    with app.app_context():
        get_db().execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("maria", generate_password_hash("senha-de-teste", method="pbkdf2:sha256:1000")),  # poucas iterações: teste rápido
        )
    return app


class Client:
    """Cliente de teste que cuida do token CSRF para não repetir isso em cada teste."""

    def __init__(self, flask_client):
        self.c = flask_client

    def token(self) -> str:
        html = self.c.get("/login").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def post(self, url, data=None, csrf=True, **kw):
        data = dict(data or {})
        if csrf:
            data["csrf_token"] = self.token()
        return self.c.post(url, data=data, **kw)

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def login(self, username="maria", password="senha-de-teste"):
        return self.post("/login", {"username": username, "password": password})


@pytest.fixture()
def client(app):
    return Client(app.test_client())


@pytest.fixture()
def logged(client):
    client.login()
    return client


def make_product(client, sku="CAN-001", name="Caneta azul", price="2,50", min_stock="10"):
    return client.post("/products/new", {"sku": sku, "name": name, "price": price, "min_stock": min_stock})
