"""Идентификаторы: разные типы не сравниваются даже при равных строках"""

from __future__ import annotations

import pytest

from coupon_scraper.domain.errors import InvalidIdentifierError
from coupon_scraper.domain.values.identifiers import OfferId, RunId, TaskId, TenantId


def test_different_kinds_never_match() -> None:
    """mypy отвергает такое сравнение статически, и это уже половина защиты.

    Тест закрывает вторую половину — путь, где значения приходят как Any: из
    базы, из разобранного JSON, из тела запроса.
    """
    tenant: object = TenantId("acme")
    run: object = RunId("acme")
    task: object = TaskId("x")
    offer: object = OfferId("x")

    assert tenant != run
    assert task != offer


def test_same_kind_matches_by_value() -> None:
    assert RunId("r-42") == RunId("r-42")


@pytest.mark.parametrize("value", ["", "   ", "r 42", "r\t42", "r\n42"])
def test_blank_or_spaced_values_are_rejected(value: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        RunId(value)


def test_error_names_the_kind() -> None:
    with pytest.raises(InvalidIdentifierError, match="TenantId"):
        TenantId("")
