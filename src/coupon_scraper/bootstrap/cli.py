"""Запуск процессов"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING

import uvicorn

from coupon_scraper import __version__
from coupon_scraper.bootstrap.config import ConfigurationError, Settings, load_settings
from coupon_scraper.bootstrap.observability import configure_logging
from coupon_scraper.presentation.api.app import create_app
from coupon_scraper.presentation.lifecycle import GracefulShutdown
from coupon_scraper.presentation.planner.runner import Planner
from coupon_scraper.presentation.worker.runner import Worker

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coupon_scraper.presentation.service import PollingService

EXIT_OK = 0
EXIT_BAD_CONFIG = 2

SERVICES: dict[str, Callable[[], PollingService]] = {"worker": Worker, "planner": Planner}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coupon-scraper",
        description="Сбор данных и снимков карточек с агрегаторов купонов и гифт-карт",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "command",
        choices=("api", "worker", "planner"),
        help="api — управление прогонами, worker — сбор, planner — раскладка и обслуживание",
    )
    return parser


class _Server(uvicorn.Server):
    """Сигналы обрабатывает GracefulShutdown"""

    def install_signal_handlers(self) -> None:
        return


async def _serve_api(settings: Settings) -> None:
    server = _Server(
        uvicorn.Config(
            create_app(root_path=settings.api.root_path),
            host=settings.api.host,
            port=settings.api.port,
            log_config=None,
        )
    )
    shutdown = GracefulShutdown()

    with shutdown.installed():
        serving = asyncio.create_task(server.serve())
        await shutdown.wait()
        server.should_exit = True
        await serving


async def _serve_background(service: PollingService) -> None:
    shutdown = GracefulShutdown()

    with shutdown.installed():
        await service.run(shutdown)


def main(argv: Sequence[str] | None = None) -> int:
    command = _parser().parse_args(argv).command

    try:
        settings = load_settings()
    except ConfigurationError as error:
        sys.stderr.write(f"{error}\n")
        return EXIT_BAD_CONFIG

    configure_logging(settings.observability)

    if command == "api":
        asyncio.run(_serve_api(settings))
    else:
        asyncio.run(_serve_background(SERVICES[command]()))

    return EXIT_OK
