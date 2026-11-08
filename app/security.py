import hashlib
import hmac
import secrets

from flask import abort, request, session
from werkzeug.security import generate_password_hash


def hash_password(password: str) -> str:
    # scrypt é o padrão do Werkzeug, mas alguns Pythons (ex.: o da Apple, com LibreSSL)
    # vêm sem hashlib.scrypt. PBKDF2 serve de reserva; check_password_hash lê os dois formatos.
    method = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2:sha256"
    return generate_password_hash(password, method=method)


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf() -> None:
    """Toda requisição que altera estado precisa devolver o token da sessão."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, "Token CSRF inválido. Recarregue a página e tente de novo.")


def is_safe_next(target: str) -> bool:
    """Só aceita caminhos internos, para o login não virar redirecionamento aberto."""
    return target.startswith("/") and not target.startswith("//") and "\\" not in target
