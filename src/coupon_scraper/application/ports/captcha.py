from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from coupon_scraper.application.ports.browser import Challenge
    from coupon_scraper.application.ports.proxies import ProxyLease


@runtime_checkable
class CaptchaSolver(Protocol):
    @property
    def name(self) -> str: ...

    async def solve(self, challenge: Challenge, through: ProxyLease) -> str: ...
