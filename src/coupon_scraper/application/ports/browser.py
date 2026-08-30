from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from types import TracebackType

    from coupon_scraper.application.ports.proxies import ProxyLease
    from coupon_scraper.domain.values.extraction import RawSnapshot, Readiness
    from coupon_scraper.domain.values.urls import CanonicalUrl


class ChallengeKind(StrEnum):
    TURNSTILE = "turnstile"
    RECAPTCHA = "recaptcha"
    HCAPTCHA = "hcaptcha"

    @property
    def response_field(self) -> str:
        return {
            ChallengeKind.TURNSTILE: "cf-turnstile-response",
            ChallengeKind.RECAPTCHA: "g-recaptcha-response",
            ChallengeKind.HCAPTCHA: "h-captcha-response",
        }[self]


@dataclass(frozen=True, slots=True)
class Challenge:
    kind: ChallengeKind
    site_key: str
    page_url: CanonicalUrl
    action: str | None = None


@dataclass(frozen=True, slots=True)
class Visit:
    requested: CanonicalUrl
    final: CanonicalUrl
    status: int | None
    looks_banned: bool
    bytes_received: int = 0

    @property
    def landed_on_target(self) -> bool:
        return self.requested == self.final


@dataclass(frozen=True, slots=True)
class Screenshot:
    body: bytes
    content_type: str = "image/png"

    @property
    def digest(self) -> str:
        return sha256(self.body).hexdigest()


@runtime_checkable
class PageSession(Protocol):
    async def open(self, url: CanonicalUrl) -> Visit: ...

    async def open_from(self, listing: CanonicalUrl, card_selector: str) -> Visit: ...

    async def settle(self, readiness: Readiness) -> None: ...

    async def detect_challenge(self) -> Challenge | None: ...

    async def submit_token(self, challenge: Challenge, token: str) -> None: ...

    async def snapshot(self) -> RawSnapshot: ...

    async def screenshot_card(self, selector: str) -> Screenshot: ...


class BrowserRuntime(Protocol):
    def session(self, lease: ProxyLease) -> AsyncSession:
        """Сессия под конкретный адрес"""
        ...

    async def recycle(self, lease: ProxyLease) -> None:
        """Выбросить процесс"""
        ...


class AsyncSession(Protocol):
    async def __aenter__(self) -> PageSession: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...
