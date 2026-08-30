"""Проверки .env.example: он единственная инструкция по заполнению .env"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, SecretStr

from coupon_scraper.bootstrap.config import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
ASSIGNMENT = re.compile(r"^(?P<name>[A-Z][A-Z0-9_]*)=(?P<value>.*)$")


def _fields(model: type[BaseModel], prefix: str = "", *, required_only: bool) -> Iterator[str]:
    for name, field in model.model_fields.items():
        annotation = field.annotation

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if field.is_required() or not required_only:
                yield from _fields(annotation, f"{prefix}{name}__", required_only=required_only)
            continue

        if field.is_required() or not required_only:
            yield f"{prefix}{name}".upper()


def _secret_fields(model: type[BaseModel], prefix: str = "") -> Iterator[str]:
    for name, field in model.model_fields.items():
        annotation = field.annotation

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            yield from _secret_fields(annotation, f"{prefix}{name}__")
            continue

        if SecretStr in (annotation, *getattr(annotation, "__args__", ())):
            yield f"{prefix}{name}".upper()


def _declared() -> dict[str, str]:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    matches = (ASSIGNMENT.match(line) for line in lines)
    return {m["name"]: m["value"] for m in matches if m is not None}


def test_every_required_setting_is_listed() -> None:
    """Иначе заполнивший .env по примеру получит отказ старта без объяснений"""
    missing = set(_fields(Settings, required_only=True)) - set(_declared())

    assert not missing, f"в .env.example не хватает обязательных: {sorted(missing)}"


def test_no_unknown_keys() -> None:
    """Ловит опечатки и переменные, пережившие удаление настройки"""
    unknown = set(_declared()) - set(_fields(Settings, required_only=False))

    assert not unknown, f"в .env.example переменные, которых нет в конфигурации: {sorted(unknown)}"


def test_secrets_are_left_empty() -> None:
    """В примере не должно быть ни одного настоящего значения"""
    declared = _declared()
    filled = sorted(name for name in _secret_fields(Settings) if declared.get(name, "").strip())

    assert not filled, f"в .env.example заполнены секреты: {filled}"
