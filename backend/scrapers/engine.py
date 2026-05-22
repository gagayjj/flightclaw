"""多平台爬虫引擎 - 整合携程、去哪儿、飞猪、航司直营"""

import asyncio
import json
import random
import time
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import PriceRecord, SessionLocal
from flights.models import Route, Flight, FlightPrice
from flights.client import FlightClient
from flights.providers.scraper import CtripScraperProvider
from flights.providers.qunar_scraper import QunarScraperProvider
from flights.providers.fliggy_scraper import FliggyScraperProvider

# 搜索日期范围（出发15-26号，回程最远到30号）
START_DATE = date(2026, 6, 15)
END_DATE = date(2026, 6, 30)
MAX_TOTAL_PRICE = 2000  # 含税最高价（票+机建¥50+燃油¥170）
MIN_TOTAL_PRICE = 300   # 最低合理价格

# 航线列表（可扩展）
ROUTES = [
    {"origin": "深圳", "destination": "北京"},
    {"origin": "北京", "destination": "深圳"},
]

# 各平台预订链接模板
BOOKING_URLS = {
    "ctrip": "https://flights.ctrip.com/online/list/oneway-{dep}-{arr}?depdate={date}&flight={flight}",
    "qunar": "https://flight.qunar.com/site/oneway_list.htm?searchDepartureAirport={dep}&searchArrivalAirport={arr}&startDate={date}",
    "fliggy": "https://www.fliggy.com/search/flight?departure={dep}&arrival={arr}&date={date}",
    "airline": "",
}

# 城市码映射
CITY_CODE_MAP = {
    "深圳": "szx", "北京": "bjs", "广州": "can", "上海": "sha",
    "成都": "ctu", "杭州": "hgh", "西安": "xiy", "重庆": "ckg",
}

# 航距估算表（公里）— 用于燃油附加费计算
ROUTE_DISTANCES = {
    ("深圳", "北京"): 2077,
    ("北京", "深圳"): 2077,
}

# 燃油附加费（2026年5月16日最新标准）
FUEL_SURCHARGE_BELOW_800 = 90   # ≤800km
FUEL_SURCHARGE_ABOVE_800 = 170  # >800km

# 机建费（民航发展基金，固定¥50/航段）
AIRPORT_FEE = 50


def calc_fees(origin: str, destination: str) -> tuple[float, float]:
    """计算机建费和燃油附加费
    返回 (airport_fee, fuel_tax)
    """
    dist = ROUTE_DISTANCES.get((origin, destination), 1200)
    # 燃油附加费按航距分级（2026年5月标准）
    if dist <= 800:
        fuel_tax = FUEL_SURCHARGE_BELOW_800
    else:
        fuel_tax = FUEL_SURCHARGE_ABOVE_800
    return AIRPORT_FEE, fuel_tax


class ScraperEngine:
    """多平台爬虫引擎（携程 + 去哪儿 + 飞猪）"""

    def __init__(self):
        self._providers = {
            "ctrip": CtripScraperProvider(),
            "qunar": QunarScraperProvider(),
            "fliggy": FliggyScraperProvider(),
        }
        self._results: dict[str, list[dict]] = {}

    def run_all(self) -> dict[str, list[dict]]:
        """运行所有平台爬虫"""
        results = {}
        for source, provider in self._providers.items():
            source_results = []
            for route in ROUTES:
                origin, dest = route["origin"], route["destination"]
                print(f"\n[{source}] 扫描路线: {origin} → {dest}")
                records = self._scrape_source(origin, dest, source, provider)
                source_results.extend(records)
            results[source] = source_results
        self._results = results
        return results

    def _scrape_source(self, origin: str, destination: str,
                       source: str, provider) -> list[dict]:
        """通用爬虫：用指定 provider 抓取指定路线"""
        airport_fee, fuel_tax = calc_fees(origin, destination)
        print(f"[{source}] 开始爬取 {START_DATE}~{END_DATE} {origin}→{destination}")

        all_records = []
        client = FlightClient(provider=provider)

        day = START_DATE
        while day <= END_DATE:
            try:
                flight = client.search(origin, destination, day)
                real_source = flight.source if flight.source != source else source
                for p in flight.prices:
                    total = int(p.price) + airport_fee + fuel_tax
                    if total < MIN_TOTAL_PRICE or total > MAX_TOTAL_PRICE:
                        continue
                    record = {
                        "source": real_source,
                        "origin": origin,
                        "destination": destination,
                        "flight_date": day.isoformat(),
                        "airline": p.airline,
                        "flight_number": p.flight_number,
                        "departure_time": p.departure_time,
                        "arrival_time": p.arrival_time,
                        "duration": p.duration,
                        "ticket_price": p.price,
                        "airport_fee": airport_fee,
                        "fuel_tax": fuel_tax,
                        "total_price": float(total),
                        "stops": p.stops,
                        "cabin_class": p.cabin_class,
                        "airport": "PEK",
                        "booking_url": self._booking_url(source, origin, destination, day, p.flight_number),
                        "captured_at": datetime.now(),
                    }
                    all_records.append(record)
                print(f"  [{source}] {day}: {len(flight.prices)} 航班, "
                      f"最低 ¥{int(flight.lowest_price or 0)}")
            except Exception as e:
                print(f"  [{source}] {day}: 失败 - {e}")
            day += timedelta(days=1)

        print(f"[{source}] {origin}→{destination} 完成, {len(all_records)} 条")
        return all_records

    @staticmethod
    def _booking_url(source: str, origin: str, destination: str,
                     flight_date: date, flight_number: str) -> str:
        """生成各平台预订链接"""
        dep = CITY_CODE_MAP.get(origin, origin.lower())
        arr = CITY_CODE_MAP.get(destination, destination.lower())
        d = flight_date.isoformat()

        if source == "ctrip":
            return f"https://flights.ctrip.com/online/list/oneway-{dep}-{arr}?depdate={d}&flight={flight_number}"
        elif source == "qunar":
            return (f"https://flight.qunar.com/site/oneway_list.htm"
                    f"?searchDepartureAirport={origin}"
                    f"&searchArrivalAirport={destination}"
                    f"&startDate={d}")
        elif source == "fliggy":
            return (f"https://www.fliggy.com/search/flight"
                    f"?departure={origin}&arrival={destination}&date={d}")
        return ""

    def save_to_db(self, records: list[dict]):
        """保存记录到数据库"""
        db = SessionLocal()
        try:
            saved = 0
            for r in records:
                exists = db.query(PriceRecord).filter(
                    PriceRecord.source == r["source"],
                    PriceRecord.flight_date == r["flight_date"],
                    PriceRecord.flight_number == r["flight_number"],
                    PriceRecord.ticket_price == r["ticket_price"],
                ).first()
                if not exists:
                    db.add(PriceRecord(**{
                        k: v for k, v in r.items() if hasattr(PriceRecord, k)
                    }))
                    saved += 1
            db.commit()
            print(f"[数据库] 新增 {saved} 条记录")
        except Exception as e:
            db.rollback()
            print(f"[数据库] 错误: {e}")
        finally:
            db.close()

    def get_lowest_prices(self, db_session: Session,
                          origin: str = "", destination: str = "") -> list[dict]:
        """获取当前最低价列表（每天最低）"""
        from sqlalchemy import func
        query = db_session.query(
            PriceRecord.flight_date,
            func.min(PriceRecord.total_price).label("min_price")
        ).filter(
            PriceRecord.total_price.between(MIN_TOTAL_PRICE, MAX_TOTAL_PRICE),
        )
        if origin:
            query = query.filter(PriceRecord.origin == origin)
        if destination:
            query = query.filter(PriceRecord.destination == destination)
        sub = query.group_by(PriceRecord.flight_date).subquery()

        results = db_session.query(PriceRecord).join(
            sub,
            (PriceRecord.flight_date == sub.c.flight_date) &
            (PriceRecord.total_price == sub.c.min_price)
        ).all()

        return [r.to_dict() for r in results]

    def get_price_trend(self, db_session: Session,
                        origin: str = "", destination: str = "") -> list[dict]:
        """获取价格趋势"""
        from sqlalchemy import func
        query = db_session.query(
            PriceRecord.flight_date,
            func.min(PriceRecord.total_price),
            func.max(PriceRecord.total_price),
            func.avg(PriceRecord.total_price),
            func.count(PriceRecord.id),
        )
        if origin:
            query = query.filter(PriceRecord.origin == origin)
        if destination:
            query = query.filter(PriceRecord.destination == destination)
        rows = query.group_by(PriceRecord.flight_date).order_by(PriceRecord.flight_date).all()

        return [
            {
                "date": r[0], "min": round(r[1], 1), "max": round(r[2], 1),
                "avg": round(r[3], 1), "count": r[4],
            }
            for r in rows
        ]


def quick_scan(origin: str = "", destination: str = "") -> list[dict]:
    """快速扫描当前最低价（不走数据库，直接查携程）"""
    engine = ScraperEngine()
    results = engine.run_all()
    records = results.get("ctrip", [])
    engine.save_to_db(records)

    # 按路线+日期分组取最低
    by_route_date: dict[tuple[str, str, str], list[dict]] = {}
    for r in records:
        key = (r["origin"], r["destination"], r["flight_date"])
        by_route_date.setdefault(key, []).append(r)

    lowest = []
    for key, flights in sorted(by_route_date.items()):
        best = min(flights, key=lambda x: x["total_price"])
        lowest.append(best)
    return lowest
