from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from coupon_scraper.domain.values.extraction import FillRate
    from coupon_scraper.domain.values.identifiers import RunId


@runtime_checkable
class MetricsSink(Protocol):
    def page_collected(self, run: RunId, fill_rate: FillRate) -> None: ...

    def page_failed(self, run: RunId, reason: str) -> None: ...

    def drift_seen(self, run: RunId, profile_version: int) -> None: ...

    def endpoint_banned(self, run: RunId, identity: str) -> None: ...

    def challenge_seen(self, run: RunId, *, solved: bool) -> None: ...

    def traffic_spent(self, run: RunId, bytes_used: int) -> None: ...
