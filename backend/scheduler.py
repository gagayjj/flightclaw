"""定时任务调度器"""

import time
from datetime import datetime, date
from apscheduler.schedulers.background import BackgroundScheduler

from backend.scrapers.engine import ScraperEngine
from backend.push import WeChatPusher
from backend.database import SessionLocal, PriceRecord, PriceAlert, WeeklySummary, RoundTripDeal
from backend.comparator import scan_all_combinations, get_best_deals
from sqlalchemy import func


class TicketScheduler:
    """自动抓取 & 推送调度器"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.engine = ScraperEngine()
        self._last_prices: dict[str, float] = {}  # date -> lowest price for change detection

    def start(self):
        """启动所有定时任务（可重复调用）"""
        if self.scheduler.running:
            return
        self.scheduler.add_job(
            self._capture_job, "interval", minutes=30,
            id="capture", name="定时抓取航班价格", replace_existing=True,
        )
        self.scheduler.add_job(
            self._daily_summary_job, "cron", hour=20, minute=0,
            id="daily_summary", name="每日低价推送", replace_existing=True,
        )
        self.scheduler.add_job(
            self._weekly_summary_job, "cron", day_of_week="mon", hour=9, minute=0,
            id="weekly_summary", name="每周低价总结", replace_existing=True,
        )
        self.scheduler.start()
        print(f"[调度器] 定时任务已启动 (30min抓取 + 每日20点推送 + 每周一9点周报)")

    def stop(self):
        self.scheduler.shutdown()

    def _capture_job(self):
        """抓取任务 - 检查低价并推送"""
        print(f"\n[抓取] {datetime.now().strftime('%Y-%m-%d %H:%M')} 开始扫描...")
        try:
            results = self.engine.run_all()
            records = results.get("ctrip", [])

            if not records:
                print("[抓取] 无数据")
                return

            self.engine.save_to_db(records)

            # 按路线+日期分组检查新低价
            by_route_date: dict[tuple[str, str, str], list[dict]] = {}
            for r in records:
                key = (r["origin"], r["destination"], r["flight_date"])
                by_route_date.setdefault(key, []).append(r)

            for (orig, dest, d), flights in sorted(by_route_date.items()):
                best = min(flights, key=lambda x: x["total_price"])
                prev = self._last_prices.get(f"{orig}→{dest}|{d}")

                if prev is None or best["total_price"] < prev:
                    route_str = f"{orig}→{dest}"
                    WeChatPusher.push_price_alert(
                        best,
                        reason=f"发现新低价! {d} {route_str} 最低仅 ¥{int(best['total_price'])}"
                    )
                    self._last_prices[f"{orig}→{dest}|{d}"] = best["total_price"]
                    print(f"  🚨 推送新低价 {route_str} {d}: ¥{int(best['total_price'])}")

            print(f"[抓取] 完成, 共 {len(records)} 条记录")

            # 同步数据到云数据库（手机端可查）
            try:
                import subprocess
                import os as _os
                sync_dir = _os.path.dirname(_os.path.dirname(__file__))
                subprocess.run(
                    [_os.path.join(sync_dir, '.venv/bin/python3'),
                     _os.path.join(sync_dir, 'backend/sync-to-cloud.py')],
                    capture_output=True, text=True, timeout=120,
                )
                print(f"[云同步] 完成")
            except Exception as e3:
                print(f"[云同步] 错误: {e3}")

            # 往返比价扫描
            try:
                db = SessionLocal()
                scan_all_combinations(db)
                deals = get_best_deals(db)
                if deals:
                    cheapest = deals[0]
                    print(f"  ✈️ 最佳往返: {cheapest['outbound_date']}→{cheapest['return_date']} "
                          f"¥{int(cheapest['total_price'])}")
                    # 预算内推送
                    budget_deals = [d for d in deals if d['total_price'] <= 1700]
                    if budget_deals:
                        best = budget_deals[0]
                        WeChatPusher.push_roundtrip_alert(best)
                db.close()
            except Exception as e2:
                print(f"[往返比价] 错误: {e2}")

        except Exception as e:
            print(f"[抓取] 错误: {e}")

    def _daily_summary_job(self):
        """每日推送"""
        print("[每日推送] 生成今日低价汇总...")
        db = SessionLocal()
        try:
            # 遍历所有路线推送每日汇总
            from backend.scrapers.engine import ROUTES
            for route in ROUTES:
                origin, dest = route["origin"], route["destination"]
                lowest = self.engine.get_lowest_prices(db, origin=origin, destination=dest)
                if lowest:
                    WeChatPusher.push_daily_summary(lowest, origin=origin, destination=dest)
                else:
                    print(f"[每日推送] {origin}→{dest} 无数据")
        finally:
            db.close()

    def _weekly_summary_job(self):
        """每周总结推送"""
        print("[周报] 生成每周总结...")
        db = SessionLocal()
        try:
            from backend.scrapers.engine import ROUTES
            for route in ROUTES:
                origin, dest = route["origin"], route["destination"]
                today = date.today()
                week_ago = today.isoformat()
                records = db.query(PriceRecord).filter(
                    PriceRecord.flight_date >= week_ago,
                    PriceRecord.origin == origin,
                    PriceRecord.destination == dest,
                ).all()

                trend = self.engine.get_price_trend(db, origin=origin, destination=dest)
                WeChatPusher.push_weekly_summary(
                    [r.to_dict() for r in records], trend,
                    origin=origin, destination=dest,
                )

                # 保存周报
                if records:
                    summary = WeeklySummary(
                        week_start=f"{today.year}-W{today.isocalendar()[1]:02d}",
                        route=f"{origin}-{dest}",
                        lowest_price=min((r.total_price for r in records), default=0),
                        lowest_flight={},
                        avg_price=sum((r.total_price for r in records), 0) / max(len(records), 1),
                        price_trend=trend,
                    )
                    db.add(summary)
                    db.commit()
        finally:
            db.close()
