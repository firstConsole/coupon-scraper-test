"""Классификация отказов и повторы: решение по типу, а не по счётчику"""

from __future__ import annotations

import statistics
from datetime import timedelta
from random import Random

import pytest

from coupon_scraper.domain.errors import InvalidPacingError
from coupon_scraper.domain.failures import (
    ChallengeUnsolvedError,
    EndpointBannedError,
    ExtractionDriftError,
    NavigationTimeoutError,
    ScrapeError,
    TargetGoneError,
    WrongDestinationError,
)
from coupon_scraper.domain.values.extraction import FillRate, RawSnapshot
from coupon_scraper.domain.values.retry import (
    DECISIONS,
    UNKNOWN_FAILURE,
    Decision,
    RetryPolicy,
    decide,
)

SEED = 20260830
DRAWS = 3000


def _drift() -> ExtractionDriftError:
    return ExtractionDriftError(
        url="https://cupones.example/gift-cards/zalando",
        fill_rate=FillRate.of(6, 10),
        profile_version=4,
        snapshot=RawSnapshot(html="<div class='card'></div>"),
    )


def _leaves(base: type[ScrapeError]) -> set[type[ScrapeError]]:
    """Типы отказов из самого пакета.

    Классы, объявленные в тестах, отсеиваются по модулю: __subclasses__ отдаёт
    и их, а порядок сборки мусора между тестами не гарантирован — проверка
    полноты карты стала бы зависеть от порядка запуска.
    """
    direct = [
        kind for kind in base.__subclasses__() if kind.__module__.startswith("coupon_scraper")
    ]
    return set(direct).union(*(_leaves(child) for child in direct)) if direct else set()


# ── Решение по типу отказа ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (EndpointBannedError("session-4c2a", 429), Decision.RETRY_ELSEWHERE),
        (ChallengeUnsolvedError("capsolver", "таймаут"), Decision.RETRY_FRESH_PERSONA),
        (WrongDestinationError("/gift-cards/zalando", "/"), Decision.RETRY_FRESH_SESSION),
        (NavigationTimeoutError("https://cupones.example/x", 30_000), Decision.RETRY),
        (TargetGoneError("https://cupones.example/x", 404), Decision.DROP),
    ],
)
def test_failure_maps_to_its_decision(failure: ScrapeError, expected: Decision) -> None:
    assert decide(failure) == expected


def test_drift_is_not_retried() -> None:
    """Повтор воспроизведёт ту же ошибку — это пять оплаченных загрузок впустую"""
    assert decide(_drift()) is Decision.DEAD_LETTER


def test_missing_page_is_an_answer_not_a_failure() -> None:
    assert decide(TargetGoneError("https://cupones.example/x", 410)) is Decision.DROP


def test_every_failure_kind_is_classified() -> None:
    """Новый тип отказа обязан появиться в карте, иначе он молча уйдёт в мёртвые письма"""
    unclassified = sorted(kind.__name__ for kind in _leaves(ScrapeError) - set(DECISIONS))

    assert not unclassified, f"не классифицированы: {unclassified}"


def test_unknown_failure_goes_to_a_human() -> None:
    """Пять попыток по неизвестной причине — пять загрузок и ни одной новой мысли"""

    class SomethingNewError(ScrapeError):
        pass

    assert decide(SomethingNewError()) is UNKNOWN_FAILURE is Decision.DEAD_LETTER


def test_drift_carries_the_snapshot() -> None:
    """Воспроизвести состояние страницы через час невозможно — сайт уже другой"""
    assert _drift().snapshot.html is not None


# ── Повторы ───────────────────────────────────────────────────────────────────


def test_window_doubles_with_every_attempt() -> None:
    policy = RetryPolicy(base=timedelta(seconds=2), ceiling=timedelta(hours=1))

    windows = [policy.window_for(attempt).total_seconds() for attempt in range(1, 6)]

    assert windows == [2, 4, 8, 16, 32]


def test_window_stops_at_the_ceiling() -> None:
    policy = RetryPolicy(base=timedelta(seconds=2), ceiling=timedelta(seconds=10))

    assert policy.window_for(20) == timedelta(seconds=10)


def test_jitter_is_full_not_a_sprinkle() -> None:
    """Без него воркеры возвращаются одной волной, которую цель видит как атаку"""
    policy = RetryPolicy(base=timedelta(seconds=8))
    rnd = Random(SEED)  # noqa: S311 — расписание повторов, а не криптография

    drawn = [policy.delay_for(3, rnd).total_seconds() for _ in range(DRAWS)]

    assert min(drawn) < 1.0
    assert max(drawn) > 31.0
    assert statistics.mean(drawn) == pytest.approx(16.0, abs=1.0)


def test_same_seed_gives_the_same_schedule() -> None:
    policy = RetryPolicy()

    def draw() -> list[float]:
        rnd = Random(SEED)  # noqa: S311
        return [policy.delay_for(n, rnd).total_seconds() for n in range(1, 6)]

    assert draw() == draw()


def test_attempts_run_out() -> None:
    policy = RetryPolicy(max_attempts=3)

    assert not policy.is_exhausted(2)
    assert policy.is_exhausted(3)


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_attempts": 0},
        {"base": timedelta(0)},
        {"ceiling": timedelta(seconds=1), "base": timedelta(seconds=5)},
    ],
)
def test_degenerate_policy_is_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(InvalidPacingError):
        RetryPolicy(**overrides)  # type: ignore[arg-type]


def test_attempts_are_numbered_from_one() -> None:
    with pytest.raises(InvalidPacingError, match="с единицы"):
        RetryPolicy().window_for(0)
