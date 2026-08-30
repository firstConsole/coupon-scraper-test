from __future__ import annotations

import asyncio
import contextlib
import signal
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

STOP_SIGNALS: Iterable[signal.Signals] = (signal.SIGTERM, signal.SIGINT)
SIGNAL_NAMES = MappingProxyType({int(item): item.name for item in STOP_SIGNALS})


class GracefulShutdown:
    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._reason: str | None = None

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        return self._reason

    def request(self, reason: str) -> None:
        if not self._event.is_set():
            self._reason = reason
            self._event.set()

    async def wait(self) -> None:
        await self._event.wait()

    async def sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._event.wait(), timeout=seconds)

    @contextlib.contextmanager
    def installed(self) -> Iterator[GracefulShutdown]:
        loop = asyncio.get_running_loop()
        attached: list[signal.Signals] = []

        for item in STOP_SIGNALS:
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(item, self.request, SIGNAL_NAMES[int(item)])
                attached.append(item)

        try:
            yield self
        finally:
            for item in attached:
                with contextlib.suppress(NotImplementedError):
                    loop.remove_signal_handler(item)
