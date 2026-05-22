import os
from datetime import date

from dotenv import load_dotenv

from flights.models import Flight, Route
from flights.providers import FlightProvider
from flights.providers.mock import MockProvider

load_dotenv()


class FlightClient:
    def __init__(self, provider: FlightProvider | None = None):
        self._provider = provider or self._auto_provider()

    @staticmethod
    def _auto_provider() -> FlightProvider:
        # 优先用 Ctrip 爬虫（需要 Playwright）
        try:
            from flights.providers.scraper import CtripScraperProvider
            return CtripScraperProvider()
        except Exception:
            return MockProvider()

    @property
    def source(self) -> str:
        return type(self._provider).__name__.replace("Provider", "").lower()

    def search(
        self,
        origin: str,
        destination: str,
        flight_date: date | str | None = None,
    ) -> Flight:
        if isinstance(flight_date, str):
            flight_date = date.fromisoformat(flight_date)
        flight_date = flight_date or date.today()
        route = Route(origin, destination, flight_date)
        return self._provider.search(route)

    def compare_routes(
        self,
        origin: str,
        destinations: list[str],
        flight_date: date | str | None = None,
    ) -> list[Flight]:
        return [self.search(origin, dst, flight_date) for dst in destinations]
