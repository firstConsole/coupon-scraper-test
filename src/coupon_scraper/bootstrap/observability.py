"""Настройка вывода логов. Вызывается один раз при старте процесса."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import structlog

from coupon_scraper.infrastructure.observability.logs import shared_processors

if TYPE_CHECKING:
    from structlog.typing import Processor

    from coupon_scraper.bootstrap.config import ObservabilitySettings

# Библиотеки, чья отладочная болтовня не несёт информации, но уносит место в выводе.
NOISY_LOGGERS = ("asyncio", "botocore", "urllib3", "aiobotocore", "sqlalchemy.engine")


def _renderer(*, as_json: bool) -> Processor:
    if as_json:
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=True)


def configure_logging(settings: ObservabilitySettings) -> None:
    shared = shared_processors()

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _renderer(as_json=settings.log_format == "json"),
            ],
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(logging.INFO, root.level))
