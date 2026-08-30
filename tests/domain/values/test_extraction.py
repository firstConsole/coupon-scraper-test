"""Профиль извлечения: описание цели как данные"""

from __future__ import annotations

from typing import Any

import pytest

from coupon_scraper.domain.errors import InvalidProfileError
from coupon_scraper.domain.values.extraction import (
    ExtractionProfile,
    FieldRule,
    FieldSource,
    FillRate,
    RawSnapshot,
    Readiness,
)

FIELDS = {
    "merchant": FieldRule(source=FieldSource.PAYLOAD, path="$.merchant.name", required=True),
    "face_value": FieldRule(source=FieldSource.PAYLOAD, path="$.faceValue", required=True),
    "terms": FieldRule(source=FieldSource.DOM, path=".card__terms"),
}
READINESS = Readiness(data_url_pattern="/api/v1/cards/*", ready_selector=".card")


def _profile(**overrides: Any) -> ExtractionProfile:
    base: dict[str, Any] = {
        "version": 4,
        "card_selector": ".card",
        "fields": FIELDS,
        "readiness": READINESS,
    }
    return ExtractionProfile(**(base | overrides))


def test_profile_knows_its_required_fields() -> None:
    assert _profile().required_fields == {"merchant", "face_value"}


def test_fields_are_frozen_after_construction() -> None:
    """Профиль приходит от арендатора — менять его после проверки нельзя"""
    profile = _profile()

    with pytest.raises(TypeError):
        profile.fields["merchant"] = FIELDS["terms"]  # type: ignore[index]


def test_profile_without_required_fields_is_refused() -> None:
    """Полнота была бы всегда единицей, и дрейф вёрстки остался бы незамеченным"""
    relaxed = {name: FieldRule(source=rule.source, path=rule.path) for name, rule in FIELDS.items()}

    with pytest.raises(InvalidProfileError, match="обязательного поля"):
        _profile(fields=relaxed)


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": 0},
        {"card_selector": "  "},
        {"fields": {}},
        {"min_fill_rate": 0.0},
        {"min_fill_rate": 1.5},
    ],
)
def test_broken_profile_is_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidProfileError):
        _profile(**overrides)


def test_readiness_needs_something_to_wait_for() -> None:
    """networkidle на одностраничном приложении не наступает — ждать надо конкретное"""
    with pytest.raises(InvalidProfileError, match="снимок уедет раньше содержимого"):
        Readiness()


def test_attribute_makes_sense_only_for_markup() -> None:
    with pytest.raises(InvalidProfileError, match="только для разметки"):
        FieldRule(source=FieldSource.PAYLOAD, path="$.x", attribute="href")


# ── Полнота ───────────────────────────────────────────────────────────────────


def test_fill_rate_counts_required_fields() -> None:
    assert FillRate.of(filled=9, required=10).value == pytest.approx(0.9)


def test_fill_rate_is_compared_with_the_threshold() -> None:
    assert FillRate.of(9, 10).meets(0.9)
    assert not FillRate.of(8, 10).meets(0.9)


def test_fill_rate_without_required_fields_is_meaningless() -> None:
    with pytest.raises(InvalidProfileError):
        FillRate.of(filled=0, required=0)


def test_fill_rate_reads_as_a_percentage() -> None:
    assert str(FillRate.of(92, 100)) == "92%"


# ── Снимок ────────────────────────────────────────────────────────────────────


def test_snapshot_needs_at_least_one_source() -> None:
    with pytest.raises(InvalidProfileError, match="со страницы не снято ничего"):
        RawSnapshot()


def test_snapshot_accepts_any_single_source() -> None:
    assert RawSnapshot(html="<div class='card'></div>").payloads == ()
