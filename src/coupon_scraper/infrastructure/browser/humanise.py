from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from random import Random

    from playwright.async_api import Locator, Page

    from coupon_scraper.application.ports.clock import Sleeper

CURVE_STEPS: Final = 24
SCROLL_STEPS: Final = 8
OVERSHOOT: Final = 12


def _bezier(
    start: tuple[float, float],
    end: tuple[float, float],
    bend: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    inverse = 1 - t
    x = inverse**2 * start[0] + 2 * inverse * t * bend[0] + t**2 * end[0]
    y = inverse**2 * start[1] + 2 * inverse * t * bend[1] + t**2 * end[1]

    return x, y


class Humaniser:
    def __init__(self, page: Page, rnd: Random, sleeper: Sleeper) -> None:
        self._page = page
        self._rnd = rnd
        self._sleeper = sleeper
        self._at = (0.0, 0.0)

    async def scroll_to(self, locator: Locator) -> None:
        box = await locator.bounding_box()

        if box is None:
            await locator.scroll_into_view_if_needed()
            return

        remaining = box["y"] - self._rnd.uniform(80, 200)

        for step in range(SCROLL_STEPS, 0, -1):
            portion = remaining * step / sum(range(1, SCROLL_STEPS + 1))
            await self._page.mouse.wheel(0, portion)
            await self._pause(0.04, 0.12)

        await locator.scroll_into_view_if_needed()

    async def move_to(self, locator: Locator) -> None:
        box = await locator.bounding_box()

        if box is None:
            return

        target = (
            box["x"] + box["width"] * self._rnd.uniform(0.3, 0.7),
            box["y"] + box["height"] * self._rnd.uniform(0.3, 0.7),
        )
        bend = (
            (self._at[0] + target[0]) / 2 + self._rnd.uniform(-120, 120),
            (self._at[1] + target[1]) / 2 + self._rnd.uniform(-120, 120),
        )
        overshot = (target[0] + self._rnd.uniform(-OVERSHOOT, OVERSHOOT), target[1])

        for step in range(1, CURVE_STEPS + 1):
            x, y = _bezier(self._at, overshot, bend, step / CURVE_STEPS)
            await self._page.mouse.move(x, y)
            await self._pause(0.008, 0.03)

        await self._page.mouse.move(*target)
        self._at = target

    async def click(self, locator: Locator) -> None:
        await self.scroll_to(locator)
        await self.move_to(locator)
        await self._pause(0.08, 0.25)
        await locator.click()

    async def _pause(self, low: float, high: float) -> None:
        await self._sleeper.sleep(timedelta(seconds=self._rnd.uniform(low, high)))
