"""Правила страницы, которые проверяются без браузера"""

from __future__ import annotations

import pytest

from coupon_scraper.application.ports.browser import ChallengeKind
from coupon_scraper.domain.values.proxy import ProxyIdentity
from coupon_scraper.infrastructure.browser.humanise import _bezier
from coupon_scraper.infrastructure.browser.page import PlaywrightPage
from coupon_scraper.infrastructure.browser.runtime import ProxyCredentials


@pytest.mark.parametrize("status", [401, 403, 407, 429])
def test_refusal_codes_read_as_a_ban(status: int) -> None:
    assert PlaywrightPage._looks_banned(status, "<html></html>")


def test_challenge_page_under_code_200_reads_as_a_ban() -> None:
    """Заглушка приходит с обычным кодом — по одному статусу её не отличить"""
    assert PlaywrightPage._looks_banned(200, "<div id='challenge-platform'></div>")


def test_normal_page_is_not_a_ban() -> None:
    assert not PlaywrightPage._looks_banned(200, "<div class='card'>Zalando</div>")


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://challenges.cloudflare.com/turnstile/v0/api.js", ChallengeKind.TURNSTILE),
        ("https://www.google.com/recaptcha/api2/anchor?k=6Lc", ChallengeKind.RECAPTCHA),
        ("https://hcaptcha.com/1/api.js", ChallengeKind.HCAPTCHA),
        ("https://cupones.example/api/cards", None),
    ],
)
def test_challenge_is_recognised_by_the_request_it_makes(
    url: str, kind: ChallengeKind | None
) -> None:
    """Перехваченный запрос к провайдеру однозначнее любого признака в разметке"""
    assert PlaywrightPage._challenge_kind(url) == kind


def test_site_key_is_taken_from_the_request() -> None:
    key = PlaywrightPage._site_key("https://www.google.com/recaptcha/api2/anchor?k=6LcAbCd")

    assert key == "6LcAbCd"


def test_curve_starts_and_ends_where_asked() -> None:
    start, end, bend = (0.0, 0.0), (100.0, 50.0), (20.0, 90.0)

    assert _bezier(start, end, bend, 0.0) == start
    assert _bezier(start, end, bend, 1.0) == end


def test_curve_bends_away_from_the_straight_line() -> None:
    """Прямая с постоянной скоростью — признак не менее заметный, чем маркер в JS"""
    middle = _bezier((0.0, 0.0), (100.0, 0.0), (50.0, 80.0), 0.5)

    assert middle[1] > 1.0


def test_session_name_travels_in_the_login_not_in_the_lease() -> None:
    """Учётные данные подставляет тот слой, который открывает соединение"""
    credentials = ProxyCredentials("gw.example:10000", "acme", "s3cr3t")

    connection = credentials.for_identity(ProxyIdentity("session-4c2a"))

    assert connection["username"].endswith("session-4c2a")
    assert connection["server"] == "gw.example:10000"
