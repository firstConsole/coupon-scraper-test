"""Подделки портов.

Ведут общий журнал вызовов: часть свойств цикла — про порядок, а не про
результат, и проверить их иначе нечем.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Self

from coupon_scraper.application.ports.browser import Screenshot, Visit
from coupon_scraper.application.ports.http import FetchedPage
from coupon_scraper.application.ports.proxies import ProxyLease
from coupon_scraper.application.ports.storage import ArtifactKey
from coupon_scraper.domain.failures import ChallengeUnsolvedError, PoolExhaustedError
from coupon_scraper.domain.values.proxy import ProxyIdentity

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from types import TracebackType

    from coupon_scraper.application.ports.browser import Challenge
    from coupon_scraper.domain.entities.offer import Offer
    from coupon_scraper.domain.values.extraction import (
        FieldRule,
        FieldSource,
        RawSnapshot,
        Readiness,
    )
    from coupon_scraper.domain.values.geo import Country
    from coupon_scraper.domain.values.identifiers import RunId
    from coupon_scraper.domain.values.urls import CanonicalUrl

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class Journal:
    """Общий журнал: кто и в каком порядке был вызван."""

    entries: list[str] = field(default_factory=list)

    def record(self, what: str) -> None:
        self.entries.append(what)

    def index(self, what: str) -> int:
        return self.entries.index(what)

    def happened(self, what: str) -> bool:
        return what in self.entries


# ── Время и ожидание ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class FrozenClock:
    moment: datetime = NOW

    def now(self) -> datetime:
        return self.moment


@dataclass(slots=True)
class RecordingSleeper:
    """Не спит, а записывает. Иначе тест цикла шёл бы по четыре секунды."""

    journal: Journal
    pauses: list[timedelta] = field(default_factory=list)

    async def sleep(self, delay: timedelta) -> None:
        self.pauses.append(delay)
        self.journal.record("pause")


# ── Пул адресов ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class FakeProxyPool:
    journal: Journal
    empty: bool = False
    quarantined: list[ProxyIdentity] = field(default_factory=list)
    successes: list[ProxyIdentity] = field(default_factory=list)
    released: list[ProxyIdentity] = field(default_factory=list)

    async def acquire(self, run: RunId, geo: Country) -> ProxyLease:
        if self.empty:
            raise PoolExhaustedError(str(geo))

        self.journal.record("acquire")
        return ProxyLease(
            identity=ProxyIdentity("session-4c2a"), geo=geo, expires_at=NOW + timedelta(minutes=5)
        )

    async def release(self, lease: ProxyLease) -> None:
        self.released.append(lease.identity)
        self.journal.record("release")

    async def report_success(self, lease: ProxyLease) -> None:
        self.successes.append(lease.identity)
        self.journal.record("report_success")

    async def quarantine(self, lease: ProxyLease, failure: Exception) -> None:
        self.quarantined.append(lease.identity)
        self.journal.record("quarantine")


# ── Браузер ───────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class FakePage:
    """Страница, отдающая заранее записанное."""

    journal: Journal
    visit: Visit
    snapshot_body: RawSnapshot
    challenge: Challenge | None = None
    open_error: Exception | None = None
    tokens: list[str] = field(default_factory=list)

    async def open(self, url: CanonicalUrl) -> Visit:
        self.journal.record("open")

        if self.open_error is not None:
            raise self.open_error

        return self.visit

    async def open_from(self, listing: CanonicalUrl, card_selector: str) -> Visit:
        self.journal.record("open_from")
        return self.visit

    async def settle(self, readiness: Readiness) -> None:
        self.journal.record("settle")

    async def detect_challenge(self) -> Challenge | None:
        return self.challenge

    async def submit_token(self, challenge: Challenge, token: str) -> None:
        self.tokens.append(token)
        self.journal.record("submit_token")

    async def snapshot(self) -> RawSnapshot:
        self.journal.record("snapshot")
        return self.snapshot_body

    async def screenshot_card(self, selector: str) -> Screenshot:
        self.journal.record("screenshot")
        return Screenshot(b"png-bytes")


@dataclass(slots=True)
class FakeBrowser:
    journal: Journal
    page: FakePage
    recycled: list[ProxyIdentity] = field(default_factory=list)

    @asynccontextmanager
    async def session(self, lease: ProxyLease) -> AsyncIterator[FakePage]:
        self.journal.record("session")
        try:
            yield self.page
        finally:
            self.journal.record("session_closed")

    async def recycle(self, lease: ProxyLease) -> None:
        self.recycled.append(lease.identity)
        self.journal.record("recycle")


# ── Решатель проверок ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class FakeCaptcha:
    journal: Journal
    token: str = "solved-token"
    fails: bool = False

    @property
    def name(self) -> str:
        return "fake"

    async def solve(self, challenge: Challenge, through: ProxyLease) -> str:
        self.journal.record("solve")

        if self.fails:
            raise ChallengeUnsolvedError(self.name, "таймаут провайдера")

        return self.token


# ── Хранилище и база ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class FakeArtifacts:
    journal: Journal
    screenshots: list[Screenshot] = field(default_factory=list)
    forensics: list[RawSnapshot] = field(default_factory=list)

    async def put_screenshot(self, tenant: object, run: object, shot: Screenshot) -> ArtifactKey:
        self.screenshots.append(shot)
        self.journal.record("put_screenshot")
        return ArtifactKey(f"acme/run/card/{shot.digest}.png")

    async def put_forensics(
        self, tenant: object, run: object, task: object, snapshot: RawSnapshot
    ) -> ArtifactKey:
        self.forensics.append(snapshot)
        self.journal.record("put_forensics")
        return ArtifactKey("acme/run/forensics/1.json")

    async def presign(self, key: ArtifactKey, ttl: timedelta) -> str:
        return f"https://storage.example/{key}"


@dataclass(slots=True)
class FakeOffers:
    journal: Journal
    saved: list[Offer] = field(default_factory=list)

    async def upsert(self, offer: Offer) -> None:
        self.saved.append(offer)
        self.journal.record("upsert")


@dataclass(slots=True)
class FakeUnitOfWork:
    journal: Journal
    commits: int = 0

    async def __aenter__(self) -> Self:
        self.journal.record("begin")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.journal.record("end")

    async def commit(self) -> None:
        self.commits += 1
        self.journal.record("commit")

    async def rollback(self) -> None:
        self.journal.record("rollback")


# ── Метрики и чтение снимка ───────────────────────────────────────────────────


@dataclass(slots=True)
class FakeMetrics:
    collected: int = 0
    failed: list[str] = field(default_factory=list)
    drifts: int = 0
    bans: list[str] = field(default_factory=list)
    challenges: list[bool] = field(default_factory=list)
    traffic: int = 0

    def page_collected(self, run: RunId, fill_rate: object) -> None:
        self.collected += 1

    def page_failed(self, run: RunId, reason: str) -> None:
        self.failed.append(reason)

    def drift_seen(self, run: RunId, profile_version: int) -> None:
        self.drifts += 1

    def endpoint_banned(self, run: RunId, identity: str) -> None:
        self.bans.append(identity)

    def challenge_seen(self, run: RunId, *, solved: bool) -> None:
        self.challenges.append(solved)

    def traffic_spent(self, run: RunId, bytes_used: int) -> None:
        self.traffic += bytes_used


@dataclass(slots=True)
class ScriptedReader:
    answers: Mapping[tuple[FieldSource, str], str]

    def read(self, snapshot: RawSnapshot, rule: FieldRule) -> str | None:
        return self.answers.get((rule.source, rule.path))


@dataclass(slots=True)
class StubFetcher:
    async def fetch(self, url: CanonicalUrl, through: ProxyLease) -> FetchedPage:
        return FetchedPage(status=200, body="<html></html>", looks_banned=False, bytes_received=1)
