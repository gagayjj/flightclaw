"""
云端运行器 — GitHub Actions 入口
执行抓取 → 保存到 SQLite → 推送到云数据库
"""

import os
import sys
import json
import urllib.request
import urllib.error

# 把项目根目录加入 path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 云函数 HTTP 地址（从环境变量读取，GitHub Actions 里配置）
SYNC_URL = os.environ.get(
    "SYNC_URL",
    "https://cloudbase-d7g70bhvj07f8e6dd.service.tcloudbase.com/sync-import",
)
AUTH_TOKEN = "flightclaw-sync-2026"


def run_scraper():
    """执行全部爬虫"""
    from backend.database import engine, Base
    from backend.scrapers.engine import ScraperEngine, ROUTES

    # 确保数据库表存在
    Base.metadata.create_all(bind=engine)

    engine_s = ScraperEngine()
    results = engine_s.run_all()

    # 汇总统计
    total = sum(len(v) for v in results.values())
    print(f"\n=== 抓取完成 ===")
    for source, records in results.items():
        print(f"  {source}: {len(records)} 条")
    print(f"  总计: {total} 条")

    # 去重合并后保存
    all_records = []
    seen = set()
    for records in results.values():
        for r in records:
            key = (r["source"], r["flight_date"], r["flight_number"])
            if key not in seen:
                seen.add(key)
                all_records.append(r)

    from backend.database import SessionLocal, PriceRecord
    db = SessionLocal()
    try:
        saved = 0
        for r in all_records:
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
        print(f"\n数据库新增: {saved} 条")
    except Exception as e:
        db.rollback()
        print(f"数据库错误: {e}")
    finally:
        db.close()

    return all_records


def sync_to_cloud(data):
    """推送到云数据库"""
    if not SYNC_URL:
        print("未配置 SYNC_URL，跳过云同步")
        return

    print(f"\n开始云同步 ({len(data)} 条)...")

    # 按日期分批（最多 500 条一批）
    MAX_BATCH = 500
    for i in range(0, len(data), MAX_BATCH):
        batch = data[i:i + MAX_BATCH]
        payload = json.dumps({
            "action": "sync_prices",
            "token": AUTH_TOKEN,
            "data": batch,
        }).encode("utf-8")

        req = urllib.request.Request(
            SYNC_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                print(f"  批次 {i // MAX_BATCH + 1}: {result.get('message', result)}")
        except Exception as e:
            print(f"  批次 {i // MAX_BATCH + 1} 失败: {e}")

    # 同步往返比价
    try:
        from backend.database import SessionLocal
        from backend.comparator import scan_all_combinations
        db = SessionLocal()
        deals = scan_all_combinations(db)
        db.close()

        payload = json.dumps({
            "action": "sync_roundtrip",
            "token": AUTH_TOKEN,
            "data": deals,
        }).encode("utf-8")
        req = urllib.request.Request(
            SYNC_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"  往返同步: {result.get('message', result)}")
    except Exception as e:
        print(f"  往返同步失败: {e}")

    print("云同步完成")


def save_json(data):
    """保存为 JSON 文件（供 GitHub 提交 + 云函数拉取）"""
    import json
    from backend.comparator import scan_all_combinations

    out_dir = os.path.join(ROOT, "data")
    os.makedirs(out_dir, exist_ok=True)

    # 价格记录（去重）
    seen = set()
    unique = []
    for r in data:
        key = (r["source"], r["flight_date"], r["flight_number"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # 往返方案
    try:
        from backend.database import SessionLocal
        db = SessionLocal()
        deals = scan_all_combinations(db)
        db.close()
    except Exception as e:
        print(f"  往返比价失败: {e}")
        deals = []

    out = {"prices": unique, "roundtrip": deals, "count": len(unique), "deal_count": len(deals)}
    path = os.path.join(out_dir, "latest_prices.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"JSON 已保存: {path} ({len(unique)} 条价格, {len(deals)} 个往返)")


def main():
    print("=" * 50)
    print("  航班价格抓取 & 云同步")
    print(f"  PYTHONPATH: {ROOT}")
    print("=" * 50)

    data = run_scraper()
    if not data:
        print("无数据，跳过")
        return

    # 1. 尝试 HTTP 推送（如果配置了 SYNC_URL）
    sync_to_cloud(data)

    # 2. 保存 JSON（供 GitHub 提交 + 云函数拉取）
    save_json(data)


if __name__ == "__main__":
    main()
