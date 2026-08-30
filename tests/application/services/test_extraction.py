"""Извлечение: порядок мест, полнота и происхождение значений"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coupon_scraper.application.ports.snapshot import SnapshotReader
from coupon_scraper.application.services.extraction import ExtractedFields, OfferExtractor
from coupon_scraper.domain.values.extraction import (
    ExtractionProfile,
    FieldRule,
    FieldSource,
    OfferKind,
    RawSnapshot,
    Readiness,
)
from coupon_scraper.domain.values.geo import Country

if TYPE_CHECKING:
    from collections.abc import Mapping

SNAPSHOT = RawSnapshot(payloads=("{}",), embedded="{}", html="<div class='card'></div>")

FIELDS: Mapping[str, tuple[FieldRule, ...]] = {
    "merchant": (FieldRule(source=FieldSource.PAYLOAD, path="$.merchant", required=True),),
    "face_value": (
        FieldRule(source=FieldSource.PAYLOAD, path="$.faceValue", required=True),
        FieldRule(source=FieldSource.EMBEDDED, path="$.props.faceValue", required=True),
        FieldRule(source=FieldSource.DOM, path=".card__value"),
    ),
    "terms": (FieldRule(source=FieldSource.DOM, path=".card__terms"),),
}


class ScriptedReader:
    """Отдаёт заранее записанные ответы по паре «источник + путь»."""

    def __init__(self, answers: Mapping[tuple[FieldSource, str], str | None]) -> None:
        self._answers = answers
        self.asked: list[tuple[FieldSource, str]] = []

    def read(self, snapshot: RawSnapshot, rule: FieldRule) -> str | None:
        self.asked.append((rule.source, rule.path))
        return self._answers.get((rule.source, rule.path))


def _profile(**overrides: Any) -> ExtractionProfile:
    base: dict[str, Any] = {
        "version": 4,
        "card_selector": ".card",
        "fields": FIELDS,
        "readiness": Readiness(ready_selector=".card"),
        "offer_kind": OfferKind.GIFT_CARD,
        "geo": Country("ES"),
        "default_currency": "EUR",
    }
    return ExtractionProfile(**(base | overrides))


def _extract(answers: Mapping[tuple[FieldSource, str], str | None]) -> ExtractedFields:
    return OfferExtractor(ScriptedReader(answers)).extract(SNAPSHOT, _profile())


ALL_PRESENT = {
    (FieldSource.PAYLOAD, "$.merchant"): "Zalando",
    (FieldSource.PAYLOAD, "$.faceValue"): "50.00",
    (FieldSource.DOM, ".card__terms"): "Válida en zalando.es",
}


def test_scripted_reader_satisfies_the_port() -> None:
    assert isinstance(ScriptedReader({}), SnapshotReader)


def test_values_are_taken_from_the_first_place_that_answers() -> None:
    extracted = _extract(ALL_PRESENT)

    assert extracted.values["face_value"] == "50.00"
    assert extracted.sources["face_value"] is FieldSource.PAYLOAD
    assert extracted.fill_rate.value == pytest.approx(1.0)


def test_next_place_is_tried_when_the_first_is_silent() -> None:
    """Сайт переехал на серверный рендер — номинал теперь вшит в документ"""
    answers = dict(ALL_PRESENT)
    del answers[FieldSource.PAYLOAD, "$.faceValue"]
    answers[FieldSource.EMBEDDED, "$.props.faceValue"] = "50.00"

    extracted = _extract(answers)

    assert extracted.values["face_value"] == "50.00"
    assert extracted.sources["face_value"] is FieldSource.EMBEDDED


def test_places_after_a_hit_are_not_asked() -> None:
    reader = ScriptedReader(ALL_PRESENT)

    OfferExtractor(reader).extract(SNAPSHOT, _profile())

    assert (FieldSource.DOM, ".card__value") not in reader.asked


def test_blank_answer_counts_as_absence() -> None:
    """Пустая строка из разметки — это не значение, а пустой узел"""
    answers = dict(ALL_PRESENT)
    answers[FieldSource.PAYLOAD, "$.faceValue"] = "   "
    answers[FieldSource.EMBEDDED, "$.props.faceValue"] = "50.00"

    assert _extract(answers).sources["face_value"] is FieldSource.EMBEDDED


def test_values_are_trimmed() -> None:
    answers = dict(ALL_PRESENT) | {(FieldSource.PAYLOAD, "$.merchant"): "  Zalando\n"}

    assert _extract(answers).values["merchant"] == "Zalando"


# ── Полнота ───────────────────────────────────────────────────────────────────


def test_fill_rate_counts_only_required_fields() -> None:
    """Пропавшие условия — не повод считать карточку битой"""
    answers = dict(ALL_PRESENT)
    del answers[FieldSource.DOM, ".card__terms"]

    extracted = _extract(answers)

    assert extracted.fill_rate.value == pytest.approx(1.0)
    assert "terms" not in extracted.values


def test_missing_required_field_lowers_the_fill_rate() -> None:
    answers = dict(ALL_PRESENT)
    del answers[FieldSource.PAYLOAD, "$.faceValue"]

    extracted = _extract(answers)

    assert extracted.fill_rate.value == pytest.approx(0.5)
    assert extracted.missing(_profile()) == {"face_value"}


def test_empty_snapshot_gives_zero_fill_rate() -> None:
    extracted = _extract({})

    assert extracted.fill_rate.value == pytest.approx(0.0)
    assert extracted.missing(_profile()) == {"merchant", "face_value"}


# ── Ранний признак переезда ───────────────────────────────────────────────────


def test_change_of_source_is_reported() -> None:
    """Разметка цела, полнота в норме — но профиль уже держится на запасном месте"""
    answers = dict(ALL_PRESENT)
    del answers[FieldSource.PAYLOAD, "$.faceValue"]
    answers[FieldSource.EMBEDDED, "$.props.faceValue"] = "50.00"

    drifted = _extract(answers).drifted_from({"face_value": FieldSource.PAYLOAD})

    assert drifted == {"face_value"}


def test_unchanged_sources_report_nothing() -> None:
    expected = {"merchant": FieldSource.PAYLOAD, "face_value": FieldSource.PAYLOAD}

    assert not _extract(ALL_PRESENT).drifted_from(expected)
