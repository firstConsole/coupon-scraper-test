from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from coupon_scraper.application.ports.proxies import ProxyLease
    from coupon_scraper.domain.values.urls import CanonicalUrl


@dataclass(frozen=True, slots=True)
class FetchedPage:
    """Ответ, полученный без браузера"""

    status: int
    body: str
    looks_banned: bool
    bytes_received: int


@runtime_checkable
class HttpFetcher(Protocol):
    async def fetch(self, url: CanonicalUrl, through: ProxyLease) -> FetchedPage: ...
