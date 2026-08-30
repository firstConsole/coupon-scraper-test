from __future__ import annotations

import re
from contextlib import suppress
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Final

import structlog
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Response, Route

from coupon_scraper.application.ports.browser import (
    Challenge,
    ChallengeKind,
    Screenshot,
    Visit,
)
from coupon_scraper.domain.errors import InvalidUrlError
from coupon_scraper.domain.failures import NavigationTimeoutError
from coupon_scraper.domain.values.extraction import RawSnapshot
from coupon_scraper.domain.values.urls import CanonicalUrl

if TYPE_CHECKING:
    from playwright.async_api import Page

    from coupon_scraper.domain.values.extraction import Readiness
    from coupon_scraper.infrastructure.browser.humanise import Humaniser

BAN_STATUSES: Final = frozenset({401, 403, 407, 409, 429})
BAN_MARKERS: Final = ("cf-browser-verification", "challenge-platform", "Access denied")
BLOCKED_TYPES: Final = frozenset({"font", "media", "websocket"})
BLOCKED_HOSTS: Final = (
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "facebook.net",
    "hotjar.com",
    "yandex.ru/metrika",
)

CHALLENGE_HOSTS: Final = {
    "challenges.cloudflare.com": ChallengeKind.TURNSTILE,
    "www.google.com/recaptcha": ChallengeKind.RECAPTCHA,
    "hcaptcha.com": ChallengeKind.HCAPTCHA,
}

IMAGES_SETTLED: Final = """
(selector) => {
  const card = document.querySelector(selector);
  if (!card) return false;
  return [...card.querySelectorAll('img')].every(i => i.complete && i.naturalWidth > 0);
}
"""
_SITE_KEY = re.compile(r"(?:sitekey|k)=([\w\-]+)")
_log = structlog.get_logger("browser.page")


class PlaywrightPage:
    def __init__(self, page: Page, humaniser: Humaniser, navigation_timeout_ms: int) -> None:
        self._page = page
        self._humaniser = humaniser
        self._timeout_ms = navigation_timeout_ms
        self._payloads: list[str] = []
        self._seen: list[str] = []
        self._challenge: Challenge | None = None
        self._bytes = 0

        page.on("response", self._capture)

    async def install_gate(self) -> None:
        await self._page.route("**/*", self._gate)

    async def open(self, url: CanonicalUrl) -> Visit:
        self._payloads.clear()
        self._seen.clear()
        self._bytes = 0

        try:
            response = await self._page.goto(
                str(url), wait_until="commit", timeout=self._timeout_ms
            )
        except PlaywrightError as error:
            raise NavigationTimeoutError(str(url), self._timeout_ms) from error

        status = response.status if response is not None else None
        body = await self._safe_content()

        return Visit(
            requested=url,
            final=self._final_url(url),
            status=status,
            looks_banned=self._looks_banned(status, body),
            bytes_received=self._bytes,
        )

    async def open_from(self, listing: CanonicalUrl, card_selector: str) -> Visit:
        visit = await self.open(listing)

        if not visit.looks_banned:
            await self._humaniser.click(self._page.locator(card_selector).first)

        return Visit(
            requested=listing,
            final=self._final_url(listing),
            status=visit.status,
            looks_banned=visit.looks_banned,
            bytes_received=self._bytes,
        )

    async def settle(self, readiness: Readiness) -> None:
        pattern = readiness.data_url_pattern

        if pattern is not None and not self._already_seen(pattern):
            with suppress(PlaywrightError):
                await self._page.wait_for_event(
                    "response",
                    predicate=lambda response: fnmatchcase(response.url, pattern),
                    timeout=readiness.timeout_ms,
                )

        if readiness.ready_selector is not None:
            await self._page.wait_for_selector(
                readiness.ready_selector, state="visible", timeout=readiness.timeout_ms
            )

        if readiness.skeleton_selector is not None:
            await self._page.wait_for_selector(
                readiness.skeleton_selector, state="detached", timeout=readiness.timeout_ms
            )

    async def detect_challenge(self) -> Challenge | None:
        return self._challenge

    async def submit_token(self, challenge: Challenge, token: str) -> None:
        await self._page.evaluate(
            """([field, value]) => {
                const input = document.querySelector(`[name="${field}"]`)
                    ?? Object.assign(document.createElement('input'),
                                     {type: 'hidden', name: field});
                input.value = value;
                if (!input.isConnected) document.body.appendChild(input);
                window.__challengeCallback?.(value);
            }""",
            [challenge.kind.response_field, token],
        )

    async def snapshot(self) -> RawSnapshot:
        html = await self._safe_content()

        return RawSnapshot(
            payloads=tuple(self._payloads),
            embedded=html,
            html=html,
        )

    async def screenshot_card(self, selector: str) -> Screenshot:
        card = self._page.locator(selector).first
        await self._humaniser.scroll_to(card)

        with suppress(PlaywrightError):
            await self._page.wait_for_function(IMAGES_SETTLED, arg=selector, timeout=10_000)

        return Screenshot(await card.screenshot(scale="css", type="png"))

    def _already_seen(self, pattern: str) -> bool:
        return any(fnmatchcase(url, pattern) for url in self._seen)

    async def _capture(self, response: Response) -> None:
        self._seen.append(response.url)
        self._bytes += int(response.headers.get("content-length") or 0)

        if kind := self._challenge_kind(response.url):
            self._challenge = Challenge(
                kind=kind,
                site_key=self._site_key(response.url),
                page_url=self._final_url(None),
            )
            return

        if "application/json" not in (response.headers.get("content-type") or ""):
            return

        with suppress(PlaywrightError, UnicodeDecodeError):
            body = await response.text()
            self._bytes += len(body.encode())
            self._payloads.append(body)

    async def _gate(self, route: Route) -> None:
        request = route.request

        if request.resource_type in BLOCKED_TYPES or any(
            host in request.url for host in BLOCKED_HOSTS
        ):
            await route.abort()
            return

        await route.continue_()

    async def _safe_content(self) -> str:
        with suppress(PlaywrightError):
            return await self._page.content()

        return ""

    def _final_url(self, fallback: CanonicalUrl | None) -> CanonicalUrl:
        try:
            return CanonicalUrl.parse(self._page.url)
        except InvalidUrlError:
            _log.debug("итоговый адрес неразбираем", url=self._page.url)
            return (
                fallback if fallback is not None else CanonicalUrl.parse("https://invalid.local/")
            )

    @staticmethod
    def _looks_banned(status: int | None, body: str) -> bool:
        if status in BAN_STATUSES:
            return True

        return any(marker in body for marker in BAN_MARKERS)

    @staticmethod
    def _challenge_kind(url: str) -> ChallengeKind | None:
        return next((kind for host, kind in CHALLENGE_HOSTS.items() if host in url), None)

    @staticmethod
    def _site_key(url: str) -> str:
        found = _SITE_KEY.search(url)
        return found.group(1) if found is not None else ""
