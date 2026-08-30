"""Подделки удовлетворяют портам структурно.

Проверка неполная — runtime_checkable сверяет наличие методов, а не подписи, —
но ловит самое частое: порт переименовали, а реализацию забыли.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from coupon_scraper.application.ports.captcha import CaptchaSolver
from coupon_scraper.application.ports.clock import Clock
from coupon_scraper.application.ports.http import FetchedPage, HttpFetcher
from coupon_scraper.application.ports.metrics import MetricsSink
from coupon_scraper.application.ports.proxies import ProxyLease, ProxyPool
from coupon_scraper.application.ports.repositories import (
    ExtractionProfileRepository,
    OfferRepository,
    PageTaskRepository,
)
from coupon_scraper.application.ports.storage import ArtifactStorage
from coupon_scraper.domain.values.geo import Country
from coupon_scraper.domain.values.proxy import ProxyIdentity
from coupon_scraper.domain.values.urls import CanonicalUrl

if TYPE_CHECKING:
    from coupon_scraper.domain.values.identifiers import RunId

LEASE = ProxyLease(
    identity=ProxyIdentity("session-1"),
    geo=Country("ES"),
    expires_at=datetime(2026, 8, 30, 12, 0, tzinfo=UTC) + timedelta(minutes=5),
)
PAGE = CanonicalUrl.parse("https://cupones.example/gift-cards/zalando")


class FrozenClock:
    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class NullMetrics:
    def page_collected(self, run: RunId, fill_rate: object) -> None: ...
    def page_failed(self, run: RunId, reason: str) -> None: ...
    def drift_seen(self, run: RunId, profile_version: int) -> None: ...
    def endpoint_banned(self, run: RunId, identity: str) -> None: ...
    def challenge_seen(self, run: RunId, *, solved: bool) -> None: ...
    def traffic_spent(self, run: RunId, bytes_used: int) -> None: ...


class StubFetcher:
    async def fetch(self, url: CanonicalUrl, through: ProxyLease) -> FetchedPage:
        return FetchedPage(status=200, body="<html></html>", looks_banned=False, bytes_received=13)


class StubSolver:
    @property
    def name(self) -> str:
        return "stub"

    async def solve(self, challenge: object, through: ProxyLease) -> str:
        return "token"


def test_frozen_clock_satisfies_the_port() -> None:
    clock = FrozenClock(datetime(2026, 8, 30, 12, 0, tzinfo=UTC))

    assert isinstance(clock, Clock)
    assert clock.now().tzinfo is not None


def test_null_metrics_satisfies_the_port() -> None:
    assert isinstance(NullMetrics(), MetricsSink)


def test_stubs_satisfy_their_ports() -> None:
    assert isinstance(StubFetcher(), HttpFetcher)
    assert isinstance(StubSolver(), CaptchaSolver)


@pytest.mark.parametrize("port", [ProxyPool, ArtifactStorage, PageTaskRepository, OfferRepository])
def test_bare_object_does_not_satisfy_a_port(port: type) -> None:
    """Иначе проверка выше ничего не значила бы"""
    assert not isinstance(object(), port)


def test_profile_repository_carries_the_canary_lookup() -> None:
    """Профили живут отдельно от задач: у версии профиля своя жизнь с канарейкой"""
    assert hasattr(ExtractionProfileRepository, "by_task")
    assert not hasattr(PageTaskRepository, "by_task")


def test_lease_carries_no_credentials() -> None:
    """Логин и пароль провайдера остаются в инфраструктуре, которая открывает соединение"""
    fields = ProxyLease.__dataclass_fields__

    assert set(fields) == {"identity", "geo", "expires_at"}


async def test_fetcher_returns_traffic_for_metering() -> None:
    """Байты считаются на задаче: трафик — почти весь счёт прогона"""
    page = await StubFetcher().fetch(PAGE, LEASE)

    assert page.bytes_received > 0
