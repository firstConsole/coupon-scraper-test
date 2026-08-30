"""Разбор команд и отказ при непригодной конфигурации"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coupon_scraper.bootstrap.cli import EXIT_BAD_CONFIG, main

if TYPE_CHECKING:
    from pathlib import Path


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(SystemExit) as exit_code:
        main(["collect-everything"])

    assert exit_code.value.code == 2


def test_missing_command_is_rejected() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_bad_configuration_stops_before_anything_starts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Процесс не должен подняться наполовину и упасть на первой задаче"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POSTGRES__PASSWORD", raising=False)

    assert main(["worker"]) == EXIT_BAD_CONFIG
    assert "POSTGRES__PASSWORD" in capsys.readouterr().err
