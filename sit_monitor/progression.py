"""渐进式纠正计划：阈值随每日表现逐阶段收紧。

阶段表 5 级，所有阈值联动（阶段 5 = 现有标准默认）。
表现驱动：连续 3 天良好率≥80% 解锁下一阶段，只升不降。
"""

import json
import os

# 阶段阈值表（索引 0 = 阶段 1）。阶段 5 与 settings 标准默认一致。
STAGE_TABLE = [
    {"shoulder": 16.0, "neck": 30.0, "torso": 12.0, "head_tilt": 18.0},
    {"shoulder": 14.0, "neck": 27.0, "torso": 11.0, "head_tilt": 16.0},
    {"shoulder": 12.0, "neck": 24.0, "torso": 10.0, "head_tilt": 14.0},
    {"shoulder": 11.0, "neck": 22.0, "torso": 9.0, "head_tilt": 13.0},
    {"shoulder": 10.0, "neck": 20.0, "torso": 8.0, "head_tilt": 12.0},
]
MAX_STAGE = 5
GOAL_RATIO = 0.80      # 单日良好率达标线
GOAL_DAYS = 3          # 连续达标天数解锁下一阶段
MAX_DT = 60.0          # 两次 record 间隔超过此值不累计（防暂停/休眠误计）


class ProgressionTracker:
    """按自然日累计良好率、判定进阶。时间与日期由调用方传入（便于测试）。"""

    def __init__(self, path):
        self.path = path
        self.stage = 1
        self.stage_since = None
        self.current_day = None
        self.today_good = 0.0
        self.today_bad = 0.0
        self.recent_days = []       # [{"date":..., "good_ratio":...}]
        self.consecutive_met = 0
        self._last_ts = None
        self._last_state = None
        self._advance_event = None  # 刚进阶到的阶段号，供 UI 弹一次通知
        self._load()

    # ── 阈值 ──
    def current_thresholds(self):
        return dict(STAGE_TABLE[self.stage - 1])

    # ── 记录一次检测 ──
    def record(self, state, now_ts, day_str):
        """state: 'good'/'bad'/'away'(或 None)；now_ts: 秒时间戳；day_str: 'YYYY-MM-DD'。"""
        if self.current_day is None:
            self.current_day = day_str
            if self.stage_since is None:
                self.stage_since = day_str
        elif day_str != self.current_day:
            self._settle_and_advance()
            self.current_day = day_str
            self.today_good = 0.0
            self.today_bad = 0.0
            self._last_ts = None
            self._last_state = None

        if self._last_ts is not None and self._last_state in ("good", "bad"):
            dt = now_ts - self._last_ts
            if 0 < dt < MAX_DT:
                if self._last_state == "good":
                    self.today_good += dt
                else:
                    self.today_bad += dt

        self._last_ts = now_ts
        self._last_state = state if state in ("good", "bad") else None
        self._save()

    def _settle_and_advance(self):
        total = self.today_good + self.today_bad
        if total <= 0:
            return  # 无数据日：跳过，不影响连续序列
        ratio = self.today_good / total
        self.recent_days.append({"date": self.current_day, "good_ratio": round(ratio, 3)})
        self.recent_days = self.recent_days[-30:]
        if ratio >= GOAL_RATIO:
            self.consecutive_met += 1
        else:
            self.consecutive_met = 0
        if self.consecutive_met >= GOAL_DAYS and self.stage < MAX_STAGE:
            self.stage += 1
            self.consecutive_met = 0
            self.stage_since = self.current_day
            self._advance_event = self.stage

    # ── UI 接口 ──
    def progress_summary(self):
        total = self.today_good + self.today_bad
        today_ratio = (self.today_good / total) if total > 0 else 0.0
        return {
            "stage": self.stage,
            "max_stage": MAX_STAGE,
            "today_ratio": today_ratio,
            "consecutive_met": self.consecutive_met,
            "goal_days": GOAL_DAYS,
        }

    def pop_advance_event(self):
        """返回刚进阶到的阶段号（若有），并清除——供调用方只弹一次通知。"""
        ev = self._advance_event
        self._advance_event = None
        return ev

    def set_stage(self, stage):
        self.stage = max(1, min(MAX_STAGE, int(stage)))
        self.consecutive_met = 0
        self._save()

    # ── 持久化 ──
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.stage = int(d.get("stage", 1))
            self.stage_since = d.get("stage_since")
            self.current_day = d.get("current_day")
            self.today_good = float(d.get("today_good", 0.0))
            self.today_bad = float(d.get("today_bad", 0.0))
            self.recent_days = d.get("recent_days", [])
            self.consecutive_met = int(d.get("consecutive_met", 0))
        except (OSError, ValueError, KeyError, TypeError):
            pass  # 文件不存在/损坏 → 保持初始状态（阶段 1）

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({
                    "stage": self.stage,
                    "stage_since": self.stage_since,
                    "current_day": self.current_day,
                    "today_good": round(self.today_good, 1),
                    "today_bad": round(self.today_bad, 1),
                    "recent_days": self.recent_days,
                    "consecutive_met": self.consecutive_met,
                }, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
