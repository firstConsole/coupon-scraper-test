from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coupon_scraper.application.ports.health import ReadinessProbe

_log = structlog.get_logger("api.health")


async def _inspect(probe: ReadinessProbe) -> tuple[str, bool]:
    try:
        return probe.name, await probe.is_ready()
    except Exception:  # noqa: BLE001 — любой отказ зависимости это «не готов»
        _log.warning("проверка готовности упала", probe=probe.name, exc_info=True)
        return probe.name, False


def health_router(probes: Sequence[ReadinessProbe]) -> APIRouter:
    router = APIRouter(tags=["служебное"])

    @router.get("/healthz/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/healthz/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        checks = dict(await asyncio.gather(*(_inspect(probe) for probe in probes)))
        healthy = all(checks.values())

        return JSONResponse(
            status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ready": healthy, "checks": checks},
        )

    return router
