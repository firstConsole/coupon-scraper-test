from __future__ import annotations

from dataclasses import dataclass
from random import Random  # noqa: TC003
from typing import TYPE_CHECKING

from coupon_scraper.domain.failures import (
    ChallengeUnsolvedError,
    EndpointBannedError,
    ExtractionDriftError,
    ScrapeError,
    WrongDestinationError,
)
from coupon_scraper.domain.values.retry import Decision, decide

if TYPE_CHECKING:
    from coupon_scraper.application.ports.browser import BrowserRuntime, PageSession, Screenshot
    from coupon_scraper.application.ports.captcha import CaptchaSolver
    from coupon_scraper.application.ports.clock import Clock, Sleeper
    from coupon_scraper.application.ports.metrics import MetricsSink
    from coupon_scraper.application.ports.proxies import ProxyLease, ProxyPool
    from coupon_scraper.application.ports.repositories import OfferRepository
    from coupon_scraper.application.ports.storage import ArtifactKey, ArtifactStorage
    from coupon_scraper.application.ports.unit_of_work import UnitOfWork
    from coupon_scraper.application.services.extraction import ExtractedFields, OfferExtractor
    from coupon_scraper.application.services.offers import OfferAssembler
    from coupon_scraper.domain.entities.page_task import PageTask
    from coupon_scraper.domain.values.extraction import ExtractionProfile
    from coupon_scraper.domain.values.identifiers import OfferId, TaskId
    from coupon_scraper.domain.values.pacing import PacingPolicy


@dataclass(frozen=True, slots=True)
class Approach:
    proxies: ProxyPool
    browser: BrowserRuntime
    captcha: CaptchaSolver
    pacing: PacingPolicy
    sleeper: Sleeper
    rnd: Random


@dataclass(frozen=True, slots=True)
class Interpretation:
    extractor: OfferExtractor
    assembler: OfferAssembler


@dataclass(frozen=True, slots=True)
class Persistence:
    artifacts: ArtifactStorage
    offers: OfferRepository
    uow: UnitOfWork


@dataclass(frozen=True, slots=True)
class PageOutcome:
    task: TaskId
    offer: OfferId | None = None
    screenshot: ArtifactKey | None = None
    failure: ScrapeError | None = None

    @property
    def collected(self) -> bool:
        return self.failure is None

    @property
    def decision(self) -> Decision | None:
        return None if self.failure is None else decide(self.failure)


class ScrapePage:
    def __init__(
        self,
        *,
        approach: Approach,
        interpretation: Interpretation,
        persistence: Persistence,
        clock: Clock,
        metrics: MetricsSink,
    ) -> None:
        self._approach = approach
        self._reading = interpretation
        self._store = persistence
        self._clock = clock
        self._metrics = metrics

    async def execute(self, task: PageTask, profile: ExtractionProfile) -> PageOutcome:
        lease = await self._approach.proxies.acquire(task.run_id, profile.geo)

        try:
            extracted, shot = await self._collect(task, profile, lease)
        except EndpointBannedError as banned:
            await self._approach.proxies.quarantine(lease, banned)
            self._metrics.endpoint_banned(task.run_id, banned.identity)
            return PageOutcome(task=task.id, failure=banned)
        except ChallengeUnsolvedError as unsolved:
            await self._approach.browser.recycle(lease)
            self._metrics.challenge_seen(task.run_id, solved=False)
            return PageOutcome(task=task.id, failure=unsolved)
        except ExtractionDriftError as drift:
            await self._store.artifacts.put_forensics(
                task.tenant_id, task.run_id, task.key, drift.snapshot
            )
            self._metrics.drift_seen(task.run_id, profile.version)
            return PageOutcome(task=task.id, failure=drift)
        except ScrapeError as failure:
            self._metrics.page_failed(task.run_id, type(failure).__name__)
            return PageOutcome(task=task.id, failure=failure)
        else:
            key = await self._store.artifacts.put_screenshot(task.tenant_id, task.run_id, shot)
            offer = self._reading.assembler.assemble(
                task, profile, extracted, self._clock.now(), str(key)
            )

            async with self._store.uow:
                await self._store.offers.upsert(offer)
                await self._store.uow.commit()

            await self._approach.proxies.report_success(lease)
            self._metrics.page_collected(task.run_id, extracted.fill_rate)

            return PageOutcome(task=task.id, offer=offer.id, screenshot=key)
        finally:
            await self._approach.proxies.release(lease)

    async def _collect(
        self, task: PageTask, profile: ExtractionProfile, lease: ProxyLease
    ) -> tuple[ExtractedFields, Screenshot]:
        async with self._approach.browser.session(lease) as page:
            pause = self._approach.pacing.next_pause(self._approach.rnd)
            await self._approach.sleeper.sleep(pause)

            visit = await page.open(task.url)
            self._metrics.traffic_spent(task.run_id, visit.bytes_received)

            if visit.looks_banned:
                raise EndpointBannedError(str(lease.identity), visit.status)

            if not visit.landed_on_target:
                raise WrongDestinationError(str(task.url), str(visit.final))

            await self._pass_challenge(page, lease, task)

            await page.settle(profile.readiness)
            snapshot = await page.snapshot()
            extracted = self._reading.extractor.extract(snapshot, profile)

            if not extracted.fill_rate.meets(profile.min_fill_rate):
                raise ExtractionDriftError(
                    url=str(task.url),
                    fill_rate=extracted.fill_rate,
                    profile_version=profile.version,
                    snapshot=snapshot,
                )

            return extracted, await page.screenshot_card(profile.card_selector)

    async def _pass_challenge(self, page: PageSession, lease: ProxyLease, task: PageTask) -> None:
        challenge = await page.detect_challenge()

        if challenge is None:
            return

        token = await self._approach.captcha.solve(challenge, through=lease)
        await page.submit_token(challenge, token)
        self._metrics.challenge_seen(task.run_id, solved=True)
