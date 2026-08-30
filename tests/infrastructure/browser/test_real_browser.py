"""Дымовой прогон против настоящего Chromium.

Проверяет не цель, а то, что адаптер вообще работает: реальный движок, реальный
DOM, реальные байты снимка. Против настоящего сайта он не прогонялся — доступа
нет, и в README это сказано прямо.

Страница подаётся как data:-адрес, а не с локального сервера: доменная проверка
адресов отвергает петлю и приватные сети, и правильно делает — обходить
собственную защиту ради удобства теста было бы худшим из решений.
"""

from __future__ import annotations

from random import Random
from typing import TYPE_CHECKING
from urllib.parse import quote

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from coupon_scraper.domain.values.extraction import Readiness
from coupon_scraper.infrastructure.browser.humanise import Humaniser
from coupon_scraper.infrastructure.browser.page import PlaywrightPage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import timedelta

PAGE = """
<html><body style="margin:0">
  <div class="skeleton">загрузка…</div>
  <div class="card" style="width:320px;height:180px;background:#eee;padding:16px">
    <h2>Zalando</h2><p class="value">50,00 €</p><p class="terms">Válida en zalando.es</p>
  </div>
  <script>setTimeout(() => document.querySelector('.skeleton').remove(), 50)</script>
</body></html>
"""

DATA_URL = "data:text/html;charset=utf-8," + quote(PAGE)


class NoSleep:
    """Ждать в дымовом прогоне нечего."""

    async def sleep(self, delay: timedelta) -> None:
        return


@pytest.fixture
async def session() -> AsyncIterator[PlaywrightPage]:
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(headless=True)
        except PlaywrightError as error:  # pragma: no cover
            pytest.skip(f"нужен playwright install chromium: {error}")

        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(DATA_URL)

        yield PlaywrightPage(page, Humaniser(page, Random(1), NoSleep()), 5_000)  # noqa: S311

        await browser.close()


async def test_card_is_photographed(session: PlaywrightPage) -> None:
    shot = await session.screenshot_card(".card")

    assert shot.body.startswith(b"\x89PNG")
    assert len(shot.digest) == 64


async def test_snapshot_carries_the_markup(session: PlaywrightPage) -> None:
    snapshot = await session.snapshot()

    assert snapshot.html is not None
    assert "Zalando" in snapshot.html


async def test_settle_waits_for_the_skeleton_to_go(session: PlaywrightPage) -> None:
    """Заглушка отрисована раньше карточки и совпала бы с её селектором"""
    await session.settle(
        Readiness(ready_selector=".card", skeleton_selector=".skeleton", timeout_ms=5_000)
    )

    assert await session._page.locator(".skeleton").count() == 0


async def test_no_challenge_on_a_plain_page(session: PlaywrightPage) -> None:
    assert await session.detect_challenge() is None
