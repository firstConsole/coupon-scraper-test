from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ReadinessProbe(Protocol):
    """Проверка одной зависимости"""

    @property
    def name(self) -> str:
        """Имя зависимости"""
        ...

    async def is_ready(self) -> bool:
        """Готова ли зависимость принять работу прямо сейчас."""
        ...
