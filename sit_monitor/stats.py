"""运行期间的统计计数器"""

import time


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

        self._last_state = state
        self._last_state_time = now

    def summary(self):
        """返回统计摘要字符串"""
        elapsed = time.time() - self.start_time
        mins = elapsed / 60
        bad_pct = (self.bad_seconds_total / (self.good_seconds_total + self.bad_seconds_total) * 100
                   if (self.good_seconds_total + self.bad_seconds_total) > 0 else 0)
        lines = [
            f"运行时长: {mins:.1f} 分钟",
            f"总检测次数: {self.total_checks}",
            f"  姿势良好: {self.good_count} 次 ({self.good_seconds_total/60:.1f} 分钟)",
            f"  姿势不良: {self.bad_count} 次 ({self.bad_seconds_total/60:.1f} 分钟, {bad_pct:.0f}%)",
            f"  人不在位: {self.no_person_count} 次",
            f"坐姿提醒: {self.notifications_sent} 次",
            f"久坐提醒: {self.sit_notifications_sent} 次",
        ]
        return "\n".join(lines)
