"""cloud/ 模块单元测试 — CloudClient + SyncManager mock 测试"""

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from sit_monitor.cloud.client import CloudClient
from sit_monitor.cloud.models import DailyReport, LeaderboardEntry, UserProfile
from sit_monitor.cloud.sync import SyncManager
from sit_monitor.settings import Settings


class TestCloudClient:
    def _make_client(self):
        return CloudClient(supabase_url="https://test.supabase.co", anon_key="test-key")

    def test_headers_without_auth(self):
        c = self._make_client()
        h = c._headers(auth=False)
        assert h["apikey"] == "test-key"
        assert "Authorization" not in h

    def test_headers_with_auth(self):
        c = self._make_client()
        c.access_token = "tok123"
        h = c._headers(auth=True)
        assert h["Authorization"] == "Bearer tok123"

    def test_rest_url(self):
        c = self._make_client()
        assert c._rest("users") == "https://test.supabase.co/rest/v1/users"

    def test_rpc_url(self):
        c = self._make_client()
        assert c._rpc("leaderboard_daily") == "https://test.supabase.co/rest/v1/rpc/leaderboard_daily"

    def test_sign_up_device_success(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "at123",
            "refresh_token": "rt456",
            "user": {"id": "uid789"},
        }
        c._client = MagicMock()
        c._client.post.return_value = mock_resp

        assert c.sign_up_device("test_device") is True
        assert c.access_token == "at123"
        assert c.refresh_token == "rt456"
        assert c.user_id == "uid789"

    def test_sign_up_device_failure(self):
        c = self._make_client()
        mock_login = MagicMock()
        mock_login.status_code = 400
        mock_login.text = "invalid"
        mock_signup = MagicMock()
        mock_signup.status_code = 500
        mock_signup.text = "error"
        c._client = MagicMock()
        c._client.post.side_effect = [mock_login, mock_signup]

        assert c.sign_up_device("bad_device") is False

    def test_refresh_session_success(self):
        c = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_at",
            "refresh_token": "new_rt",
            "user": {"id": "uid"},
        }
        c._client = MagicMock()
        c._client.post.return_value = mock_resp

        assert c.refresh_session("old_rt") is True
        assert c.access_token == "new_at"

    def test_refresh_session_no_token(self):
        c = self._make_client()
        assert c.refresh_session("") is False

    def test_upsert_daily_report(self):
        c = self._make_client()
        c.access_token = "tok"
        c.user_id = "uid"
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        c._client = MagicMock()
        c._client.post.return_value = mock_resp

        report = DailyReport(report_date="2026-03-02", good_checks=10, bad_checks=2, good_pct=83)
        assert c.upsert_daily_report(report) is True
        # 验证请求包含 user_id
        call_kwargs = c._client.post.call_args
        assert call_kwargs[1]["json"]["user_id"] == "uid"

    def test_leaderboard_daily(self):
        c = self._make_client()
        c.access_token = "tok"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"rank": 1, "user_id": "u1", "nickname": "小明", "good_pct": 95, "total_minutes": 120, "likes_count": 3},
            {"rank": 2, "user_id": "u2", "nickname": "小红", "good_pct": 88, "total_minutes": 90, "likes_count": 1},
        ]
        c._client = MagicMock()
        c._client.post.return_value = mock_resp

        entries = c.leaderboard_daily("2026-03-02")
        assert len(entries) == 2
        assert entries[0].nickname == "小明"
        assert entries[0].good_pct == 95
        assert entries[1].rank == 2

    def test_send_like(self):
        c = self._make_client()
        c.access_token = "tok"
        c.user_id = "me"
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        c._client = MagicMock()
        c._client.post.return_value = mock_resp

        assert c.send_like("other_user", "2026-03-02", "👍") is True

    def test_network_error_returns_false(self):
        c = self._make_client()
        c.access_token = "tok"
        c.user_id = "uid"
        c._client = MagicMock()
        c._client.post.side_effect = Exception("network error")

        report = DailyReport(report_date="2026-03-02")
        assert c.upsert_daily_report(report) is False

    def test_create_challenge(self):
        c = self._make_client()
        c.access_token = "tok"
        c.user_id = "me"
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = [{"id": "ch1", "status": "pending"}]
        c._client = MagicMock()
        c._client.post.return_value = mock_resp

        result = c.create_challenge("opponent_id")
        assert result is not None
        assert result["id"] == "ch1"

    def test_list_my_challenges(self):
        c = self._make_client()
        c.access_token = "tok"
        c.user_id = "me"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "ch1", "status": "active", "creator_id": "me"},
        ]
        c._client = MagicMock()
        c._client.get.return_value = mock_resp

        challenges = c.list_my_challenges()
        assert len(challenges) == 1


class TestSyncManager:
    def test_sync_state_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "sync_state.json")
            settings = Settings(cloud_enabled=True)
            client = MagicMock()

            with patch("sit_monitor.cloud.sync.SYNC_STATE_PATH", state_path):
                mgr = SyncManager(settings, client)
                mgr._sync_state = {"last_sync": 12345}
                mgr._save_sync_state()

                # 重新加载
                mgr2 = SyncManager(settings, client)
                assert mgr2._sync_state.get("last_sync") == 12345

    def test_sync_disabled(self):
        settings = Settings(cloud_enabled=False)
        client = MagicMock()
        mgr = SyncManager(settings, client)
        mgr.sync_once()
        # cloud_enabled=False 时不应调用 ensure_auth
        client.ensure_auth.assert_not_called()

    def test_sync_uploads_reports(self):
        settings = Settings(cloud_enabled=True)
        client = MagicMock()
        client.ensure_auth.return_value = True
        client.user_id = "uid"
        client.refresh_token = ""
        client.upsert_profile.return_value = True
        client.upsert_daily_report.return_value = True
        client.list_my_challenges.return_value = []

        summary_data = {
            "date": "2026-03-02",
            "good_checks": 10,
            "bad_checks": 2,
            "good_pct": 83,
            "alerts": 1,
            "sit_alerts": 0,
            "good_minutes": 30.0,
            "bad_minutes": 5.0,
            "total_minutes": 35.0,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "sync_state.json")
            with patch("sit_monitor.cloud.sync.SYNC_STATE_PATH", state_path), \
                 patch("sit_monitor.cloud.sync.daily_summary", return_value=summary_data):
                mgr = SyncManager(settings, client)
                mgr.sync_once()
                # 应该上传了日报（今天 + 昨天各一次）
                assert client.upsert_daily_report.call_count == 2
