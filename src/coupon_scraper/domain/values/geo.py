from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from coupon_scraper.domain.errors import InvalidCountryError

CODE_LENGTH: Final = 2


@dataclass(frozen=True, slots=True)
class Country:
    """Страна по ISO 3166-1 alpha-2"""

    code: str

    def __post_init__(self) -> None:
        if len(self.code) != CODE_LENGTH or not self.code.isalpha() or not self.code.isupper():
            raise InvalidCountryError(self.code)

    @classmethod
    def parse(cls, raw: str) -> Country:
        return cls(raw.strip().upper())

    def __str__(self) -> str:
        return self.code
