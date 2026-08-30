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


class NaiveMomentError(DomainError):
    """Момент времени без часового пояса"""

    def __init__(self, field: str) -> None:
        super().__init__(f"{field}: момент времени должен быть с часовым поясом")


class InvalidBudgetError(DomainError):
    """Бюджет запросов, при котором адрес бесполезен"""

    def __init__(self, reason: str) -> None:
        super().__init__(f"бюджет запросов непригоден: {reason}")


class InvalidProxyIdentityError(DomainError):
    """Имя выходного адреса непригодно"""

    def __init__(self, reason: str) -> None:
        super().__init__(f"имя выходного адреса непригодно: {reason}")


class InvalidCountryError(DomainError):
    """Страна задаётся двумя буквами по ISO 3166-1"""

    def __init__(self, value: str) -> None:
        super().__init__(f"страна задаётся двумя буквами по ISO 3166-1, получено {value!r}")


class EndpointRestingError(DomainError):
    """Попытка занять адрес, который отдыхает"""

    def __init__(self, identity: str, until: str) -> None:
        super().__init__(f"адрес {identity} отдыхает до {until}")
        self.identity = identity


class InconsistentPersonaError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"личность несогласована: {reason}")


class InvalidPacingError(DomainError):
    """Параметры ритма обращений, при которых он перестаёт быть ритмом"""

    def __init__(self, reason: str) -> None:
        super().__init__(f"ритм обращений непригоден: {reason}")
