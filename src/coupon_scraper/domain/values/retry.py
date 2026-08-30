from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coupon_scraper.domain.errors import InvalidPacingError
from coupon_scraper.domain.failures import (
    ChallengeUnsolvedError,
    EndpointBannedError,
    ExtractionDriftError,
    NavigationTimeoutError,
    PoolExhaustedError,
    ScrapeError,
    TargetGoneError,
    WrongDestinationError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from random import Random


class Decision(StrEnum):
    """Что делать с задачей после отказа."""

    RETRY = "retry"
    RETRY_ELSEWHERE = "retry_elsewhere"
    RETRY_FRESH_PERSONA = "retry_fresh_persona"
    RETRY_FRESH_SESSION = "retry_fresh_session"
    DEAD_LETTER = "dead_letter"
    DROP = "drop"


DECISIONS: Final[Mapping[type[ScrapeError], Decision]] = MappingProxyType(
    {
        EndpointBannedError: Decision.RETRY_ELSEWHERE,
        ChallengeUnsolvedError: Decision.RETRY_FRESH_PERSONA,
        WrongDestinationError: Decision.RETRY_FRESH_SESSION,
        NavigationTimeoutError: Decision.RETRY,
        PoolExhaustedError: Decision.RETRY,
        ExtractionDriftError: Decision.DEAD_LETTER,
        TargetGoneError: Decision.DROP,
    }
)
UNKNOWN_FAILURE: Final = Decision.DEAD_LETTER


def decide(failure: ScrapeError) -> Decision:
    """Решение по типу отказа, с учётом наследования."""
    for kind in type(failure).__mro__:
        decision = DECISIONS.get(kind)
        if decision is not None:
            return decision

    return UNKNOWN_FAILURE


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base: timedelta = timedelta(seconds=2)
    ceiling: timedelta = timedelta(minutes=30)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise InvalidPacingError("ноль попыток означает, что задача не будет выполнена ни разу")

        if self.base <= timedelta(0):
            raise InvalidPacingError("основание задержки должно быть положительным")

        if self.ceiling < self.base:
            raise InvalidPacingError("потолок задержки ниже её основания")

    def is_exhausted(self, attempts: int) -> bool:
        return attempts >= self.max_attempts

    def window_for(self, attempt: int) -> timedelta:
        """Верхняя граница задержки. Растёт вдвое с каждой попыткой и упирается в потолок"""
        if attempt < 1:
            raise InvalidPacingError("попытки нумеруются с единицы")

        return min(self.base * (1 << (attempt - 1)), self.ceiling)

    def delay_for(self, attempt: int, rnd: Random) -> timedelta:
        """Равномерно от нуля до окна. Источник случайности приходит аргументом."""
        window = self.window_for(attempt)

        return timedelta(seconds=rnd.uniform(0.0, window.total_seconds()))
