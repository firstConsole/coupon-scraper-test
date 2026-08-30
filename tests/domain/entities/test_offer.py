"""Купон и гифт-карта: пустое поле означает у них противоположное"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from coupon_scraper.domain.entities.offer import CouponKind, CouponOffer, GiftCardOffer
from coupon_scraper.domain.errors import (
    CurrencyMismatchError,
    InvalidOfferError,
    NaiveMomentError,
)
from coupon_scraper.domain.values.extraction import FillRate
from coupon_scraper.domain.values.geo import Country
from coupon_scraper.domain.values.identifiers import OfferId
from coupon_scraper.domain.values.money import Currency, Money, Percentage
from coupon_scraper.domain.values.urls import CanonicalUrl

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
EUR = Currency("EUR")


def _eur(amount: str) -> Money:
    return Money(Decimal(amount), EUR)


def _common(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": OfferId("offer-1"),
        "merchant": "Zalando",
        "merchant_domain": "zalando.es",
        "country": Country("ES"),
        "source": CanonicalUrl.parse("https://cupones.example/gift-cards/zalando"),
        "collected_at": NOW,
        "profile_version": 4,
        "fill_rate": FillRate.of(10, 10),
    }
    return base | overrides


def _gift_card(**overrides: Any) -> GiftCardOffer:
    fields: dict[str, Any] = {"face_value": _eur("50.00"), "price": _eur("46.50")}
    return GiftCardOffer(**_common(**(fields | overrides)))


def _coupon(**overrides: Any) -> CouponOffer:
    fields: dict[str, Any] = {"kind": CouponKind.CODE, "code": "ZAL15AUG"}
    return CouponOffer(**_common(**(fields | overrides)))


# ── Гифт-карта ────────────────────────────────────────────────────────────────


def test_gift_card_knows_its_discount() -> None:
    assert _gift_card().discount == Percentage(Decimal(7))


def test_gift_card_without_face_value_is_refused() -> None:
    with pytest.raises(InvalidOfferError, match="номинал и цена"):
        _gift_card(face_value=None)


def test_gift_card_mixing_currencies_is_refused() -> None:
    with pytest.raises(CurrencyMismatchError):
        _gift_card(price=Money(Decimal("46.50"), Currency("USD")))


def test_available_values_share_the_currency() -> None:
    with pytest.raises(CurrencyMismatchError):
        _gift_card(available_values=(Money(Decimal(25), Currency("USD")),))


# ── Купон ─────────────────────────────────────────────────────────────────────


def test_coupon_with_a_code_carries_it() -> None:
    assert _coupon().code == "ZAL15AUG"


def test_coupon_of_kind_code_without_a_code_is_refused() -> None:
    """Это не собранная карточка, а пропущенное поле — молчать о нём нельзя"""
    with pytest.raises(InvalidOfferError, match="без кода"):
        _coupon(code=None)


@pytest.mark.parametrize("kind", [CouponKind.DEAL, CouponKind.FREE_SHIPPING])
def test_coupon_without_a_code_must_not_have_one(kind: CouponKind) -> None:
    with pytest.raises(InvalidOfferError, match="кода быть не должно"):
        _coupon(kind=kind, code="ZAL15AUG")


def test_discount_is_either_a_share_or_a_sum() -> None:
    with pytest.raises(InvalidOfferError, match="и долей, и суммой"):
        _coupon(discount_percent=Percentage(Decimal(15)), discount_amount=_eur("10.00"))


# ── Общее ─────────────────────────────────────────────────────────────────────


def test_offer_without_a_merchant_is_refused() -> None:
    with pytest.raises(InvalidOfferError, match="без мерчанта"):
        _gift_card(merchant="  ")


def test_expiry_is_recognised() -> None:
    """Сайт показывает просроченное; собираем как есть, но отличать обязаны"""
    offer = _gift_card(valid_until=NOW + timedelta(days=1))

    assert not offer.is_expired(NOW)
    assert offer.is_expired(NOW + timedelta(days=2))


def test_offer_without_expiry_never_expires() -> None:
    assert not _gift_card().is_expired(NOW + timedelta(days=3650))


@pytest.mark.parametrize("field", ["collected_at", "valid_until"])
def test_naive_moments_are_rejected(field: str) -> None:
    with pytest.raises(NaiveMomentError, match=field):
        _gift_card(**{field: datetime(2026, 8, 30, 12, 0)})  # noqa: DTZ001
