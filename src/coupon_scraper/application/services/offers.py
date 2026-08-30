from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from coupon_scraper.domain.entities.offer import (
    CouponKind,
    CouponOffer,
    GiftCardOffer,
    Offer,
)
from coupon_scraper.domain.errors import InvalidOfferError
from coupon_scraper.domain.values.extraction import OfferKind
from coupon_scraper.domain.values.identifiers import OfferId
from coupon_scraper.domain.values.money import Money, Percentage

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coupon_scraper.application.services.extraction import ExtractedFields
    from coupon_scraper.domain.entities.page_task import PageTask
    from coupon_scraper.domain.values.extraction import ExtractionProfile


def _moment(raw: str | None) -> datetime | None:
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class OfferAssembler:
    def assemble(
        self,
        task: PageTask,
        profile: ExtractionProfile,
        extracted: ExtractedFields,
        collected_at: datetime,
        screenshot_key: str | None = None,
    ) -> Offer:
        values = extracted.values
        currency = values.get("currency", profile.default_currency)

        common = {
            "id": OfferId(str(task.key)),
            "merchant": values.get("merchant", ""),
            "merchant_domain": values.get("merchant_domain", ""),
            "country": profile.geo,
            "source": task.url,
            "collected_at": collected_at,
            "profile_version": profile.version,
            "fill_rate": extracted.fill_rate,
            "terms": values.get("terms"),
            "valid_until": _moment(values.get("valid_until")),
            "category": values.get("category"),
            "screenshot_key": screenshot_key,
        }

        if profile.offer_kind is OfferKind.GIFT_CARD:
            return self._gift_card(common, values, currency)

        return self._coupon(common, values, currency)

    @staticmethod
    def _gift_card(
        common: dict[str, object], values: Mapping[str, str], currency: str
    ) -> GiftCardOffer:
        face_value, price = values.get("face_value"), values.get("price")

        if face_value is None:
            raise InvalidOfferError("номинал не найден на странице")

        return GiftCardOffer(
            **common,  # type: ignore[arg-type]
            face_value=Money.parse(face_value, currency),
            price=Money.parse(price if price is not None else face_value, currency),
            in_stock=values.get("in_stock", "true").lower() not in {"false", "0", "no"},
        )

    @staticmethod
    def _coupon(common: dict[str, object], values: Mapping[str, str], currency: str) -> CouponOffer:
        code = values.get("code")
        kind = CouponKind.CODE if code else CouponKind(values.get("kind", CouponKind.DEAL))
        amount = values.get("discount_amount")
        share = values.get("discount_percent")

        return CouponOffer(
            **common,  # type: ignore[arg-type]
            kind=kind,
            code=code,
            discount_percent=Percentage(Money.parse(share, currency).amount) if share else None,
            discount_amount=Money.parse(amount, currency) if amount and not share else None,
            min_order=Money.parse(values["min_order"], currency) if "min_order" in values else None,
            exclusions=values.get("exclusions"),
        )
