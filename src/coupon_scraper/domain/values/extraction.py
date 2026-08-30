from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from coupon_scraper.domain.errors import InvalidProfileError

if TYPE_CHECKING:
    from collections.abc import Mapping


class FieldSource(StrEnum):
    PAYLOAD = "payload"
    EMBEDDED = "embedded"
    DOM = "dom"


@dataclass(frozen=True, slots=True)
class FieldRule:
    source: FieldSource
    path: str
    attribute: str | None = None
    required: bool = False

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise InvalidProfileError("пустой путь к полю")

        if self.attribute is not None and self.source is not FieldSource.DOM:
            raise InvalidProfileError("атрибут имеет смысл только для разметки")


@dataclass(frozen=True, slots=True)
class Readiness:
    data_url_pattern: str | None = None
    ready_selector: str | None = None
    skeleton_selector: str | None = None
    timeout_ms: int = 30_000

    def __post_init__(self) -> None:
        if self.timeout_ms <= 0:
            raise InvalidProfileError("нулевое ожидание готовности")

        if self.data_url_pattern is None and self.ready_selector is None:
            raise InvalidProfileError(
                "нет ни ожидаемого ответа, ни селектора готовности — "
                "снимок уедет раньше содержимого"
            )


@dataclass(frozen=True, slots=True)
class ExtractionProfile:
    version: int
    card_selector: str
    fields: Mapping[str, tuple[FieldRule, ...]]
    readiness: Readiness
    min_fill_rate: float = 0.9
    code_behind_click: bool = False
    respect_robots: bool = True

    def __post_init__(self) -> None:
        if self.version < 1:
            raise InvalidProfileError("версия профиля начинается с единицы")

        if not self.card_selector.strip():
            raise InvalidProfileError("пустой селектор карточки — нечего снимать")

        if not self.fields:
            raise InvalidProfileError("профиль без полей ничего не извлекает")

        for name, lookup in self.fields.items():
            if not lookup:
                raise InvalidProfileError(f"поле {name!r} без единого места поиска")

        if not self.required_fields:
            raise InvalidProfileError(
                "нет ни одного обязательного поля — полнота всегда будет единицей "
                "и дрейф вёрстки останется незамеченным"
            )

        if not 0 < self.min_fill_rate <= 1:
            raise InvalidProfileError(f"порог полноты {self.min_fill_rate} вне диапазона (0, 1]")

        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    @property
    def required_fields(self) -> frozenset[str]:
        """Поле обязательно, если обязательным объявлено хотя бы одно его место."""
        return frozenset(
            name for name, lookup in self.fields.items() if any(rule.required for rule in lookup)
        )


@dataclass(frozen=True, slots=True)
class FillRate:
    value: float

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 1:
            raise InvalidProfileError(f"полнота {self.value} вне диапазона [0, 1]")

    @classmethod
    def of(cls, filled: int, required: int) -> FillRate:
        if required <= 0:
            raise InvalidProfileError("полнота без обязательных полей не имеет смысла")

        return cls(min(filled, required) / required)

    def meets(self, threshold: float) -> bool:
        return self.value >= threshold

    def __str__(self) -> str:
        return f"{self.value:.0%}"


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    payloads: tuple[str, ...] = ()
    embedded: str | None = None
    html: str | None = None
    fields: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (self.payloads or self.embedded or self.html):
            raise InvalidProfileError("пустой снимок: со страницы не снято ничего")
