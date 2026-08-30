"""Живость и готовность: разные вопросы, разные ответы"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from coupon_scraper.application.ports.health import ReadinessProbe
from coupon_scraper.presentation.api.app import create_app


@dataclass(frozen=True, slots=True)
class FakeProbe:
    """Подделка проверки: отвечает заданным или падает."""

    name: str
    ready: bool = True
    explodes: bool = False

    async def is_ready(self) -> bool:
        if self.explodes:
            raise ConnectionError(self.name)
        return self.ready


def _client(*probes: ReadinessProbe) -> TestClient:
    return TestClient(create_app(probes=probes))


def test_fake_probe_satisfies_the_port() -> None:
    assert isinstance(FakeProbe(name="redis"), ReadinessProbe)


def test_live_ignores_dependencies() -> None:
    """Иначе перезапуск по живости случается из-за чужого отказа"""
    response = _client(FakeProbe(name="postgres", ready=False)).get("/healthz/live")

    assert response.status_code == HTTPStatus.OK


def test_ready_without_dependencies() -> None:
    response = _client().get("/healthz/ready")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"ready": True, "checks": {}}


def test_ready_names_the_failing_dependency() -> None:
    client = _client(FakeProbe(name="postgres"), FakeProbe(name="proxy_pool", ready=False))

    response = client.get("/healthz/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json() == {
        "ready": False,
        "checks": {"postgres": True, "proxy_pool": False},
    }


def test_broken_probe_is_not_ready_rather_than_error() -> None:
    """Отказ зависимости должен читаться как «не готов», а не как «сломан»"""
    response = _client(FakeProbe(name="storage", explodes=True)).get("/healthz/ready")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["checks"] == {"storage": False}


def test_metrics_are_exposed() -> None:
    response = _client().get("/metrics")

    assert response.status_code == HTTPStatus.OK
    assert "python_info" in response.text


@pytest.mark.parametrize("path", ["/healthz/live", "/healthz/ready", "/metrics"])
def test_service_endpoints_stay_out_of_the_public_schema(path: str) -> None:
    """Служебные ручки не часть контракта: клиенту про них знать нечего"""
    schema = _client().get("/openapi.json").json()

    assert path not in schema["paths"]
