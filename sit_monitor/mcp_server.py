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


# --- 社交功能 ---

def _get_cloud_client():
    """获取已认证的 CloudClient（懒加载）"""
    settings = Settings.load()
    if not settings.cloud_enabled:
        return None, "云端功能未开启，请先在设置中开启 Enable Cloud"
    from sit_monitor.cloud.client import CloudClient
    client = CloudClient()
    settings.ensure_device_id()
    settings.ensure_device_id()
    if not client.ensure_auth(settings.supabase_refresh_token, settings.device_id):
        return None, "云端认证失败，请检查网络连接"
    # 保存可能更新的 refresh_token
    if client.refresh_token != settings.supabase_refresh_token:
        settings.supabase_refresh_token = client.refresh_token
        settings.save()
    return client, None


@mcp.tool()
def social_leaderboard(
    period: str = "daily",
    date: str | None = None,
) -> str:
    """获取坐姿排行榜。

    Args:
        period: 排行榜类型 - "daily"（今日）或 "weekly"（本周）
        date: 日期字符串 YYYY-MM-DD，daily 模式为目标日期，weekly 模式为周一日期。默认今天/本周。
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    from datetime import date as _date, timedelta
    today = _date.today()

    if period == "weekly":
        target = date or str(today - timedelta(days=today.weekday()))
        entries = client.leaderboard_weekly(target)
    else:
        target = date or str(today)
        entries = client.leaderboard_daily(target)

    client.close()
    result = []
    for e in entries:
        result.append({
            "rank": e.rank,
            "nickname": e.nickname,
            "good_pct": e.good_pct,
            "total_minutes": e.total_minutes,
            "likes_count": e.likes_count,
            "user_id": e.user_id,
        })
    return json.dumps({"period": period, "date": target, "entries": result}, ensure_ascii=False)


@mcp.tool()
def social_my_achievements() -> str:
    """获取我的成就/徽章列表，包含已解锁和未解锁的。"""
    from sit_monitor.cloud.achievements import AchievementEngine
    engine = AchievementEngine()
    # 先检查是否有新成就可以解锁
    newly = engine.check_and_unlock()
    achs = engine.get_all_achievements()
    return json.dumps({
        "unlocked_count": engine.unlocked_count,
        "total_count": engine.total_count,
        "newly_unlocked": [{"id": a.id, "name": a.name, "icon": a.icon} for a in newly],
        "achievements": achs,
    }, ensure_ascii=False)


@mcp.tool()
def social_send_like(
    to_user_id: str,
    report_date: str,
    emoji: str = "👍",
) -> str:
    """给排行榜上某用户的日报点赞/鼓励。

    Args:
        to_user_id: 目标用户 ID（从排行榜获取）
        report_date: 日报日期 YYYY-MM-DD
        emoji: 表情，默认 👍
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    ok = client.send_like(to_user_id, report_date, emoji)
    # 解锁"社交蝴蝶"成就
    if ok:
        from sit_monitor.cloud.achievements import AchievementEngine
        engine = AchievementEngine()
        engine.unlock("first_like")
        if client:
            client.upload_achievement("first_like", engine._unlocked.get("first_like", ""))

    client.close()
    return json.dumps({"success": ok}, ensure_ascii=False)


@mcp.tool()
def social_create_challenge(
    opponent_id: str,
    challenge_type: str = "good_pct",
    target_value: int = 80,
    duration_days: int = 7,
) -> str:
    """向另一位用户发起坐姿挑战。

    Args:
        opponent_id: 对手用户 ID（从排行榜获取）
        challenge_type: 挑战类型 - "good_pct"（良好率）或 "total_minutes"（监控时长）
        target_value: 目标值（good_pct 时为百分比，total_minutes 时为分钟数）
        duration_days: 挑战持续天数，默认 7
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    result = client.create_challenge(opponent_id, challenge_type, target_value, duration_days)
    client.close()
    if result:
        return json.dumps({"success": True, "challenge": result}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "创建挑战失败"}, ensure_ascii=False)


@mcp.tool()
def social_my_challenges() -> str:
    """获取我发起的和收到的挑战列表。"""
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    challenges = client.list_my_challenges()
    client.close()
    return json.dumps({"challenges": challenges}, ensure_ascii=False)


@mcp.tool()
def social_profile() -> str:
    """获取当前用户的社交资料（昵称、设备ID、分享设置）。"""
    settings = Settings.load()
    return json.dumps({
        "cloud_enabled": settings.cloud_enabled,
        "nickname": settings.nickname,
        "device_id": settings.device_id,
        "share_posture": settings.share_posture,
        "share_exercise": settings.share_exercise,
        "auth_provider": settings.auth_provider,
    }, ensure_ascii=False)


# --- 俯卧撑对战 ---

@mcp.tool()
def battle_create(
    opponent_id: str,
    mode: str = "async",
    time_limit: int = 120,
    quality_weight: float = 0.3,
) -> str:
    """创建俯卧撑对战。

    Args:
        opponent_id: 对手用户 ID（从排行榜获取）
        mode: 对战模式 - "async"（异步，双方各自完成）或 "realtime"（实时）
        time_limit: 时间限制（秒），默认 120
        quality_weight: 质量权重 0-1，默认 0.3（动作质量占比 30%）
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    result = client.create_battle(opponent_id, mode, time_limit, quality_weight)
    client.close()
    if result:
        return json.dumps({"success": True, "battle": result}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "创建对战失败"}, ensure_ascii=False)


@mcp.tool()
def battle_accept(battle_id: str) -> str:
    """接受俯卧撑对战邀请。

    Args:
        battle_id: 对战 ID
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    ok = client.accept_battle(battle_id)
    client.close()
    return json.dumps({"success": ok}, ensure_ascii=False)


@mcp.tool()
def battle_cancel(battle_id: str) -> str:
    """取消俯卧撑对战。

    Args:
        battle_id: 对战 ID
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    ok = client.cancel_battle(battle_id)
    client.close()
    return json.dumps({"success": ok}, ensure_ascii=False)


@mcp.tool()
def battle_list(status: str = "") -> str:
    """列出我的俯卧撑对战。

    Args:
        status: 筛选状态（invite/accepted/active/finished/expired/cancelled），默认全部
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    battles = client.list_my_battles(status)
    client.close()
    return json.dumps({"battles": battles}, ensure_ascii=False)


@mcp.tool()
def battle_details(battle_id: str) -> str:
    """获取对战详情。

    Args:
        battle_id: 对战 ID
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    battle = client.get_battle(battle_id)
    client.close()
    if battle:
        return json.dumps({"battle": battle}, ensure_ascii=False)
    return json.dumps({"error": "对战不存在"}, ensure_ascii=False)


@mcp.tool()
def battle_start_exercise(battle_id: str) -> str:
    """开始对战运动（启动俯卧撑训练子进程）。

    Args:
        battle_id: 对战 ID
    """
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    battle = client.get_battle(battle_id)
    if not battle:
        client.close()
        return json.dumps({"error": "对战不存在"}, ensure_ascii=False)

    if battle["status"] not in ("accepted", "active"):
        client.close()
        return json.dumps({"error": f"对战状态为 {battle['status']}，无法开始"}, ensure_ascii=False)

    # 更新状态为 active
    if battle["status"] == "accepted":
        client._client.patch(
            client._rest("pushup_battles") + f"?id=eq.{battle_id}",
            headers=client._headers(),
            json={"status": "active", "started_at": datetime.now().isoformat()},
        )

    client.close()
    return json.dumps({
        "success": True,
        "message": "请通过托盘菜单 '⚔️ Push-up Battle' 或命令行启动俯卧撑训练",
        "battle_id": battle_id,
        "time_limit": battle.get("time_limit_seconds", 120),
        "quality_weight": battle.get("quality_weight", 0.3),
    }, ensure_ascii=False)


# --- OAuth / 账号 ---

@mcp.tool()
def auth_status() -> str:
    """获取当前认证状态和绑定的社交账号。"""
    settings = Settings.load()
    result = {
        "auth_provider": settings.auth_provider,
        "cloud_enabled": settings.cloud_enabled,
        "device_id": settings.device_id,
    }

    if settings.cloud_enabled:
        client, err = _get_cloud_client()
        if not err:
            profile = client.get_user_profile_from_provider()
            client.close()
            result.update(profile)

    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def auth_link_google() -> str:
    """绑定 Google 账号。返回授权 URL，用户需在浏览器中完成授权。"""
    client, err = _get_cloud_client()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    from sit_monitor.cloud.social_auth import start_google_oauth
    try:
        result = start_google_oauth(client)
        client.close()
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        client.close()
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def auth_unlink_provider(provider: str = "google") -> str:
    """解绑社交账号，恢复设备匿名认证。

    Args:
        provider: 要解绑的平台（google）
    """
    settings = Settings.load()
    settings.auth_provider = "device"
    settings.save()
    return json.dumps({"success": True, "message": f"已解绑 {provider}，恢复匿名认证"}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
