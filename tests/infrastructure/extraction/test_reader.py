"""Три источника: ответы сайта, состояние документа, разметка"""

from __future__ import annotations

import json

import pytest

from coupon_scraper.domain.values.extraction import FieldRule, FieldSource, RawSnapshot
from coupon_scraper.infrastructure.extraction.paths import tokens, walk
from coupon_scraper.infrastructure.extraction.reader import DocumentReader

CARD = {
    "merchant": {"name": "Zalando", "domain": "zalando.es"},
    "faceValue": 50.0,
    "prices": [{"amount": "46,50", "currency": "EUR"}],
    "inStock": True,
    "terms": None,
}

MARKUP = """
<html><body>
  <div class="card" data-sku="ZAL-50">
    <h2 class="merchant">Zalando</h2>
    <p class="value">50,00 €</p>
    <p class="terms">  Válida en zalando.es  </p>
    <p class="empty"></p>
  </div>
</body></html>
"""


def _read(
    snapshot: RawSnapshot, source: FieldSource, path: str, attribute: str | None = None
) -> str | None:
    rule = FieldRule(source=source, path=path, attribute=attribute)
    return DocumentReader().read(snapshot, rule)


# ── Путь ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("$.merchant.name", ("merchant", "name")),
        ("merchant.name", ("merchant", "name")),
        ("$.prices[0].amount", ("prices", 0, "amount")),
        ("$", ()),
    ],
)
def test_path_is_split_into_keys_and_indexes(path: str, expected: tuple[object, ...]) -> None:
    assert tokens(path) == expected


@pytest.mark.parametrize(
    "path", ["$.merchant.brand", "$.prices[7].amount", "$.faceValue.name", "$.merchant[0]"]
)
def test_path_leading_nowhere_gives_nothing(path: str) -> None:
    """Отсутствие поля — обычный исход: исключение роняло бы карточку целиком"""
    assert walk(CARD, path) is None


# ── Ответы сайта ──────────────────────────────────────────────────────────────


def test_value_is_taken_from_the_response() -> None:
    snapshot = RawSnapshot(payloads=(json.dumps(CARD),))

    assert _read(snapshot, FieldSource.PAYLOAD, "$.merchant.name") == "Zalando"
    assert _read(snapshot, FieldSource.PAYLOAD, "$.prices[0].amount") == "46,50"


def test_numbers_and_flags_become_strings() -> None:
    snapshot = RawSnapshot(payloads=(json.dumps(CARD),))

    assert _read(snapshot, FieldSource.PAYLOAD, "$.faceValue") == "50.0"
    assert _read(snapshot, FieldSource.PAYLOAD, "$.inStock") == "true"


def test_nested_structure_is_not_glued_into_a_string() -> None:
    """Список на месте номинала означает, что путь указывает не туда"""
    snapshot = RawSnapshot(payloads=(json.dumps(CARD),))

    assert _read(snapshot, FieldSource.PAYLOAD, "$.prices") is None


def test_several_responses_are_tried_in_turn() -> None:
    """Карточка, цены и наличие приходят по отдельности — это норма, а не сбой"""
    snapshot = RawSnapshot(
        payloads=('{"unrelated": 1}', "не json вовсе", json.dumps(CARD)),
    )

    assert _read(snapshot, FieldSource.PAYLOAD, "$.merchant.name") == "Zalando"


# ── Состояние в документе ─────────────────────────────────────────────────────


def test_next_data_is_read() -> None:
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({"props": {"card": CARD}})
        + "</script>"
    )

    assert (
        _read(RawSnapshot(embedded=html), FieldSource.EMBEDDED, "$.props.card.faceValue") == "50.0"
    )


def test_window_assignment_is_read() -> None:
    html = '<script>window.__NUXT__={"data":[{"card":' + json.dumps(CARD) + "}]}</script>"

    value = _read(RawSnapshot(embedded=html), FieldSource.EMBEDDED, "$.data[0].card.merchant.name")

    assert value == "Zalando"


def test_rsc_chunks_are_glued_back_together() -> None:
    """Поток приходит строковыми кусками — по одному в них ничего не найти"""
    payload = json.dumps({"card": CARD})
    first, second = payload[: len(payload) // 2], payload[len(payload) // 2 :]
    html = (
        f"<script>self.__next_f.push([1,{json.dumps(first)}])</script>"
        f"<script>self.__next_f.push([1,{json.dumps(second)}])</script>"
    )

    assert _read(RawSnapshot(embedded=html), FieldSource.EMBEDDED, "$.card.faceValue") == "50.0"


def test_broken_embedded_json_is_skipped_not_fatal() -> None:
    html = '<script id="__NEXT_DATA__" type="application/json">{сломано</script>'

    assert _read(RawSnapshot(embedded=html), FieldSource.EMBEDDED, "$.props") is None


# ── Разметка ──────────────────────────────────────────────────────────────────


def test_text_is_taken_from_the_selector() -> None:
    assert _read(RawSnapshot(html=MARKUP), FieldSource.DOM, ".merchant") == "Zalando"


def test_text_is_trimmed() -> None:
    assert _read(RawSnapshot(html=MARKUP), FieldSource.DOM, ".terms") == "Válida en zalando.es"


def test_attribute_is_taken_when_asked() -> None:
    value = _read(RawSnapshot(html=MARKUP), FieldSource.DOM, ".card", attribute="data-sku")

    assert value == "ZAL-50"


@pytest.mark.parametrize(("path", "attribute"), [(".missing", None), (".card", "data-absent")])
def test_selector_hitting_nothing_gives_nothing(path: str, attribute: str | None) -> None:
    """Именно этот случай и есть дрейф вёрстки — падать здесь нельзя"""
    assert _read(RawSnapshot(html=MARKUP), FieldSource.DOM, path, attribute) is None


def test_empty_node_counts_as_absence() -> None:
    assert _read(RawSnapshot(html=MARKUP), FieldSource.DOM, ".empty") is None


def test_source_without_data_gives_nothing() -> None:
    snapshot = RawSnapshot(html=MARKUP)

    assert _read(snapshot, FieldSource.PAYLOAD, "$.merchant.name") is None
    assert _read(snapshot, FieldSource.EMBEDDED, "$.merchant.name") is None
