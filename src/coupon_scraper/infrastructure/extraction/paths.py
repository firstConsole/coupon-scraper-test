from __future__ import annotations

import re
from typing import Final

_TOKEN: Final = re.compile(r"\[(\d+)\]|([^.\[\]]+)")


def tokens(path: str) -> tuple[str | int, ...]:
    """Разбирает `$.items[0].price` в ('items', 0, 'price')."""
    trimmed = path.removeprefix("$").removeprefix(".")

    return tuple(
        int(index) if index else key for index, key in _TOKEN.findall(trimmed) if index or key
    )


def walk(document: object, path: str) -> object | None:
    """Идёт по пути и отдаёт значение либо None"""
    node = document

    for token in tokens(path):
        if isinstance(token, int):
            if not isinstance(node, list) or not -len(node) <= token < len(node):
                return None

            node = node[token]
            continue

        if not isinstance(node, dict) or token not in node:
            return None

        node = node[token]

    return node
