"""Деньги: Decimal, одна валюта и никакой арифметики между разными"""

from __future__ import annotations

from decimal import Decimal

import pytest

from coupon_scraper.domain.errors import CurrencyMismatchError, InvalidMoneyError
from coupon_scraper.domain.values.money import Currency, Money, Percentage

EUR = Currency("EUR")
USD = Currency("USD")


def _eur(amount: str) -> Money:
    return Money(Decimal(amount), EUR)


def test_gift_card_discount_is_computed_from_face_value() -> None:
    """Номинал 50 за 46.50 — это ровно 7 %, а не 6.99 из-за float"""
    discount = _eur("46.50").discount_from(_eur("50.00"))

    assert discount.value == Decimal(7)


def test_cross_currency_comparison_is_refused() -> None:
    with pytest.raises(CurrencyMismatchError, match=r"EUR|USD"):
        _eur("10.00").same_currency_as(Money(Decimal(10), USD))


def test_discount_from_zero_face_value_is_refused() -> None:
    with pytest.raises(InvalidMoneyError, match="номинал нулевой"):
        _eur("5.00").discount_from(_eur("0.00"))


@pytest.mark.parametrize("code", ["eur", "EU", "EURO", "1UR", ""])
def test_currency_must_be_iso_4217(code: str) -> None:
    with pytest.raises(InvalidMoneyError):
        Currency(code)


def test_currency_parses_loose_input() -> None:
    assert Currency.parse(" eur ") == EUR


def test_negative_amount_is_refused() -> None:
    with pytest.raises(InvalidMoneyError, match="отрицательная"):
        _eur("-1.00")


@pytest.mark.parametrize("value", ["-0.1", "100.1", "1000"])
def test_share_outside_the_range_is_refused(value: str) -> None:
    with pytest.raises(InvalidMoneyError, match="вне диапазона"):
        Percentage(Decimal(value))


# ── Разбор строки: цель в другой стране, разделитель у неё свой ───────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("46.50", "46.50"),
        ("46,50", "46.50"),
        ("1 234,56", "1234.56"),
        ("1 234,56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("1,234", "1234"),
        ("€ 46.50", "46.50"),
        ("46,50 €", "46.50"),
        ("50", "50"),
    ],
)
def test_amount_is_read_in_any_local_notation(raw: str, expected: str) -> None:
    """Последний из встреченных разделителей и есть дробный, левее — разряды"""
    assert Money.parse(raw, "eur") == Money(Decimal(expected), EUR)


@pytest.mark.parametrize("raw", ["", "   ", "бесплатно", "—"])
def test_string_without_a_number_is_refused(raw: str) -> None:
    with pytest.raises(InvalidMoneyError, match="нет числа"):
        Money.parse(raw, "EUR")


def test_negative_amount_from_a_page_is_refused() -> None:
    """Отрицательный номинал означает, что разобрали не то поле"""
    with pytest.raises(InvalidMoneyError, match="отрицательная"):
        Money.parse("-5.00", "EUR")
