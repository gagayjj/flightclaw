"""低价机票追踪 - FastAPI 后端服务"""

import os
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import init_db, get_db, PriceRecord, RoundTripDeal
from backend.scrapers.engine import ScraperEngine, quick_scan
from backend.scheduler import TicketScheduler
from backend.push import WeChatPusher
from backend.comparator import compare_roundtrip, scan_all_combinations, get_best_deals
from sqlalchemy import func

scheduler = TicketScheduler()
engine = ScraperEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    print("[启动] 数据库已初始化，调度器已自动启动")
    yield
    scheduler.stop()
    print("[关闭] 调度器已停止")


app = FastAPI(
    title="低价机票追踪 API",
    description="实时监控深圳↔北京低价机票，多渠道比价，微信推送",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== API 路由 ======

@app.get("/")
def root():
    return {"status": "ok", "name": "低价机票追踪", "version": "1.0.0"}


@app.get("/api/prices")
def get_prices(
    date_from: str = Query("2026-06-15"),
    date_to: str = Query("2026-06-23"),
    origin: str = Query("深圳"),
    destination: str = Query("北京"),
    max_price: float = Query(1300),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """获取符合预算的航班列表"""
    query = db.query(PriceRecord).filter(
        PriceRecord.origin == origin,
        PriceRecord.destination == destination,
        PriceRecord.flight_date.between(date_from, date_to),
        PriceRecord.total_price <= max_price,
        PriceRecord.total_price >= 300,
    )
    if source:
        query = query.filter(PriceRecord.source == source)

    rows = query.order_by(PriceRecord.flight_date, PriceRecord.total_price).all()
    return {"count": len(rows), "data": [r.to_dict() for r in rows]}


@app.get("/api/prices/lowest")
def get_lowest_prices(
    date_from: str = Query("2026-06-15"),
    date_to: str = Query("2026-06-23"),
    origin: str = Query("深圳"),
    destination: str = Query("北京"),
    db: Session = Depends(get_db),
):
    """获取每天最低价"""
    sub = db.query(
        PriceRecord.flight_date,
        func.min(PriceRecord.total_price).label("min_price")
    ).filter(
        PriceRecord.origin == origin,
        PriceRecord.destination == destination,
        PriceRecord.flight_date.between(date_from, date_to),
        PriceRecord.total_price >= 300,
    ).group_by(PriceRecord.flight_date).subquery()

    rows = db.query(PriceRecord).join(
        sub,
        (PriceRecord.flight_date == sub.c.flight_date) &
        (PriceRecord.total_price == sub.c.min_price)
    ).order_by(PriceRecord.flight_date).all()

    data = [r.to_dict() for r in rows]
    return {"count": len(data), "data": data}


@app.get("/api/prices/compare")
def price_comparison(
    date: str = Query(...),
    origin: str = Query("深圳"),
    destination: str = Query("北京"),
    db: Session = Depends(get_db),
):
    """按平台对比某天的航班价格"""
    rows = db.query(PriceRecord).filter(
        PriceRecord.origin == origin,
        PriceRecord.destination == destination,
        PriceRecord.flight_date == date,
    ).order_by(PriceRecord.total_price).all()

    # 按航班号分组，每个航班下列出各平台价格
    by_flight: dict = {}
    for r in rows:
        key = r.flight_number
        if key not in by_flight:
            by_flight[key] = {
                "flight_number": r.flight_number,
                "airline": r.airline,
                "departure_time": r.departure_time,
                "arrival_time": r.arrival_time,
                "duration": r.duration,
                "stops": r.stops,
                "prices": {},
            }
        by_flight[key]["prices"][r.source] = {
            "ticket_price": r.ticket_price,
            "total_price": r.total_price,
            "booking_url": r.booking_url,
        }

    # 获取所有已知平台列表
    all_sources = db.query(PriceRecord.source).distinct().all()
    all_sources = [s[0] for s in all_sources]

    return {
        "date": date,
        "sources": all_sources,
        "data": list(by_flight.values()),
    }


@app.get("/api/prices/trend")
def get_trend(
    date_from: str = Query("2026-06-15"),
    date_to: str = Query("2026-06-23"),
    origin: str = Query("深圳"),
    destination: str = Query("北京"),
    db: Session = Depends(get_db),
):
    """获取价格趋势"""
    rows = db.query(
        PriceRecord.flight_date,
        func.min(PriceRecord.total_price),
        func.max(PriceRecord.total_price),
        func.avg(PriceRecord.total_price),
        func.count(PriceRecord.id),
    ).filter(
        PriceRecord.origin == origin,
        PriceRecord.destination == destination,
        PriceRecord.flight_date.between(date_from, date_to),
    ).group_by(PriceRecord.flight_date).order_by(PriceRecord.flight_date).all()

    data = [
        {"date": r[0], "min": round(r[1], 1), "max": round(r[2], 1),
         "avg": round(r[3], 1), "count": r[4]}
        for r in rows
    ]
    return {"data": data}


@app.post("/api/scan")
def trigger_scan():
    """手动触发一次扫描"""
    try:
        results = engine.run_all()
        records = results.get("ctrip", [])
        engine.save_to_db(records)
        return {"status": "ok", "count": len(records)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/start-monitor")
def start_monitor():
    """启动自动监控"""
    scheduler.start()
    return {"status": "ok", "message": "监控已启动 (30min/次)"}


@app.post("/api/stop-monitor")
def stop_monitor():
    """停止自动监控"""
    scheduler.stop()
    return {"status": "ok", "message": "监控已停止"}


@app.get("/api/statistics")
def get_statistics(db: Session = Depends(get_db)):
    """获取统计数据"""
    total = db.query(PriceRecord).count()
    sources = db.query(
        PriceRecord.source, func.count(PriceRecord.id)
    ).group_by(PriceRecord.source).all()

    # 当前最低价
    lowest = db.query(
        func.min(PriceRecord.total_price)
    ).filter(
        PriceRecord.total_price >= 300
    ).scalar()

    # 今日新增
    today_count = db.query(PriceRecord).filter(
        func.date(PriceRecord.captured_at) == date.today().isoformat()
    ).count()

    return {
        "total_records": total,
        "lowest_price": lowest or 0,
        "today_new": today_count,
        "sources": {s: c for s, c in sources},
    }


@app.get("/api/roundtrip/compare")
def roundtrip_compare(
    date: str = Query("2026-06-15"),
    db: Session = Depends(get_db),
):
    """查询某天出发的往返比价"""
    result = compare_roundtrip(db, date)
    return result


@app.get("/api/roundtrip/deals")
def roundtrip_deals(
    max_total: float = Query(1700),
    db: Session = Depends(get_db),
):
    """获取预算内的往返方案"""
    deals = get_best_deals(db, max_total)
    return {"count": len(deals), "data": deals}


@app.post("/api/roundtrip/scan")
def roundtrip_scan(db: Session = Depends(get_db)):
    """手动触发往返扫描"""
    deals = scan_all_combinations(db)
    return {"status": "ok", "count": len(deals)}


@app.post("/api/push/test")
def test_push():
    """测试微信推送"""
    test_record = {
        "origin": "深圳",
        "destination": "北京",
        "flight_date": "2026-06-21",
        "airline": "深圳航空",
        "flight_number": "ZH9101",
        "departure_time": "07:30",
        "arrival_time": "11:00",
        "ticket_price": 910,
        "airport_fee": 50,
        "fuel_tax": 170,
        "total_price": 1130,
        "stops": 0,
        "source": "携程",
        "booking_url": "https://flights.ctrip.com/",
    }
    ok = WeChatPusher.push_price_alert(test_record, reason="测试推送")
    return {"status": "sent" if ok else "failed", "note": "需要配置 SERVERCHAN_KEY 或 WECOM_WEBHOOK"}


# ====== 启动 ======
if __name__ == "__main__":
    import uvicorn
    init_db()
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
