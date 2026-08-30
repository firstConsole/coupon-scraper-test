from __future__ import annotations

from hashlib import sha256
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coupon_scraper.domain.values.persona import (
    COUNTRY_TIMEZONES,
    Locale,
    Persona,
    Screen,
)

if TYPE_CHECKING:
    from coupon_scraper.domain.values.geo import Country
    from coupon_scraper.domain.values.proxy import ProxyIdentity

DEVICES: Final = (
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
        Screen(width=1920, height=1080, avail_height=1040, device_pixel_ratio=1.0),
        ("Arial", "Calibri", "Segoe UI", "Tahoma", "Times New Roman", "Verdana"),
        "Google Inc. (NVIDIA)",
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
        Screen(width=1366, height=768, avail_height=728, device_pixel_ratio=1.0),
        ("Arial", "Calibri", "Segoe UI", "Tahoma", "Times New Roman", "Verdana"),
        "Google Inc. (Intel)",
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:141.0) Gecko/20100101 Firefox/141.0",
        Screen(width=1512, height=982, avail_height=957, device_pixel_ratio=2.0),
        ("Helvetica", "Helvetica Neue", "Menlo", "SF Pro Text", "Times", "Geneva"),
        "Apple Inc.",
    ),
)

COUNTRY_LANGUAGE: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "AM": "hy",
        "AZ": "az",
        "BR": "pt",
        "BY": "be",
        "CA": "en",
        "DE": "de",
        "ES": "es",
        "FR": "fr",
        "GB": "en",
        "GE": "ka",
        "IT": "it",
        "KG": "ky",
        "KZ": "kk",
        "MD": "ro",
        "MX": "es",
        "NL": "nl",
        "PL": "pl",
        "PT": "pt",
        "RU": "ru",
        "TJ": "tg",
        "TM": "tk",
        "UA": "uk",
        "US": "en",
        "UZ": "uz",
    }
)


class UnsupportedCountryError(Exception):
    def __init__(self, country: str) -> None:
        super().__init__(f"личность для страны {country} не собрать: нет в каталоге")


class PersonaFactory:
    def for_identity(self, identity: ProxyIdentity, geo: Country) -> Persona:
        language = COUNTRY_LANGUAGE.get(geo.code)
        zones = COUNTRY_TIMEZONES.get(geo.code)

        if language is None or zones is None:
            raise UnsupportedCountryError(geo.code)

        seed = int.from_bytes(sha256(str(identity).encode()).digest()[:8], "big")
        user_agent, screen, fonts, vendor = DEVICES[seed % len(DEVICES)]

        return Persona(
            user_agent=user_agent,
            locale=Locale(f"{language}-{geo.code}"),
            timezone=sorted(zones)[seed % len(zones)],
            screen=screen,
            fonts=fonts,
            webgl_vendor=vendor,
            country=geo,
        )
