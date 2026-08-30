from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coupon_scraper.domain.values.extraction import FillRate

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coupon_scraper.application.ports.snapshot import SnapshotReader
    from coupon_scraper.domain.values.extraction import (
        ExtractionProfile,
        FieldSource,
        RawSnapshot,
    )


@dataclass(frozen=True, slots=True)
class ExtractedFields:
    values: Mapping[str, str]
    sources: Mapping[str, FieldSource]
    fill_rate: FillRate

    def missing(self, profile: ExtractionProfile) -> frozenset[str]:
        """Каких обязательных полей не хватает. Идёт в форензику при дрейфе."""
        return profile.required_fields - set(self.values)

    def drifted_from(self, expected: Mapping[str, FieldSource]) -> frozenset[str]:
        """Поля, приехавшие не оттуда, откуда приезжали раньше.

        Ранний признак: сайт сменил транспорт, разметка ещё цела, полнота ещё в
        норме — но профиль уже держится на запасном источнике.
        """
        return frozenset(
            name
            for name, source in self.sources.items()
            if name in expected and expected[name] is not source
        )


class OfferExtractor:
    def __init__(self, reader: SnapshotReader) -> None:
        self._reader = reader

    def extract(self, snapshot: RawSnapshot, profile: ExtractionProfile) -> ExtractedFields:
        values: dict[str, str] = {}
        sources: dict[str, FieldSource] = {}

        for name, lookup in profile.fields.items():
            for rule in lookup:
                found = self._reader.read(snapshot, rule)

                if found is not None and found.strip():
                    values[name] = found.strip()
                    sources[name] = rule.source
                    break

        required = profile.required_fields

        return ExtractedFields(
            values=values,
            sources=sources,
            fill_rate=FillRate.of(len(required & set(values)), len(required)),
        )
