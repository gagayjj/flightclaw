from abc import ABC, abstractmethod
from flights.models import Flight, Route


class FlightProvider(ABC):
    @abstractmethod
    def search(self, route: Route) -> Flight:
        ...
