"""后台数据同步管理器"""

import json
import logging
import os
import threading
import time
from datetime import date, timedelta

from sit_monitor.cloud.client import CloudClient
from sit_monitor.cloud.models import DailyReport, UserProfile
from sit_monitor.report import daily_summary
from sit_monitor.settings import Settings

log = logging.getLogger(__name__)

from sit_monitor.paths import sync_state_path

SYNC_STATE_PATH = sync_state_path()
SYNC_INTERVAL = 300  # 5 分钟


class SyncManager:
    """后台 daemon 线程，定期上传日报数据到云端"""

    def __init__(self, settings: Settings, client: CloudClient):
        self.settings = settings
        self.client = client
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._sync_state = self._load_sync_state()

    # --- Sync state 持久化 ---

    def _load_sync_state(self) -> dict:
        if os.path.exists(SYNC_STATE_PATH):
            try:
                with open(SYNC_STATE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_sync_state(self):
        os.makedirs(os.path.dirname(SYNC_STATE_PATH), exist_ok=True)
        try:
            with open(SYNC_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._sync_state, f, indent=2)
        except OSError as e:
            log.warning("Save sync state error: %s", e)

    # --- 认证 ---

    def _ensure_auth(self) -> bool:
        """确保认证，成功后同步 profile"""
        ok = self.client.ensure_auth(self.settings.supabase_refresh_token, self.settings.device_id)
        if ok:
            # 保存 refresh_token 到 settings
            if self.client.refresh_token != self.settings.supabase_refresh_token:
                self.settings.supabase_refresh_token = self.client.refresh_token
                self.settings.save()
            # 同步 profile
            profile = UserProfile(
                user_id=self.client.user_id,
                device_id=self.settings.device_id,
                nickname=self.settings.nickname,
                share_posture=self.settings.share_posture,
                share_exercise=self.settings.share_exercise,
            )
            self.client.upsert_profile(profile)
        return ok

    # --- 日报同步 ---

    def _sync_report_for_date(self, d: date) -> bool:
        """上传指定日期的日报"""
        summary = daily_summary(d)
        if summary is None:
            return False

        report = DailyReport(
            user_id=self.client.user_id,
            report_date=str(d),
            good_checks=summary["good_checks"],
            bad_checks=summary["bad_checks"],
            good_pct=summary["good_pct"],
            alerts=summary["alerts"],
            sit_alerts=summary["sit_alerts"],
            good_minutes=summary["good_minutes"],
            bad_minutes=summary["bad_minutes"],
            total_minutes=summary["good_minutes"] + summary["bad_minutes"],
        )
        return self.client.upsert_daily_report(report)

    def _sync_reports(self):
        """同步今日 + 昨日的日报"""
        today = date.today()
        yesterday = today - timedelta(days=1)

        for d in (today, yesterday):
            try:
                ok = self._sync_report_for_date(d)
                if ok:
                    self._sync_state[str(d)] = time.time()
                    log.debug("Synced report for %s", d)
            except Exception as e:
                log.warning("Sync report for %s error: %s", d, e)

        self._sync_state["last_sync"] = time.time()
        self._save_sync_state()

    def _update_challenge_scores(self):
        """同步时自动更新挑战进度"""
        try:
            challenges = self.client.list_my_challenges()
            for ch in challenges:
                if ch.get("status") != "active":
                    continue
                # 计算我在挑战期间的平均 good_pct
                start = ch.get("start_date", "")
                end = ch.get("end_date", "")
                if not start:
                    continue
                today = date.today()
                # 简单取今日 good_pct 作为分数更新
                summary = daily_summary(today)
                if summary is None:
                    continue
                score = summary["good_pct"]
                uid = self.client.user_id
                field = "creator_score" if ch.get("creator_id") == uid else "opponent_score"
                self.client.update_challenge_score(ch["id"], field, score)
        except Exception as e:
            log.warning("Update challenge scores error: %s", e)

    # --- 同步循环 ---

    def sync_once(self):
        """立即执行一次同步"""
        if not self.settings.cloud_enabled:
            return
        try:
            if not self._ensure_auth():
                log.warning("Cloud auth failed, skipping sync")
                return
            self._sync_reports()
            self._update_challenge_scores()
        except Exception as e:
            log.warning("Sync error: %s", e)

    def _loop(self):
        """后台循环：启动时立即同步一次，之后每 5 分钟"""
        self.sync_once()
        while not self._stop_event.wait(SYNC_INTERVAL):
            self.sync_once()

    def start(self):
        """启动后台同步线程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cloud-sync")
        self._thread.start()

    def stop(self):
        """停止后台同步"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
