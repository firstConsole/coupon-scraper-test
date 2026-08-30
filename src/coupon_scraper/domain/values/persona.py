from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from coupon_scraper.domain.errors import InconsistentPersonaError
from coupon_scraper.domain.values.geo import Country

COUNTRY_TIMEZONES: Final[MappingProxyType[str, frozenset[str]]] = MappingProxyType(
    {
        # СНГ
        "AM": frozenset({"Asia/Yerevan"}),
        "AZ": frozenset({"Asia/Baku"}),
        "BY": frozenset({"Europe/Minsk"}),
        "GE": frozenset({"Asia/Tbilisi"}),
        "KG": frozenset({"Asia/Bishkek"}),
        "KZ": frozenset(
            {
                "Asia/Almaty",
                "Asia/Aqtau",
                "Asia/Aqtobe",
                "Asia/Atyrau",
                "Asia/Oral",
                "Asia/Qostanay",
                "Asia/Qyzylorda",
            }
        ),
        "MD": frozenset({"Europe/Chisinau"}),
        "RU": frozenset(
            {
                "Europe/Kaliningrad",
                "Europe/Moscow",
                "Europe/Kirov",
                "Europe/Volgograd",
                "Europe/Astrakhan",
                "Europe/Saratov",
                "Europe/Ulyanovsk",
                "Europe/Samara",
                "Asia/Yekaterinburg",
                "Asia/Omsk",
                "Asia/Novosibirsk",
                "Asia/Barnaul",
                "Asia/Tomsk",
                "Asia/Novokuznetsk",
                "Asia/Krasnoyarsk",
                "Asia/Irkutsk",
                "Asia/Chita",
                "Asia/Yakutsk",
                "Asia/Khandyga",
                "Asia/Vladivostok",
                "Asia/Ust-Nera",
                "Asia/Magadan",
                "Asia/Sakhalin",
                "Asia/Srednekolymsk",
                "Asia/Kamchatka",
                "Asia/Anadyr",
            }
        ),
        "TJ": frozenset({"Asia/Dushanbe"}),
        "TM": frozenset({"Asia/Ashgabat"}),
        "UA": frozenset({"Europe/Kyiv", "Europe/Simferopol"}),
        "UZ": frozenset({"Asia/Samarkand", "Asia/Tashkent"}),
        # Европа
        "DE": frozenset({"Europe/Berlin"}),
        "ES": frozenset({"Europe/Madrid", "Atlantic/Canary"}),
        "FR": frozenset({"Europe/Paris"}),
        "GB": frozenset({"Europe/London"}),
        "IT": frozenset({"Europe/Rome"}),
        "NL": frozenset({"Europe/Amsterdam"}),
        "PL": frozenset({"Europe/Warsaw"}),
        "PT": frozenset({"Europe/Lisbon", "Atlantic/Madeira", "Atlantic/Azores"}),
        # Америка
        "BR": frozenset({"America/Sao_Paulo", "America/Manaus", "America/Fortaleza"}),
        "CA": frozenset({"America/Toronto", "America/Vancouver", "America/Halifax"}),
        "MX": frozenset({"America/Mexico_City", "America/Tijuana", "America/Monterrey"}),
        "US": frozenset(
            {
                "America/New_York",
                "America/Chicago",
                "America/Denver",
                "America/Los_Angeles",
                "America/Phoenix",
            }
        ),
    }
)

_LOCALE = re.compile(r"^(?P<language>[a-z]{2})-(?P<region>[A-Z]{2})$")
MIN_SCREEN_SIDE: Final = 640
MAX_SCREEN_SIDE: Final = 7680
MIN_FONTS: Final = 5
MIN_PIXEL_RATIO: Final = 0.5
MAX_PIXEL_RATIO: Final = 4.0
SELF_DEFEATING_MARKERS: Final = ("HeadlessChrome", "PhantomJS", "Electron", "python-requests")


@dataclass(frozen=True, slots=True)
class Locale:
    """Языковой тег вида es-ES. Регион в нём и есть страна — сверять его бесплатно."""

    tag: str

    def __post_init__(self) -> None:
        if _LOCALE.match(self.tag) is None:
            raise InconsistentPersonaError(f"локаль {self.tag!r} не вида es-ES")

    @property
    def region(self) -> Country:
        matched = _LOCALE.match(self.tag)
        if matched is None:
            raise InconsistentPersonaError(self.tag)
        return Country(matched["region"])

    def __str__(self) -> str:
        return self.tag


@dataclass(frozen=True, slots=True)
class Screen:
    width: int
    height: int
    avail_height: int
    device_pixel_ratio: float = 1.0

    def __post_init__(self) -> None:
        for name, side in (("ширина", self.width), ("высота", self.height)):
            if not MIN_SCREEN_SIDE <= side <= MAX_SCREEN_SIDE:
                raise InconsistentPersonaError(f"{name} экрана {side} неправдоподобна")

        if not 0 < self.avail_height < self.height:
            raise InconsistentPersonaError(
                "рабочая область равна высоте экрана — у живого пользователя есть панель задач"
            )

        if not MIN_PIXEL_RATIO <= self.device_pixel_ratio <= MAX_PIXEL_RATIO:
            raise InconsistentPersonaError(f"масштаб {self.device_pixel_ratio} неправдоподобен")


@dataclass(frozen=True, slots=True)
class Persona:
    user_agent: str
    locale: Locale
    timezone: str
    screen: Screen
    fonts: tuple[str, ...]
    webgl_vendor: str
    country: Country

    def __post_init__(self) -> None:
        if not self.user_agent.strip():
            raise InconsistentPersonaError("пустой User-Agent")

        if marker := next((m for m in SELF_DEFEATING_MARKERS if m in self.user_agent), None):
            raise InconsistentPersonaError(f"User-Agent содержит {marker!r} и выдаёт сам себя")

        if self.locale.region != self.country:
            raise InconsistentPersonaError(
                f"локаль {self.locale} против страны адреса {self.country}"
            )

        allowed = COUNTRY_TIMEZONES.get(self.country.code)
        if allowed is None:
            raise InconsistentPersonaError(
                f"часовые пояса страны {self.country} неизвестны — "
                f"добавьте её в каталог, а не угадывайте"
            )

        if self.timezone not in allowed:
            raise InconsistentPersonaError(
                f"часовой пояс {self.timezone!r} не принадлежит стране {self.country}"
            )

        if len(self.fonts) < MIN_FONTS:
            raise InconsistentPersonaError(
                f"набор из {len(self.fonts)} шрифтов беднее любой настоящей системы"
            )

        if not self.webgl_vendor.strip():
            raise InconsistentPersonaError("пустой вендор WebGL")
