from __future__ import annotations

from coupon_scraper.presentation.service import PollingService

PLANNER_IDLE_SECONDS = 5.0


class Planner(PollingService):
    def __init__(self) -> None:
        super().__init__(name="planner", idle_delay=PLANNER_IDLE_SECONDS)

    async def handle_batch(self) -> bool:
        return False
