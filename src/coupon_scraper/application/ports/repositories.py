from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime, timedelta

    from coupon_scraper.domain.entities.offer import Offer
    from coupon_scraper.domain.entities.page_task import PageTask
    from coupon_scraper.domain.values.extraction import ExtractionProfile
    from coupon_scraper.domain.values.identifiers import RunId, TenantId
    from coupon_scraper.domain.values.urls import TaskKey


@runtime_checkable
class PageTaskRepository(Protocol):
    async def add_missing(self, tasks: Sequence[PageTask]) -> int: ...

    async def lease_batch(
        self, tenant: TenantId, worker: str, now: datetime, ttl: timedelta, limit: int
    ) -> Sequence[PageTask]: ...

    async def save(self, task: PageTask) -> None: ...

    async def reclaim_expired(self, now: datetime, limit: int) -> int: ...


@runtime_checkable
class OfferRepository(Protocol):
    async def upsert(self, offer: Offer) -> None:
        """Обновить текущее состояние и дописать строку в историю"""
        ...


@runtime_checkable
class ExtractionProfileRepository(Protocol):
    async def active_for(self, tenant: TenantId, run: RunId) -> ExtractionProfile: ...

    async def by_task(self, tenant: TenantId, task: TaskKey) -> ExtractionProfile | None: ...
