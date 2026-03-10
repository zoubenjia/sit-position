"""运行期间的统计计数器"""

import time

from sit_monitor.i18n import t


class Stats:
    def __init__(self):
        self.start_time = time.time()
        self.total_checks = 0
        self.good_count = 0
        self.bad_count = 0
        self.no_person_count = 0
        self.notifications_sent = 0
        self.sit_notifications_sent = 0
        self.bad_seconds_total = 0.0
        self.good_seconds_total = 0.0
        self.max_good_streak_seconds = 0.0  # 最大连续好姿势时长
        self._good_streak_start = None  # 当前连续好姿势开始时间
        self._last_state = None  # "good" / "bad" / None
        self._last_state_time = None

    def record(self, state, now):
        """记录一次检测结果，state: 'good'/'bad'/'away'"""
        self.total_checks += 1
        if state == "good":
            self.good_count += 1
        elif state == "bad":
            self.bad_count += 1
        else:
            self.no_person_count += 1

        # 累计好/坏姿势持续时长
        if self._last_state in ("good", "bad") and self._last_state_time:
            dt = now - self._last_state_time
            if self._last_state == "good":
                self.good_seconds_total += dt
            else:
                self.bad_seconds_total += dt

        # 追踪连续好姿势时长
        if state == "good":
            if self._good_streak_start is None:
                self._good_streak_start = now
        else:
            if self._good_streak_start is not None:
                streak = now - self._good_streak_start
                if streak > self.max_good_streak_seconds:
                    self.max_good_streak_seconds = streak
                self._good_streak_start = None

        self._last_state = state
        self._last_state_time = now

    @property
    def current_good_streak_seconds(self):
        """当前连续好姿势秒数（实时）"""
        if self._good_streak_start is None:
            return 0.0
        return time.time() - self._good_streak_start

    def summary(self):
        """返回统计摘要字符串"""
        elapsed = time.time() - self.start_time
        mins = elapsed / 60
        bad_pct = (self.bad_seconds_total / (self.good_seconds_total + self.bad_seconds_total) * 100
                   if (self.good_seconds_total + self.bad_seconds_total) > 0 else 0)
        lines = [
            t("stats.runtime", minutes=mins),
            t("stats.total_checks", count=self.total_checks),
            t("stats.good_posture", count=self.good_count, minutes=self.good_seconds_total/60),
            t("stats.bad_posture", count=self.bad_count, minutes=self.bad_seconds_total/60, pct=bad_pct),
            t("stats.no_person", count=self.no_person_count),
            t("stats.posture_alerts", count=self.notifications_sent),
            t("stats.sit_alerts", count=self.sit_notifications_sent),
        ]
        return "\n".join(lines)
