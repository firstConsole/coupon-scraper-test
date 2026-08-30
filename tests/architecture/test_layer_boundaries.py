"""Тест-страж границ между слоями"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterator

PACKAGE_NAME = "coupon_scraper"
PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / PACKAGE_NAME

ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "domain": frozenset(),
    "application": frozenset({"domain"}),
    "infrastructure": frozenset({"domain", "application"}),
    "presentation": frozenset({"domain", "application"}),
    "bootstrap": frozenset({"domain", "application", "infrastructure", "presentation"}),
}

FRAMEWORKS = (
    "aioboto3",
    "alembic",
    "asyncpg",
    "boto3",
    "botocore",
    "camoufox",
    "curl_cffi",
    "fastapi",
    "httpx",
    "lxml",
    "patchright",
    "playwright",
    "prometheus_client",
    "redis",
    "selectolax",
    "sqlalchemy",
    "starlette",
    "uvicorn",
)

FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    "domain": (*FRAMEWORKS, "pydantic"),
    "application": FRAMEWORKS,
}

# Обращения к текущему времени. Домен обязан получать момент аргументом: иначе
# карантин адреса невозможно проверить, не подождав пятнадцать минут.
CLOCK_CALLS = frozenset({"now", "utcnow", "today", "monotonic", "perf_counter"})


class SourceFile(NamedTuple):
    """Разобранный исходник вместе с его местом в пакете."""

    path: Path
    layer: str
    package: tuple[str, ...]
    tree: ast.Module


def _layer_dirs() -> Iterator[Path]:
    """Каталоги слоёв - те, что являются пакетами. Кэши интерпретатора мимо."""
    for path in sorted(PACKAGE_ROOT.iterdir()):
        if path.is_dir() and (path / "__init__.py").exists():
            yield path


def _iter_sources() -> Iterator[SourceFile]:
    """Проходит по всем модулям внутри слоёв и разбирает их в AST."""
    for layer_dir in _layer_dirs():
        for path in sorted(layer_dir.rglob("*.py")):
            parts = path.relative_to(PACKAGE_ROOT).with_suffix("").parts
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            yield SourceFile(path=path, layer=parts[0], package=parts[:-1], tree=tree)


def _imported_modules(source: SourceFile) -> Iterator[str]:
    """Отдаёт полные имена всех импортированных модулей"""
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module is not None:
                    yield node.module
                continue

            base = source.package[: len(source.package) - (node.level - 1)]
            tail = tuple(node.module.split(".")) if node.module else ()

            yield ".".join((PACKAGE_NAME, *base, *tail))


def _layer_of(module: str) -> str | None:
    """Определяет слой по имени модуля. Для внешних библиотек — None."""
    parts = module.split(".")

    if parts[0] != PACKAGE_NAME or len(parts) < 2:
        return None

    return parts[1]


def test_every_layer_is_described_in_the_rules() -> None:
    """Новый слой должен появиться в правилах, иначе он никем не проверяется"""
    on_disk = {path.name for path in _layer_dirs()}
    described = set(ALLOWED_IMPORTS)

    assert on_disk == described, (
        "Слои на диске разошлись с правилами импорта.\n"
        f"  только на диске: {sorted(on_disk - described) or '—'}\n"
        f"  только в правилах: {sorted(described - on_disk) or '—'}"
    )


def test_dependencies_point_inwards() -> None:
    """Ни один слой не импортирует то, что снаружи него"""
    violations: list[str] = []

    for source in _iter_sources():
        allowed = ALLOWED_IMPORTS[source.layer]

        for module in _imported_modules(source):
            imported_layer = _layer_of(module)

            if imported_layer is None or imported_layer == source.layer:
                continue

            if imported_layer not in allowed:
                violations.append(
                    f"  {source.path.relative_to(PACKAGE_ROOT)}: "
                    f"«{source.layer}» тянет «{imported_layer}» ({module})"
                )

    assert not violations, "Зависимость смотрит наружу:\n" + "\n".join(violations)


def test_core_layers_stay_framework_free() -> None:
    """Домен и приложение остаются на стандартной библиотеке"""
    violations: list[str] = []

    for source in _iter_sources():
        forbidden = FORBIDDEN_IMPORTS.get(source.layer)

        if forbidden is None:
            continue

        for module in _imported_modules(source):
            root = module.split(".")[0]

            if root in forbidden:
                violations.append(
                    f"  {source.path.relative_to(PACKAGE_ROOT)}: "
                    f"«{source.layer}» импортирует «{root}»"
                )

    assert not violations, "Фреймворк пробрался в ядро:\n" + "\n".join(violations)


def _clock_calls(source: SourceFile) -> Iterator[str]:
    """Ищет вызовы вида datetime.now(), time.monotonic(), date.today()."""
    for node in ast.walk(source.tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in CLOCK_CALLS
        ):
            yield f"{ast.unparse(node.func)}()"


def test_domain_does_not_read_the_clock() -> None:
    """Момент времени приходит в домен аргументом, а не берётся из системных часов"""
    violations = [
        f"  {source.path.relative_to(PACKAGE_ROOT)}: {call}"
        for source in _iter_sources()
        if source.layer == "domain"
        for call in _clock_calls(source)
    ]

    assert not violations, (
        "Домен смотрит на часы — правило станет непроверяемым без ожидания:\n"
        + "\n".join(violations)
    )
