from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coupon_scraper.domain.values.extraction import FillRate, RawSnapshot


class ScrapeError(Exception):
    """Страницу собрать не удалось по внешней причине"""


class EndpointBannedError(ScrapeError):
    """Цель отказала конкретному выходному адресу"""

    def __init__(self, identity: str, status: int | None = None) -> None:
        seen = f"код {status}" if status is not None else "маркер проверки в теле ответа"
        super().__init__(f"адрес {identity} забанен: {seen}")
        self.identity = identity
        self.status = status


class ChallengeUnsolvedError(ScrapeError):
    """Проверку пройти не удалось"""

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"проверка не пройдена ({provider}): {reason}")
        self.provider = provider
        self.reason = reason


class WrongDestinationError(ScrapeError):
    """Одностраничное приложение увело не туда"""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"ожидали {expected}, оказались на {actual}")
        self.expected = expected
        self.actual = actual


class NavigationTimeoutError(ScrapeError):
    """Страница не догрузилась за отведённое время"""

    def __init__(self, url: str, waited_ms: int) -> None:
        super().__init__(f"{url}: не дождались за {waited_ms} мс")
        self.url = url
        self.waited_ms = waited_ms


class ExtractionDriftError(ScrapeError):
    """Страница собралась неполной"""

    def __init__(
        self,
        url: str,
        fill_rate: FillRate,
        profile_version: int,
        snapshot: RawSnapshot,
    ) -> None:
        super().__init__(f"{url}: полнота {fill_rate} по профилю версии {profile_version}")
        self.url = url
        self.fill_rate = fill_rate
        self.profile_version = profile_version
        self.snapshot = snapshot


class TargetGoneError(ScrapeError):
    """Страницы больше нет"""

    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"{url}: страница снята с публикации ({status})")
        self.url = url
        self.status = status
