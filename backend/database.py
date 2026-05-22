import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, JSON, func
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tickets.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class PriceRecord(Base):
    __tablename__ = "price_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(32), index=True)            # ctrip, qunar, fliggy, airline
    origin = Column(String(16), index=True)             # 深圳
    destination = Column(String(16), index=True)        # 北京
    flight_date = Column(String(16), index=True)         # 2026-06-21
    airline = Column(String(64))                        # 中国国航
    flight_number = Column(String(32))                  # CA1358
    departure_time = Column(String(16))                 # 20:00
    arrival_time = Column(String(16))                   # 23:15
    duration = Column(String(16))                       # 3h15
    ticket_price = Column(Float)                        # 票价
    airport_fee = Column(Float, default=50)            # 机建费（固定¥50）
    fuel_tax = Column(Float, default=50)               # 燃油附加费（按航距浮动）
    total_price = Column(Float)                         # 票价+机建+燃油
    stops = Column(Integer, default=0)                  # 经停次数
    cabin_class = Column(String(32), default="经济舱")
    airport = Column(String(16), default="PEK")        # 到达机场
    booking_url = Column(String(512), default="")       # 预订链接
    captured_at = Column(DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "origin": self.origin,
            "destination": self.destination,
            "flight_date": self.flight_date,
            "airline": self.airline,
            "flight_number": self.flight_number,
            "departure_time": self.departure_time,
            "arrival_time": self.arrival_time,
            "duration": self.duration,
            "ticket_price": self.ticket_price,
            "airport_fee": self.airport_fee,
            "fuel_tax": self.fuel_tax,
            "total_price": self.total_price,
            "stops": self.stops,
            "airport": self.airport,
            "booking_url": self.booking_url,
            "captured_at": self.captured_at.isoformat() if self.captured_at else "",
        }


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    route = Column(String(64), index=True)               # 深圳-北京
    flight_date = Column(String(16))                     # 2026-06-21
    target_price = Column(Float)                         # 目标价
    current_lowest = Column(Float)                       # 当前最低
    notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    notified_at = Column(DateTime, nullable=True)


class RoundTripDeal(Base):
    """往返比价方案"""
    __tablename__ = "round_trip_deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    outbound_date = Column(String(16), index=True)         # 去程日期 2026-06-15
    return_date = Column(String(16), index=True)           # 回程日期 2026-06-18
    stay_days = Column(Integer)                             # 停留天数 3
    # 去程信息
    outbound_airline = Column(String(64))
    outbound_flight = Column(String(32))
    outbound_dep_time = Column(String(16))
    outbound_arr_time = Column(String(16))
    outbound_price = Column(Float)                          # 去程含税总价
    # 回程信息
    return_airline = Column(String(64))
    return_flight = Column(String(32))
    return_dep_time = Column(String(16))
    return_arr_time = Column(String(16))
    return_price = Column(Float)                            # 回程含税总价
    # 汇总
    total_price = Column(Float, index=True)                 # 往返总价
    within_budget = Column(Boolean, default=False)          # 是否在预算内（≤¥1700）
    captured_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "outbound_date": self.outbound_date,
            "return_date": self.return_date,
            "stay_days": self.stay_days,
            "outbound": {
                "airline": self.outbound_airline,
                "flight": self.outbound_flight,
                "dep_time": self.outbound_dep_time,
                "arr_time": self.outbound_arr_time,
                "price": self.outbound_price,
            },
            "return": {
                "airline": self.return_airline,
                "flight": self.return_flight,
                "dep_time": self.return_dep_time,
                "arr_time": self.return_arr_time,
                "price": self.return_price,
            },
            "total_price": self.total_price,
            "within_budget": self.within_budget,
            "captured_at": self.captured_at.isoformat() if self.captured_at else "",
        }


class WeeklySummary(Base):
    __tablename__ = "weekly_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    week_start = Column(String(16))                      # 2026-W25
    route = Column(String(64))
    lowest_price = Column(Float)
    lowest_flight = Column(JSON)                         # 最低价航班详情
    avg_price = Column(Float)                            # 平均价
    price_trend = Column(JSON)                           # 价格趋势
    created_at = Column(DateTime, default=datetime.now)


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
