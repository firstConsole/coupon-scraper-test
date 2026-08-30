from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coupon_scraper.domain.errors import EndpointRestingError, NaiveMomentError
from coupon_scraper.domain.values.pacing import Concurrency

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from coupon_scraper.domain.values.geo import Country
    from coupon_scraper.domain.values.proxy import ProxyIdentity, RequestBudget

MAX_STRIKE_POWER: Final = 4


def _require_aware(moment: datetime, field_name: str) -> datetime:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise NaiveMomentError(field_name)

    return moment


@dataclass(slots=True)
class ProxyEndpoint:
    identity: ProxyIdentity
    geo: Country
    budget: RequestBudget
    spent: int = 0
    resting_until: datetime | None = None
    strikes: int = 0
    concurrency: Concurrency = field(default_factory=Concurrency)

    @property
    def remaining(self) -> int:
        """Сколько запросов осталось до паузы. Пулу это нужно, чтобы выбирать адрес."""
        return max(0, self.budget.limit - self.spent)

    def is_available(self, now: datetime) -> bool:
        _require_aware(now, "now")

        return self.resting_until is None or now >= self.resting_until

    def take(self, now: datetime) -> None:
        """Занять один запрос. Исчерпав бюджет, адрес уходит на паузу сам."""
        if not self.is_available(now):
            raise EndpointRestingError(str(self.identity), str(self.resting_until))

        self.spent += 1

        if self.spent >= self.budget.limit:
            self._rest(now, self.budget.cooldown)

    def report_success(self) -> None:
        self.strikes = 0

    def quarantine(self, now: datetime) -> None:
        """Замечен бан: адрес уходит с растущей паузой."""
        self.strikes += 1
        self.concurrency.report_refusal()
        self._rest(now, self.budget.cooldown * 2 ** min(self.strikes, MAX_STRIKE_POWER))

    def _rest(self, now: datetime, duration: timedelta) -> None:
        _require_aware(now, "now")

        self.resting_until = now + duration
        self.spent = 0
