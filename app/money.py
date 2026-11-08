import re
from typing import Optional


def parse_brl(text: str) -> Optional[int]:
    """'1.234,56' -> 123456. Devolve None se não for um valor válido (>= 0)."""
    raw = text.strip().replace("R$", "").strip()
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", raw):
        return None
    whole, _, frac = raw.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def format_brl(cents: int) -> str:
    whole, frac = divmod(int(cents), 100)
    return f"R$ {whole:,}".replace(",", ".") + f",{frac:02d}"
