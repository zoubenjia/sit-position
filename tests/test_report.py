"""report.py 单元测试"""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import patch

from sit_monitor.report import daily_summary, weekly_report


def _write_log(events, path):
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


class TestDailySummary:
    def test_no_log_file(self):
        with patch("sit_monitor.report.LOG_FILE", "/tmp/nonexistent_log_12345.jsonl"):
            result = daily_summary()
        assert result is None

    def test_with_events(self):
        today = datetime.now().date()
        ts = datetime.now().isoformat()
        events = [
            {"ts": ts, "event": "start"},
            {"ts": ts, "event": "good", "shoulder": 3.0},
            {"ts": ts, "event": "good", "shoulder": 2.0},
            {"ts": ts, "event": "bad", "shoulder": 12.0, "reasons": ["test"]},
            {"ts": ts, "event": "posture_alert", "reasons": ["test"]},
            {"ts": ts, "event": "stop", "good_minutes": 5.0, "bad_minutes": 2.0,
             "notifications": 1},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
            path = f.name
        try:
            with patch("sit_monitor.report.LOG_FILE", path):
                result = daily_summary(today)
            assert result is not None
            assert result["good_checks"] == 2
            assert result["bad_checks"] == 1
            assert result["alerts"] == 1
            assert result["good_minutes"] == 5.0
        finally:
            os.unlink(path)


class TestWeeklyReport:
    def test_no_data(self):
        with patch("sit_monitor.report.LOG_FILE", "/tmp/nonexistent_12345.jsonl"):
            text = weekly_report()
        assert "暂无" in text

    def test_with_data(self):
        ts = datetime.now().isoformat()
        events = [
            {"ts": ts, "event": "good"},
            {"ts": ts, "event": "bad"},
            {"ts": ts, "event": "posture_alert"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
            path = f.name
        try:
            with patch("sit_monitor.report.LOG_FILE", path):
                text = weekly_report()
            assert "7 天" in text
            assert "合计" in text
        finally:
            os.unlink(path)
