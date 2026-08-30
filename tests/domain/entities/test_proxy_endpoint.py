"""Бюджет и карантин адреса — правило сбора, а не деталь Redis"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coupon_scraper.domain.entities.proxy_endpoint import MAX_STRIKE_POWER, ProxyEndpoint
from coupon_scraper.domain.errors import (
    EndpointRestingError,
    InvalidBudgetError,
    InvalidCountryError,
    InvalidProxyIdentityError,
    NaiveMomentError,
)
from coupon_scraper.domain.values.geo import Country
from coupon_scraper.domain.values.proxy import ProxyIdentity, RequestBudget

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
COOLDOWN = timedelta(minutes=15)
LIMIT = 15


def _endpoint(limit: int = LIMIT) -> ProxyEndpoint:
    return ProxyEndpoint(
        identity=ProxyIdentity("session-4c2a"),
        geo=Country("ES"),
        budget=RequestBudget(limit=limit, cooldown=COOLDOWN),
    )


def _spend(endpoint: ProxyEndpoint, times: int, *, at: datetime = NOW) -> None:
    for _ in range(times):
        endpoint.take(at)


# ── Бюджет ────────────────────────────────────────────────────────────────────


def test_budget_is_spent_request_by_request() -> None:
    endpoint = _endpoint()

    _spend(endpoint, 5)

    assert endpoint.remaining == LIMIT - 5
    assert endpoint.is_available(NOW)


def test_exhausted_budget_sends_the_address_to_rest_by_itself() -> None:
    """Пул не обязан помнить, сколько адрес истратил, — адрес помнит сам"""
    endpoint = _endpoint()

    _spend(endpoint, LIMIT)

    assert not endpoint.is_available(NOW)
    assert endpoint.resting_until == NOW + COOLDOWN
    assert endpoint.remaining == LIMIT


def test_rest_ends_by_itself() -> None:
    endpoint = _endpoint()
    _spend(endpoint, LIMIT)

    assert endpoint.is_available(NOW + COOLDOWN)


def test_taking_a_resting_address_is_a_mistake_of_the_caller() -> None:
    """Пул обязан спросить is_available; молчаливое ожидание скрыло бы его ошибку"""
    endpoint = _endpoint()
    _spend(endpoint, LIMIT)

    with pytest.raises(EndpointRestingError, match="session-4c2a"):
        endpoint.take(NOW)


def test_budget_starts_over_after_the_rest() -> None:
    endpoint = _endpoint()
    _spend(endpoint, LIMIT)

    endpoint.take(NOW + COOLDOWN)

    assert endpoint.remaining == LIMIT - 1


# ── Карантин ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("bans", "multiplier"), [(1, 2), (2, 4), (3, 8), (4, 16)])
def test_quarantine_doubles_with_every_ban(bans: int, multiplier: int) -> None:
    endpoint = _endpoint()

    for _ in range(bans):
        endpoint.quarantine(NOW)

    assert endpoint.resting_until == NOW + COOLDOWN * multiplier


def test_quarantine_has_a_ceiling() -> None:
    """Без потолка неудачный день выводит адрес из пула навсегда, а платим мы за пул"""
    endpoint = _endpoint()

    for _ in range(MAX_STRIKE_POWER + 5):
        endpoint.quarantine(NOW)

    assert endpoint.resting_until == NOW + COOLDOWN * 2**MAX_STRIKE_POWER


def test_success_resets_the_streak_but_not_the_budget() -> None:
    """Успех говорит о подозрительности и ничего не говорит о нагрузке"""
    endpoint = _endpoint()
    _spend(endpoint, 3)
    endpoint.quarantine(NOW)

    endpoint.report_success()

    assert endpoint.strikes == 0
    assert endpoint.remaining == LIMIT  # карантин обнулил счётчик запросов


def test_streak_survives_until_a_success() -> None:
    endpoint = _endpoint()

    endpoint.quarantine(NOW)
    endpoint.quarantine(NOW + timedelta(hours=2))

    assert endpoint.strikes == 2


# ── Что домен не принимает ────────────────────────────────────────────────────


@pytest.mark.parametrize("limit", [0, -1])
def test_budget_must_allow_at_least_one_request(limit: int) -> None:
    with pytest.raises(InvalidBudgetError):
        RequestBudget(limit=limit, cooldown=COOLDOWN)


def test_cooldown_must_be_a_real_pause() -> None:
    with pytest.raises(InvalidBudgetError, match="нулевой длины"):
        RequestBudget(limit=LIMIT, cooldown=timedelta(0))


@pytest.mark.parametrize("value", ["", "   ", "user:pass@gateway:10000", "session 4c2a"])
def test_identity_must_not_look_like_credentials(value: str) -> None:
    """Имя попадает в логи, в метрики и в базу — учётные данные в нём это три утечки"""
    with pytest.raises(InvalidProxyIdentityError):
        ProxyIdentity(value)


@pytest.mark.parametrize("value", ["", "E", "ESP", "es", "E1"])
def test_country_must_be_iso_alpha2(value: str) -> None:
    with pytest.raises(InvalidCountryError):
        Country(value)


def test_country_parses_loose_input() -> None:
    assert Country.parse(" es ") == Country("ES")


@pytest.mark.parametrize("method", ["is_available", "take", "quarantine"])
def test_naive_moment_is_rejected(method: str) -> None:
    """Наивная дата даёт молча неверный карантин при переводе часов"""
    endpoint = _endpoint()

    with pytest.raises(NaiveMomentError):
        getattr(endpoint, method)(datetime(2026, 8, 30, 12, 0))  # noqa: DTZ001
