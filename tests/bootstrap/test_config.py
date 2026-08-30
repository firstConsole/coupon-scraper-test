"""Конфигурация: что она обязана отвергнуть и о чём обязана молчать"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

from coupon_scraper.bootstrap.config import (
    MIN_ENCRYPTION_KEY_BYTES,
    ConfigurationError,
    Environment,
    Settings,
    load_settings,
)

if TYPE_CHECKING:
    from pathlib import Path

ENCRYPTION_KEY = "k" * MIN_ENCRYPTION_KEY_BYTES

MINIMAL: dict[str, Any] = {
    "postgres": {"password": "pg-local-9f2c41"},
    "redis": {"password": "redis-local-7b18de"},
    "storage": {
        "bucket": "coupon-shots",
        "access_key_id": "minio-key-3d91",
        "secret_access_key": "minio-secret-a4f7",
    },
    "security": {"secrets_encryption_key": ENCRYPTION_KEY},
}


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **(MINIMAL | overrides))  # type: ignore[call-arg]


def _deployed(**overrides: Any) -> Settings:
    """Полностью пригодная к бою конфигурация — база для проверок «а если убрать»."""
    deployed: dict[str, Any] = {
        "environment": "production",
        "browser": {"engine": "camoufox"},
        "proxy": {
            "endpoint": "gateway.example:10000",
            "username": "proxy-user-4c2a",
            "password": "proxy-pass-51ab",
            "country": "es",
        },
        "captcha": {"capsolver_api_key": "capsolver-key-8f13"},
        "security": {
            "secrets_encryption_key": ENCRYPTION_KEY,
            "allowed_target_hosts": ("cupones.example",),
        },
        "observability": {"log_format": "json"},
    }
    return _settings(**(deployed | overrides))


def _env_pairs(**overrides: str) -> dict[str, str]:
    pairs = {
        "POSTGRES__PASSWORD": "pg-local-9f2c41",
        "REDIS__PASSWORD": "redis-local-7b18de",
        "STORAGE__BUCKET": "coupon-shots",
        "STORAGE__ACCESS_KEY_ID": "minio-key-3d91",
        "STORAGE__SECRET_ACCESS_KEY": "minio-secret-a4f7",
        "SECURITY__SECRETS_ENCRYPTION_KEY": ENCRYPTION_KEY,
    }
    return pairs | overrides


# ── Что должно собираться ─────────────────────────────────────────────────────


def test_minimal_local_configuration_builds() -> None:
    settings = _settings()

    assert settings.environment is Environment.LOCAL
    assert settings.proxy.request_budget == 15
    assert settings.proxy.cooldown_seconds == 900


def test_deployed_configuration_builds() -> None:
    assert _deployed().environment.is_production


def test_country_is_normalised() -> None:
    settings = _settings(proxy={"country": "es"})

    assert settings.proxy.country == "ES"


def test_dsn_escapes_special_characters() -> None:
    settings = _settings(postgres={"password": "p@ss:word/1"})

    assert "p%40ss%3Aword%2F1" in settings.postgres.dsn


# ── Что должно отвергаться ────────────────────────────────────────────────────


def test_missing_required_section_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, redis={"password": "x" * 12})  # type: ignore[arg-type,call-arg]


def test_placeholder_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="POSTGRES__PASSWORD"):
        _settings(postgres={"password": "change-me"})


def test_short_encryption_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="32 байт"):
        _settings(security={"secrets_encryption_key": "short"})


def test_country_must_be_two_letters() -> None:
    with pytest.raises(ValidationError, match="ISO 3166-1"):
        _settings(proxy={"country": "esp"})


def test_unknown_key_is_rejected() -> None:
    """Опечатка в имени переменной обязана ломать старт, а не молча ничего не делать"""
    with pytest.raises(ValidationError):
        _settings(pgostgres={"password": "x" * 12})


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"debug": True}, "DEBUG"),
        ({"observability": {"log_format": "console"}}, "LOG_FORMAT"),
        ({"browser": {"engine": "chromium"}}, "chromium"),
    ],
)
def test_production_refuses_to_start_dirty(overrides: dict[str, Any], expected: str) -> None:
    """Лучше не подняться, чем подняться дырявым"""
    with pytest.raises(ValidationError, match=expected):
        _deployed(**overrides)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"proxy": {}}, "PROXY"),
        ({"security": {"secrets_encryption_key": ENCRYPTION_KEY}}, "ALLOWED_TARGET_HOSTS"),
        ({"captcha": {"enabled": True}}, "capsolver"),
    ],
)
def test_deployed_environment_needs_paid_access(overrides: dict[str, Any], expected: str) -> None:
    with pytest.raises(ValidationError, match=expected):
        _deployed(**overrides)


# ── О чём конфигурация обязана молчать ────────────────────────────────────────


def test_secrets_do_not_leak_into_text() -> None:
    settings = _settings()

    assert MINIMAL["postgres"]["password"] not in repr(settings)
    assert MINIMAL["storage"]["secret_access_key"] not in str(settings.storage)


def test_error_names_the_variable_but_not_its_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Текст ошибки уходит в логи, в задачи и в чаты — значению там не место"""
    bad_key = "definitely-too-short-key"
    monkeypatch.chdir(tmp_path)
    for name, value in _env_pairs(SECURITY__SECRETS_ENCRYPTION_KEY=bad_key).items():
        monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError) as failure:
        load_settings()

    message = str(failure.value)
    assert "SECURITY__SECRETS_ENCRYPTION_KEY" in message
    assert bad_key not in message


def test_load_settings_reads_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name, value in _env_pairs().items():
        monkeypatch.setenv(name, value)

    assert load_settings().postgres.database == "coupon_scraper"
