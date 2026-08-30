"""Проверка, что пакет ставится и импортируется"""

from __future__ import annotations

import coupon_scraper


def test_package_exposes_version() -> None:
    assert coupon_scraper.__version__ == "0.1.0"
