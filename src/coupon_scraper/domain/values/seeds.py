from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coupon_scraper.domain.errors import NaiveMomentError

if TYPE_CHECKING:
    from datetime import datetime

    from coupon_scraper.domain.values.urls import CanonicalUrl


@dataclass(frozen=True, slots=True)
class SeedEntry:
    """Страница, о которой сайт сам сообщил поисковикам"""

    url: CanonicalUrl
    last_modified: datetime | None = None

    def __post_init__(self) -> None:
        moment = self.last_modified

        if moment is not None and (
            moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None
        ):
            raise NaiveMomentError("last_modified")

    def changed_since(self, moment: datetime) -> bool:
        """Неизвестная дата считается изменением"""
        return self.last_modified is None or self.last_modified > moment


@dataclass(frozen=True, slots=True)
class NestedSitemap:
    url: CanonicalUrl
