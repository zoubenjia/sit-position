"""成就/徽章系统：本地 JSONL 数据判定 + 云端同步"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sit_monitor.cloud.models import Achievement
from sit_monitor.i18n import t
from sit_monitor.report import _read_events, daily_summary

log = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACHIEVEMENTS_STATE_PATH = os.path.join(SCRIPT_DIR, "logs", "achievements.json")

# 7 个预定义成就
ACHIEVEMENTS = [
    Achievement(
        id="first_day",
        name="achievement.first_day.name",
        description="achievement.first_day.desc",
        icon="🌟",
        condition_type="single_day",
        condition_value=1,
    ),
    Achievement(
        id="streak_3",
        name="achievement.streak_3.name",
        description="achievement.streak_3.desc",
        icon="🔥",
        condition_type="streak",
        condition_value=3,
    ),
    Achievement(
        id="streak_7",
        name="achievement.streak_7.name",
        description="achievement.streak_7.desc",
        icon="👑",
        condition_type="streak",
        condition_value=7,
    ),
    Achievement(
        id="perfect_day",
        name="achievement.perfect_day.name",
        description="achievement.perfect_day.desc",
        icon="💎",
        condition_type="single_day",
        condition_value=95,
    ),
    Achievement(
        id="hours_100",
        name="achievement.hours_100.name",
        description="achievement.hours_100.desc",
        icon="⏰",
        condition_type="cumulative",
        condition_value=6000,  # 100 小时 = 6000 分钟
    ),
    Achievement(
        id="first_like",
        name="achievement.first_like.name",
        description="achievement.first_like.desc",
        icon="🦋",
        condition_type="action_count",
        condition_value=1,
    ),
    Achievement(
        id="early_bird",
        name="achievement.early_bird.name",
        description="achievement.early_bird.desc",
        icon="🐦",
        condition_type="single_day",
        condition_value=7,  # 7 点
    ),
    Achievement(
        id="first_battle",
        name="achievement.first_battle.name",
        description="achievement.first_battle.desc",
        icon="⚔️",
        condition_type="action_count",
        condition_value=1,
    ),
    Achievement(
        id="battle_winner",
        name="achievement.battle_winner.name",
        description="achievement.battle_winner.desc",
        icon="🏆",
        condition_type="action_count",
        condition_value=1,
    ),
    Achievement(
        id="battle_streak_3",
        name="achievement.battle_streak_3.name",
        description="achievement.battle_streak_3.desc",
        icon="🔥",
        condition_type="streak",
        condition_value=3,
    ),
]

ACHIEVEMENTS_MAP = {a.id: a for a in ACHIEVEMENTS}


class AchievementEngine:
    """本地成就判定引擎"""

    def __init__(self):
        self._unlocked: dict[str, str] = {}  # achievement_id -> unlocked_at ISO
        self._load_state()

    def _load_state(self):
        if os.path.exists(ACHIEVEMENTS_STATE_PATH):
            try:
                with open(ACHIEVEMENTS_STATE_PATH, "r", encoding="utf-8") as f:
                    self._unlocked = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._unlocked = {}

    def _save_state(self):
        os.makedirs(os.path.dirname(ACHIEVEMENTS_STATE_PATH), exist_ok=True)
        with open(ACHIEVEMENTS_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(self._unlocked, f, indent=2)

    @property
    def unlocked_ids(self) -> set[str]:
        return set(self._unlocked.keys())

    @property
    def unlocked_count(self) -> int:
        return len(self._unlocked)

    @property
    def total_count(self) -> int:
        return len(ACHIEVEMENTS)

    def get_all_achievements(self) -> list[dict]:
        """获取所有成就及其解锁状态"""
        result = []
        for a in ACHIEVEMENTS:
            result.append({
                "id": a.id,
                "name": t(a.name),
                "description": t(a.description),
                "icon": a.icon,
                "unlocked": a.id in self._unlocked,
                "unlocked_at": self._unlocked.get(a.id, ""),
            })
        return result

    def unlock(self, achievement_id: str) -> bool:
        """手动解锁（如 first_like 由外部触发）"""
        if achievement_id in self._unlocked:
            return False
        self._unlocked[achievement_id] = datetime.now().isoformat()
        self._save_state()
        return True

    def check_and_unlock(self) -> list[Achievement]:
        """检查所有条件并解锁满足的成就，返回新解锁列表"""
        newly_unlocked = []

        for ach in ACHIEVEMENTS:
            if ach.id in self._unlocked:
                continue

            unlocked = False
            if ach.id == "first_day":
                unlocked = self._check_first_day()
            elif ach.id == "streak_3":
                unlocked = self._check_streak(3)
            elif ach.id == "streak_7":
                unlocked = self._check_streak(7)
            elif ach.id == "perfect_day":
                unlocked = self._check_perfect_day(95)
            elif ach.id == "hours_100":
                unlocked = self._check_cumulative_minutes(6000)
            elif ach.id == "early_bird":
                unlocked = self._check_early_bird(7)
            # first_like 由外部手动触发，不在此检查

            if unlocked:
                self._unlocked[ach.id] = datetime.now().isoformat()
                newly_unlocked.append(ach)

        if newly_unlocked:
            self._save_state()

        return newly_unlocked

    # --- 判定方法 ---

    def _check_first_day(self) -> bool:
        """首次使用坐姿监控一整天"""
        events = _read_events(days=30)
        has_start = any(e.get("event") == "start" for e in events)
        has_stop = any(e.get("event") == "stop" for e in events)
        return has_start and has_stop

    def _check_streak(self, n: int) -> bool:
        """连续 N 天良好率 ≥ 70%"""
        today = date.today()
        streak = 0
        for i in range(30):  # 最多回查 30 天
            d = today - timedelta(days=i)
            summary = daily_summary(d)
            if summary and summary["good_pct"] >= 70:
                streak += 1
                if streak >= n:
                    return True
            else:
                streak = 0
        return False

    def _check_perfect_day(self, threshold: int) -> bool:
        """某天良好率达到阈值以上"""
        today = date.today()
        for i in range(30):
            d = today - timedelta(days=i)
            summary = daily_summary(d)
            if summary and summary["good_pct"] >= threshold:
                return True
        return False

    def _check_cumulative_minutes(self, target: float) -> bool:
        """累计监控时长"""
        events = _read_events(days=365)
        stops = [e for e in events if e.get("event") == "stop"]
        total = sum(
            e.get("good_minutes", 0) + e.get("bad_minutes", 0)
            for e in stops
        )
        return total >= target

    def _check_early_bird(self, hour: int) -> bool:
        """在指定小时前开始监控"""
        events = _read_events(days=30)
        for e in events:
            if e.get("event") == "start":
                ts = datetime.fromisoformat(e["ts"])
                if ts.hour < hour:
                    return True
        return False
