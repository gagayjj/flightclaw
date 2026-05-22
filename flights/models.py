from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class Route:
    origin: str
    destination: str
    date: date

    def __str__(self):
        return f"{self.origin}→{self.destination} ({self.date})"


@dataclass
class FlightPrice:
    airline: str
    flight_number: str
    departure_time: str
    arrival_time: str
    duration: str
    price: float
    currency: str = "CNY"
    stops: int = 0
    cabin_class: str = "经济舱"
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Flight:
    route: Route
    prices: list[FlightPrice] = field(default_factory=list)
    lowest_price: Optional[float] = None
    source: str = "mock"

    def __post_init__(self):
        if self.prices and self.lowest_price is None:
            self.lowest_price = min(p.price for p in self.prices)

    def best_deal(self) -> Optional[FlightPrice]:
        return min(self.prices, key=lambda p: p.price) if self.prices else None
