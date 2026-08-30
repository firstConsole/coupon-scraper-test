from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from coupon_scraper.domain.errors import InvalidIdentifierError

if TYPE_CHECKING:
    from datetime import timedelta

    from coupon_scraper.application.ports.browser import Screenshot
    from coupon_scraper.domain.values.extraction import RawSnapshot
    from coupon_scraper.domain.values.identifiers import RunId, TenantId
    from coupon_scraper.domain.values.urls import TaskKey


@dataclass(frozen=True, slots=True)
class ArtifactKey:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise InvalidIdentifierError("ArtifactKey", "пустой ключ")

        if self.value.startswith("/") or ".." in self.value:
            raise InvalidIdentifierError("ArtifactKey", "путь выводит за пределы префикса")

    def __str__(self) -> str:
        return self.value


@runtime_checkable
class ArtifactStorage(Protocol):
    async def put_screenshot(
        self, tenant: TenantId, run: RunId, shot: Screenshot
    ) -> ArtifactKey: ...

    async def put_forensics(
        self, tenant: TenantId, run: RunId, task: TaskKey, snapshot: RawSnapshot
    ) -> ArtifactKey: ...

    async def presign(self, key: ArtifactKey, ttl: timedelta) -> str: ...
