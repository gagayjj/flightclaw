"""往返比价引擎 - 方案1：两单程比价

对每个出发日 D：
  1. 取 D 日深圳→北京最低价
  2. 取 D+3 和 D+4 日北京→深圳最低价
  3. 总价 = 去程 + 回程（选更便宜的停留天数）
  4. 推荐 ≤¥1700 的组合
"""

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import PriceRecord, RoundTripDeal, SessionLocal

BUDGET = 1700  # 预算上限（含税总价）
STAY_OPTIONS = [3, 4]  # 停留天数选项
ORIGIN_CITY = "深圳"
DEST_CITY = "北京"
OUTBOUND_DATE_MAX = "2026-06-26"  # 最晚出发日期


def _get_lowest_oneway(db: Session, origin: str, destination: str, flight_date: str) -> Optional[dict]:
    """获取某天某路线的最低票价记录"""
    record = db.query(PriceRecord).filter(
        PriceRecord.origin == origin,
        PriceRecord.destination == destination,
        PriceRecord.flight_date == flight_date,
        PriceRecord.total_price >= 300,
    ).order_by(PriceRecord.total_price).first()

    if record:
        return record.to_dict()
    return None


def compare_roundtrip(db: Session, outbound_date_str: str) -> dict:
    """计算指定出发日的往返方案"""
    result = {
        "outbound_date": outbound_date_str,
        "combinations": [],
        "best": None,
    }

    d = date.fromisoformat(outbound_date_str)

    # 去程最低价
    outbound = _get_lowest_oneway(db, ORIGIN_CITY, DEST_CITY, outbound_date_str)
    if not outbound:
        result["error"] = f"{outbound_date_str} 无去程数据"
        return result

    result["outbound"] = outbound

    # 尝试不同停留天数
    best_combo = None

    for stay in STAY_OPTIONS:
        return_date = d + timedelta(days=stay)
        return_date_str = return_date.isoformat()

        inbound = _get_lowest_oneway(db, DEST_CITY, ORIGIN_CITY, return_date_str)
        if not inbound:
            continue

        total = outbound["total_price"] + inbound["total_price"]
        within = total <= BUDGET

        combo = {
            "stay_days": stay,
            "return_date": return_date_str,
            "outbound_price": outbound["total_price"],
            "return_price": inbound["total_price"],
            "total_price": round(total, 1),
            "within_budget": within,
            "outbound_flight": {
                "airline": outbound["airline"],
                "flight_number": outbound["flight_number"],
                "departure_time": outbound["departure_time"],
                "arrival_time": outbound["arrival_time"],
            },
            "return_flight": {
                "airline": inbound["airline"],
                "flight_number": inbound["flight_number"],
                "departure_time": inbound["departure_time"],
                "arrival_time": inbound["arrival_time"],
            },
        }
        result["combinations"].append(combo)

        if best_combo is None or total < best_combo["total_price"]:
            best_combo = combo

    result["best"] = best_combo
    return result


def scan_all_combinations(db: Optional[Session] = None) -> list[dict]:
    """扫描所有日期组合，找出预算内往返方案，保存到数据库"""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # 先清除旧的往返数据，避免重复
        db.query(RoundTripDeal).delete()
        db.flush()

        # 获取数据库中有数据的日期范围
        date_range = db.query(
            PriceRecord.flight_date,
            PriceRecord.origin,
            PriceRecord.destination,
        ).filter(
            PriceRecord.total_price >= 300,
        ).distinct().all()

        # 提取深圳→北京有数据的日期
        outbound_dates = set()
        for dr in date_range:
            if dr.origin == ORIGIN_CITY and dr.destination == DEST_CITY:
                outbound_dates.add(dr.flight_date)

        # 提取北京→深圳有数据的日期
        inbound_dates = set()
        for dr in date_range:
            if dr.origin == DEST_CITY and dr.destination == ORIGIN_CITY:
                inbound_dates.add(dr.flight_date)

        deals = []
        for d_str in sorted(outbound_dates):
            # 只考虑15-26号出发
            if d_str > OUTBOUND_DATE_MAX:
                continue
            d = date.fromisoformat(d_str)
            outbound = _get_lowest_oneway(db, ORIGIN_CITY, DEST_CITY, d_str)
            if not outbound:
                continue

            for stay in STAY_OPTIONS:
                return_d = d + timedelta(days=stay)
                return_d_str = return_d.isoformat()

                if return_d_str not in inbound_dates:
                    continue

                inbound = _get_lowest_oneway(db, DEST_CITY, ORIGIN_CITY, return_d_str)
                if not inbound:
                    continue

                total = outbound["total_price"] + inbound["total_price"]

                # 保存到数据库
                deal = RoundTripDeal(
                    outbound_date=d_str,
                    return_date=return_d_str,
                    stay_days=stay,
                    outbound_airline=outbound["airline"],
                    outbound_flight=outbound["flight_number"],
                    outbound_dep_time=outbound["departure_time"],
                    outbound_arr_time=outbound["arrival_time"],
                    outbound_price=outbound["total_price"],
                    return_airline=inbound["airline"],
                    return_flight=inbound["flight_number"],
                    return_dep_time=inbound["departure_time"],
                    return_arr_time=inbound["arrival_time"],
                    return_price=inbound["total_price"],
                    total_price=round(total, 1),
                    within_budget=total <= BUDGET,
                )
                db.add(deal)
                deals.append(deal.to_dict())

        db.commit()
        print(f"[比价] 扫描完成，共 {len(deals)} 个往返组合")
        return deals

    except Exception as e:
        db.rollback()
        print(f"[比价] 错误: {e}")
        return []
    finally:
        if close_db:
            db.close()


def get_best_deals(db: Session, max_total: float = BUDGET) -> list[dict]:
    """获取预算内最低价往返方案"""
    deals = db.query(RoundTripDeal).filter(
        RoundTripDeal.total_price <= max_total,
    ).order_by(RoundTripDeal.total_price).all()

    return [d.to_dict() for d in deals]
