from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Self

from coupon_scraper.domain.errors import InvalidOfferError, NaiveMomentError

if TYPE_CHECKING:
    from datetime import datetime

    from coupon_scraper.domain.values.extraction import FillRate
    from coupon_scraper.domain.values.geo import Country
    from coupon_scraper.domain.values.identifiers import OfferId
    from coupon_scraper.domain.values.money import Money, Percentage
    from coupon_scraper.domain.values.urls import CanonicalUrl


class Delivery(StrEnum):
    DIGITAL = "digital"
    PHYSICAL = "physical"


class CouponKind(StrEnum):
    CODE = "code"
    DEAL = "deal"
    FREE_SHIPPING = "free_shipping"


def _require_aware(moment: datetime | None, field_name: str) -> None:
    if moment is not None and (moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None):
        raise NaiveMomentError(field_name)


@dataclass(frozen=True, slots=True)
class Offer:
    id: OfferId
    merchant: str
    merchant_domain: str
    country: Country
    source: CanonicalUrl
    collected_at: datetime
    profile_version: int
    fill_rate: FillRate
    terms: str | None = None
    valid_until: datetime | None = None
    category: str | None = None
    screenshot_key: str | None = None

    def __post_init__(self) -> None:
        if not self.merchant.strip():
            raise InvalidOfferError("предложение без мерчанта неотличимо от чужого")

        _require_aware(self.collected_at, "collected_at")
        _require_aware(self.valid_until, "valid_until")

    def with_screenshot(self, key: str) -> Self:
        return replace(self, screenshot_key=key)

    def is_expired(self, now: datetime) -> bool:
        _require_aware(now, "now")

        return self.valid_until is not None and now >= self.valid_until


@dataclass(frozen=True, slots=True)
class GiftCardOffer(Offer):
    """Предоплаченный номинал. Ценность — номинал и цена покупки."""

    face_value: Money | None = None
    price: Money | None = None
    available_values: tuple[Money, ...] = ()
    delivery: Delivery = Delivery.DIGITAL
    in_stock: bool = True

    def __post_init__(self) -> None:
        Offer.__post_init__(self)

        if self.face_value is None or self.price is None:
            raise InvalidOfferError("у гифт-карты обязаны быть номинал и цена покупки")

        self.price.same_currency_as(self.face_value)

        for value in self.available_values:
            value.same_currency_as(self.face_value)

    @property
    def discount(self) -> Percentage:
        if self.face_value is None or self.price is None:
            raise InvalidOfferError("номинал или цена отсутствуют")

        return self.price.discount_from(self.face_value)


@dataclass(frozen=True, slots=True)
class CouponOffer(Offer):
    kind: CouponKind = CouponKind.DEAL
    code: str | None = None
    discount_percent: Percentage | None = None
    discount_amount: Money | None = None
    min_order: Money | None = None
    exclusions: str | None = None
    last_verified_at: datetime | None = None

    def __post_init__(self) -> None:
        Offer.__post_init__(self)
        _require_aware(self.last_verified_at, "last_verified_at")

        has_code = bool(self.code and self.code.strip())

        if self.kind is CouponKind.CODE and not has_code:
            raise InvalidOfferError("купон с кодом без кода — это не собранная карточка")

        if self.kind is not CouponKind.CODE and has_code:
            raise InvalidOfferError(f"у купона вида {self.kind} кода быть не должно")

        if self.discount_percent is not None and self.discount_amount is not None:
            raise InvalidOfferError("скидка задана и долей, и суммой одновременно")

        if self.min_order is not None and self.discount_amount is not None:
            self.discount_amount.same_currency_as(self.min_order)
