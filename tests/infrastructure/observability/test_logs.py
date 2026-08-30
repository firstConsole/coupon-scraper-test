"""Проверки скраббера: что он вырезает и что обязан оставить"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest
import structlog

from coupon_scraper.bootstrap.config import ObservabilitySettings
from coupon_scraper.bootstrap.observability import configure_logging
from coupon_scraper.infrastructure.observability.logs import (
    REDACTED,
    redact_text,
    scrub_secrets,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

POSTGRES_DSN = "postgresql+asyncpg://coupon_scraper:s3cr3t-pg@db.internal:5432/coupon_scraper"
REDIS_DSN = "redis://:s3cr3t-redis@cache.internal:6379/0"
PROXY_URL = "http://proxy-user-4c2a:s3cr3t-proxy@gateway.example:10000"


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """configure_logging трогает глобальное состояние — возвращаем его на место."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        yield
    finally:
        root.handlers, root.level = handlers, level
        structlog.reset_defaults()


def _scrub(**event: Any) -> dict[str, Any]:
    return dict(scrub_secrets(None, "info", event))


# ── Что вырезается ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        (POSTGRES_DSN, "s3cr3t-pg"),
        (REDIS_DSN, "s3cr3t-redis"),
        (PROXY_URL, "s3cr3t-proxy"),
        ("GET /v1/runs?api_key=abcdef123456&limit=10", "abcdef123456"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload", "eyJhbGciOiJIUzI1NiJ9.payload"),
    ],
)
def test_secret_disappears_from_text(text: str, secret: str) -> None:
    cleaned = redact_text(text)

    assert secret not in cleaned
    assert REDACTED in cleaned


def test_sensitive_field_is_redacted_by_name() -> None:
    cleaned = _scrub(proxy_password="s3cr3t", capsolver_api_key="key-1", cookie="sid=abc")

    assert cleaned == {
        "proxy_password": REDACTED,
        "capsolver_api_key": REDACTED,
        "cookie": REDACTED,
    }


def test_nested_structures_are_cleaned() -> None:
    cleaned = _scrub(proxy={"endpoint": PROXY_URL, "password": "s3cr3t"}, dsns=[POSTGRES_DSN])

    assert "s3cr3t-proxy" not in str(cleaned)
    assert cleaned["proxy"]["password"] == REDACTED
    assert "s3cr3t-pg" not in str(cleaned["dsns"])


# ── Что обязано остаться ──────────────────────────────────────────────────────


def test_host_and_scheme_survive() -> None:
    """Лог без адреса базы бесполезен для разбора — вырезается пароль, не всё подряд"""
    cleaned = redact_text(POSTGRES_DSN)

    assert "db.internal:5432" in cleaned
    assert "postgresql+asyncpg://" in cleaned
    assert "coupon_scraper" in cleaned


def test_ordinary_values_are_untouched() -> None:
    cleaned = _scrub(run_id=17, url="https://cupones.example/gift-cards/zalando", fill_rate=0.92)

    assert cleaned == {
        "run_id": 17,
        "url": "https://cupones.example/gift-cards/zalando",
        "fill_rate": 0.92,
    }


# ── Сквозной вывод ────────────────────────────────────────────────────────────


def test_foreign_library_output_is_scrubbed(capsys: pytest.CaptureFixture[str]) -> None:
    """Секрет чаще утекает из чужого кода, чем из своего"""
    configure_logging(ObservabilitySettings(log_format="json"))

    logging.getLogger("sqlalchemy.engine").error("cannot connect to %s", POSTGRES_DSN)

    captured = capsys.readouterr()
    assert "s3cr3t-pg" not in captured.err + captured.out
    assert "db.internal" in captured.err + captured.out


def test_traceback_is_scrubbed(capsys: pytest.CaptureFixture[str]) -> None:
    """Пароль в тексте исключения уходит в вывод в обход проверки полей"""
    configure_logging(ObservabilitySettings(log_format="json"))

    try:
        raise ConnectionError(f"refused: {POSTGRES_DSN}")
    except ConnectionError:
        structlog.get_logger("worker").exception("не поднялось соединение")

    captured = capsys.readouterr()
    assert "s3cr3t-pg" not in captured.err + captured.out


def test_context_reaches_every_record(capsys: pytest.CaptureFixture[str]) -> None:
    """run_id и task_id привязываются один раз и попадают во все записи задачи"""
    configure_logging(ObservabilitySettings(log_format="json"))

    with structlog.contextvars.bound_contextvars(run_id="r-42", task_id="t-7"):
        structlog.get_logger("worker").info("страница собрана")

    captured = capsys.readouterr()
    assert '"run_id": "r-42"' in captured.err + captured.out
    assert '"task_id": "t-7"' in captured.err + captured.out
