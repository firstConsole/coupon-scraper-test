"""Личность выводится из адреса и не меняется, пока живёт адрес"""

from __future__ import annotations

import pytest

from coupon_scraper.domain.values.geo import Country
from coupon_scraper.domain.values.proxy import ProxyIdentity
from coupon_scraper.infrastructure.browser.personas import (
    PersonaFactory,
    UnsupportedCountryError,
)

SPAIN = Country("ES")


def _persona(identity: str, country: Country = SPAIN) -> object:
    return PersonaFactory().for_identity(ProxyIdentity(identity), country)


def test_same_address_always_gets_the_same_profile() -> None:
    """Случайная личность на каждой странице — не маскировка, а аномалия:
    у живого пользователя устройство не меняется между двумя карточками"""
    assert _persona("session-4c2a") == _persona("session-4c2a")


def test_different_addresses_get_different_profiles() -> None:
    profiles = {_persona(f"session-{n}") for n in range(24)}

    assert len(profiles) > 1


def test_profile_matches_the_country_of_the_address() -> None:
    persona = PersonaFactory().for_identity(ProxyIdentity("session-1"), SPAIN)

    assert str(persona.locale) == "es-ES"
    assert persona.timezone in {"Europe/Madrid", "Atlantic/Canary"}


@pytest.mark.parametrize(
    ("code", "language"), [("RU", "ru"), ("KZ", "kk"), ("UA", "uk"), ("BY", "be")]
)
def test_cis_profiles_are_built(code: str, language: str) -> None:
    persona = PersonaFactory().for_identity(ProxyIdentity("session-1"), Country(code))

    assert str(persona.locale) == f"{language}-{code}"


def test_unknown_country_is_refused_rather_than_guessed() -> None:
    """Угадать профиль страны дешевле, чем сжечь на этом пул, — но только на вид"""
    with pytest.raises(UnsupportedCountryError):
        _persona("session-1", Country("JP"))


def test_device_parts_are_consistent_with_each_other() -> None:
    """Firefox на Windows не выдаёт шрифты Ubuntu, а Retina не бывает на офисном мониторе"""
    for n in range(24):
        persona = PersonaFactory().for_identity(ProxyIdentity(f"session-{n}"), SPAIN)
        mac = "Mac OS X" in persona.user_agent

        assert ("Helvetica" in persona.fonts) is mac
        assert (persona.screen.device_pixel_ratio > 1) is mac
