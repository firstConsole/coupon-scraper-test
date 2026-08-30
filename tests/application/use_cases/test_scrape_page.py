"""Основной цикл: бан, проверка, дрейф и увод — без сети, базы и браузера"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from random import Random
from typing import TYPE_CHECKING, Any

import pytest

from coupon_scraper.application.ports.browser import Challenge, ChallengeKind, Visit
from coupon_scraper.application.services.extraction import OfferExtractor
from coupon_scraper.application.services.offers import OfferAssembler
from coupon_scraper.application.use_cases.scrape_page import (
    Approach,
    Interpretation,
    Persistence,
    ScrapePage,
)
from coupon_scraper.domain.entities.offer import GiftCardOffer
from coupon_scraper.domain.entities.page_task import PageTask
from coupon_scraper.domain.failures import NavigationTimeoutError
from coupon_scraper.domain.values.extraction import (
    ExtractionProfile,
    FieldRule,
    FieldSource,
    OfferKind,
    RawSnapshot,
    Readiness,
)
from coupon_scraper.domain.values.geo import Country
from coupon_scraper.domain.values.identifiers import RunId, TaskId, TenantId
from coupon_scraper.domain.values.money import Percentage
from coupon_scraper.domain.values.pacing import PacingPolicy
from coupon_scraper.domain.values.retry import Decision
from coupon_scraper.domain.values.urls import CanonicalUrl
from tests.application.use_cases import fakes

if TYPE_CHECKING:
    from coupon_scraper.application.use_cases.scrape_page import PageOutcome

CARD = CanonicalUrl.parse("https://cupones.example/gift-cards/zalando")
HOME = CanonicalUrl.parse("https://cupones.example/")
SNAPSHOT = RawSnapshot(payloads=("{}",), html="<div class='card'></div>")

PROFILE = ExtractionProfile(
    version=4,
    card_selector=".card",
    fields={
        "merchant": (FieldRule(source=FieldSource.PAYLOAD, path="$.merchant", required=True),),
        "face_value": (FieldRule(source=FieldSource.PAYLOAD, path="$.faceValue", required=True),),
        "price": (FieldRule(source=FieldSource.PAYLOAD, path="$.price"),),
    },
    readiness=Readiness(ready_selector=".card"),
    offer_kind=OfferKind.GIFT_CARD,
    geo=Country("ES"),
    default_currency="EUR",
)

FULL_PAGE = {
    (FieldSource.PAYLOAD, "$.merchant"): "Zalando",
    (FieldSource.PAYLOAD, "$.faceValue"): "50,00",
    (FieldSource.PAYLOAD, "$.price"): "46,50",
}

CHALLENGE = Challenge(kind=ChallengeKind.TURNSTILE, site_key="0x4A", page_url=CARD)

COLLECTED_VISIT = Visit(
    requested=CARD, final=CARD, status=200, looks_banned=False, bytes_received=2_500_000
)


class Stand:
    """Собранный сценарий вместе со всеми подделками."""

    def __init__(self, **overrides: Any) -> None:
        self.journal = fakes.Journal()
        self.page = fakes.FakePage(
            journal=self.journal,
            visit=overrides.get("visit", COLLECTED_VISIT),
            snapshot_body=SNAPSHOT,
            challenge=overrides.get("challenge"),
            open_error=overrides.get("open_error"),
        )
        self.browser = fakes.FakeBrowser(journal=self.journal, page=self.page)
        self.proxies = fakes.FakeProxyPool(journal=self.journal)
        self.captcha = fakes.FakeCaptcha(
            journal=self.journal, fails=overrides.get("captcha_fails", False)
        )
        self.artifacts = fakes.FakeArtifacts(journal=self.journal)
        self.offers = fakes.FakeOffers(journal=self.journal)
        self.uow = fakes.FakeUnitOfWork(journal=self.journal)
        self.sleeper = fakes.RecordingSleeper(journal=self.journal)
        self.metrics = fakes.FakeMetrics()

        self.scrape = ScrapePage(
            approach=Approach(
                proxies=self.proxies,
                browser=self.browser,
                captcha=self.captcha,
                pacing=PacingPolicy(),
                sleeper=self.sleeper,
                rnd=Random(20260830),  # noqa: S311 — ритм, а не криптография
            ),
            interpretation=Interpretation(
                extractor=OfferExtractor(fakes.ScriptedReader(overrides.get("answers", FULL_PAGE))),
                assembler=OfferAssembler(),
            ),
            persistence=Persistence(artifacts=self.artifacts, offers=self.offers, uow=self.uow),
            clock=fakes.FrozenClock(),
            metrics=self.metrics,
        )

    async def run(self) -> PageOutcome:
        task = PageTask(
            id=TaskId("t-7"), tenant_id=TenantId("acme"), run_id=RunId("r-42"), url=CARD
        )
        task.lease("worker-1", datetime(2026, 8, 30, 11, 0, tzinfo=UTC), timedelta(minutes=5))
        return await self.scrape.execute(task, PROFILE)


async def test_happy_path_collects_the_card() -> None:
    stand = Stand()

    outcome = await stand.run()

    assert outcome.collected
    assert outcome.decision is None
    assert len(stand.offers.saved) == 1


async def test_collected_offer_carries_what_the_page_gave() -> None:
    stand = Stand()

    await stand.run()
    offer = stand.offers.saved[0]

    assert isinstance(offer, GiftCardOffer)
    assert offer.merchant == "Zalando"
    assert offer.discount == Percentage(Decimal(7))
    assert offer.screenshot_key is not None


async def test_object_is_written_before_the_row() -> None:
    """Осиротевший снимок вычистится по сроку; строка со ссылкой в никуда сломает выдачу"""
    stand = Stand()

    await stand.run()

    assert stand.journal.index("put_screenshot") < stand.journal.index("upsert")
    assert stand.journal.index("upsert") < stand.journal.index("commit")


async def test_success_is_reported_before_the_lease_goes_back() -> None:
    """Иначе регулятор нагрузки этого адреса про удачный запрос не узнает"""
    stand = Stand()

    await stand.run()

    assert stand.journal.index("report_success") < stand.journal.index("release")


async def test_pause_comes_before_the_navigation() -> None:
    stand = Stand()

    await stand.run()

    assert stand.journal.index("pause") < stand.journal.index("open")
    assert stand.sleeper.pauses[0].total_seconds() > 0


async def test_traffic_is_metered() -> None:
    """Трафик — почти весь счёт прогона, поэтому считается на задаче"""
    stand = Stand()

    await stand.run()

    assert stand.metrics.traffic == 2_500_000


# ── Бан ───────────────────────────────────────────────────────────────────────


def _banned() -> Stand:
    return Stand(
        visit=Visit(requested=CARD, final=CARD, status=429, looks_banned=True, bytes_received=900)
    )


async def test_ban_sends_the_address_to_quarantine() -> None:
    stand = _banned()

    await stand.run()

    assert stand.proxies.quarantined == [stand.proxies.released[0]]
    assert stand.metrics.bans


async def test_ban_leaves_the_task_untouched() -> None:
    """Виноват адрес, а не задача: она уйдёт другому нетронутой"""
    stand = _banned()

    outcome = await stand.run()

    assert outcome.decision is Decision.RETRY_ELSEWHERE
    assert not stand.offers.saved
    assert stand.uow.commits == 0


# ── Проверка сайта ────────────────────────────────────────────────────────────


async def test_solved_challenge_lets_the_page_continue() -> None:
    stand = Stand(challenge=CHALLENGE)

    outcome = await stand.run()

    assert outcome.collected
    assert stand.page.tokens == ["solved-token"]
    assert stand.metrics.challenges == [True]


async def test_token_is_submitted_before_the_content_is_read() -> None:
    stand = Stand(challenge=CHALLENGE)

    await stand.run()

    assert stand.journal.index("submit_token") < stand.journal.index("snapshot")


async def test_unsolved_challenge_throws_away_the_process() -> None:
    """Личность помечена — другим токеном её не отмыть"""
    stand = Stand(challenge=CHALLENGE, captcha_fails=True)

    outcome = await stand.run()

    assert outcome.decision is Decision.RETRY_FRESH_PERSONA
    assert stand.browser.recycled
    assert stand.metrics.challenges == [False]


# ── Увод одностраничным приложением ───────────────────────────────────────────


async def test_redirect_to_the_home_page_is_not_collected() -> None:
    """Без этой проверки прогон соберёт тысячи копий главной и отчитается об успехе"""
    stand = Stand(
        visit=Visit(requested=CARD, final=HOME, status=200, looks_banned=False, bytes_received=800)
    )

    outcome = await stand.run()

    assert outcome.decision is Decision.RETRY_FRESH_SESSION
    assert not stand.offers.saved


# ── Дрейф вёрстки ─────────────────────────────────────────────────────────────


def _drifted() -> Stand:
    return Stand(answers={(FieldSource.PAYLOAD, "$.merchant"): "Zalando"})


async def test_drift_is_not_retried() -> None:
    """Повтор воспроизведёт ту же ошибку — это оплаченные загрузки впустую"""
    stand = _drifted()

    outcome = await stand.run()

    assert outcome.decision is Decision.DEAD_LETTER
    assert not stand.offers.saved


async def test_drift_keeps_the_page_for_a_human() -> None:
    """Воспроизвести состояние страницы через час невозможно — сайт уже другой"""
    stand = _drifted()

    await stand.run()

    assert stand.artifacts.forensics == [SNAPSHOT]
    assert stand.metrics.drifts == 1


async def test_drift_does_not_burn_the_address() -> None:
    """Адрес ни при чём: банить его за переезд вёрстки значит терять пул"""
    stand = _drifted()

    await stand.run()

    assert not stand.proxies.quarantined


# ── Общее для всех отказов ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stand_factory",
    [
        Stand,
        _banned,
        _drifted,
        lambda: Stand(challenge=CHALLENGE, captcha_fails=True),
        lambda: Stand(open_error=NavigationTimeoutError(str(CARD), 30_000)),
    ],
)
async def test_lease_always_goes_back(stand_factory: Any) -> None:
    """Незакрытая аренда выводит адрес из пула навсегда"""
    stand = stand_factory()

    await stand.run()

    assert len(stand.proxies.released) == 1


async def test_navigation_timeout_is_retried_as_is() -> None:
    stand = Stand(open_error=NavigationTimeoutError(str(CARD), 30_000))

    outcome = await stand.run()

    assert outcome.decision is Decision.RETRY
    assert stand.metrics.failed == ["NavigationTimeoutError"]


async def test_browser_session_is_closed_on_failure() -> None:
    stand = _banned()

    await stand.run()

    assert stand.journal.happened("session_closed")
