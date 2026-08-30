from __future__ import annotations

import json
import re
from json import JSONDecoder
from typing import TYPE_CHECKING, Final

import structlog
from selectolax.lexbor import LexborHTMLParser

from coupon_scraper.domain.values.extraction import FieldSource
from coupon_scraper.infrastructure.extraction.paths import walk

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coupon_scraper.domain.values.extraction import FieldRule, RawSnapshot

STATE_ASSIGNMENTS: Final = re.compile(
    r"(?:window|self)\.(?:__NUXT__|__APOLLO_STATE__|__INITIAL_STATE__)\s*=\s*(?=\{)"
)
RSC_CHUNK: Final = re.compile(r"self\.__next_f\.push\(\[\d+\s*,\s*(\"(?:[^\"\\]|\\.)*\")")
MAX_DOCUMENTS: Final = 64

_decoder = JSONDecoder()
_log = structlog.get_logger("extraction.reader")


def _objects_in(text: str, limit: int = MAX_DOCUMENTS) -> Iterator[object]:
    found = 0

    for match in re.finditer(r"\{", text):
        if found >= limit:
            return

        try:
            document, _ = _decoder.raw_decode(text, match.start())
        except ValueError:
            continue

        found += 1
        yield document


class DocumentReader:
    def read(self, snapshot: RawSnapshot, rule: FieldRule) -> str | None:
        if rule.source is FieldSource.PAYLOAD:
            return self._from_payloads(snapshot, rule.path)

        if rule.source is FieldSource.EMBEDDED:
            return self._from_embedded(snapshot, rule.path)

        return self._from_markup(snapshot, rule)

    def _from_payloads(self, snapshot: RawSnapshot, path: str) -> str | None:
        for body in snapshot.payloads:
            try:
                document = json.loads(body)
            except ValueError:
                continue

            if (value := walk(document, path)) is not None:
                return _stringify(value)

        return None

    def _from_embedded(self, snapshot: RawSnapshot, path: str) -> str | None:
        if snapshot.embedded is None:
            return None

        for document in self._embedded_documents(snapshot.embedded):
            if (value := walk(document, path)) is not None:
                return _stringify(value)

        return None

    def _embedded_documents(self, html: str) -> Iterator[object]:
        tree = LexborHTMLParser(html)

        for node in tree.css('script[type="application/json"]'):
            with_text = node.text()

            if with_text:
                try:
                    yield json.loads(with_text)
                except ValueError:
                    _log.debug("встроенный JSON не разобран", node_id=node.attributes.get("id"))

        body = html

        for match in STATE_ASSIGNMENTS.finditer(body):
            yield from _objects_in(body[match.end() :], limit=1)

        chunks = [json.loads(match.group(1)) for match in RSC_CHUNK.finditer(body)]

        if chunks:
            yield from _objects_in("".join(chunks))

    @staticmethod
    def _from_markup(snapshot: RawSnapshot, rule: FieldRule) -> str | None:
        if snapshot.html is None:
            return None

        node = LexborHTMLParser(snapshot.html).css_first(rule.path)

        if node is None:
            return None  # type: ignore[unreachable]

        if rule.attribute is not None:
            found = node.attributes.get(rule.attribute)
            return found if isinstance(found, str) else None

        return node.text(strip=True) or None


def _stringify(value: object) -> str | None:
    if isinstance(value, (dict, list)):
        return None

    if isinstance(value, bool):
        return "true" if value else "false"

    return str(value)
