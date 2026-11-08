import csv
import io
import sqlite3

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db, transaction
from .money import parse_brl

bp = Blueprint("inventory", __name__)

STOCK_SQL = """
    SELECT p.id, p.sku, p.name, p.price_cents, p.min_stock,
           COALESCE(SUM(CASE m.kind WHEN 'in' THEN m.quantity ELSE -m.quantity END), 0) AS stock
    FROM products p
    LEFT JOIN movements m ON m.product_id = p.id
    WHERE p.active = 1 {where}
    GROUP BY p.id
    {having}
    ORDER BY p.name COLLATE NOCASE
"""


def like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_products(db: sqlite3.Connection, term: str = "", low_only: bool = False):
    where, params = "", []
    if term:
        where = "AND (p.name LIKE ? ESCAPE '\\' OR p.sku LIKE ? ESCAPE '\\')"
        params = [like_pattern(term)] * 2
    having = "HAVING stock <= p.min_stock" if low_only else ""
    return db.execute(STOCK_SQL.format(where=where, having=having), params).fetchall()


def get_product(db: sqlite3.Connection, product_id: int):
    row = db.execute(
        STOCK_SQL.format(where="AND p.id = ?", having=""), (product_id,)
    ).fetchone()
    if row is None:
        abort(404)
    return row


@bp.route("/")
@login_required
def products():
    term = request.args.get("q", "").strip()
    return render_template("products.html", products=list_products(get_db(), term), q=term)


@bp.route("/products/new", methods=["GET", "POST"])
@login_required
def new_product():
    form = {"sku": "", "name": "", "price": "", "min_stock": "0"}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        price = parse_brl(form["price"])
        errors = []
        if not form["sku"] or len(form["sku"]) > 40:
            errors.append("Informe um SKU de até 40 caracteres.")
        if not form["name"] or len(form["name"]) > 120:
            errors.append("Informe um nome de até 120 caracteres.")
        if price is None:
            errors.append("Preço inválido. Exemplo: 12,50")
        if not form["min_stock"].isdigit():
            errors.append("Estoque mínimo deve ser um número inteiro.")

        if not errors:
            try:
                cur = get_db().execute(
                    "INSERT INTO products (sku, name, price_cents, min_stock) VALUES (?, ?, ?, ?)",
                    (form["sku"], form["name"], price, int(form["min_stock"])),
                )
            except sqlite3.IntegrityError:
                errors.append("Já existe um produto com esse SKU.")
            else:
                flash("Produto cadastrado.", "ok")
                return redirect(url_for("inventory.product_detail", product_id=cur.lastrowid))

        for e in errors:
            flash(e, "error")

    return render_template("product_form.html", form=form)


@bp.route("/products/<int:product_id>")
@login_required
def product_detail(product_id: int):
    db = get_db()
    product = get_product(db, product_id)
    history = db.execute(
        """SELECT m.*, u.username FROM movements m
           LEFT JOIN users u ON u.id = m.user_id
           WHERE m.product_id = ? ORDER BY m.id DESC LIMIT 50""",
        (product_id,),
    ).fetchall()
    return render_template("product_detail.html", product=product, history=history)


@bp.post("/products/<int:product_id>/movements")
@login_required
def add_movement(product_id: int):
    db = get_db()
    get_product(db, product_id)  # 404 se não existir

    kind = request.form.get("kind", "")
    quantity_raw = request.form.get("quantity", "").strip()
    note = request.form.get("note", "").strip()[:200] or None

    if kind not in ("in", "out") or not quantity_raw.isdigit() or int(quantity_raw) < 1:
        flash("Informe o tipo e uma quantidade inteira maior que zero.", "error")
        return redirect(url_for("inventory.product_detail", product_id=product_id))
    quantity = int(quantity_raw)

    with transaction(db):
        # relê o saldo já dentro da transação travada
        stock = get_product(db, product_id)["stock"]
        if kind == "out" and quantity > stock:
            flash(f"Saída maior que o estoque disponível ({stock}).", "error")
        else:
            db.execute(
                "INSERT INTO movements (product_id, kind, quantity, note, user_id) VALUES (?, ?, ?, ?, ?)",
                (product_id, kind, quantity, note, g.user["id"]),
            )
            flash("Movimentação registrada.", "ok")

    return redirect(url_for("inventory.product_detail", product_id=product_id))


@bp.route("/reports/low-stock")
@login_required
def low_stock():
    return render_template("low_stock.html", products=list_products(get_db(), low_only=True))


def csv_safe(value) -> str:
    """Planilhas executam fórmulas em células que começam com = + - @.
    Um nome de produto malicioso vira fórmula ao abrir o CSV no Excel; o apóstrofo evita isso."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.route("/export.csv")
@login_required
def export_csv():
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["sku", "nome", "preco", "estoque", "estoque_minimo"])
    for p in list_products(get_db()):
        writer.writerow(
            [csv_safe(p["sku"]), csv_safe(p["name"]), f"{p['price_cents'] / 100:.2f}".replace(".", ","), p["stock"], p["min_stock"]]
        )
    return Response(
        "﻿" + buf.getvalue(),  # BOM para o Excel abrir acentos corretamente
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=estoque.csv"},
    )
