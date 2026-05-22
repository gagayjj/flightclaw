"""去哪儿爬虫 — Playwright 拦截航班数据 API"""

import asyncio
from datetime import date
from typing import Optional

from flights.models import Flight, FlightPrice, Route
from flights.providers import FlightProvider

_CITY_CODE = {
    "北京": "BJS", "上海": "SHA", "广州": "CAN", "深圳": "SZX",
    "成都": "CTU", "杭州": "HGH", "西安": "XIY", "重庆": "CKG",
    "昆明": "KMG", "南京": "NKG", "厦门": "XMN", "武汉": "WUH",
    "长沙": "CSX", "郑州": "CGO", "青岛": "TAO", "大连": "DLC",
    "海口": "HAK", "三亚": "SYX", "哈尔滨": "HRB", "贵阳": "KWE",
}


class QunarScraperProvider(FlightProvider):
    """通过 Playwright 从去哪儿抓取真实航班价格"""

    def __init__(self, headless: bool = True, timeout_ms: int = 30000):
        self._headless = headless
        self._timeout = timeout_ms
        self._cache: dict[str, Flight] = {}

    def search(self, route: Route) -> Flight:
        cache_key = f"qunar-{route.origin}-{route.destination}-{route.date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            flight = asyncio.run(self._scrape_qunar(route))
            if flight and flight.prices:
                self._cache[cache_key] = flight
                return flight
        except Exception:
            pass
        flight = self._fallback(route)
        self._cache[cache_key] = flight
        return flight

    async def _scrape_qunar(self, route: Route) -> Optional[Flight]:
        from playwright.async_api import async_playwright

        dep_name = route.origin
        arr_name = route.destination
        date_str = route.date.strftime("%Y-%m-%d")
        url = (
            f"https://flight.qunar.com/site/oneway_list.htm"
            f"?searchDepartureAirport={dep_name}"
            f"&searchArrivalAirport={arr_name}"
            f"&startDate={date_str}"
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            page = await browser.new_page()
            page.set_default_timeout(self._timeout)

            # 收集所有符合的响应
            responses = []

            def on_response(resp):
                url_lower = resp.url.lower()
                if any(kw in url_lower for kw in [
                    "twell/searchrt_ui/js/", "api/searchflight",
                    "api/flightsearch", "searchflight",
                ]):
                    responses.append(resp)

            page.on("response", on_response)
            await page.goto(url, wait_until="networkidle", timeout=self._timeout)
            await asyncio.sleep(3)  # 给 JS 渲染时间
            await browser.close()

        if not responses:
            return None

        # 尝试每个响应，找到有航班数据的
        for resp in responses:
            try:
                body = await resp.json()
            except Exception:
                continue

            data = self._parse_response(body)
            if data:
                return Flight(route=route, prices=data, source="qunar")

        return None

    def _parse_response(self, body: dict) -> Optional[list[FlightPrice]]:
        """尝试多种可能的响应结构"""
        prices = []

        # Qunar 可能的响应结构 1: data.flightItineraryList
        try:
            flights = body["data"]["flightItineraryList"]
            for f in flights:
                seg = f["flightSegments"][0]
                fl = seg["flightList"][0]
                price_info = f.get("priceList", [{}])[0]
                ticket_price = float(price_info.get("adultPrice", 0))
                if ticket_price <= 0:
                    continue
                dep = fl.get("departureDateTime", "")
                arr = fl.get("arrivalDateTime", "")
                dur = seg.get("duration", 0)
                prices.append(FlightPrice(
                    airline=fl.get("marketAirlineName", ""),
                    flight_number=fl.get("flightNo", ""),
                    departure_time=dep[11:16] if len(dep) > 16 else dep,
                    arrival_time=arr[11:16] if len(arr) > 16 else arr,
                    duration=f"{dur // 60}h{dur % 60:02d}",
                    price=ticket_price,
                    stops=seg.get("transferCount", 0),
                ))
            if prices:
                return prices
        except (KeyError, TypeError, IndexError):
            pass

        # 结构 2: data.flightList (Qunar 旧版 API)
        try:
            flights = body["data"]["flightList"]
            for f in flights:
                ticket_price = float(f.get("price", 0) or f.get("totalPrice", 0))
                if ticket_price <= 0:
                    continue
                prices.append(FlightPrice(
                    airline=f.get("airlineName", ""),
                    flight_number=f.get("flightNo", ""),
                    departure_time=f.get("departTime", ""),
                    arrival_time=f.get("arriveTime", ""),
                    duration=f.get("flightTime", ""),
                    price=ticket_price,
                    stops=int(f.get("stopNum", 0)),
                ))
            if prices:
                return prices
        except (KeyError, TypeError):
            pass

        # 结构 3: ret=true 时的 data 数组
        try:
            flights = body.get("data", [])
            if isinstance(flights, list):
                for f in flights:
                    ticket_price = float(f.get("price", 0) or f.get("totalPrice", 0) or 0)
                    if ticket_price <= 0:
                        continue
                    prices.append(FlightPrice(
                        airline=f.get("airlineName", ""),
                        flight_number=f.get("flightNo", ""),
                        departure_time=f.get("departTime", ""),
                        arrival_time=f.get("arriveTime", ""),
                        duration=f.get("flightTime", ""),
                        price=ticket_price,
                        stops=int(f.get("stopNum", 0)),
                    ))
            if prices:
                return prices
        except (TypeError, ValueError):
            pass

        return None

    def _fallback(self, route: Route) -> Flight:
        """兜底：模拟数据"""
        import random
        from flights.providers.mock import AIRLINES
        lo, hi = 500, 2000
        num = random.randint(3, 5)
        prices = []
        for _ in range(num):
            airline = random.choice(AIRLINES)
            dep_h = random.randint(6, 22)
            dep_m = random.choice([0, 15, 30, 45])
            dur_h = random.randint(2, 4)
            dur_m = random.choice([0, 15, 30])
            arr_h = (dep_h + dur_h + (dep_m + dur_m) // 60) % 24
            arr_m = (dep_m + dur_m) % 60
            prices.append(FlightPrice(
                airline=airline,
                flight_number=f"{airline[:2]}{''.join(random.choices('0123456789', k=4))}",
                departure_time=f"{dep_h:02d}:{dep_m:02d}",
                arrival_time=f"{arr_h:02d}:{arr_m:02d}",
                duration=f"{dur_h}h{dur_m:02d}",
                price=random.randint(lo, hi),
                stops=random.choices([0, 0, 0, 1], [0.5, 0.3, 0.15, 0.05])[0],
            ))
        return Flight(route=route, prices=prices, source="mock(qunar)")
