from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from coupon_scraper.domain.errors import IllegalTransitionError, NaiveMomentError

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from coupon_scraper.domain.values.identifiers import RunId, TaskId, TenantId
    from coupon_scraper.domain.values.urls import CanonicalUrl, TaskKey


class TaskState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    DONE = "done"
    FAILED = "failed"
    DEAD = "dead"


TERMINAL: frozenset[TaskState] = frozenset({TaskState.DONE, TaskState.FAILED, TaskState.DEAD})


def _require_aware(moment: datetime, field_name: str) -> None:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise NaiveMomentError(field_name)


@dataclass(slots=True)
class PageTask:
    id: TaskId
    tenant_id: TenantId
    run_id: RunId
    url: CanonicalUrl
    priority: int = 0
    state: TaskState = TaskState.PENDING
    attempts: int = 0
    leased_by: str | None = None
    lease_until: datetime | None = None
    run_after: datetime | None = None
    outcome_reason: str | None = None

    @property
    def key(self) -> TaskKey:
        return self.url.key

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    def is_ready(self, now: datetime) -> bool:
        _require_aware(now, "now")

        return self.state is TaskState.PENDING and (self.run_after is None or now >= self.run_after)

    def lease(self, worker: str, now: datetime, ttl: timedelta) -> None:
        _require_aware(now, "now")

        if not self.is_ready(now):
            raise IllegalTransitionError(self.state, "lease")

        if ttl.total_seconds() <= 0:
            raise IllegalTransitionError(self.state, "lease без срока")

        self.state = TaskState.LEASED
        self.leased_by = worker
        self.lease_until = now + ttl
        self.attempts += 1

    def is_lease_expired(self, now: datetime) -> bool:
        _require_aware(now, "now")

        return (
            self.state is TaskState.LEASED
            and self.lease_until is not None
            and now >= self.lease_until
        )

    def reclaim(self, now: datetime) -> None:
        """Вернуть протухшую аренду в очередь. Делает планировщик."""
        if not self.is_lease_expired(now):
            raise IllegalTransitionError(self.state, "reclaim")

        self._release()

    def complete(self, now: datetime) -> None:
        _require_aware(now, "now")

        if self.state is not TaskState.LEASED:
            raise IllegalTransitionError(self.state, "complete")

        self._release()
        self.state = TaskState.DONE

    def defer(self, now: datetime, delay: timedelta) -> None:
        """Вернуть в очередь с задержкой: адрес виноват, задача — нет."""
        _require_aware(now, "now")

        if self.state is not TaskState.LEASED:
            raise IllegalTransitionError(self.state, "defer")

        self._release()
        self.run_after = now + delay

    def exhaust(self, reason: str) -> None:
        if self.state is not TaskState.LEASED:
            raise IllegalTransitionError(self.state, "exhaust")

        self._release()
        self.state = TaskState.FAILED
        self.outcome_reason = reason

    def bury(self, reason: str) -> None:
        if self.is_terminal:
            raise IllegalTransitionError(self.state, "bury")

        self._release()
        self.state = TaskState.DEAD
        self.outcome_reason = reason

    def _release(self) -> None:
        self.state = TaskState.PENDING
        self.leased_by = None
        self.lease_until = None
