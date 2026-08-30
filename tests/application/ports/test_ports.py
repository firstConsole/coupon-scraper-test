"""Порты: то немногое в них, что является логикой, а не объявлением"""

from __future__ import annotations

import pytest

from coupon_scraper.application.ports.browser import (
    Challenge,
    ChallengeKind,
    Screenshot,
    Visit,
)
from coupon_scraper.application.ports.storage import ArtifactKey
from coupon_scraper.domain.errors import InvalidIdentifierError
from coupon_scraper.domain.failures import PoolExhaustedError
from coupon_scraper.domain.values.retry import Decision, decide
from coupon_scraper.domain.values.urls import CanonicalUrl

CARD = CanonicalUrl.parse("https://cupones.example/gift-cards/zalando")
HOME = CanonicalUrl.parse("https://cupones.example/")


# ── Проверки сайта ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ChallengeKind.TURNSTILE, "cf-turnstile-response"),
        (ChallengeKind.RECAPTCHA, "g-recaptcha-response"),
        (ChallengeKind.HCAPTCHA, "h-captcha-response"),
    ],
)
def test_each_challenge_has_its_own_response_field(kind: ChallengeKind, expected: str) -> None:
    """Поля разные, и их регулярно путают: токен уходит не туда и не засчитывается"""
    assert kind.response_field == expected


def test_response_fields_do_not_repeat() -> None:
    fields = {kind.response_field for kind in ChallengeKind}

    assert len(fields) == len(ChallengeKind)


def test_challenge_carries_what_the_solver_needs() -> None:
    challenge = Challenge(kind=ChallengeKind.TURNSTILE, site_key="0x4A", page_url=CARD)

    assert (challenge.site_key, challenge.page_url) == ("0x4A", CARD)


# ── Переход ───────────────────────────────────────────────────────────────────


def test_visit_to_the_requested_page_landed() -> None:
    visit = Visit(requested=CARD, final=CARD, status=200, looks_banned=False)

    assert visit.landed_on_target


def test_redirect_to_the_home_page_did_not_land() -> None:
    """Без этой проверки прогон соберёт тысячи копий главной и отчитается об успехе"""
    visit = Visit(requested=CARD, final=HOME, status=200, looks_banned=False)

    assert not visit.landed_on_target


def test_landing_is_judged_by_canonical_form() -> None:
    """Разметка кампании в итоговом адресе не означает, что нас увели"""
    visit = Visit(
        requested=CARD,
        final=CanonicalUrl.parse(f"{CARD}?utm_source=redirect"),
        status=200,
        looks_banned=False,
    )

    assert visit.landed_on_target


# ── Снимок ────────────────────────────────────────────────────────────────────


def test_identical_screenshots_share_the_address() -> None:
    """Адресация содержимым: одинаковые карточки не занимают место дважды"""
    assert Screenshot(b"png-bytes").digest == Screenshot(b"png-bytes").digest


def test_different_screenshots_differ() -> None:
    assert Screenshot(b"one").digest != Screenshot(b"two").digest


# ── Ключ артефакта ────────────────────────────────────────────────────────────


def test_key_starting_with_a_tenant_is_accepted() -> None:
    key = ArtifactKey("acme/run/r-42/card/a3f9.png")

    assert str(key).startswith("acme/")


@pytest.mark.parametrize("value", ["", "   ", "/etc/passwd", "acme/../other/secret.png"])
def test_key_leaving_the_prefix_is_refused(value: str) -> None:
    """Ключ приходит из данных: выход за префикс арендатора — чтение чужого бакета"""
    with pytest.raises(InvalidIdentifierError):
        ArtifactKey(value)


# ── Отказ пула ────────────────────────────────────────────────────────────────


def test_empty_pool_waits_instead_of_burning_attempts() -> None:
    """Собирать нечем — это не ошибка задачи и не отказ цели"""
    assert decide(PoolExhaustedError("ES")) is Decision.RETRY
