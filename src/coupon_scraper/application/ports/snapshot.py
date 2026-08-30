from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from coupon_scraper.domain.values.extraction import FieldRule, RawSnapshot


@runtime_checkable
class SnapshotReader(Protocol):
    """Достаёт значение по правилу профиля"""

    def read(self, snapshot: RawSnapshot, rule: FieldRule) -> str | None:
        """Значение или None, если по этому правилу ничего нет"""
        ...
