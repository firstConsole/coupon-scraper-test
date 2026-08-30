from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from coupon_scraper.domain.errors import CurrencyMismatchError, InvalidMoneyError

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_NOT_A_NUMBER = re.compile(r"[^\d.,\-]")
_THOUSANDS = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d)")
MAX_PERCENT: Final = Decimal(100)
GROUP_SIZE: Final = 3


@dataclass(frozen=True, slots=True)
class Currency:
    """Код валюты по ISO 4217."""

    code: str

    def __post_init__(self) -> None:
        if _CURRENCY.match(self.code) is None:
            raise InvalidMoneyError(f"код валюты {self.code!r} не вида EUR")

    @classmethod
    def parse(cls, raw: str) -> Currency:
        return cls(raw.strip().upper())

    def __str__(self) -> str:
        return self.code


def _to_decimal(raw: str) -> Decimal:
    cleaned = _THOUSANDS.sub("", _NOT_A_NUMBER.sub("", raw.strip()))

    if not cleaned:
        raise InvalidMoneyError(f"в строке {raw!r} нет числа")

    dot, comma = cleaned.rfind("."), cleaned.rfind(",")

    if dot >= 0 and comma >= 0:
        fractional, thousands = (".", ",") if dot > comma else (",", ".")
        cleaned = cleaned.replace(thousands, "").replace(fractional, ".")
    elif comma >= 0:
        tail = len(cleaned) - comma - 1
        cleaned = cleaned.replace(",", "" if tail == GROUP_SIZE else ".")

    try:
        return Decimal(cleaned)
    except InvalidOperation as error:
        raise InvalidMoneyError(f"строка {raw!r} не разбирается как сумма") from error


@dataclass(frozen=True, slots=True)
class Money:
    """Сумма в конкретной валюте"""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise InvalidMoneyError(f"отрицательная сумма {self.amount}")

    @classmethod
    def parse(cls, amount: str, currency: str) -> Money:
        return cls(_to_decimal(amount), Currency.parse(currency))

    def same_currency_as(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(str(self.currency), str(other.currency))

    def is_at_most(self, other: Money) -> bool:
        self.same_currency_as(other)
        return self.amount <= other.amount

    def discount_from(self, face_value: Money) -> Percentage:
        """Насколько цена ниже номинала. Основная величина в каталоге гифт-карт."""
        self.same_currency_as(face_value)

        if face_value.amount <= 0:
            raise InvalidMoneyError("номинал нулевой — скидка от него не считается")

        return Percentage((face_value.amount - self.amount) / face_value.amount * MAX_PERCENT)

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


@dataclass(frozen=True, slots=True)
class Percentage:
    """Доля в процентах"""

    value: Decimal

    def __post_init__(self) -> None:
        if not 0 <= self.value <= MAX_PERCENT:
            raise InvalidMoneyError(f"доля {self.value} вне диапазона 0–100")

    def __str__(self) -> str:
        return f"{self.value}%"
