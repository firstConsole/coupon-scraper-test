from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from ipaddress import ip_address
from typing import Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from coupon_scraper.domain.errors import InvalidTaskKeyError, InvalidUrlError

ALLOWED_SCHEMES: Final = frozenset({"http", "https"})
DEFAULT_PORTS: Final = {"http": 80, "https": 443}
TRACKING_PREFIXES: Final = ("utm_",)
TRACKING_PARAMS: Final = frozenset(
    {
        "_ga",
        "_gl",
        "_openstat",
        "dclid",
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "twclid",
        "yclid",
    }
)
LOCAL_HOSTNAMES: Final = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
KEY_LENGTH: Final = 64
HEX_DIGITS: Final = frozenset("0123456789abcdef")
_PERCENT_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
_REPEATED_SLASH = re.compile(r"/{2,}")


def _is_tracking(name: str) -> bool:
    lowered = name.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PREFIXES)


def _normalised_host(raw: str, host: str) -> str:
    if host in LOCAL_HOSTNAMES:
        raise InvalidUrlError(raw, "адрес указывает на саму машину сборщика")

    try:
        literal = ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise InvalidUrlError(raw, "адрес указывает во внутреннюю сеть")

    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _normalised_path(path: str) -> str:
    path = _PERCENT_ESCAPE.sub(lambda match: match.group(0).upper(), path)
    path = _REPEATED_SLASH.sub("/", path)
    return path or "/"


def _normalised_query(query: str) -> str:
    kept = [
        (name, value)
        for name, value in parse_qsl(query, keep_blank_values=True)
        if not _is_tracking(name)
    ]
    return urlencode(sorted(kept))


@dataclass(frozen=True, slots=True)
class TaskKey:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) != KEY_LENGTH or not HEX_DIGITS.issuperset(self.value):
            raise InvalidTaskKeyError(self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CanonicalUrl:
    value: str

    @classmethod
    def parse(cls, raw: str) -> CanonicalUrl:
        stripped = raw.strip()

        if not stripped:
            raise InvalidUrlError(raw, "пустая строка")

        parts = urlsplit(stripped)
        scheme = parts.scheme.lower()

        if scheme not in ALLOWED_SCHEMES:
            raise InvalidUrlError(raw, f"схема {scheme or 'отсутствует'!r} не поддерживается")

        if parts.username is not None or parts.password is not None:
            raise InvalidUrlError(raw, "учётные данные в адресе не принимаются")

        try:
            host = parts.hostname
        except ValueError as error:
            raise InvalidUrlError(raw, "хост неразбираем") from error

        if not host:
            raise InvalidUrlError(raw, "хост отсутствует")

        try:
            port = parts.port
        except ValueError as error:
            raise InvalidUrlError(raw, "порт неразбираем") from error

        authority = _normalised_host(raw, host)
        if ":" in authority:
            authority = f"[{authority}]"
        if port is not None and port != DEFAULT_PORTS[scheme]:
            authority = f"{authority}:{port}"

        path = _normalised_path(parts.path)
        query = _normalised_query(parts.query)

        return cls(urlunsplit((scheme, authority, path, query, "")))

    @property
    def key(self) -> TaskKey:
        return TaskKey(sha256(self.value.encode()).hexdigest())

    @property
    def host(self) -> str:
        return urlsplit(self.value).netloc

    def __str__(self) -> str:
        return self.value
