"""坐姿监控 MCP Server — 让 AI 查询和分析坐姿数据"""

import json
import os
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP

from sit_monitor.report import _read_events, daily_summary, weekly_report
from sit_monitor.settings import Settings

mcp = FastMCP("sit-monitor", instructions="坐姿监控数据查询工具，可分析坐姿趋势并提供改善建议")


@mcp.tool()
def posture_daily_summary(date: str | None = None) -> str:
    """获取指定日期的坐姿摘要。

    Args:
        date: 日期字符串 YYYY-MM-DD，默认今天
    """
    target = None
    if date:
        target = datetime.strptime(date, "%Y-%m-%d").date()
    result = daily_summary(target)
    if result is None:
        return json.dumps({"error": f"没有 {date or '今天'} 的坐姿数据"}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def posture_weekly_report() -> str:
    """获取最近 7 天的坐姿周报，包含每日良好率和提醒次数。"""
    return weekly_report()


@mcp.tool()
def posture_query_events(
    days: int = 7,
    event_type: str | None = None,
    limit: int = 50,
) -> str:
    """查询原始坐姿事件数据，支持按类型过滤。

    Args:
        days: 查询最近多少天的数据，默认 7
        event_type: 过滤事件类型（good/bad/posture_alert/sit_alert/start/stop），默认全部
        limit: 返回条数上限，默认 50
    """
    events = _read_events(days=days)
    if event_type:
        events = [e for e in events if e.get("event") == event_type]
    events = events[-limit:]  # 取最近的
    return json.dumps(events, ensure_ascii=False)


@mcp.tool()
def posture_trend_analysis(
    days: int = 7,
    group_by: str = "day",
) -> str:
    """按时段聚合坐姿数据，用于识别趋势和模式。

    Args:
        days: 分析最近多少天的数据，默认 7
        group_by: 聚合方式 - "hour"（按小时）或 "day"（按天，默认）
    """
    events = _read_events(days=days)
    if not events:
        return json.dumps({"error": "没有坐姿数据"}, ensure_ascii=False)

    buckets = defaultdict(lambda: {
        "good": 0, "bad": 0, "alerts": 0,
        "shoulder_sum": 0.0, "neck_sum": 0.0, "torso_sum": 0.0,
        "angle_count": 0,
    })

    for e in events:
        ts = datetime.fromisoformat(e["ts"])
        if group_by == "hour":
            key = ts.strftime("%Y-%m-%d %H:00")
        else:
            key = ts.strftime("%Y-%m-%d")

        evt = e.get("event")
        if evt == "good":
            buckets[key]["good"] += 1
        elif evt == "bad":
            buckets[key]["bad"] += 1
        elif evt == "posture_alert":
            buckets[key]["alerts"] += 1

        # 累加角度值用于求平均
        if evt in ("good", "bad"):
            has_angle = False
            for angle_key in ("shoulder", "neck", "torso"):
                val = e.get(angle_key)
                if val is not None:
                    buckets[key][f"{angle_key}_sum"] += val
                    has_angle = True
            if has_angle:
                buckets[key]["angle_count"] += 1

    result = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        total = b["good"] + b["bad"]
        good_pct = round(b["good"] / total * 100) if total > 0 else 0
        entry = {
            "period": key,
            "good": b["good"],
            "bad": b["bad"],
            "good_pct": good_pct,
            "alerts": b["alerts"],
        }
        if b["angle_count"] > 0:
            n = b["angle_count"]
            entry["avg_shoulder"] = round(b["shoulder_sum"] / n, 1)
            entry["avg_neck"] = round(b["neck_sum"] / n, 1)
            entry["avg_torso"] = round(b["torso_sum"] / n, 1)
        result.append(entry)

    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def posture_get_settings() -> str:
    """获取当前坐姿监控的阈值和配置参数。"""
    settings = Settings.load()
    data = asdict(settings)
    # 添加阈值说明
    data["_descriptions"] = {
        "shoulder_threshold": "肩膀倾斜角度阈值（度）",
        "neck_threshold": "头部前倾角度阈值（度）",
        "torso_threshold": "躯干前倾角度阈值（度）",
        "interval": "检测间隔（秒）",
        "bad_seconds": "持续不良姿势多少秒后发出提醒",
        "cooldown": "两次提醒之间的最小间隔（秒）",
        "sit_max_minutes": "连续坐多少分钟后发出久坐提醒",
    }
    return json.dumps(data, ensure_ascii=False)


@mcp.tool()
def exercise_query_sessions(
    days: int = 30,
    exercise_type: str | None = None,
    limit: int = 20,
) -> str:
    """查询运动训练记录，返回训练日期、类型、次数、时长、姿势错误等。

    Args:
        days: 查询最近多少天的数据，默认 30
        exercise_type: 过滤运动类型（如 pushup），默认全部
        limit: 返回会话数上限，默认 20
    """
    log_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs", "exercise.jsonl",
    )
    if not os.path.exists(log_path):
        return json.dumps({"error": "没有运动训练数据", "sessions": []}, ensure_ascii=False)

    cutoff = datetime.now() - timedelta(days=days)
    events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                ts = datetime.fromisoformat(e["ts"])
                if ts >= cutoff:
                    events.append(e)
            except (json.JSONDecodeError, KeyError):
                continue

    # 将 exercise_start/exercise_stop 配对为会话
    sessions = []
    current = None
    for e in events:
        evt = e.get("event")
        ex_type = e.get("exercise", "")

        if exercise_type and ex_type != exercise_type:
            continue

        if evt == "exercise_start":
            current = {
                "start_time": e["ts"],
                "exercise": ex_type,
                "reps": [],
            }
        elif evt == "rep" and current is not None:
            current["reps"].append({
                "count": e.get("count"),
                "metrics": e.get("metrics", {}),
            })
        elif evt == "exercise_stop":
            session = {
                "start_time": current["start_time"] if current else e["ts"],
                "exercise": ex_type,
                "total_reps": e.get("total_reps", 0),
                "duration_seconds": e.get("duration_seconds", 0),
                "form_errors": e.get("form_errors", {}),
            }
            sessions.append(session)
            current = None

    sessions = sessions[-limit:]
    return json.dumps({"total_sessions": len(sessions), "sessions": sessions}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
