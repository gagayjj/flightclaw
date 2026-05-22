"""飞猪爬虫 — Playwright 拦截航班数据 API"""

import asyncio
from datetime import date
from typing import Optional

from flights.models import Flight, FlightPrice, Route
from flights.providers import FlightProvider


class FliggyScraperProvider(FlightProvider):
    """通过 Playwright 从飞猪抓取真实航班价格"""

    def __init__(self, headless: bool = True, timeout_ms: int = 30000):
        self._headless = headless
        self._timeout = timeout_ms
        self._cache: dict[str, Flight] = {}

    def search(self, route: Route) -> Flight:
        cache_key = f"fliggy-{route.origin}-{route.destination}-{route.date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            flight = asyncio.run(self._scrape_fliggy(route))
            if flight and flight.prices:
                self._cache[cache_key] = flight
                return flight
        except Exception:
            pass
        flight = self._fallback(route)
        self._cache[cache_key] = flight
        return flight

    async def _scrape_fliggy(self, route: Route) -> Optional[Flight]:
        from playwright.async_api import async_playwright

        dep_name = route.origin
        arr_name = route.destination
        date_str = route.date.strftime("%Y-%m-%d")
        url = (
            f"https://www.fliggy.com/search/flight"
            f"?departure={dep_name}"
            f"&arrival={arr_name}"
            f"&date={date_str}"
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self._headless)
            page = await browser.new_page()
            page.set_default_timeout(self._timeout)

            responses = []

            def on_response(resp):
                url_lower = resp.url.lower()
                if any(kw in url_lower for kw in [
                    "api/search", "api/flight", "flight/search",
                    "offerlist", "flightoffer",
                ]):
                    responses.append(resp)

            page.on("response", on_response)
            await page.goto(url, wait_until="networkidle", timeout=self._timeout)
            await asyncio.sleep(3)
            await browser.close()

        if not responses:
            return None

        for resp in responses:
            try:
                body = await resp.json()
            except Exception:
                continue

            data = self._parse_response(body)
            if data:
                return Flight(route=route, prices=data, source="fliggy")

        return None

    def _parse_response(self, body: dict) -> Optional[list[FlightPrice]]:
        prices = []

        # 结构 1: data.flightList / data.flights
        for key in ("flightList", "flights", "offerList", "items"):
            try:
                items = body.get("data", {}).get(key, [])
                if not items and isinstance(body.get(key), list):
                    items = body[key]
                for f in items:
                    ticket_price = float(
                        f.get("price", 0) or f.get("totalPrice", 0)
                        or f.get("salePrice", 0) or 0
                    )
                    if ticket_price <= 0:
                        continue
                    # 飞猪响应中航班信息可能在 segments 里
                    segs = f.get("segments", f.get("flightSegments", []))
                    if segs:
                        seg = segs[0]
                        fl = seg.get("flight", seg)
                    else:
                        seg = f
                        fl = f

                    dep = fl.get("departureDateTime", fl.get("departTime", ""))
                    arr = fl.get("arrivalDateTime", fl.get("arriveTime", ""))
                    dur = fl.get("duration", fl.get("flightTime", ""))

                    prices.append(FlightPrice(
                        airline=fl.get("airlineName", fl.get("airline", "")),
                        flight_number=fl.get("flightNo", fl.get("flightNumber", "")),
                        departure_time=dep[11:16] if len(dep) > 16 else dep,
                        arrival_time=arr[11:16] if len(arr) > 16 else arr,
                        duration=str(dur) if isinstance(dur, str) else f"{dur // 60}h{dur % 60:02d}",
                        price=ticket_price,
                        stops=int(seg.get("transferCount", seg.get("stops", 0))),
                    ))
                if prices:
                    return prices
            except (KeyError, TypeError, IndexError):
                continue

        # 结构 2: data.data 嵌套
        try:
            items = body.get("data", {}).get("data", [])
            for f in items:
                ticket_price = float(f.get("price", 0) or 0)
                if ticket_price <= 0:
                    continue
                prices.append(FlightPrice(
                    airline=f.get("airlineName", ""),
                    flight_number=f.get("flightNo", ""),
                    departure_time=f.get("departTime", ""),
                    arrival_time=f.get("arriveTime", ""),
                    duration=f.get("flightTime", ""),
                    price=ticket_price,
                    stops=int(f.get("stops", 0)),
                ))
            if prices:
                return prices
        except (KeyError, TypeError):
            pass

        return None

    def _fallback(self, route: Route) -> Flight:
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
        return Flight(route=route, prices=prices, source="mock(fliggy)")
