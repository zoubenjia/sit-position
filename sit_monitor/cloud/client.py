"""Supabase REST API 薄封装（httpx）"""

import json
import logging
import os
import uuid
from dataclasses import asdict

import httpx

from sit_monitor.cloud.models import (
    Challenge,
    DailyReport,
    LeaderboardEntry,
    UserProfile,
)

log = logging.getLogger(__name__)

# Supabase 配置：优先环境变量，其次 hardcode（anon key 是公开的）
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

# 从本地配置文件读取（不提交到 git）
_CLOUD_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "cloud_config.json")

def _load_cloud_config():
    global SUPABASE_URL, SUPABASE_ANON_KEY
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        return
    if os.path.exists(_CLOUD_CONFIG):
        try:
            with open(_CLOUD_CONFIG, "r") as f:
                cfg = json.load(f)
            SUPABASE_URL = SUPABASE_URL or cfg.get("supabase_url", "")
            SUPABASE_ANON_KEY = SUPABASE_ANON_KEY or cfg.get("supabase_anon_key", "")
        except (json.JSONDecodeError, OSError):
            pass

_load_cloud_config()

_TIMEOUT = 10.0


class CloudClient:
    """Supabase HTTP 客户端，负责认证和数据读写"""

    def __init__(self, supabase_url: str = "", anon_key: str = ""):
        self.url = (supabase_url or SUPABASE_URL).rstrip("/")
        self.anon_key = anon_key or SUPABASE_ANON_KEY
        self.access_token: str = ""
        self.refresh_token: str = ""
        self.user_id: str = ""
        self._client = httpx.Client(timeout=_TIMEOUT)

    def close(self):
        self._client.close()

    # --- 内部 helpers ---

    def _headers(self, auth=True) -> dict:
        h = {
            "apikey": self.anon_key,
            "Content-Type": "application/json",
        }
        if auth and self.access_token:
            h["Authorization"] = f"Bearer {self.access_token}"
        return h

    def _rest(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _rpc(self, fn: str) -> str:
        return f"{self.url}/rest/v1/rpc/{fn}"

    def _auth_url(self, path: str) -> str:
        return f"{self.url}/auth/v1/{path}"

    # --- Auth ---

    def sign_up_device(self, device_id: str) -> bool:
        """用 device_id 生成伪邮箱自动注册，零门槛获取身份"""
        email = f"{device_id}@sit-monitor.app"
        password = uuid.uuid5(uuid.NAMESPACE_DNS, f"sit-monitor-{device_id}").hex
        headers = {"apikey": self.anon_key, "Content-Type": "application/json"}
        try:
            # 先尝试登录（已注册的设备）
            resp = self._client.post(
                self._auth_url("token?grant_type=password"),
                headers=headers,
                json={"email": email, "password": password},
            )
            if resp.status_code == 200:
                data = resp.json()
                self.access_token = data.get("access_token", "")
                self.refresh_token = data.get("refresh_token", "")
                self.user_id = data.get("user", {}).get("id", "")
                return bool(self.access_token and self.user_id)

            # 登录失败则注册
            resp = self._client.post(
                self._auth_url("signup"),
                headers=headers,
                json={"email": email, "password": password},
            )
            if resp.status_code not in (200, 201):
                log.warning("Sign up failed: %s %s", resp.status_code, resp.text)
                return False
            data = resp.json()
            self.access_token = data.get("access_token", "")
            self.refresh_token = data.get("refresh_token", "")
            self.user_id = data.get("user", {}).get("id", "")
            return bool(self.access_token and self.user_id)
        except Exception as e:
            log.warning("Sign up error: %s", e)
            return False

    def refresh_session(self, refresh_token: str = "") -> bool:
        """用 refresh_token 换取新 access_token"""
        token = refresh_token or self.refresh_token
        if not token:
            return False
        try:
            resp = self._client.post(
                self._auth_url("token?grant_type=refresh_token"),
                headers={"apikey": self.anon_key, "Content-Type": "application/json"},
                json={"refresh_token": token},
            )
            if resp.status_code != 200:
                log.warning("Refresh session failed: %s", resp.status_code)
                return False
            data = resp.json()
            self.access_token = data.get("access_token", "")
            self.refresh_token = data.get("refresh_token", self.refresh_token)
            self.user_id = data.get("user", {}).get("id", self.user_id)
            return bool(self.access_token)
        except Exception as e:
            log.warning("Refresh session error: %s", e)
            return False

    def ensure_auth(self, stored_refresh_token: str = "", device_id: str = "") -> bool:
        """确保已认证：先尝试刷新，再用 device_id 注册/登录"""
        if self.access_token and self.user_id:
            return True
        if stored_refresh_token and self.refresh_session(stored_refresh_token):
            return True
        if device_id:
            return self.sign_up_device(device_id)
        return False

    # --- Profile ---

    def upsert_profile(self, profile: UserProfile) -> bool:
        """创建或更新用户资料"""
        try:
            data = asdict(profile)
            data["user_id"] = self.user_id
            resp = self._client.post(
                self._rest("users"),
                headers={**self._headers(), "Prefer": "resolution=merge-duplicates"},
                json=data,
            )
            return resp.status_code in (200, 201)
        except Exception as e:
            log.warning("Upsert profile error: %s", e)
            return False

    def update_nickname(self, nickname: str) -> bool:
        """更新昵称"""
        try:
            resp = self._client.patch(
                self._rest("users") + f"?user_id=eq.{self.user_id}",
                headers=self._headers(),
                json={"nickname": nickname},
            )
            return resp.status_code in (200, 204)
        except Exception as e:
            log.warning("Update nickname error: %s", e)
            return False

    # --- Daily Report ---

    def upsert_daily_report(self, report: DailyReport) -> bool:
        """上传日报（UPSERT by user_id + report_date）"""
        try:
            data = asdict(report)
            data["user_id"] = self.user_id
            resp = self._client.post(
                self._rest("daily_reports"),
                headers={**self._headers(), "Prefer": "resolution=merge-duplicates"},
                json=data,
            )
            return resp.status_code in (200, 201)
        except Exception as e:
            log.warning("Upsert daily report error: %s", e)
            return False

    # --- Leaderboard ---

    def leaderboard_daily(self, target_date: str) -> list[LeaderboardEntry]:
        """获取日排行榜"""
        return self._leaderboard_rpc("leaderboard_daily", {"target_date": target_date})

    def leaderboard_weekly(self, week_start: str) -> list[LeaderboardEntry]:
        """获取周排行榜"""
        return self._leaderboard_rpc("leaderboard_weekly", {"week_start": week_start})

    def _leaderboard_rpc(self, fn: str, params: dict) -> list[LeaderboardEntry]:
        try:
            resp = self._client.post(
                self._rpc(fn),
                headers=self._headers(),
                json=params,
            )
            if resp.status_code != 200:
                log.warning("Leaderboard RPC %s failed: %s", fn, resp.status_code)
                return []
            rows = resp.json()
            entries = []
            for i, row in enumerate(rows, 1):
                entries.append(LeaderboardEntry(
                    rank=row.get("rank", i),
                    user_id=row.get("user_id", ""),
                    nickname=row.get("nickname", "匿名"),
                    good_pct=row.get("good_pct", 0),
                    total_minutes=row.get("total_minutes", 0),
                    likes_count=row.get("likes_count", 0),
                ))
            return entries
        except Exception as e:
            log.warning("Leaderboard RPC error: %s", e)
            return []

    # --- Likes ---

    def send_like(self, to_user_id: str, report_date: str, emoji: str = "👍") -> bool:
        """给某用户的日报点赞"""
        try:
            resp = self._client.post(
                self._rest("likes"),
                headers=self._headers(),
                json={
                    "from_user_id": self.user_id,
                    "to_user_id": to_user_id,
                    "report_date": report_date,
                    "emoji": emoji,
                },
            )
            return resp.status_code in (200, 201)
        except Exception as e:
            log.warning("Send like error: %s", e)
            return False

    def get_likes_for_date(self, target_date: str) -> list[dict]:
        """获取某日的点赞统计"""
        try:
            resp = self._client.get(
                self._rest("likes") + f"?report_date=eq.{target_date}&select=to_user_id,emoji",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return resp.json()
        except Exception as e:
            log.warning("Get likes error: %s", e)
            return []

    # --- Achievements ---

    def upload_achievement(self, achievement_id: str, unlocked_at: str) -> bool:
        """上传解锁的成就"""
        try:
            resp = self._client.post(
                self._rest("user_achievements"),
                headers={**self._headers(), "Prefer": "resolution=merge-duplicates"},
                json={
                    "user_id": self.user_id,
                    "achievement_id": achievement_id,
                    "unlocked_at": unlocked_at,
                },
            )
            return resp.status_code in (200, 201)
        except Exception as e:
            log.warning("Upload achievement error: %s", e)
            return False

    def get_my_achievements(self) -> list[dict]:
        """获取我的已解锁成就"""
        try:
            resp = self._client.get(
                self._rest("user_achievements") + f"?user_id=eq.{self.user_id}&select=achievement_id,unlocked_at",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return resp.json()
        except Exception as e:
            log.warning("Get achievements error: %s", e)
            return []

    # --- Challenges ---

    def create_challenge(
        self,
        opponent_id: str,
        challenge_type: str = "good_pct",
        target_value: int = 80,
        duration_days: int = 7,
    ) -> dict | None:
        """创建挑战"""
        try:
            resp = self._client.post(
                self._rest("challenges"),
                headers={**self._headers(), "Prefer": "return=representation"},
                json={
                    "creator_id": self.user_id,
                    "opponent_id": opponent_id,
                    "challenge_type": challenge_type,
                    "target_value": target_value,
                    "duration_days": duration_days,
                    "status": "pending",
                },
            )
            if resp.status_code in (200, 201):
                rows = resp.json()
                return rows[0] if rows else None
            return None
        except Exception as e:
            log.warning("Create challenge error: %s", e)
            return None

    def accept_challenge(self, challenge_id: str) -> bool:
        """接受挑战"""
        try:
            resp = self._client.patch(
                self._rest("challenges") + f"?id=eq.{challenge_id}",
                headers=self._headers(),
                json={"status": "active"},
            )
            return resp.status_code in (200, 204)
        except Exception as e:
            log.warning("Accept challenge error: %s", e)
            return False

    def list_my_challenges(self) -> list[dict]:
        """列出我的挑战（创建的或收到的）"""
        try:
            uid = self.user_id
            resp = self._client.get(
                self._rest("challenges") + f"?or=(creator_id.eq.{uid},opponent_id.eq.{uid})&order=created_at.desc",
                headers=self._headers(),
            )
            if resp.status_code != 200:
                return []
            return resp.json()
        except Exception as e:
            log.warning("List challenges error: %s", e)
            return []

    def update_challenge_score(self, challenge_id: str, field: str, score: float) -> bool:
        """更新挑战分数"""
        try:
            resp = self._client.patch(
                self._rest("challenges") + f"?id=eq.{challenge_id}",
                headers=self._headers(),
                json={field: score},
            )
            return resp.status_code in (200, 204)
        except Exception as e:
            log.warning("Update challenge score error: %s", e)
            return False
