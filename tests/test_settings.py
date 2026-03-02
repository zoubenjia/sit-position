"""settings.py 单元测试"""

import json
import os
import tempfile

from sit_monitor.settings import Settings


class TestSettingsDefaults:
    def test_default_values(self):
        s = Settings()
        assert s.shoulder_threshold == 10.0
        assert s.neck_threshold == 20.0
        assert s.torso_threshold == 8.0
        assert s.interval == 5.0
        assert s.bad_seconds == 30
        assert s.cooldown == 180
        assert s.sit_max_minutes == 45
        assert s.sound is False
        assert s.auto_pause is False

    def test_thresholds_property(self):
        s = Settings()
        t = s.thresholds
        assert t == {"shoulder": 10.0, "neck": 20.0, "torso": 8.0}

    def test_custom_values(self):
        s = Settings(shoulder_threshold=12.0, sound=True)
        assert s.shoulder_threshold == 12.0
        assert s.sound is True
        assert s.thresholds["shoulder"] == 12.0


class TestSettingsPersistence:
    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            s = Settings(shoulder_threshold=8.5, sound=True, sit_max_minutes=30)
            s.save(path)

            loaded = Settings.load(path)
            assert loaded.shoulder_threshold == 8.5
            assert loaded.sound is True
            assert loaded.sit_max_minutes == 30
            # 未修改的保持默认
            assert loaded.neck_threshold == 20.0
        finally:
            os.unlink(path)

    def test_load_missing_file(self):
        s = Settings.load("/tmp/nonexistent_sit_settings_12345.json")
        assert s.shoulder_threshold == 10.0  # 返回默认值

    def test_load_corrupt_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json{{{")
            path = f.name
        try:
            s = Settings.load(path)
            assert s.shoulder_threshold == 10.0  # 损坏文件返回默认值
        finally:
            os.unlink(path)

    def test_load_ignores_unknown_fields(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"shoulder_threshold": 9.0, "unknown_field": 42}, f)
            path = f.name
        try:
            s = Settings.load(path)
            assert s.shoulder_threshold == 9.0
            assert not hasattr(s, "unknown_field")
        finally:
            os.unlink(path)

    def test_round_trip_all_fields(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            original = Settings(
                shoulder_threshold=12.0, neck_threshold=15.0, torso_threshold=8.0,
                interval=3.0, bad_seconds=20, cooldown=120, sit_max_minutes=30,
                away_seconds=5.0, sound=True, auto_pause=True, camera=1, browser="Arc",
            )
            original.save(path)
            loaded = Settings.load(path)
            assert loaded.shoulder_threshold == original.shoulder_threshold
            assert loaded.neck_threshold == original.neck_threshold
            assert loaded.torso_threshold == original.torso_threshold
            assert loaded.interval == original.interval
            assert loaded.bad_seconds == original.bad_seconds
            assert loaded.cooldown == original.cooldown
            assert loaded.sit_max_minutes == original.sit_max_minutes
            assert loaded.away_seconds == original.away_seconds
            assert loaded.sound == original.sound
            assert loaded.auto_pause == original.auto_pause
            assert loaded.camera == original.camera
            assert loaded.browser == original.browser
        finally:
            os.unlink(path)


class TestSettingsApplyArgs:
    def test_non_default_args_override(self):
        from argparse import Namespace
        s = Settings()
        args = Namespace(
            shoulder_threshold=12.0, neck_threshold=10.0, torso_threshold=5.0,
            interval=5.0, bad_seconds=30, cooldown=180, sit_max_minutes=45,
            away_seconds=3.0, sound=True, auto_pause=False, camera=0, browser=None,
        )
        s.apply_args(args)
        assert s.shoulder_threshold == 12.0  # 非默认，覆盖
        assert s.sound is True               # 非默认，覆盖
        assert s.neck_threshold == 10.0      # 默认值，不覆盖

    def test_default_args_dont_override_saved(self):
        from argparse import Namespace
        s = Settings(shoulder_threshold=9.0, sound=True)
        args = Namespace(
            shoulder_threshold=10.0, neck_threshold=20.0, torso_threshold=8.0,
            interval=5.0, bad_seconds=30, cooldown=180, sit_max_minutes=45,
            away_seconds=3.0, sound=False, auto_pause=False, camera=0, browser=None,
        )
        s.apply_args(args)
        # 10.0 是默认值，不应覆盖已保存的 9.0
        assert s.shoulder_threshold == 9.0
        # sound=False 是默认值，不应覆盖已保存的 True
        assert s.sound is True
