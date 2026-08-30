from __future__ import annotations

from coupon_scraper.presentation.service import PollingService


class Worker(PollingService):
    def __init__(self) -> None:
        super().__init__(name="worker")

    async def handle_batch(self) -> bool:
        return False
