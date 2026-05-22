"""微信推送模块 - 支持 Server酱 / 企业微信"""

import os
import json
from datetime import date, datetime
from typing import Optional

import requests

# 从环境变量读取推送配置
SERVERCHAN_KEY = os.getenv("SERVERCHAN_KEY", "")  # Server酱 SendKey
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "")    # 企业微信机器人 Webhook
WECOM_KEY = os.getenv("WECOM_KEY", "")            # 企业微信 robot key

PUSH_INTERVAL_MINUTES = 15  # 最低价推送间隔（防刷）


class WeChatPusher:
    """微信消息推送"""

    @staticmethod
    def send(title: str, content: str) -> bool:
        """通用推送，自动选择通道"""
        sent = False
        if SERVERCHAN_KEY:
            sent = WeChatPusher._send_serverchan(title, content) or sent
        if WECOM_WEBHOOK or WECOM_KEY:
            sent = WeChatPusher._send_wecom(title, content) or sent
        return sent

    @staticmethod
    def _send_serverchan(title: str, content: str) -> bool:
        """通过 Server酱 推送"""
        try:
            url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
            resp = requests.post(url, data={"title": title, "desp": content}, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                print(f"[推送] Server酱 成功")
                return True
            print(f"[推送] Server酱 失败: {data}")
            return False
        except Exception as e:
            print(f"[推送] Server酱 异常: {e}")
            return False

    @staticmethod
    def _send_wecom(title: str, content: str) -> bool:
        """通过企业微信机器人推送"""
        try:
            key = WECOM_KEY or WECOM_WEBHOOK.split("key=")[-1]
            url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## {title}\n{content}"
                }
            }
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get("errcode") == 0:
                print(f"[推送] 企业微信 成功")
                return True
            print(f"[推送] 企业微信 失败: {data}")
            return False
        except Exception as e:
            print(f"[推送] 企业微信 异常: {e}")
            return False

    @staticmethod
    def push_daily_summary(lowest_prices: list[dict], origin: str = "深圳", destination: str = "北京"):
        """推送每日低价汇总"""
        if not lowest_prices:
            return

        date_str = date.today().strftime("%Y-%m-%d")
        title = f"✈️ {origin}→{destination} 每日低价 ({date_str})"

        lines = [f"## 📊 {origin}→{destination} 今日低价航班\n"]
        for p in sorted(lowest_prices, key=lambda x: x["flight_date"])[:10]:
            stops = "直飞" if p.get("stops", 0) == 0 else f'{p["stops"]}次中转'
            fee_a = int(p.get("airport_fee", 50))
            fee_f = int(p.get("fuel_tax", 50))
            lines.append(
                f"- **{p['flight_date']}**  {p['airline']} {p['flight_number']}  "
                f"{p['departure_time']}-{p['arrival_time']}  "
                f"💰 **¥{int(p['total_price'])}**（票¥{int(p['ticket_price'])}+"
                f"机建¥{fee_a}+燃油¥{fee_f}）{stops}"
            )

        lines.append(f"\n---\n来源: {lowest_prices[0].get('source', '携程')}")

        WeChatPusher.send(title, "\n".join(lines))

    @staticmethod
    def push_price_alert(record: dict, reason: str = "新低价!"):
        """推送实时低价预警"""
        orig = record.get("origin", "深圳")
        dest = record.get("destination", "北京")
        fee_a = int(record.get("airport_fee", 50))
        fee_f = int(record.get("fuel_tax", 50))
        title = f"🚨 {orig}→{dest} 低价预警! ¥{int(record['total_price'])}"
        stops_text = "直飞" if record.get("stops", 0) == 0 else f'{record["stops"]}次中转'
        content = "\n".join([
            f"## 🚨 {reason}",
            f"- **路线**: {orig} → {dest}",
            f"- **日期**: {record['flight_date']}",
            f"- **航空公司**: {record['airline']} {record['flight_number']}",
            f"- **时间**: {record['departure_time']} → {record['arrival_time']}",
            f"- **票价**: ¥{int(record['ticket_price'])}",
            f"- **机建费**: ¥{fee_a}",
            f"- **燃油附加费**: ¥{fee_f}",
            f"- **含税总价**: 💰 **¥{int(record['total_price'])}**",
            f"- **经停**: {stops_text}",
            f"- **来源**: {record.get('source', '携程')}",
            "",
            f"[立即预订]({record.get('booking_url', '#')})",
        ])
        WeChatPusher.send(title, content)

    @staticmethod
    def push_weekly_summary(records: list[dict], trend: list[dict],
                            origin: str = "深圳", destination: str = "北京"):
        """推送每周低价总结"""
        from datetime import date
        today = date.today()
        week_num = today.isocalendar()[1]

        title = f"📈 {origin}→{destination} 周报 (第{week_num}周)"
        lines = [f"## 📈 {origin}↔{destination} 第{week_num}周价格总结\n"]

        if records:
            avg_price = sum(r["total_price"] for r in records) / len(records)
            min_price = min(r["total_price"] for r in records)
            max_price = max(r["total_price"] for r in records)
            lines.append(f"- **本周最低**: ¥{int(min_price)}")
            lines.append(f"- **本周最高**: ¥{int(max_price)}")
            lines.append(f"- **本周平均**: ¥{int(avg_price)}")
            lines.append(f"- **监控航班数**: {len(records)}")

        if trend:
            lines.append(f"\n### 每日最低价趋势\n")
            for t in trend:
                lines.append(f"- {t['date']}: ¥{int(t['min'])} ~ ¥{int(t['max'])}")

        lines.append(f"\n### 下周预测\n继续监控中...")
        WeChatPusher.send(title, "\n".join(lines))

    @staticmethod
    def push_roundtrip_alert(deal: dict):
        """推送往返低价方案"""
        ob = deal["outbound"]
        rb = deal["return"]
        title = f"✈️ 深圳↔北京 往返 ¥{int(deal['total_price'])}"

        budget_flag = " 💰预算内" if deal.get("within_budget") else ""
        content = "\n".join([
            f"## ✈️ 深圳↔北京 往返方案{budget_flag}",
            f"",
            f"**去程 {deal['outbound_date']}**: {ob['airline']} {ob['flight_number']}  "
            f"{ob['dep_time']}-{ob['arr_time']}  ¥{int(deal['outbound_price'])}",
            f"**回程 {deal['return_date']}**: {rb['airline']} {rb['flight_number']}  "
            f"{rb['dep_time']}-{rb['arr_time']}  ¥{int(deal['return_price'])}",
            f"",
            f"**往返总价**: 💰 **¥{int(deal['total_price'])}** (停留{deal['stay_days']}天)",
            f"",
            f"---\n来自低价机票追踪系统",
        ])
        WeChatPusher.send(title, content)
