"""Структурные логи"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.typing import EventDict, Processor, WrappedLogger

REDACTED = "***"
SENSITIVE_MARKERS = (
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "passwd",
    "password",
    "private_key",
    "secret",
    "signature",
    "token",
)
_URL_CREDENTIALS = re.compile(r"(?P<head>[a-zA-Z][\w+.\-]*://[^:/?#\s]*:)[^@\s/]+(?P<tail>@)")
_QUERY_SECRET = re.compile(
    r"(?i)(?P<head>[?&](?:api[_-]?key|token|secret|password|sig|signature)=)[^&\s\"']+"
)
_BEARER = re.compile(r"(?i)(?P<head>bearer\s+)[\w.\-~+/]+=*")


def is_sensitive(key: str) -> bool:
    """Имя поля, значение которого не показывается ни при каких условиях."""
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS)


def redact_text(text: str) -> str:
    """Вырезает секреты из строки, сохраняя всё, что нужно для разбора."""
    text = _URL_CREDENTIALS.sub(rf"\g<head>{REDACTED}\g<tail>", text)
    text = _QUERY_SECRET.sub(rf"\g<head>{REDACTED}", text)
    return _BEARER.sub(rf"\g<head>{REDACTED}", text)


def _redact(key: str, value: Any) -> Any:
    if is_sensitive(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {inner: _redact(str(inner), item) for inner, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_redact(key, item) for item in value)
    return value


def scrub_secrets(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Обработчик structlog: чистит и своё событие, и запись чужой библиотеки."""
    return {key: _redact(str(key), value) for key, value in event_dict.items()}


def shared_processors() -> list[Processor]:
    """Цепочка, общая для собственных логов и для записей стандартного logging."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        scrub_secrets,
    ]
