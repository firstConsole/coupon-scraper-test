from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from coupon_scraper.domain.errors import InvalidBudgetError, InvalidProxyIdentityError

FORBIDDEN_IN_IDENTITY: Final = ("@", " ", "\t", "\n")


@dataclass(frozen=True, slots=True)
class ProxyIdentity:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise InvalidProxyIdentityError("пустое имя")

        if any(token in self.value for token in FORBIDDEN_IN_IDENTITY):
            raise InvalidProxyIdentityError("похоже на строку с учётными данными")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RequestBudget:
    limit: int
    cooldown: timedelta

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise InvalidBudgetError(f"лимит {self.limit} не даёт сделать ни одного запроса")

        if self.cooldown <= timedelta(0):
            raise InvalidBudgetError("пауза нулевой длины не является паузой")
