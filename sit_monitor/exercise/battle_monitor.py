"""对战模式运动监控：包装 ExerciseMonitor，追踪 good_reps、计时、上传进度。"""

import logging
import threading
import time

from sit_monitor.cloud.battle import calculate_battle_score
from sit_monitor.cloud.models import BattleResult
from sit_monitor.exercise.pushup import PushupAnalyzer, classify_rep

log = logging.getLogger(__name__)

# 轮询对手进度间隔（秒）
_POLL_INTERVAL = 2.0


class BattleExerciseTracker:
    """追踪对战期间的运动数据，每个 rep 判定质量。"""

    def __init__(self, quality_weight: float = 0.3, time_limit: int = 120):
        self.quality_weight = quality_weight
        self.time_limit = time_limit
        self.reps = 0
        self.good_reps = 0
        self.form_error_counts: dict[str, int] = {}
        self.start_time = 0.0
        self._current_rep_feedbacks: list[tuple[str, str]] = []
        self._current_rep_min_elbow = 180.0

    def start(self):
        self.start_time = time.time()

    @property
    def elapsed(self) -> float:
        if self.start_time <= 0:
            return 0.0
        return time.time() - self.start_time

    @property
    def time_remaining(self) -> float:
        return max(0.0, self.time_limit - self.elapsed)

    @property
    def is_time_up(self) -> bool:
        return self.time_limit > 0 and self.elapsed >= self.time_limit

    def on_frame(self, result, last_rep_count: int):
        """每帧调用，追踪当前 rep 的姿势反馈。"""
        # 累积当前 rep 期间的反馈
        for cat, msg in result.form_feedbacks:
            self._current_rep_feedbacks.append((cat, msg))

        elbow = result.metrics.get("elbow", 180.0)
        self._current_rep_min_elbow = min(self._current_rep_min_elbow, elbow)

        # 检测到新 rep
        if result.rep_count > last_rep_count:
            quality = classify_rep(self._current_rep_feedbacks, self._current_rep_min_elbow)
            self.reps = result.rep_count
            if quality == "good":
                self.good_reps += 1
            # 统计 form errors
            for cat, _ in self._current_rep_feedbacks:
                self.form_error_counts[cat] = self.form_error_counts.get(cat, 0) + 1
            # 重置当前 rep 追踪
            self._current_rep_feedbacks = []
            self._current_rep_min_elbow = 180.0
            return quality
        return None

    def get_result(self) -> BattleResult:
        """获取最终对战结果。"""
        score = calculate_battle_score(self.reps, self.good_reps, self.quality_weight)
        return BattleResult(
            reps=self.reps,
            good_reps=self.good_reps,
            form_errors=dict(self.form_error_counts),
            score=score,
            duration_seconds=int(self.elapsed),
        )


class BattleProgressPoller:
    """后台轮询对手进度。"""

    def __init__(self, cloud_client, battle_id: str, opponent_id: str):
        self._client = cloud_client
        self._battle_id = battle_id
        self._opponent_id = opponent_id
        self._running = False
        self._thread = None
        self.opponent_reps = 0
        self.opponent_elapsed = 0.0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        while self._running:
            try:
                data = self._client.poll_opponent_progress(self._battle_id, self._opponent_id)
                if data:
                    self.opponent_reps = data.get("rep_number", 0)
                    self.opponent_elapsed = data.get("elapsed_seconds", 0.0)
            except Exception as e:
                log.debug("Poll error: %s", e)
            time.sleep(_POLL_INTERVAL)
