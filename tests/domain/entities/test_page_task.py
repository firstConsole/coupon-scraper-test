"""Жизненный цикл задачи: владение выражено арендой, а не флагом"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coupon_scraper.domain.entities.page_task import PageTask, TaskState
from coupon_scraper.domain.errors import IllegalTransitionError, NaiveMomentError
from coupon_scraper.domain.values.identifiers import RunId, TaskId, TenantId
from coupon_scraper.domain.values.urls import CanonicalUrl

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
TTL = timedelta(minutes=5)
URL = "https://cupones.example/gift-cards/zalando"


def _task() -> PageTask:
    return PageTask(
        id=TaskId("t-7"),
        tenant_id=TenantId("acme"),
        run_id=RunId("r-42"),
        url=CanonicalUrl.parse(URL),
    )


def _leased() -> PageTask:
    task = _task()
    task.lease("worker-1", NOW, TTL)
    return task


# ── Аренда ────────────────────────────────────────────────────────────────────


def test_lease_marks_the_owner_and_the_deadline() -> None:
    task = _leased()

    assert task.state is TaskState.LEASED
    assert task.leased_by == "worker-1"
    assert task.lease_until == NOW + TTL


def test_attempt_is_counted_at_lease_not_at_failure() -> None:
    """Воркер может умереть до того, как сообщит хоть что-нибудь"""
    task = _leased()

    assert task.attempts == 1


def test_expired_lease_returns_to_the_queue() -> None:
    task = _leased()

    task.reclaim(NOW + TTL)

    assert task.state is TaskState.PENDING
    assert task.leased_by is None
    assert task.is_ready(NOW + TTL)


def test_live_lease_is_not_reclaimed() -> None:
    """Иначе двое собирали бы одну страницу и оба платили за трафик"""
    task = _leased()

    with pytest.raises(IllegalTransitionError, match="reclaim"):
        task.reclaim(NOW + TTL - timedelta(seconds=1))


def test_leasing_a_leased_task_is_refused() -> None:
    task = _leased()

    with pytest.raises(IllegalTransitionError, match="lease"):
        task.lease("worker-2", NOW, TTL)


# ── Исходы ────────────────────────────────────────────────────────────────────


def test_completion_clears_the_lease() -> None:
    task = _leased()

    task.complete(NOW + timedelta(seconds=12))

    assert task.state is TaskState.DONE
    assert (task.leased_by, task.lease_until) == (None, None)


def test_defer_returns_the_task_and_holds_it_back() -> None:
    """Адрес виноват, задача — нет: она вернётся, но не сразу"""
    task = _leased()

    task.defer(NOW, timedelta(minutes=30))

    assert task.state is TaskState.PENDING
    assert not task.is_ready(NOW)
    assert task.is_ready(NOW + timedelta(minutes=30))


def test_exhaust_is_not_death() -> None:
    """Попытки кончились, но причина могла быть временной — это разные исходы"""
    task = _leased()

    task.exhaust("адрес банится")

    assert task.state is TaskState.FAILED
    assert task.outcome_reason == "адрес банится"


def test_bury_stops_the_task_for_good() -> None:
    task = _leased()

    task.bury("дрейф вёрстки")

    assert task.state is TaskState.DEAD
    assert task.is_terminal


@pytest.mark.parametrize("action", ["complete", "exhaust", "defer"])
def test_outcome_requires_a_lease(action: str) -> None:
    """Сообщить исход по задаче, которой не владеешь, нельзя"""
    task = _task()
    arguments = {"complete": (NOW,), "exhaust": ("причина",), "defer": (NOW, TTL)}[action]

    with pytest.raises(IllegalTransitionError, match=action):
        getattr(task, action)(*arguments)


def test_finished_task_cannot_be_buried_again() -> None:
    task = _leased()
    task.complete(NOW)

    with pytest.raises(IllegalTransitionError, match="bury"):
        task.bury("поздно")


# ── Мелочи, которые ломаются молча ────────────────────────────────────────────


def test_key_follows_the_address() -> None:
    """Ключ выводится из адреса, а не хранится рядом: два источника правды разойдутся"""
    task = _task()

    assert task.key == CanonicalUrl.parse(f"{URL}?utm_source=mail").key


def test_naive_moment_is_rejected() -> None:
    with pytest.raises(NaiveMomentError):
        _task().lease("worker-1", datetime(2026, 8, 30, 12, 0), TTL)  # noqa: DTZ001


def test_lease_without_a_deadline_is_refused() -> None:
    with pytest.raises(IllegalTransitionError):
        _task().lease("worker-1", NOW, timedelta(0))
