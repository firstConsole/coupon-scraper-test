"""Карта сайта — недоверенный ввод с чужого сервера"""

from __future__ import annotations

import gzip
import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from lxml import etree

from coupon_scraper.domain.values.seeds import NestedSitemap, SeedEntry
from coupon_scraper.infrastructure.sitemap.reader import SitemapReader

if TYPE_CHECKING:
    from pathlib import Path

NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

URLSET = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="{NS}">
  <url><loc>https://cupones.example/gift-cards/zalando</loc><lastmod>2026-08-29</lastmod></url>
  <url><loc>https://cupones.example/gift-cards/ikea</loc><lastmod>2026-08-30T09:15:00+02:00</lastmod></url>
  <url><loc>https://cupones.example/gift-cards/fnac</loc></url>
</urlset>"""

INDEX = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="{NS}">
  <sitemap><loc>https://cupones.example/sitemap-cards-1.xml</loc></sitemap>
  <sitemap><loc>https://cupones.example/sitemap-cards-2.xml.gz</loc></sitemap>
</sitemapindex>"""


def _read(document: str | bytes, **options: object) -> list[SeedEntry | NestedSitemap]:
    body = document.encode() if isinstance(document, str) else document
    reader = SitemapReader(**options)  # type: ignore[arg-type]

    return list(reader.read(io.BytesIO(body)))


# ── Обычный разбор ────────────────────────────────────────────────────────────


def test_urlset_gives_entries() -> None:
    entries = _read(URLSET)

    assert len(entries) == 3
    assert all(isinstance(item, SeedEntry) for item in entries)


def test_dates_are_read_with_a_timezone() -> None:
    """Домен наивные даты отвергает, а в карте они встречаются постоянно"""
    first, second, third = _read(URLSET)

    assert isinstance(first, SeedEntry)
    assert first.last_modified == datetime(2026, 8, 29, tzinfo=UTC)
    assert isinstance(second, SeedEntry)
    assert second.last_modified is not None
    assert second.last_modified.tzinfo is not None
    assert isinstance(third, SeedEntry)
    assert third.last_modified is None


def test_unknown_date_counts_as_changed() -> None:
    """Пропустить обновление дороже, чем загрузить страницу лишний раз"""
    entry = SeedEntry(url=_read(URLSET)[2].url)

    assert entry.changed_since(datetime(2030, 1, 1, tzinfo=UTC))


def test_index_gives_nested_maps() -> None:
    nested = _read(INDEX)

    assert len(nested) == 2
    assert all(isinstance(item, NestedSitemap) for item in nested)


def test_gzip_is_recognised_without_being_told() -> None:
    """Ни расширение, ни заголовок ответа об этом не сообщают надёжно"""
    assert len(_read(gzip.compress(URLSET.encode()))) == 3


def test_map_without_a_namespace_is_read() -> None:
    plain = URLSET.replace(f' xmlns="{NS}"', "")

    assert len(_read(plain)) == 3


def test_comments_do_not_break_the_walk() -> None:
    with_comment = URLSET.replace("<urlset", "<!-- выгрузка от 30.08 -->\n<urlset")

    assert len(_read(with_comment)) == 3


# ── Недоверенный ввод ─────────────────────────────────────────────────────────


def test_external_entity_reads_nothing_from_disk(tmp_path: Path) -> None:
    """Классическая XXE: сущность подставляет содержимое файла прямо в адрес.

    Правильный исход здесь не исключение, а тишина: сущность отбрасывается,
    остальные адреса разбираются дальше. Падать на чужой карте незачем — она
    приходит с сервера цели, а не от нас.
    """
    secret = tmp_path / "secret.txt"
    secret.write_text("MARKER-9F2C-DO-NOT-LEAK", encoding="utf-8")

    hostile = f"""<?xml version="1.0"?>
<!DOCTYPE urlset [<!ENTITY xxe SYSTEM "file://{secret}">]>
<urlset xmlns="{NS}">
  <url><loc>https://cupones.example/&xxe;</loc></url>
  <url><loc>https://cupones.example/gift-cards/ikea</loc></url>
</urlset>"""

    addresses = [str(item.url) for item in _read(hostile)]

    assert not any("MARKER-9F2C" in address for address in addresses)
    assert "https://cupones.example/gift-cards/ikea" in addresses


def test_nested_entities_do_not_expand() -> None:
    """Billion laughs: девять уровней разворачиваются в гигабайты — если разворачивать"""
    entities = "\n".join(
        f'<!ENTITY lol{level} "&lol{level - 1};&lol{level - 1};&lol{level - 1};">'
        for level in range(1, 10)
    )
    hostile = f"""<?xml version="1.0"?>
<!DOCTYPE urlset [<!ENTITY lol0 "lol">{entities}]>
<urlset xmlns="{NS}">
  <url><loc>https://cupones.example/&lol9;</loc></url>
</urlset>"""

    addresses = [str(item.url) for item in _read(hostile)]

    assert addresses == ["https://cupones.example/"]


def test_broken_map_is_an_error_not_a_guess() -> None:
    with pytest.raises(etree.XMLSyntaxError):
        _read("<urlset><url><loc>https://cupones.example/x</loc>")


# ── Отсев адресов ─────────────────────────────────────────────────────────────


def test_address_leading_inside_is_dropped_silently() -> None:
    """Один битый адрес не повод бросать остальные сорок девять тысяч"""
    hostile = URLSET.replace(
        "https://cupones.example/gift-cards/ikea", "http://169.254.169.254/latest/meta-data/"
    )

    assert len(_read(hostile)) == 2


@pytest.mark.parametrize("address", ["javascript:alert(1)", "not-a-url", "ftp://cupones.example/x"])
def test_unusable_address_is_dropped(address: str) -> None:
    hostile = URLSET.replace("https://cupones.example/gift-cards/ikea", address)

    assert len(_read(hostile)) == 2


def test_foreign_host_is_dropped_when_the_target_is_known() -> None:
    """В чужой карте может лежать что угодно, включая чужие адреса"""
    mixed = URLSET.replace("https://cupones.example/gift-cards/ikea", "https://otro.example/x")

    assert len(_read(mixed, expected_host="cupones.example")) == 2


# ── Ограничения ───────────────────────────────────────────────────────────────


def test_oversized_map_is_refused() -> None:
    """Протокол ограничивает файл 50 000 адресами; больше — либо ошибка, либо атака"""
    urls = "".join(f"<url><loc>https://cupones.example/{n}</loc></url>" for n in range(5))
    document = f'<?xml version="1.0"?><urlset xmlns="{NS}">{urls}</urlset>'

    with pytest.raises(ValueError, match="больше 3 записей"):
        _read(document, max_entries=3)


def test_reading_is_lazy() -> None:
    """Карта на пятьдесят тысяч адресов не должна оказываться в памяти целиком"""
    urls = "".join(f"<url><loc>https://cupones.example/{n}</loc></url>" for n in range(1000))
    document = f'<?xml version="1.0"?><urlset xmlns="{NS}">{urls}</urlset>'

    stream = SitemapReader().read(io.BytesIO(document.encode()))

    assert isinstance(next(stream), SeedEntry)
