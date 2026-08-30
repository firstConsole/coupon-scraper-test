from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from coupon_scraper.presentation.lifecycle import GracefulShutdown

IDLE_DELAY_SECONDS = 1.0


class PollingService(ABC):
    def __init__(self, *, name: str, idle_delay: float = IDLE_DELAY_SECONDS) -> None:
        self._name = name
        self._idle_delay = idle_delay
        self._log = structlog.get_logger(name)

    @property
    def name(self) -> str:
        return self._name

    async def run(self, shutdown: GracefulShutdown) -> None:
        self._log.info("процесс поднялся", service=self._name)

        while not shutdown.requested:
            if not await self.handle_batch():
                await shutdown.sleep(self._idle_delay)

        self._log.info("процесс остановлен", service=self._name, reason=shutdown.reason)

    @abstractmethod
    async def handle_batch(self) -> bool: ...
