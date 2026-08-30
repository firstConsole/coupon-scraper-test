from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from coupon_scraper.domain.errors import InvalidPacingError

if TYPE_CHECKING:
    from random import Random

DEFAULT_MU: Final = 1.2
DEFAULT_SIGMA: Final = 0.5


@dataclass(frozen=True, slots=True)
class PacingPolicy:
    """Пауза перед обращением: логнормальная случайная величина, ограниченная сверху и снизу"""

    mu: float = DEFAULT_MU
    sigma: float = DEFAULT_SIGMA
    floor: timedelta = timedelta(milliseconds=800)
    ceiling: timedelta = timedelta(seconds=20)

    def __post_init__(self) -> None:
        if self.sigma <= 0:
            raise InvalidPacingError("нулевая дисперсия — это постоянная пауза, то есть сигнатура")

        if self.floor <= timedelta(0):
            raise InvalidPacingError("пол должен быть положительным")

        if self.ceiling <= self.floor:
            raise InvalidPacingError("потолок не выше пола")

    def next_pause(self, rnd: Random) -> timedelta:
        """Источник случайности приходит аргументом — иначе тест недетерминирован."""
        drawn = timedelta(seconds=rnd.lognormvariate(self.mu, self.sigma))

        return min(max(drawn, self.floor), self.ceiling)


@dataclass(slots=True)
class Concurrency:
    """Сколько запросов адрес ведёт одновременно: аддитивный рост, кратное падение"""

    limit: float = 1.0
    ceiling: float = 4.0
    floor: float = 1.0
    step: float = 1.0
    backoff: float = 0.5

    def __post_init__(self) -> None:
        if self.floor < 1:
            raise InvalidPacingError("пол ниже одного запроса останавливает адрес насовсем")

        if self.ceiling < self.floor:
            raise InvalidPacingError("потолок ниже пола")

        if not 0 < self.backoff < 1:
            raise InvalidPacingError("падение должно быть кратным, а не отменой или удвоением")

        self.limit = min(max(self.limit, self.floor), self.ceiling)

    @property
    def permits(self) -> int:
        """Сколько запросов разрешено прямо сейчас. Дробный запрос не бывает."""
        return int(self.limit)

    def report_success(self) -> None:
        self.limit = min(self.ceiling, self.limit + self.step)

    def report_refusal(self) -> None:
        """Отказ цели: делим, а не вычитаем. Вычитание догоняет проблему слишком долго."""
        self.limit = max(self.floor, self.limit * self.backoff)
