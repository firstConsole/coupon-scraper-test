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


class InvalidIdentifierError(DomainError):
    """Идентификатор непригоден"""

    def __init__(self, kind: str, reason: str) -> None:
        super().__init__(f"{kind}: {reason}")


class InvalidMoneyError(DomainError):
    """Денежная величина непригодна"""

    def __init__(self, reason: str) -> None:
        super().__init__(f"денежная величина непригодна: {reason}")


class CurrencyMismatchError(DomainError):
    """Сравнение или сложение сумм в разных валютах"""

    def __init__(self, left: str, right: str) -> None:
        super().__init__(f"нельзя сопоставлять {left} и {right}: это разные валюты")


class InvalidProfileError(DomainError):
    """Профиль извлечения непригоден"""

    def __init__(self, reason: str) -> None:
        super().__init__(f"профиль извлечения непригоден: {reason}")


class InvalidOfferError(DomainError):
    """Предложение противоречиво само себе"""

    def __init__(self, reason: str) -> None:
        super().__init__(f"предложение непригодно: {reason}")


class IllegalTransitionError(DomainError):
    """Переход состояния, которого в жизненном цикле задачи нет"""

    def __init__(self, current: str, action: str) -> None:
        super().__init__(f"задача в состоянии {current}: действие {action!r} недопустимо")
        self.current = current
        self.action = action
