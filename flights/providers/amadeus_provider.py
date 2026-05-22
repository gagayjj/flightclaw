import os
from typing import Optional

from amadeus import Client, ResponseError

from flights.models import Flight, FlightPrice, Route
from flights.providers import FlightProvider

# 城市名 → IATA 代码映射（北京默认首都机场 PEK）
_CITY_IATA: dict[str, str] = {
    "北京": "PEK", "上海": "SHA", "广州": "CAN", "深圳": "SZX",
    "成都": "CTU", "杭州": "HGH", "西安": "XIY", "重庆": "CKG",
    "昆明": "KMG", "南京": "NKG", "厦门": "XMN", "武汉": "WUH",
    "长沙": "CSX", "郑州": "CGO", "青岛": "TAO", "大连": "DLC",
    "海口": "HAK", "三亚": "SYX", "哈尔滨": "HRB", "贵阳": "KWE",
}

FIXED_FUEL_FEE = 50  # 国内航线燃油附加费（模拟固定值）


class AmadeusProvider(FlightProvider):
    def __init__(self, client: Optional[Client] = None):
        self._client = client or Client(
            client_id=os.getenv("AMADEUS_API_KEY", ""),
            client_secret=os.getenv("AMADEUS_API_SECRET", ""),
            hostname="test",  # test 环境 / 生产用 "production"
        )

    def search(self, route: Route) -> Flight:
        origin = _CITY_IATA.get(route.origin)
        destination = _CITY_IATA.get(route.destination)
        if not origin or not destination:
            raise ValueError(f"不支持的城市: {route.origin} 或 {route.destination}")

        try:
            resp = self._client.shopping.flight_offers_search.get(
                originLocationCode=origin,
                destinationLocationCode=destination,
                departureDate=route.date.isoformat(),
                adults=1,
                currencyCode="CNY",
                max=10,
            )
        except ResponseError as e:
            raise RuntimeError(f"Amadeus API 错误: {e}") from e

        data = resp.data or []
        prices = []
        for offer in data:
            first_segment = offer["itineraries"][0]["segments"][0]
            last_segment = offer["itineraries"][0]["segments"][-1]
            airline = first_segment["carrierCode"]
            flight_num = first_segment["number"]
            price = float(offer["price"]["grandTotal"])
            stops = len(offer["itineraries"][0]["segments"]) - 1

            prices.append(FlightPrice(
                airline=airline,
                flight_number=f"{airline}{flight_num}",
                departure_time=first_segment["departure"]["at"][11:16],
                arrival_time=last_segment["arrival"]["at"][11:16],
                duration=offer["itineraries"][0]["duration"][2:].lower(),
                price=price,
                currency="CNY",
                stops=stops,
            ))

        if not prices:
            raise RuntimeError(f"未找到 {route.origin}→{route.destination} 的航班")

        return Flight(route=route, prices=prices, source="amadeus")
