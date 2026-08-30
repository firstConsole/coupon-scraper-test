from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Self
from urllib.parse import quote_plus

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import Iterator

MIN_ENCRYPTION_KEY_BYTES = 32
COUNTRY_CODE_LENGTH = 2
PLACEHOLDER_SECRETS = frozenset(
    {"", "-", "change-me", "changeme", "example", "password", "secret", "test", "todo", "xxx"}
)


class ConfigurationError(Exception):
    """Приложение не может собрать конфигурацию и не должно стартовать"""


class Environment(StrEnum):
    """Окружение, в котором запущено приложение"""

    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production(self) -> bool:
        return self is Environment.PRODUCTION

    @property
    def is_deployed(self) -> bool:
        """Staging и production ходят на настоящую цель, а значит платят за трафик."""
        return self is not Environment.LOCAL


def _unset_empty_values(data: Any) -> Any:
    """Пустая строка в .env означает «не задано», а не «задано пустым»."""
    if not isinstance(data, dict):
        return data

    return {
        key: value
        for key, value in data.items()
        if not (isinstance(value, str) and not value.strip())
    }


class Section(BaseModel):
    """Общий предок секций конфигурации"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _treat_empty_strings_as_unset(cls, data: Any) -> Any:
        return _unset_empty_values(data)


class PostgresSettings(Section):
    """Состояние прогонов, очередь задач, собранные офферы и их история."""

    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    user: str = "coupon_scraper"
    password: SecretStr
    database: str = "coupon_scraper"
    pool_size: int = Field(default=10, ge=1, le=100)

    @property
    def dsn(self) -> str:
        password = quote_plus(self.password.get_secret_value())
        return (
            f"postgresql+asyncpg://{quote_plus(self.user)}:{password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


class RedisSettings(Section):
    """Бюджеты выходных адресов, карантины, предохранитель, лидерство планировщика."""

    host: str = "localhost"
    port: int = Field(default=6379, ge=1, le=65535)
    password: SecretStr
    database: int = Field(default=0, ge=0, le=15)

    @property
    def dsn(self) -> str:
        return (
            f"redis://:{quote_plus(self.password.get_secret_value())}"
            f"@{self.host}:{self.port}/{self.database}"
        )


class StorageSettings(Section):
    """Снимки карточек и форензика по сбоям: S3-совместимое хранилище."""

    bucket: str
    access_key_id: SecretStr
    secret_access_key: SecretStr
    endpoint_url: str | None = None
    region: str = "auto"
    presign_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    retention_days: int = Field(default=90, ge=1)


class BrowserSettings(Section):
    """Пул браузерных процессов. Личность задаётся при запуске процесса."""

    engine: Literal["chromium", "camoufox", "patchright"] = "chromium"
    headless: bool = True
    pool_size: int = Field(default=4, ge=1, le=64)
    max_pages_per_process: int = Field(default=200, ge=1)
    max_rss_mb: int = Field(default=2048, ge=256)
    navigation_timeout_ms: int = Field(default=30_000, ge=1_000)


class ProxySettings(Section):
    """Выходные адреса. Бюджет и пауза — доменные величины, здесь только их значения."""

    endpoint: str | None = None
    username: SecretStr | None = None
    password: SecretStr | None = None
    country: str | None = None
    request_budget: int = Field(default=15, ge=1)
    cooldown_seconds: int = Field(default=900, ge=1)

    @field_validator("country")
    @classmethod
    def _country_is_iso_alpha2(cls, value: str | None) -> str | None:
        if value is None:
            return None

        code = value.strip().upper()
        if len(code) != COUNTRY_CODE_LENGTH or not code.isalpha():
            raise ValueError("страна задаётся двумя буквами по ISO 3166-1, например ES")

        return code

    @property
    def is_configured(self) -> bool:
        return None not in (self.endpoint, self.username, self.password, self.country)


class CaptchaSettings(Section):
    """Распознавание проверок. По умолчанию включено — это согласованное решение."""

    enabled: bool = True
    primary: Literal["capsolver", "capmonster"] = "capsolver"
    capsolver_api_key: SecretStr | None = None
    capmonster_api_key: SecretStr | None = None
    timeout_seconds: int = Field(default=120, ge=5, le=600)

    @property
    def is_configured(self) -> bool:
        """Выключенное распознавание настроено по определению: решать нечем и не нужно."""
        if not self.enabled:
            return True

        keys = {"capsolver": self.capsolver_api_key, "capmonster": self.capmonster_api_key}
        return keys[self.primary] is not None


class ApiSettings(Section):
    """HTTP-интерфейс управления прогонами."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    root_path: str = ""
    request_timeout_seconds: int = Field(default=30, ge=1)


class SecuritySettings(Section):
    """Мастер-ключ шифрования и список хостов, куда браузеру позволено ходить."""

    secrets_encryption_key: SecretStr
    allowed_target_hosts: tuple[str, ...] = ()

    @field_validator("secrets_encryption_key")
    @classmethod
    def _key_is_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < MIN_ENCRYPTION_KEY_BYTES:
            raise ValueError(
                f"ключ короче {MIN_ENCRYPTION_KEY_BYTES} байт; "
                f"сгенерируйте: openssl rand -base64 48"
            )

        return value


class ObservabilitySettings(Section):
    """Логи и метрики."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "console"
    metrics_enabled: bool = True


class Settings(BaseSettings):
    """Корень конфигурации. Собирается один раз при старте процесса."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid",
        frozen=True,
    )

    environment: Environment = Environment.LOCAL
    debug: bool = False

    postgres: PostgresSettings
    redis: RedisSettings
    storage: StorageSettings
    security: SecuritySettings
    browser: BrowserSettings = BrowserSettings()
    proxy: ProxySettings = ProxySettings()
    captcha: CaptchaSettings = CaptchaSettings()
    api: ApiSettings = ApiSettings()
    observability: ObservabilitySettings = ObservabilitySettings()

    @model_validator(mode="before")
    @classmethod
    def _treat_empty_strings_as_unset(cls, data: Any) -> Any:
        return _unset_empty_values(data)

    @model_validator(mode="after")
    def _deployed_environment_is_not_dirty(self) -> Self:
        """Лучше не подняться, чем подняться дырявым."""
        complaints: list[str] = []

        if placeholders := sorted(self._placeholder_secrets()):
            complaints.append(f"шаблонные значения в секретах: {', '.join(placeholders)}")

        if self.environment.is_production:
            if self.debug:
                complaints.append("DEBUG=true")
            if self.observability.log_format != "json":
                complaints.append("OBSERVABILITY__LOG_FORMAT не json — логи не разобрать машинно")
            if self.browser.engine == "chromium":
                complaints.append(
                    "BROWSER__ENGINE=chromium — штатная сборка определяется как автоматическая "
                    "на первой же странице; для настоящей цели нужен camoufox"
                )

        if self.environment.is_deployed:
            if not self.proxy.is_configured:
                complaints.append(
                    "секция PROXY заполнена не полностью — сбор пойдёт с адреса сервера"
                )
            if not self.captcha.is_configured:
                complaints.append(
                    f"CAPTCHA__ENABLED=true, но ключа основного провайдера "
                    f"({self.captcha.primary}) нет — сбор встанет на первой же проверке"
                )
            if not self.security.allowed_target_hosts:
                complaints.append(
                    "SECURITY__ALLOWED_TARGET_HOSTS пуст — браузер откроет любой присланный адрес"
                )

        if complaints:
            raise ValueError(
                f"окружение {self.environment.value} не допускает такую конфигурацию: "
                + "; ".join(complaints)
            )

        return self

    def _placeholder_secrets(self) -> Iterator[str]:
        """Ищет шаблонные пароли во всех секциях. Значения наружу не выносятся."""
        for section_name, section in self:
            if not isinstance(section, Section):
                continue

            for field_name, value in section:
                if isinstance(value, SecretStr) and (
                    value.get_secret_value().strip().lower() in PLACEHOLDER_SECRETS
                ):
                    yield f"{section_name.upper()}__{field_name.upper()}"


def _env_name(location: tuple[Any, ...]) -> str:
    return "__".join(str(part).upper() for part in location) or "корень"


def _variables_behind(location: tuple[Any, ...]) -> list[str]:
    """Разворачивает отсутствующую секцию в список переменных, которых не хватает"""
    if len(location) != 1:
        return [_env_name(location)]

    field = Settings.model_fields.get(str(location[0]))
    annotation = field.annotation if field is not None else None

    if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
        return [_env_name(location)]

    return [
        _env_name((*location, name))
        for name, nested in annotation.model_fields.items()
        if nested.is_required()
    ] or [_env_name(location)]


def _readable(message: str) -> str:
    return "не задано" if message == "Field required" else message


def load_settings() -> Settings:
    """Собирает конфигурацию или объясняет, почему не может"""
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as error:
        problems = sorted(
            {
                f"  {name}: {_readable(str(issue['msg']))}"
                for issue in error.errors()
                for name in _variables_behind(tuple(issue["loc"]))
            }
        )
        raise ConfigurationError("конфигурация непригодна:\n" + "\n".join(problems)) from None
