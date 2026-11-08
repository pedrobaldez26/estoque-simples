import re

from app.db import get_db
from app.inventory import csv_safe
from conftest import make_product


def stock_of(app, sku):
    with app.app_context():
        row = get_db().execute(
            """SELECT COALESCE(SUM(CASE m.kind WHEN 'in' THEN m.quantity ELSE -m.quantity END), 0) AS s
               FROM products p LEFT JOIN movements m ON m.product_id = p.id WHERE p.sku = ?""",
            (sku,),
        ).fetchone()
        return row["s"]


def test_rotas_exigem_login(client):
    for url in ["/", "/products/new", "/reports/low-stock", "/export.csv", "/products/1"]:
        r = client.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"], url


def test_login_errado_e_certo(client):
    r = client.login(password="errada")
    assert r.status_code == 200 and "incorretos" in r.get_data(as_text=True)

    r = client.login()
    assert r.status_code == 302
    assert client.get("/").status_code == 200


def test_login_nao_redireciona_para_fora(client):
    for evil in ["https://evil.example", "//evil.example", "/\\evil.example"]:
        r = client.post(f"/login?next={evil}", {"username": "maria", "password": "senha-de-teste"})
        assert r.headers["Location"] == "/", evil
        client.post("/logout")


def test_post_sem_csrf_e_recusado(logged):
    r = logged.post("/products/new", {"sku": "X", "name": "Y", "price": "1", "min_stock": "0"}, csrf=False)
    assert r.status_code == 400


def test_cadastra_produto_e_recusa_sku_repetido(logged):
    r = make_product(logged)
    assert r.status_code == 302

    r = make_product(logged)
    assert r.status_code == 200 and "Já existe um produto com esse SKU" in r.get_data(as_text=True)

    r = make_product(logged, sku="B-1", price="abc")
    assert "Preço inválido" in r.get_data(as_text=True)


def test_entrada_e_saida_atualizam_saldo(app, logged):
    make_product(logged)
    logged.post("/products/1/movements", {"kind": "in", "quantity": "30"})
    logged.post("/products/1/movements", {"kind": "out", "quantity": "12", "note": "venda balcão"})
    assert stock_of(app, "CAN-001") == 18

    page = logged.get("/products/1").get_data(as_text=True)
    assert "venda balcão" in page and "maria" in page


def test_saida_maior_que_o_estoque_e_recusada(app, logged):
    make_product(logged)
    logged.post("/products/1/movements", {"kind": "in", "quantity": "5"})
    r = logged.post("/products/1/movements", {"kind": "out", "quantity": "6"}, follow_redirects=True)

    assert "maior que o estoque disponível (5)" in r.get_data(as_text=True)
    assert stock_of(app, "CAN-001") == 5


def test_quantidade_invalida(app, logged):
    make_product(logged)
    for q in ["0", "-3", "1.5", "abc", ""]:
        logged.post("/products/1/movements", {"kind": "in", "quantity": q})
    assert stock_of(app, "CAN-001") == 0


def test_relatorio_de_estoque_baixo(logged):
    make_product(logged, sku="A", name="Produto A", min_stock="10")
    make_product(logged, sku="B", name="Produto B", min_stock="2")
    logged.post("/products/1/movements", {"kind": "in", "quantity": "10"})  # igual ao mínimo: baixo
    logged.post("/products/2/movements", {"kind": "in", "quantity": "50"})

    html = logged.get("/reports/low-stock").get_data(as_text=True)
    assert "Produto A" in html and "Produto B" not in html


def test_busca_trata_curingas_como_texto(logged):
    make_product(logged, sku="A", name="Cabo 100%")
    make_product(logged, sku="B", name="Cabo USB")
    html = logged.get("/?q=100%25").get_data(as_text=True)
    assert "Cabo 100%" in html and "Cabo USB" not in html


def test_nome_com_html_e_escapado(logged):
    make_product(logged, sku="XSS", name="<script>alert(1)</script>")
    html = logged.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_csv_exporta_e_neutraliza_formulas(logged):
    make_product(logged, sku="F-1", name='=HYPERLINK("http://evil.example","clique")', price="1,00")
    make_product(logged, sku="F-2", name="Normal", price="3,50")

    r = logged.get("/export.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    body = r.get_data(as_text=True)
    assert "'=HYPERLINK" in body
    assert "\n=HYPERLINK" not in body and ";=HYPERLINK" not in body
    assert "F-2;Normal;3,50;0;10" in body


def test_csv_safe():
    assert csv_safe("=1+1") == "'=1+1"
    assert csv_safe("@cmd") == "'@cmd"
    assert csv_safe("+55 11") == "'+55 11"
    assert csv_safe("normal") == "normal"
    assert csv_safe(42) == "42"


def test_cabecalhos_de_seguranca(client):
    r = client.get("/login")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
