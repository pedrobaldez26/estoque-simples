import pytest

from app.money import format_brl, parse_brl


@pytest.mark.parametrize(
    "text,cents",
    [("12,50", 1250), ("1.234,56", 123456), ("R$ 7", 700), ("0,05", 5), ("10.5", 1050), ("0", 0)],
)
def test_parse_valido(text, cents):
    assert parse_brl(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "-5", "1,234", "12,5x", "1,2,3"])
def test_parse_invalido(text):
    assert parse_brl(text) is None


def test_format():
    assert format_brl(123456) == "R$ 1.234,56"
    assert format_brl(5) == "R$ 0,05"
    assert format_brl(100000000) == "R$ 1.000.000,00"
