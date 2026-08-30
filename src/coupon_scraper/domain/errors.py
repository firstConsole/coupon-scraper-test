from __future__ import annotations


class DomainError(Exception):
    """Нарушено правило предметной области"""


class InvalidUrlError(DomainError):
    """Адрес непригоден как цель сбора"""

    def __init__(self, raw: str, reason: str) -> None:
        super().__init__(f"адрес непригоден: {reason}")
        self.raw = raw
        self.reason = reason


class InvalidTaskKeyError(DomainError):
    """Ключ задачи не похож на sha256"""

    def __init__(self, value: str) -> None:
        super().__init__(
            f"ключ задачи должен быть 64 шестнадцатеричными знаками, получено {len(value)}"
        )
