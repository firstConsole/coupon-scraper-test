from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Final

import psutil
import structlog
from playwright.async_api import async_playwright

from coupon_scraper.infrastructure.browser.humanise import Humaniser
from coupon_scraper.infrastructure.browser.page import PlaywrightPage
from coupon_scraper.infrastructure.browser.personas import PersonaFactory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from random import Random

    from playwright.async_api import BrowserContext, Playwright

    from coupon_scraper.application.ports.clock import Sleeper
    from coupon_scraper.application.ports.proxies import ProxyLease
    from coupon_scraper.domain.values.persona import Persona
    from coupon_scraper.domain.values.proxy import ProxyIdentity

MEGABYTE: Final = 1024 * 1024

_log = structlog.get_logger("browser.pool")


class ProxyCredentials:
    def __init__(self, endpoint: str, username: str, password: str) -> None:
        self._endpoint = endpoint
        self._username = username
        self._password = password

    def for_identity(self, identity: ProxyIdentity) -> dict[str, str]:
        return {
            "server": self._endpoint,
            "username": f"{self._username}-session-{identity}",
            "password": self._password,
        }


class BrowserProcess:
    def __init__(self, context: BrowserContext, persona: Persona, profile_dir: Path) -> None:
        self.context = context
        self.persona = persona
        self.profile_dir = profile_dir
        self.pages_served = 0

    @property
    def resident_megabytes(self) -> float:
        try:
            root = psutil.Process(self.context.browser.process.pid)  # type: ignore[union-attr]
        except (psutil.Error, AttributeError):
            return 0.0

        family = [root, *root.children(recursive=True)]

        return sum(member.memory_info().rss for member in family) / MEGABYTE

    async def close(self) -> None:
        await self.context.close()


class PlaywrightRuntime:
    def __init__(
        self,
        *,
        engine: str,
        headless: bool,
        pool_size: int,
        max_pages_per_process: int,
        max_rss_mb: int,
        navigation_timeout_ms: int,
        credentials: ProxyCredentials,
        sleeper: Sleeper,
        rnd: Random,
        personas: PersonaFactory | None = None,
    ) -> None:
        self._engine = engine
        self._headless = headless
        self._max_pages = max_pages_per_process
        self._max_rss_mb = max_rss_mb
        self._timeout_ms = navigation_timeout_ms
        self._credentials = credentials
        self._sleeper = sleeper
        self._rnd = rnd
        self._personas = personas or PersonaFactory()
        self._slots = asyncio.Semaphore(pool_size)
        self._processes: dict[str, BrowserProcess] = {}
        self._playwright: Playwright | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()

    async def stop(self) -> None:
        for process in list(self._processes.values()):
            await process.close()

        self._processes.clear()

        if self._playwright is not None:
            await self._playwright.stop()

    @asynccontextmanager
    async def session(self, lease: ProxyLease) -> AsyncIterator[PlaywrightPage]:
        async with self._slots:
            process = await self._checkout(lease)
            page = await process.context.new_page()
            session = PlaywrightPage(
                page, Humaniser(page, self._rnd, self._sleeper), self._timeout_ms
            )
            await session.install_gate()

            try:
                yield session
            finally:
                await page.close()
                process.pages_served += 1
                await self._retire_if_worn(lease, process)

    async def recycle(self, lease: ProxyLease) -> None:
        process = self._processes.pop(str(lease.identity), None)

        if process is not None:
            _log.info("личность выброшена", identity=str(lease.identity))
            await process.close()

    async def _checkout(self, lease: ProxyLease) -> BrowserProcess:
        key = str(lease.identity)

        if (existing := self._processes.get(key)) is not None:
            return existing

        if self._playwright is None:
            message = "пул не запущен: вызовите start() до первой сессии"
            raise RuntimeError(message)

        persona = self._personas.for_identity(lease.identity, lease.geo)
        profile_dir = Path(mkdtemp(prefix=f"scraper-{key}-"))
        launcher = getattr(
            self._playwright, "firefox" if self._engine == "camoufox" else self._engine
        )

        context = await launcher.launch_persistent_context(
            profile_dir,
            headless=self._headless,
            proxy=self._credentials.for_identity(lease.identity),
            user_agent=persona.user_agent,
            locale=str(persona.locale),
            timezone_id=persona.timezone,
            viewport={"width": persona.screen.width, "height": persona.screen.avail_height},
            screen={"width": persona.screen.width, "height": persona.screen.height},
            device_scale_factor=persona.screen.device_pixel_ratio,
        )

        self._processes[key] = BrowserProcess(context, persona, profile_dir)

        return self._processes[key]

    async def _retire_if_worn(self, lease: ProxyLease, process: BrowserProcess) -> None:
        """Браузер течёт — это его нормальный режим, а не повод для расследования."""
        resident = process.resident_megabytes

        if process.pages_served < self._max_pages and resident < self._max_rss_mb:
            return

        _log.info(
            "процесс отправлен на покой",
            identity=str(lease.identity),
            pages=process.pages_served,
            rss_mb=round(resident),
        )
        await self.recycle(lease)
