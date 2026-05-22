import random
from flights.models import Flight, FlightPrice, Route
from flights.providers import FlightProvider

AIRLINES = ["中国国航", "东方航空", "南方航空", "海南航空", "春秋航空", "吉祥航空"]


class MockProvider(FlightProvider):
    def search(self, route: Route) -> Flight:
        num_prices = random.randint(3, 6)
        prices = []
        for _ in range(num_prices):
            airline = random.choice(AIRLINES)
            flight_num = f"{''.join(random.choices('0123456789', k=4))}"
            dep_hour = random.randint(6, 22)
            dep_min = random.choice([0, 15, 30, 45])
            duration_h = random.randint(1, 5)
            duration_m = random.choice([0, 15, 30, 45])
            arr_h = (dep_hour + duration_h + (dep_min + duration_m) // 60) % 24
            arr_m = (dep_min + duration_m) % 60

            prices.append(FlightPrice(
                airline=airline,
                flight_number=f"{airline[:2]}{flight_num}",
                departure_time=f"{dep_hour:02d}:{dep_min:02d}",
                arrival_time=f"{arr_h:02d}:{arr_m:02d}",
                duration=f"{duration_h}h{duration_m:02d}",
                price=random.randint(300, 2500),
                stops=random.choices([0, 1, 2], weights=[0.5, 0.3, 0.2])[0],
            ))

        return Flight(route=route, prices=prices, source="mock")
