"""Личность браузера: признаки обязаны сойтись между собой"""

from __future__ import annotations

from typing import Any

import pytest

from coupon_scraper.domain.errors import InconsistentPersonaError
from coupon_scraper.domain.values.geo import Country
from coupon_scraper.domain.values.persona import Locale, Persona, Screen

FONTS = ("Arial", "Helvetica", "DejaVu Sans", "Liberation Serif", "Noto Sans", "Ubuntu")
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:141.0) Gecko/20100101 Firefox/141.0"


def _screen(**overrides: Any) -> Screen:
    return Screen(**({"width": 1920, "height": 1080, "avail_height": 1040} | overrides))


def _persona(**overrides: Any) -> Persona:
    base: dict[str, Any] = {
        "user_agent": UA,
        "locale": Locale("es-ES"),
        "timezone": "Europe/Madrid",
        "screen": _screen(),
        "fonts": FONTS,
        "webgl_vendor": "Mozilla",
        "country": Country("ES"),
    }
    return Persona(**(base | overrides))


def test_consistent_persona_is_built() -> None:
    assert _persona().locale.region == Country("ES")


# ── Согласованность с географией ──────────────────────────────────────────────


def test_locale_region_must_match_the_country_of_the_address() -> None:
    """Регион в языковом теге и есть страна — сверять его ничего не стоит"""
    with pytest.raises(InconsistentPersonaError, match="против страны адреса"):
        _persona(locale=Locale("ru-RU"))


def test_timezone_must_belong_to_the_country() -> None:
    """Испанский адрес с московским поясом заметнее любого отдельного маркера"""
    with pytest.raises(InconsistentPersonaError, match="не принадлежит стране"):
        _persona(timezone="Europe/Moscow")


def test_unknown_country_fails_closed() -> None:
    """Угадать часовой пояс страны — сжечь пул; отказ дешевле"""
    with pytest.raises(InconsistentPersonaError, match="добавьте её в каталог"):
        _persona(locale=Locale("ja-JP"), country=Country("JP"), timezone="Asia/Tokyo")


# ── Признаки, которые выдают сами себя ────────────────────────────────────────


@pytest.mark.parametrize("agent", ["HeadlessChrome/141.0", "python-requests/2.32", "PhantomJS/2.1"])
def test_self_defeating_user_agent_is_rejected(agent: str) -> None:
    with pytest.raises(InconsistentPersonaError, match="выдаёт сам себя"):
        _persona(user_agent=agent)


def test_full_height_working_area_is_rejected() -> None:
    """Равенство рабочей области и высоты экрана означает отсутствие панели задач"""
    with pytest.raises(InconsistentPersonaError, match="панель задач"):
        _screen(avail_height=1080)


def test_poor_font_set_is_rejected() -> None:
    with pytest.raises(InconsistentPersonaError, match="беднее любой настоящей системы"):
        _persona(fonts=("Arial", "Helvetica"))


# ── Мелочи проверки ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("tag", ["es", "ES-es", "spanish", "es_ES", "es-ESP"])
def test_malformed_locale_is_rejected(tag: str) -> None:
    with pytest.raises(InconsistentPersonaError):
        Locale(tag)


@pytest.mark.parametrize(
    "overrides",
    [
        {"width": 320},
        {"height": 240},
        {"width": 99_999},
        {"avail_height": 0},
        {"device_pixel_ratio": 12.0},
    ],
)
def test_implausible_screen_is_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(InconsistentPersonaError):
        _screen(**overrides)


@pytest.mark.parametrize(("field", "value"), [("user_agent", "  "), ("webgl_vendor", " ")])
def test_empty_marker_is_rejected(field: str, value: str) -> None:
    with pytest.raises(InconsistentPersonaError):
        _persona(**{field: value})
