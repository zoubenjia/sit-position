"""日志分析与报告生成"""

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "posture.jsonl")


def _read_events(days=7):
    """读取最近 N 天的日志事件"""
    if not os.path.exists(LOG_FILE):
        return []
    cutoff = datetime.now() - timedelta(days=days)
    events = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                ts = datetime.fromisoformat(ev["ts"])
                if ts >= cutoff:
                    events.append(ev)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return events


def daily_summary(date=None):
    """生成指定日期的摘要（默认今天），返回 dict 或 None"""
    if date is None:
        date = datetime.now().date()
    events = _read_events(days=1)
    day_events = [e for e in events
                  if datetime.fromisoformat(e["ts"]).date() == date]
    if not day_events:
        return None

    good = sum(1 for e in day_events if e["event"] == "good")
    bad = sum(1 for e in day_events if e["event"] == "bad")
    alerts = sum(1 for e in day_events if e["event"] == "posture_alert")
    sit_alerts = sum(1 for e in day_events if e["event"] == "sit_alert")

    # 估算时长（从 start/stop 事件或检测间隔推算）
    starts = [e for e in day_events if e["event"] == "start"]
    stops = [e for e in day_events if e["event"] == "stop"]
    total_good_min = sum(e.get("good_minutes", 0) for e in stops)
    total_bad_min = sum(e.get("bad_minutes", 0) for e in stops)

    total = good + bad
    good_pct = (good / total * 100) if total > 0 else 0

    return {
        "date": str(date),
        "good_checks": good,
        "bad_checks": bad,
        "good_pct": round(good_pct),
        "alerts": alerts,
        "sit_alerts": sit_alerts,
        "good_minutes": round(total_good_min, 1),
        "bad_minutes": round(total_bad_min, 1),
    }


def daily_summary_text(date=None):
    """生成每日摘要文本"""
    s = daily_summary(date)
    if not s:
        return "今日暂无坐姿数据"
    return (
        f"📊 {s['date']} 坐姿日报\n"
        f"良好 {s['good_minutes']}min / 不良 {s['bad_minutes']}min\n"
        f"检测 {s['good_checks'] + s['bad_checks']} 次，良好率 {s['good_pct']}%\n"
        f"坐姿提醒 {s['alerts']} 次 | 久坐提醒 {s['sit_alerts']} 次"
    )


def weekly_report():
    """生成最近 7 天的报告文本"""
    events = _read_events(days=7)
    if not events:
        return "最近 7 天暂无坐姿数据"

    # 按日期分组
    by_day = defaultdict(lambda: {"good": 0, "bad": 0, "alerts": 0})
    for e in events:
        day = datetime.fromisoformat(e["ts"]).strftime("%m-%d")
        if e["event"] == "good":
            by_day[day]["good"] += 1
        elif e["event"] == "bad":
            by_day[day]["bad"] += 1
        elif e["event"] == "posture_alert":
            by_day[day]["alerts"] += 1

    lines = ["📊 最近 7 天坐姿报告", ""]
    lines.append(f"{'日期':>6}  {'良好':>4}  {'不良':>4}  {'良好率':>5}  {'提醒':>4}")
    lines.append("-" * 36)

    total_good, total_bad = 0, 0
    for day in sorted(by_day.keys()):
        d = by_day[day]
        g, b = d["good"], d["bad"]
        total_good += g
        total_bad += b
        total = g + b
        pct = f"{g / total * 100:.0f}%" if total > 0 else "—"
        lines.append(f"{day:>6}  {g:>4}  {b:>4}  {pct:>5}  {d['alerts']:>4}")

    grand_total = total_good + total_bad
    grand_pct = f"{total_good / grand_total * 100:.0f}%" if grand_total > 0 else "—"
    lines.append("-" * 36)
    lines.append(f"{'合计':>6}  {total_good:>4}  {total_bad:>4}  {grand_pct:>5}")

    return "\n".join(lines)
