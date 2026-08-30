"""Мягкая остановка: начатое доводится до конца, новое не берётся"""

from __future__ import annotations

import asyncio
import time

from coupon_scraper.presentation.lifecycle import GracefulShutdown
from coupon_scraper.presentation.planner.runner import Planner
from coupon_scraper.presentation.service import PollingService
from coupon_scraper.presentation.worker.runner import Worker

BATCH_SECONDS = 0.05
IDLE_SECONDS = 30.0


class CountingService(PollingService):
    """Считает пачки и позволяет посмотреть, доработала ли последняя."""

    def __init__(self) -> None:
        super().__init__(name="counting", idle_delay=IDLE_SECONDS)
        self.started = 0
        self.finished = 0

    async def handle_batch(self) -> bool:
        self.started += 1
        await asyncio.sleep(BATCH_SECONDS)
        self.finished += 1
        return True


class IdleService(PollingService):
    """Работы нет никогда — процесс уходит в долгую паузу."""

    def __init__(self) -> None:
        super().__init__(name="idle", idle_delay=IDLE_SECONDS)

    async def handle_batch(self) -> bool:
        return False


async def test_signal_interrupts_the_idle_pause() -> None:
    """Иначе процесс досыпает свой интервал после SIGTERM и его убивают по таймауту"""
    shutdown = GracefulShutdown()
    started = time.monotonic()

    task = asyncio.create_task(IdleService().run(shutdown))
    await asyncio.sleep(0)
    shutdown.request("SIGTERM")
    await asyncio.wait_for(task, timeout=1.0)

    assert time.monotonic() - started < IDLE_SECONDS


async def test_batch_in_flight_is_finished() -> None:
    """Брошенная аренда означает повторный сбор той же страницы за те же деньги"""
    shutdown = GracefulShutdown()
    service = CountingService()

    task = asyncio.create_task(service.run(shutdown))
    await asyncio.sleep(BATCH_SECONDS / 2)
    shutdown.request("SIGTERM")
    await asyncio.wait_for(task, timeout=1.0)

    assert service.started == service.finished == 1


async def test_reason_survives_until_the_farewell_record() -> None:
    shutdown = GracefulShutdown()
    shutdown.request("SIGTERM")
    shutdown.request("SIGINT")

    assert shutdown.requested
    assert shutdown.reason == "SIGTERM"


async def test_handlers_are_removed_after_use() -> None:
    """Оставленный обработчик пережил бы процесс, ради которого его ставили"""
    shutdown = GracefulShutdown()

    with shutdown.installed():
        pass

    assert not shutdown.requested


def test_services_declare_their_names() -> None:
    assert (Worker().name, Planner().name) == ("worker", "planner")
