from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

    from coupon_scraper.domain.failures import ScrapeError
    from coupon_scraper.domain.values.geo import Country
    from coupon_scraper.domain.values.identifiers import RunId
    from coupon_scraper.domain.values.proxy import ProxyIdentity


@dataclass(frozen=True, slots=True)
class ProxyLease:
    identity: ProxyIdentity
    geo: Country
    expires_at: datetime


@runtime_checkable
class ProxyPool(Protocol):
    async def acquire(self, run: RunId, geo: Country) -> ProxyLease: ...

    async def release(self, lease: ProxyLease) -> None: ...

    async def report_success(self, lease: ProxyLease) -> None: ...

    async def quarantine(self, lease: ProxyLease, failure: ScrapeError) -> None: ...
