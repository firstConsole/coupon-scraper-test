from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from coupon_scraper import __version__
from coupon_scraper.presentation.api.health import health_router

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coupon_scraper.application.ports.health import ReadinessProbe

TITLE = "Coupon Scraper"
SUMMARY = "Управление прогонами сбора купонов и гифт-карт"


def _metrics_router() -> APIRouter:
    router = APIRouter(tags=["служебное"])

    @router.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return router


def _v1_router() -> APIRouter:
    return APIRouter(prefix="/v1", tags=["прогоны"])


def create_app(
    *,
    probes: Sequence[ReadinessProbe] = (),
    root_path: str = "",
) -> FastAPI:
    app = FastAPI(
        title=TITLE,
        summary=SUMMARY,
        version=__version__,
        root_path=root_path,
    )

    app.include_router(health_router(probes))
    app.include_router(_metrics_router())
    app.include_router(_v1_router())

    return app
