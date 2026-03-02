"""俯卧撑对战测试：评分算法、classify_rep、BattleExerciseTracker"""

import pytest

from sit_monitor.cloud.battle import (
    BattleMode,
    BattleStatus,
    calculate_battle_score,
    determine_winner,
)
from sit_monitor.exercise.pushup import classify_rep


# --- 评分算法 ---

class TestCalculateBattleScore:
    def test_zero_reps(self):
        assert calculate_battle_score(0, 0) == 0.0

    def test_all_good_reps(self):
        # 10 × (0.7 + 0.3 × 1.0) = 10.0
        assert calculate_battle_score(10, 10) == 10.0

    def test_no_good_reps(self):
        # 10 × (0.7 + 0.3 × 0.0) = 7.0
        assert calculate_battle_score(10, 0) == 7.0

    def test_half_good(self):
        # 10 × (0.7 + 0.3 × 0.5) = 8.5
        assert calculate_battle_score(10, 5) == 8.5

    def test_custom_quality_weight(self):
        # 10 × (0.5 + 0.5 × 0.5) = 7.5
        assert calculate_battle_score(10, 5, quality_weight=0.5) == 7.5

    def test_more_good_than_total_capped(self):
        # good_reps 不能超过 reps
        assert calculate_battle_score(5, 10) == 5.0

    def test_single_rep_good(self):
        assert calculate_battle_score(1, 1) == 1.0

    def test_single_rep_bad(self):
        assert calculate_battle_score(1, 0) == 0.7

    def test_large_numbers(self):
        score = calculate_battle_score(100, 80)
        # 100 × (0.7 + 0.3 × 0.8) = 94.0
        assert score == 94.0


# --- 胜负判定 ---

class TestDetermineWinner:
    def test_creator_wins(self):
        assert determine_winner(10.0, 8.0, "c", "o") == "c"

    def test_opponent_wins(self):
        assert determine_winner(8.0, 10.0, "c", "o") == "o"

    def test_draw(self):
        assert determine_winner(10.0, 10.0, "c", "o") == ""


# --- Rep 质量分类 ---

class TestClassifyRep:
    def test_good_rep(self):
        assert classify_rep([], 80.0) == "good"

    def test_shallow_by_feedback(self):
        feedbacks = [("shallow", "再低一点")]
        assert classify_rep(feedbacks, 80.0) == "shallow"

    def test_shallow_by_elbow(self):
        # min_elbow > ELBOW_SHALLOW_THRESHOLD (100°)
        assert classify_rep([], 110.0) == "shallow"

    def test_bad_hip_sag(self):
        feedbacks = [("hip_sag", "臀部太低了")]
        assert classify_rep(feedbacks, 80.0) == "bad"

    def test_bad_hip_pike(self):
        feedbacks = [("hip_pike", "臀部太高了")]
        assert classify_rep(feedbacks, 80.0) == "bad"

    def test_bad_head_drop(self):
        feedbacks = [("head_drop", "头不要低")]
        assert classify_rep(feedbacks, 80.0) == "bad"

    def test_shallow_takes_precedence_over_bad(self):
        # shallow 在 bad 之前检查
        feedbacks = [("shallow", "浅了"), ("hip_sag", "塌了")]
        assert classify_rep(feedbacks, 80.0) == "shallow"

    def test_good_with_no_issues(self):
        feedbacks = []
        assert classify_rep(feedbacks, 90.0) == "good"


# --- 状态枚举 ---

class TestBattleStatus:
    def test_values(self):
        assert BattleStatus.INVITE == "invite"
        assert BattleStatus.FINISHED == "finished"
        assert BattleStatus.CANCELLED == "cancelled"

    def test_mode_values(self):
        assert BattleMode.ASYNC == "async"
        assert BattleMode.REALTIME == "realtime"


# --- BattleExerciseTracker ---

class TestBattleExerciseTracker:
    def test_tracker_basic_flow(self):
        from sit_monitor.exercise.battle_monitor import BattleExerciseTracker

        tracker = BattleExerciseTracker(quality_weight=0.3, time_limit=120)
        tracker.start()

        assert tracker.reps == 0
        assert tracker.good_reps == 0
        assert tracker.elapsed > 0
        assert tracker.time_remaining <= 120

        result = tracker.get_result()
        assert result.reps == 0
        assert result.score == 0.0

    def test_tracker_time_up(self):
        from sit_monitor.exercise.battle_monitor import BattleExerciseTracker
        import time

        tracker = BattleExerciseTracker(quality_weight=0.3, time_limit=10)
        tracker.start_time = time.time() - 20  # 模拟已过时间
        assert tracker.is_time_up

    def test_tracker_no_time_limit(self):
        from sit_monitor.exercise.battle_monitor import BattleExerciseTracker
        import time

        tracker = BattleExerciseTracker(quality_weight=0.3, time_limit=0)
        tracker.start_time = time.time() - 9999
        assert not tracker.is_time_up  # time_limit=0 表示无限制
