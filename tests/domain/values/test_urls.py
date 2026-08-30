"""Канонизация адреса: без неё идемпотентности не существует"""

from __future__ import annotations

import pytest

from coupon_scraper.domain.errors import InvalidTaskKeyError, InvalidUrlError
from coupon_scraper.domain.values.urls import KEY_LENGTH, CanonicalUrl, TaskKey

PAGE = "https://cupones.example/gift-cards/zalando"


def _key(raw: str) -> str:
    return CanonicalUrl.parse(raw).key.value


# ── Одна страница — один ключ ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (f"{PAGE}?a=1&b=2", f"{PAGE}?b=2&a=1"),
        (f"{PAGE}?a=1", f"{PAGE}?a=1&utm_source=newsletter&utm_medium=email"),
        (f"{PAGE}?a=1", f"{PAGE}?a=1&gclid=abc123&fbclid=def456"),
        (PAGE, f"{PAGE}#reviews"),
        (PAGE, "https://CUPONES.EXAMPLE/gift-cards/zalando"),
        (PAGE, "HTTPS://cupones.example/gift-cards/zalando"),
        (PAGE, "https://cupones.example:443/gift-cards/zalando"),
        (PAGE, "https://cupones.example//gift-cards//zalando"),
        (PAGE, f"  {PAGE}  "),
        (f"{PAGE}%2Fes", f"{PAGE}%2fes"),
    ],
)
def test_same_page_gives_same_key(left: str, right: str) -> None:
    assert _key(left) == _key(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (PAGE, f"{PAGE}/"),
        (PAGE, f"{PAGE}?a=1"),
        (f"{PAGE}?a=1", f"{PAGE}?a=2"),
        (PAGE, "https://cupones.example:8443/gift-cards/zalando"),
        (PAGE, "http://cupones.example/gift-cards/zalando"),
        (PAGE, "https://cupones.example/gift-cards/Zalando"),
    ],
)
def test_different_pages_give_different_keys(left: str, right: str) -> None:
    """Хвостовой слеш и регистр пути не нормализуются намеренно: они бывают значимы"""
    assert _key(left) != _key(right)


def test_functional_parameters_survive() -> None:
    """ref и source на купонных агрегаторах бывают функциональными —
    выбросить их значит уйти не на ту страницу ради красивого ключа"""
    canonical = CanonicalUrl.parse(f"{PAGE}?ref=partner&source=widget&utm_campaign=aug")

    assert "ref=partner" in canonical.value
    assert "source=widget" in canonical.value
    assert "utm_campaign" not in canonical.value


# ── Что не принимается ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "cupones.example/gift-cards",
        "file:///etc/passwd",
        "ftp://cupones.example/list",
        "javascript:alert(1)",
        "https:///gift-cards",
    ],
)
def test_unusable_addresses_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidUrlError):
        CanonicalUrl.parse(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.5/admin",
        "http://192.168.1.1/admin",
        "http://172.16.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "http://[::1]/admin",
        "http://[fd00::1]/admin",
        "http://localhost:8000/healthz/ready",
    ],
)
def test_internal_network_is_rejected(raw: str) -> None:
    """Адрес приходит от пользователя, а открывать его будет наш браузер.
    169.254.169.254 — метаданные облака, их пробуют первым делом"""
    with pytest.raises(InvalidUrlError, match=r"внутренню|саму машину"):
        CanonicalUrl.parse(raw)


def test_credentials_in_address_are_rejected() -> None:
    """Пароль в адресе утёк бы в ключ задачи, в логи и в выгрузку"""
    with pytest.raises(InvalidUrlError, match="учётные данные"):
        CanonicalUrl.parse("https://user:hunter2@cupones.example/gift-cards")


def test_error_does_not_repeat_the_address() -> None:
    """Текст исключения уходит в логи, а в адресе бывают секреты"""
    with pytest.raises(InvalidUrlError) as failure:
        CanonicalUrl.parse("https://user:hunter2@cupones.example/gift-cards")

    assert "hunter2" not in str(failure.value)
    assert failure.value.raw.endswith("/gift-cards")


# ── Ключ ──────────────────────────────────────────────────────────────────────


def test_key_looks_like_sha256() -> None:
    key = CanonicalUrl.parse(PAGE).key

    assert len(key.value) == KEY_LENGTH
    assert str(key) == key.value


def test_key_is_stable_between_calls() -> None:
    assert CanonicalUrl.parse(PAGE).key == CanonicalUrl.parse(PAGE).key


@pytest.mark.parametrize("value", ["", "abc", "z" * KEY_LENGTH, "A" * KEY_LENGTH])
def test_malformed_key_is_rejected(value: str) -> None:
    with pytest.raises(InvalidTaskKeyError):
        TaskKey(value)


# ── Мелочи, которые ломаются молча ────────────────────────────────────────────


def test_international_host_is_folded_to_punycode() -> None:
    """Иначе одна и та же цель в двух написаниях даёт два ключа"""
    assert _key("https://пример.рф/cupones") == _key("https://xn--e1afmkfd.xn--p1ai/cupones")


def test_empty_path_becomes_root() -> None:
    assert CanonicalUrl.parse("https://cupones.example").value == "https://cupones.example/"


def test_host_is_exposed_for_the_allowlist() -> None:
    assert CanonicalUrl.parse(f"{PAGE}?a=1").host == "cupones.example"
