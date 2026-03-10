"""achievements.py 单元测试 — 成就判定逻辑"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

from sit_monitor.cloud.achievements import (
    ACHIEVEMENTS,
    ACHIEVEMENTS_MAP,
    AchievementEngine,
)


class TestAchievementDefinitions:
    def test_seven_achievements_defined(self):
        assert len(ACHIEVEMENTS) == 13

    def test_all_have_required_fields(self):
        for a in ACHIEVEMENTS:
            assert a.id
            assert a.name
            assert a.description
            assert a.icon
            assert a.condition_type in ("streak", "cumulative", "single_day", "action_count")

    def test_unique_ids(self):
        ids = [a.id for a in ACHIEVEMENTS]
        assert len(ids) == len(set(ids))


class TestAchievementEngine:
    def _make_engine(self, tmpdir, unlocked=None):
        state_path = os.path.join(tmpdir, "achievements.json")
        if unlocked:
            with open(state_path, "w") as f:
                json.dump(unlocked, f)
        with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
            engine = AchievementEngine()
        return engine, state_path

    def test_initial_state_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine, _ = self._make_engine(tmpdir)
            assert engine.unlocked_count == 0
            assert engine.total_count == 13

    def test_get_all_achievements(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine, _ = self._make_engine(tmpdir)
            achs = engine.get_all_achievements()
            assert len(achs) == 13
            assert all(not a["unlocked"] for a in achs)

    def test_manual_unlock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()
                assert engine.unlock("first_like") is True
                assert engine.unlocked_count == 1
                # 重复解锁返回 False
                assert engine.unlock("first_like") is False
                assert engine.unlocked_count == 1

    def test_unlock_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()
                engine.unlock("first_like")

            # 重新加载
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine2 = AchievementEngine()
                assert "first_like" in engine2.unlocked_ids

    def test_already_unlocked_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            unlocked = {"first_day": "2026-03-01T10:00:00"}
            engine, state_path = self._make_engine(tmpdir, unlocked)
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                # first_day 已解锁，不应重复出现在新解锁列表
                with patch("sit_monitor.cloud.achievements._read_events", return_value=[
                    {"ts": datetime.now().isoformat(), "event": "start"},
                    {"ts": datetime.now().isoformat(), "event": "stop", "good_minutes": 5},
                ]):
                    newly = engine.check_and_unlock()
                    assert all(a.id != "first_day" for a in newly)

    def test_first_day_unlocks(self):
        """有 start 和 stop 事件时解锁 first_day"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()
                events = [
                    {"ts": datetime.now().isoformat(), "event": "start"},
                    {"ts": datetime.now().isoformat(), "event": "good"},
                    {"ts": datetime.now().isoformat(), "event": "stop", "good_minutes": 5, "bad_minutes": 1},
                ]
                with patch("sit_monitor.cloud.achievements._read_events", return_value=events), \
                     patch("sit_monitor.cloud.achievements.daily_summary", return_value=None):
                    newly = engine.check_and_unlock()
                    ids = [a.id for a in newly]
                    assert "first_day" in ids

    def test_perfect_day_unlocks(self):
        """良好率 >= 95 时解锁 perfect_day"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()

                def mock_summary(d):
                    return {"good_pct": 96, "good_checks": 48, "bad_checks": 2,
                            "alerts": 0, "sit_alerts": 0, "good_minutes": 60, "bad_minutes": 2,
                            "total_minutes": 62}

                events = [
                    {"ts": datetime.now().isoformat(), "event": "start"},
                    {"ts": datetime.now().isoformat(), "event": "stop", "good_minutes": 60, "bad_minutes": 2},
                ]
                with patch("sit_monitor.cloud.achievements._read_events", return_value=events), \
                     patch("sit_monitor.cloud.achievements.daily_summary", side_effect=mock_summary):
                    newly = engine.check_and_unlock()
                    ids = [a.id for a in newly]
                    assert "perfect_day" in ids

    def test_streak_3_unlocks(self):
        """连续 3 天良好率 >= 70 时解锁 streak_3"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()

                def mock_summary(d):
                    return {"good_pct": 75, "good_checks": 30, "bad_checks": 10,
                            "alerts": 1, "sit_alerts": 0, "good_minutes": 40, "bad_minutes": 10,
                            "total_minutes": 50}

                events = [
                    {"ts": datetime.now().isoformat(), "event": "start"},
                    {"ts": datetime.now().isoformat(), "event": "stop", "good_minutes": 40, "bad_minutes": 10},
                ]
                with patch("sit_monitor.cloud.achievements._read_events", return_value=events), \
                     patch("sit_monitor.cloud.achievements.daily_summary", side_effect=mock_summary):
                    newly = engine.check_and_unlock()
                    ids = [a.id for a in newly]
                    assert "streak_3" in ids

    def test_early_bird_unlocks(self):
        """早上 7 点前开始监控解锁 early_bird"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()
                early_ts = datetime.now().replace(hour=6, minute=30).isoformat()
                events = [
                    {"ts": early_ts, "event": "start"},
                    {"ts": datetime.now().isoformat(), "event": "stop", "good_minutes": 5, "bad_minutes": 1},
                ]
                with patch("sit_monitor.cloud.achievements._read_events", return_value=events), \
                     patch("sit_monitor.cloud.achievements.daily_summary", return_value=None):
                    newly = engine.check_and_unlock()
                    ids = [a.id for a in newly]
                    assert "early_bird" in ids

    def test_focus_30_unlocks(self):
        """单次连续好姿势 >= 30 分钟解锁 focus_30"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()
                events = [
                    {"ts": datetime.now().isoformat(), "event": "start"},
                    {"ts": datetime.now().isoformat(), "event": "stop",
                     "good_minutes": 35, "bad_minutes": 5, "max_good_streak_minutes": 32.0},
                ]
                with patch("sit_monitor.cloud.achievements._read_events", return_value=events), \
                     patch("sit_monitor.cloud.achievements.daily_summary", return_value=None):
                    newly = engine.check_and_unlock()
                    ids = [a.id for a in newly]
                    assert "focus_30" in ids
                    assert "focus_60" not in ids

    def test_focus_60_and_30_unlock_together(self):
        """单次连续好姿势 >= 60 分钟同时解锁 focus_30 和 focus_60"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()
                events = [
                    {"ts": datetime.now().isoformat(), "event": "start"},
                    {"ts": datetime.now().isoformat(), "event": "stop",
                     "good_minutes": 65, "bad_minutes": 3, "max_good_streak_minutes": 62.0},
                ]
                with patch("sit_monitor.cloud.achievements._read_events", return_value=events), \
                     patch("sit_monitor.cloud.achievements.daily_summary", return_value=None):
                    newly = engine.check_and_unlock()
                    ids = [a.id for a in newly]
                    assert "focus_30" in ids
                    assert "focus_60" in ids
                    assert "focus_120" not in ids

    def test_no_unlock_when_conditions_not_met(self):
        """条件不满足时不解锁"""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "achievements.json")
            with patch("sit_monitor.cloud.achievements.ACHIEVEMENTS_STATE_PATH", state_path):
                engine = AchievementEngine()
                # 无任何事件
                with patch("sit_monitor.cloud.achievements._read_events", return_value=[]), \
                     patch("sit_monitor.cloud.achievements.daily_summary", return_value=None):
                    newly = engine.check_and_unlock()
                    assert len(newly) == 0
