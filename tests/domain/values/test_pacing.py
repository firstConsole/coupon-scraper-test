"""Ритм обращений: ловят не скорость, а регулярность"""

from __future__ import annotations

import statistics
from datetime import timedelta
from random import Random

import pytest

from coupon_scraper.domain.errors import InvalidPacingError
from coupon_scraper.domain.values.pacing import (
    DEFAULT_MU,
    DEFAULT_SIGMA,
    Concurrency,
    PacingPolicy,
)

SAMPLES = 4000
SEED = 20260830


def _draw(policy: PacingPolicy, count: int = SAMPLES) -> list[float]:
    rnd = Random(SEED)  # noqa: S311 — распределение пауз, а не криптография
    return [policy.next_pause(rnd).total_seconds() for _ in range(count)]


# ── Распределение ─────────────────────────────────────────────────────────────


def test_pauses_are_spread_not_constant() -> None:
    """Постоянная пауза сама является сигнатурой: у человека дисперсия не ноль"""
    drawn = _draw(PacingPolicy())

    assert statistics.pstdev(drawn) > 1.0
    assert len(set(drawn)) > SAMPLES // 2


def test_median_matches_the_calculation() -> None:
    """Медиана логнормали — exp(mu); из неё считался цикл страницы"""
    median = statistics.median(_draw(PacingPolicy()))

    assert median == pytest.approx(3.32, abs=0.15)


def test_same_seed_gives_the_same_sequence() -> None:
    assert _draw(PacingPolicy(), count=50) == _draw(PacingPolicy(), count=50)


def test_tails_are_clamped_on_both_sides() -> None:
    """Снизу хвост даёт всплеск, который лимитер видит как очередь; сверху — простой"""
    policy = PacingPolicy(floor=timedelta(seconds=2), ceiling=timedelta(seconds=5))

    drawn = _draw(policy)

    assert min(drawn) >= 2.0
    assert max(drawn) <= 5.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"sigma": 0.0},
        {"floor": timedelta(0)},
        {"ceiling": timedelta(milliseconds=100)},
    ],
)
def test_degenerate_pacing_is_rejected(overrides: dict[str, object]) -> None:
    settings: dict[str, object] = {"mu": DEFAULT_MU, "sigma": DEFAULT_SIGMA} | overrides

    with pytest.raises(InvalidPacingError):
        PacingPolicy(**settings)  # type: ignore[arg-type]


# ── Регулятор нагрузки ────────────────────────────────────────────────────────


def test_growth_is_additive_and_capped() -> None:
    concurrency = Concurrency(ceiling=3.0)

    for _ in range(10):
        concurrency.report_success()

    assert concurrency.permits == 3


def test_refusal_halves_instead_of_subtracting() -> None:
    """Вычитание догоняет проблему слишком долго: цель успеет забанить адрес"""
    concurrency = Concurrency(limit=4.0, ceiling=4.0)

    concurrency.report_refusal()

    assert concurrency.limit == pytest.approx(2.0)


def test_regulator_never_stops_the_address_completely() -> None:
    concurrency = Concurrency(limit=4.0, ceiling=4.0)

    for _ in range(20):
        concurrency.report_refusal()

    assert concurrency.permits == 1


@pytest.mark.parametrize(
    "overrides",
    [{"floor": 0.0}, {"ceiling": 0.5, "floor": 1.0}, {"backoff": 1.5}, {"backoff": 0.0}],
)
def test_degenerate_regulator_is_rejected(overrides: dict[str, float]) -> None:
    with pytest.raises(InvalidPacingError):
        Concurrency(**overrides)
