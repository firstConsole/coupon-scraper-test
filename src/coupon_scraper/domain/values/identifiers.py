from __future__ import annotations

from dataclasses import dataclass

from coupon_scraper.domain.errors import InvalidIdentifierError


@dataclass(frozen=True, slots=True)
class Identifier:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise InvalidIdentifierError(type(self).__name__, "пустое значение")

        if any(char.isspace() for char in self.value):
            raise InvalidIdentifierError(type(self).__name__, "пробелы внутри значения")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TenantId(Identifier):
    """Арендатор. Присутствует в каждой строке базы и в каждой записи лога."""


@dataclass(frozen=True, slots=True)
class RunId(Identifier):
    """Прогон: один план сбора от постановки до выгрузки."""


@dataclass(frozen=True, slots=True)
class TaskId(Identifier):
    """Задача на одну страницу."""


@dataclass(frozen=True, slots=True)
class OfferId(Identifier): ...
