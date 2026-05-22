import json
import os
from datetime import date, datetime
from typing import Optional

from flights.client import FlightClient
from flights.models import Flight, FlightPrice, Route


class PriceTracker:
    def __init__(self, client: FlightClient | None = None, history_file: str = ""):
        self._client = client or FlightClient()
        self._history_file = history_file or os.path.join(
            os.path.dirname(__file__), "..", "price_history.json"
        )
        self._history: dict[str, list[dict]] = self._load_history()

    def _load_history(self) -> dict[str, list[dict]]:
        if os.path.exists(self._history_file):
            with open(self._history_file) as f:
                return json.load(f)
        return {}

    def _save_history(self):
        os.makedirs(os.path.dirname(self._history_file) or ".", exist_ok=True)
        with open(self._history_file, "w") as f:
            json.dump(self._history, f, indent=2, ensure_ascii=False)

    def _route_key(self, route: Route) -> str:
        return f"{route.origin}-{route.destination}-{route.date}"

    def check_price(self, route: Route) -> Flight:
        flight = self._client.search(route.origin, route.destination, route.date)
        key = self._route_key(route)
        snapshot = {
            "date": datetime.now().isoformat(),
            "lowest_price": flight.lowest_price,
            "prices": [{"airline": p.airline, "price": p.price} for p in flight.prices],
        }
        self._history.setdefault(key, []).append(snapshot)
        self._save_history()
        return flight

    def price_history(self, route: Route) -> list[dict]:
        return self._history.get(self._route_key(route), [])

    def get_lowest_recorded(self, route: Route) -> Optional[float]:
        snapshots = self.price_history(route)
        if not snapshots:
            return None
        return min(s["lowest_price"] for s in snapshots if s["lowest_price"])

    def is_low_price(self, route: Route, threshold: float) -> bool:
        flight = self.check_price(route)
        return flight.lowest_price is not None and flight.lowest_price <= threshold
