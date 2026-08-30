from __future__ import annotations

import gzip
import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import structlog
from lxml import etree

from coupon_scraper.domain.errors import InvalidUrlError
from coupon_scraper.domain.values.seeds import NestedSitemap, SeedEntry
from coupon_scraper.domain.values.urls import CanonicalUrl

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import BinaryIO

MAX_ENTRIES: Final = 50_000
GZIP_MAGIC: Final = b"\x1f\x8b"
ENTRY_TAGS: Final = frozenset({"url", "sitemap"})

_log = structlog.get_logger("sitemap")


class _WithHead(io.RawIOBase):
    def __init__(self, head: bytes, tail: BinaryIO) -> None:
        super().__init__()
        self._head = head
        self._tail = tail

    def readable(self) -> bool:
        return True

    def read(self, size: int | None = -1) -> bytes:
        if not self._head:
            return self._tail.read() if size is None or size < 0 else self._tail.read(size)

        if size is None or size < 0:
            head, self._head = self._head, b""
            return head + self._tail.read()

        head, self._head = self._head[:size], self._head[size:]
        remaining = size - len(head)

        return head + self._tail.read(remaining) if remaining else head


def _sniffed(stream: BinaryIO) -> BinaryIO:
    head = stream.read(len(GZIP_MAGIC))
    joined: BinaryIO = _WithHead(head, stream)  # type: ignore[assignment]

    if head == GZIP_MAGIC:
        return gzip.GzipFile(fileobj=joined)  # type: ignore[return-value]

    return joined


def _local_name(element: etree._Element) -> str | None:
    try:
        return etree.QName(element).localname
    except ValueError:
        return None


def _child_text(element: etree._Element, name: str) -> str | None:
    for child in element:
        if _local_name(child) == name and child.text:
            return child.text.strip()

    return None


def _parse_moment(raw: str | None) -> datetime | None:
    if not raw:
        return None

    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        _log.debug("дата изменения не разобрана", value=raw)
        return None

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _forget(element: etree._Element) -> None:
    element.clear()
    parent = element.getparent()

    if parent is not None:
        while element.getprevious() is not None:
            del parent[0]


class SitemapReader:
    def __init__(self, *, expected_host: str | None = None, max_entries: int = MAX_ENTRIES) -> None:
        self._expected_host = expected_host
        self._max_entries = max_entries

    def read(self, stream: BinaryIO) -> Iterator[SeedEntry | NestedSitemap]:
        seen = 0

        for element in self._elements(stream):
            name = _local_name(element)
            location = _child_text(element, "loc")

            if location is not None:
                item = self._make(name, location, _child_text(element, "lastmod"))

                if item is not None:
                    seen += 1

                    if seen > self._max_entries:
                        message = f"в карте больше {self._max_entries} записей"
                        raise ValueError(message)

                    yield item

            _forget(element)

    def _elements(self, stream: BinaryIO) -> Iterator[etree._Element]:
        context = etree.iterparse(
            _sniffed(stream),
            events=("end",),
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            huge_tree=False,
            recover=False,
        )

        for _, element in context:
            if _local_name(element) in ENTRY_TAGS:
                yield element

    def _make(
        self, name: str | None, location: str, last_modified: str | None
    ) -> SeedEntry | NestedSitemap | None:
        try:
            url = CanonicalUrl.parse(location)
        except InvalidUrlError as error:
            _log.debug("адрес из карты отброшен", reason=error.reason)
            return None

        if self._expected_host is not None and url.host != self._expected_host:
            _log.debug("адрес не с той цели", host=url.host, expected=self._expected_host)
            return None

        if name == "sitemap":
            return NestedSitemap(url)

        return SeedEntry(url, _parse_moment(last_modified))
