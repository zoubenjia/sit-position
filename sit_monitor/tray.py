"""系统托盘应用：rumps 菜单栏 + 状态更新"""

import logging
import os
import subprocess
import sys
import threading
import time
from datetime import date, timedelta

import rumps

from sit_monitor.core import PostureMonitor
from sit_monitor.exercise import EXERCISE_REGISTRY, ExerciseMonitor
from sit_monitor.i18n import get_language, set_language, t
from sit_monitor.report import daily_summary_text, weekly_report
from sit_monitor.settings import Settings

log = logging.getLogger(__name__)

VERSION = "1.4.0"
REPO_URL = "https://github.com/zoubenjia/sit-position"
from sit_monitor.paths import is_bundled, project_dir, assets_dir, python_executable

PROJECT_DIR = project_dir()

# 动态图标生成
try:
    from sit_monitor.icon_gen import icon_path as _gen_icon_path
    _HAS_ICON_GEN = True
except ImportError:
    _HAS_ICON_GEN = False

# 静态图标路径（回退用）
_ASSETS = assets_dir()
_ICON_FILES = {
    "good": os.path.join(_ASSETS, "icon_good_color.png"),
    "bad": os.path.join(_ASSETS, "icon_bad_color.png"),
    "away": os.path.join(_ASSETS, "icon_idle.png"),
    "camera_adjust": os.path.join(_ASSETS, "icon_bad_color.png"),
    "camera_wait": os.path.join(_ASSETS, "icon_idle.png"),
    "stopped": os.path.join(_ASSETS, "icon_idle.png"),
}


class TrayApp(rumps.App):
    def __init__(self, settings: Settings, debug=False):
        _init_icon = _gen_icon_path("stopped") if _HAS_ICON_GEN else _ICON_FILES["stopped"]
        super().__init__("Sit Monitor", icon=_init_icon, quit_button=None)
        self.settings = settings
        self.debug = debug
        self.monitor = None
        self.monitor_thread = None
        self._exercise_proc = None
        self._preview_proc = None
        self._overlay_proc = None
        self._state = "stopped"
        self._details = {}
        self._ui_dirty = False
        self._last_daily_report_date = None
        self._auto_update_hours = 12  # 自动检查更新间隔（小时）
        # Cloud
        self._cloud_client = None
        self._sync_manager = None
        self._achievement_engine = None
        # Menu item references (set by _build_menu)
        self._mi_hint = None
        self._mi_start = None
        self._mi_pushup = None
        self._mi_stats = None
        self._mi_cloud = None
        self._mi_preview = None
        self._mi_snooze = None
        self._mi_achievements = None
        self._mi_nickname = None
        self._mi_share = None
        self._mi_auth = None
        self._mi_sound = None
        self._mi_auto_pause = None
        self._mi_fatigue = None
        self._build_menu()
        self._start_auto_update_check()

    def _build_menu(self):
        s = self.settings
        if s.simple_mode:
            self.menu = self._menu_simple(s)
        else:
            self.menu = self._menu_advanced(s)
        self._update_stats_menu()

    def _stance_label(self):
        """当前 stance_mode 的显示文字"""
        mode = self.settings.stance_mode
        return t(f"tray.menu.stance_{mode}")

    def _menu_simple(self, s):
        """精简模式：只保留核心功能，新用户友好"""
        self._mi_hint = rumps.MenuItem(t("tray.menu.posture_good"), callback=None)
        self._mi_start = rumps.MenuItem(t("tray.menu.start_monitoring"), callback=self._toggle_monitor)
        self._mi_pushup = rumps.MenuItem(t("tray.menu.pushup_training"), callback=self._toggle_pushup)
        self._mi_overlay = rumps.MenuItem(t("tray.menu.show_overlay"), callback=self._toggle_overlay)
        self._mi_stance = rumps.MenuItem(self._stance_label(), callback=self._cycle_stance)
        self._mi_stats = rumps.MenuItem(t("tray.menu.statistics"), callback=None)
        self._mi_cloud = rumps.MenuItem(
            f"{'☑' if s.cloud_enabled else '☐'} {t('tray.menu.enable_cloud')}",
            callback=self._toggle_cloud,
        )
        return [
            self._mi_hint,
            None,
            self._mi_start,
            self._mi_overlay,
            self._mi_pushup,
            self._mi_stance,
            rumps.MenuItem(t("tray.menu.quick_battle"), callback=self._quick_battle),
            None,
            self._mi_stats,
            rumps.MenuItem(t("tray.menu.view_report"), callback=self._view_report),
            None,
            self._mi_cloud,
            rumps.MenuItem(t("tray.menu.advanced_mode"), callback=self._toggle_mode),
            rumps.MenuItem(t("tray.menu.language_switch"), callback=self._switch_language),
            rumps.MenuItem(t("tray.menu.about", version=VERSION), callback=self._show_about),
            None,
        ]

    def _menu_advanced(self, s):
        """进阶模式：完整功能"""
        self._mi_hint = rumps.MenuItem(t("tray.menu.posture_good"), callback=None)
        self._mi_start = rumps.MenuItem(t("tray.menu.start_monitoring"), callback=self._toggle_monitor)
        self._mi_preview = rumps.MenuItem(t("tray.menu.show_camera"), callback=self._toggle_preview)
        self._mi_overlay = rumps.MenuItem(t("tray.menu.show_overlay"), callback=self._toggle_overlay)
        self._mi_snooze = rumps.MenuItem(t("tray.menu.pause_alerts"), callback=self._snooze)
        self._mi_stance = rumps.MenuItem(self._stance_label(), callback=self._cycle_stance)
        self._mi_pushup = rumps.MenuItem(t("tray.menu.pushup_training"), callback=self._toggle_pushup)
        self._mi_stats = rumps.MenuItem(t("tray.menu.statistics"), callback=None)

        # Stats submenu items
        mi_stats_good = rumps.MenuItem(t("tray.menu.stats_good", minutes="0"), callback=None)
        mi_stats_bad = rumps.MenuItem(t("tray.menu.stats_bad", minutes="0"), callback=None)
        mi_stats_alerts = rumps.MenuItem(t("tray.menu.stats_alerts", count=0), callback=None)
        self._mi_stats_items = (mi_stats_good, mi_stats_bad, mi_stats_alerts)

        # Settings submenu
        self._mi_setting_labels = {}
        settings_items = []
        for attr, name_key, unit in [
            ("shoulder_threshold", "tray.menu.setting_shoulder", "°"),
            ("neck_threshold", "tray.menu.setting_neck", "°"),
            ("torso_threshold", "tray.menu.setting_torso", "°"),
            ("head_tilt_threshold", "tray.menu.setting_head_tilt", "°"),
            ("bad_seconds", "tray.menu.setting_bad_seconds", "s"),
        ]:
            val = getattr(s, attr)
            name = t(name_key)
            label_item = rumps.MenuItem(f"{name}: {val}{unit}", callback=None)
            self._mi_setting_labels[attr] = (label_item, name_key, unit)
            step = 5 if attr == "bad_seconds" else 1
            settings_items.extend([
                label_item,
                rumps.MenuItem(f"  {name} +{step}",
                               callback=lambda _, a=attr, d=step: self._adjust(a, d)),
                rumps.MenuItem(f"  {name} -{step}",
                               callback=lambda _, a=attr, d=-step: self._adjust(a, d)),
                None,
            ])

        self._mi_sound = rumps.MenuItem(
            f"{'☑' if s.sound else '☐'} {t('tray.menu.sound')}",
            callback=self._toggle_sound,
        )
        self._mi_auto_pause = rumps.MenuItem(
            f"{'☑' if s.auto_pause else '☐'} {t('tray.menu.auto_pause')}",
            callback=self._toggle_auto_pause,
        )
        self._mi_call_mute = rumps.MenuItem(
            f"{'☑' if s.call_mute else '☐'} {t('tray.menu.call_mute')}",
            callback=self._toggle_call_mute,
        )
        self._mi_fatigue = rumps.MenuItem(
            f"{'☑' if s.fatigue_enabled else '☐'} {t('tray.menu.fatigue_detection')}",
            callback=self._toggle_fatigue,
        )
        settings_items.extend([self._mi_sound, self._mi_call_mute, self._mi_auto_pause, None, self._mi_fatigue])

        # Social submenu
        self._mi_achievements = rumps.MenuItem(
            t("tray.menu.achievements", unlocked=0, total=10),
            callback=self._show_achievements,
        )
        self._mi_nickname = rumps.MenuItem(
            t("tray.menu.nickname", name=s.nickname),
            callback=self._change_nickname,
        )
        self._mi_share = rumps.MenuItem(
            f"{'☑' if s.share_posture else '☐'} {t('tray.menu.share_data')}",
            callback=self._toggle_share,
        )

        # Account submenu
        self._mi_auth = rumps.MenuItem(t("tray.menu.auth_status", provider=s.auth_provider), callback=None)

        # Cloud toggle
        self._mi_cloud = rumps.MenuItem(
            f"{'☑' if s.cloud_enabled else '☐'} {t('tray.menu.enable_cloud')}",
            callback=self._toggle_cloud,
        )

        return [
            self._mi_hint,
            None,
            self._mi_start,
            self._mi_preview,
            self._mi_overlay,
            self._mi_snooze,
            self._mi_stance,
            None,
            self._mi_pushup,
            [rumps.MenuItem(t("tray.menu.battle_submenu")), [
                rumps.MenuItem(t("tray.menu.quick_battle"), callback=self._quick_battle),
                rumps.MenuItem(t("tray.menu.my_battles"), callback=self._show_battles),
            ]],
            None,
            self._mi_stats,
            [rumps.MenuItem(t("tray.menu.stats_submenu")), [
                mi_stats_good, mi_stats_bad, mi_stats_alerts,
            ]],
            rumps.MenuItem(t("tray.menu.view_report"), callback=self._view_report),
            None,
            [rumps.MenuItem(t("tray.menu.settings_submenu")), settings_items],
            None,
            [rumps.MenuItem(t("tray.menu.social_submenu")), [
                rumps.MenuItem(t("tray.menu.leaderboard_today"), callback=self._show_leaderboard_daily),
                rumps.MenuItem(t("tray.menu.leaderboard_week"), callback=self._show_leaderboard_weekly),
                None,
                self._mi_achievements,
                rumps.MenuItem(t("tray.menu.challenges"), callback=self._show_challenges),
                None,
                rumps.MenuItem(t("tray.menu.sync_now"), callback=self._sync_now),
                self._mi_nickname,
                self._mi_share,
            ]],
            [rumps.MenuItem(t("tray.menu.account_submenu")), [
                self._mi_auth,
                rumps.MenuItem(t("tray.menu.link_google"), callback=self._link_google),
                rumps.MenuItem(t("tray.menu.unlink"), callback=self._unlink_provider),
            ]],
            None,
            self._mi_cloud,
            None,
            rumps.MenuItem(t("tray.menu.check_updates"), callback=self._check_update),
            rumps.MenuItem(t("tray.menu.simple_mode"), callback=self._toggle_mode),
            rumps.MenuItem(t("tray.menu.language_switch"), callback=self._switch_language),
            rumps.MenuItem(t("tray.menu.about", version=VERSION), callback=self._show_about),
            None,
        ]

    def _rebuild_menu(self):
        """清空并重建菜单（语言切换/模式切换共用）"""
        was_running = self._is_running()
        was_exercising = self._is_exercising()
        keys = list(self.menu.keys())
        for key in keys:
            try:
                del self.menu[key]
            except Exception:
                pass
        self._build_menu()
        if was_running:
            self._mi_start.title = t("tray.menu.stop_monitoring")
        if was_exercising:
            self._mi_pushup.title = t("tray.menu.stop_pushup")

    def _switch_language(self, _):
        """切换语言"""
        lang = get_language()
        new_lang = "en" if lang == "zh" else "zh"
        self.settings.language = new_lang
        self.settings.save()
        set_language(new_lang)
        self._rebuild_menu()

    def _toggle_mode(self, _):
        """切换简单/进阶模式"""
        self.settings.simple_mode = not self.settings.simple_mode
        self.settings.save()
        self._rebuild_menu()
        mode_name = t("tray.mode.simple") if self.settings.simple_mode else t("tray.mode.advanced")
        rumps.notification("Sit Monitor", t("tray.mode.switched", mode=mode_name), "")

    # --- 图标 ---

    def _set_icon(self, state, problems=None):
        if _HAS_ICON_GEN:
            path = _gen_icon_path(state, problems or [])
        else:
            path = _ICON_FILES.get(state, _ICON_FILES["stopped"])
        if os.path.exists(path):
            self.icon = path
            self.title = None

    # --- 状态回调 ---

    def _on_state_change(self, state, details):
        # 只存数据，不直接操作 AppKit（此回调在监控线程中运行）
        self._state = state
        self._details = details
        self._ui_dirty = True

    def _poll_ui_update(self, _):
        """主线程定时器：安全地更新 UI"""
        if not self._ui_dirty:
            return
        self._ui_dirty = False
        problems = self._details.get("problems", [])
        self._set_icon(self._state, problems)
        self._update_stats_menu()
        self._update_posture_hint(self._state, self._details)

    def _update_posture_hint(self, state, details):
        """实时更新菜单顶部的姿势提示"""
        if not self._mi_hint:
            return

        fatigue = details.get("fatigue")
        fatigue_suffix = ""
        if fatigue:
            fl = fatigue.get("level", "")
            if fl == "very_tired":
                fatigue_suffix = t("tray.hint.fatigue_very_tired")
            elif fl == "tired":
                fatigue_suffix = t("tray.hint.fatigue_tired")

        stance = details.get("stance", "sitting")

        if state == "good":
            hint_key = "tray.hint.good_standing" if stance == "standing" else "tray.hint.good"
            self._mi_hint.title = t(hint_key) + fatigue_suffix
        elif state == "bad":
            reasons = details.get("reasons", [])
            if reasons:
                sep = "；" if get_language() == "zh" else "; "
                self._mi_hint.title = "⚠ " + sep.join(reasons) + fatigue_suffix
            else:
                self._mi_hint.title = t("tray.hint.bad_default") + fatigue_suffix
        elif state == "away":
            self._mi_hint.title = t("tray.hint.away")
        elif state == "camera_adjust":
            direction = details.get("direction")
            if direction:
                self._mi_hint.title = t("tray.hint.camera_adjust_direction", direction=direction)
            else:
                self._mi_hint.title = t("tray.hint.camera_adjust")
        elif state == "camera_wait":
            self._mi_hint.title = t("tray.hint.camera_wait")
        elif state == "stopped":
            self._mi_hint.title = t("tray.hint.stopped")

    def _update_stats_menu(self):
        stats = self.monitor.stats if self.monitor else None
        if stats:
            good_min = f"{stats.good_seconds_total / 60:.0f}"
            bad_min = f"{stats.bad_seconds_total / 60:.0f}"
            notif = stats.notifications_sent
        else:
            good_min, bad_min, notif = "0", "0", 0
        if self._mi_stats:
            self._mi_stats.title = t("tray.menu.statistics_summary", good=good_min, bad=bad_min, notif=notif)
        # Update advanced stats submenu if available
        if hasattr(self, '_mi_stats_items') and self._mi_stats_items:
            g, b, a = self._mi_stats_items
            g.title = t("tray.menu.stats_good", minutes=good_min)
            b.title = t("tray.menu.stats_bad", minutes=bad_min)
            a.title = t("tray.menu.stats_alerts", count=notif)

    # --- 监控控制 ---

    def _is_running(self):
        return self.monitor is not None and self.monitor.running

    def _toggle_monitor(self, sender):
        if self._is_running():
            self._stop_monitor()
            sender.title = t("tray.menu.start_monitoring")
        else:
            self._start_monitor()
            sender.title = t("tray.menu.stop_monitoring")

    def _start_monitor(self):
        if self._is_running():
            return
        self.monitor = PostureMonitor(
            self.settings,
            debug=self.debug,
            on_state_change=self._on_state_change,
        )
        if not self.monitor.check_model():
            rumps.notification("Sit Monitor", "Error", t("tray.notify.model_error"))
            return
        self.monitor_thread = threading.Thread(target=self.monitor.run, daemon=True)
        self.monitor_thread.start()

    def _stop_monitor(self):
        if self.monitor:
            self.monitor.stop()
            if self.monitor_thread:
                self.monitor_thread.join(timeout=3)
                if self.monitor_thread.is_alive():
                    # 线程仍卡在阻塞调用中，强制释放摄像头
                    log.warning("Monitor thread did not stop in time, releasing camera")
                    try:
                        import cv2
                        # 尝试打开再关闭摄像头，强制释放资源
                        _cap = cv2.VideoCapture(self.settings.camera)
                        _cap.release()
                    except Exception:
                        pass
            self.monitor = None
            self.monitor_thread = None
        self._state = "stopped"
        self._set_icon("stopped")

    # --- Exercise ---

    def _is_exercising(self):
        return self._exercise_proc is not None and self._exercise_proc.poll() is None

    def _toggle_pushup(self, sender):
        if self._is_exercising():
            self._stop_exercise()
            sender.title = t("tray.menu.pushup_training")
        else:
            # 暂停坐姿监控，启动俯卧撑训练
            was_monitoring = self._is_running()
            if was_monitoring:
                self._stop_monitor()
                self._mi_start.title = t("tray.menu.start_monitoring")

            self._start_exercise("pushup", sender, was_monitoring)

    def _start_exercise(self, exercise_id, sender, resume_posture_after=False):
        # 以独立子进程启动（cv2.imshow 需要主线程）
        python = python_executable()
        args = [python, "-m", "sit_monitor", exercise_id,
                "--camera", str(self.settings.camera), "--debug"]
        self._exercise_proc = subprocess.Popen(args, cwd=PROJECT_DIR)
        sender.title = t("tray.menu.stop_pushup")
        self._set_icon("exercise")

        def wait_and_cleanup():
            self._exercise_proc.wait()
            sender.title = t("tray.menu.pushup_training")
            self._exercise_proc = None
            self._set_icon("stopped")
            rumps.notification("Sit Monitor", t("tray.notify.exercise_done_title"),
                               t("tray.notify.exercise_done_msg"))
            if resume_posture_after:
                self._start_monitor()
                self._mi_start.title = t("tray.menu.stop_monitoring")

        threading.Thread(target=wait_and_cleanup, daemon=True).start()

    def _stop_exercise(self):
        if self._exercise_proc and self._exercise_proc.poll() is None:
            self._exercise_proc.terminate()
            try:
                self._exercise_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._exercise_proc.kill()
            self._exercise_proc = None
            self._set_icon("stopped")

    # --- Preview ---

    def _is_previewing(self):
        return self._preview_proc is not None and self._preview_proc.poll() is None

    def _toggle_preview(self, sender):
        if self._is_previewing():
            self._stop_preview()
            sender.title = t("tray.menu.show_camera")
        else:
            self._start_preview(sender)

    def _start_preview(self, sender):
        python = python_executable()
        args = [python, "-m", "sit_monitor", "preview",
                "--camera", str(self.settings.camera)]
        self._preview_proc = subprocess.Popen(args, cwd=PROJECT_DIR)
        sender.title = t("tray.menu.hide_camera")

        def wait_and_cleanup():
            self._preview_proc.wait()
            sender.title = t("tray.menu.show_camera")
            self._preview_proc = None

        threading.Thread(target=wait_and_cleanup, daemon=True).start()

    def _stop_preview(self):
        if self._preview_proc and self._preview_proc.poll() is None:
            self._preview_proc.terminate()
            try:
                self._preview_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._preview_proc.kill()
            self._preview_proc = None

    # --- Overlay ---

    def _is_overlay_running(self):
        return self._overlay_proc is not None and self._overlay_proc.poll() is None

    def _toggle_overlay(self, sender):
        if self._is_overlay_running():
            self._stop_overlay()
            sender.title = t("tray.menu.show_overlay")
        else:
            self._start_overlay(sender)

    def _start_overlay(self, sender):
        python = python_executable()
        args = [python, "-m", "sit_monitor", "overlay",
                "--camera", str(self.settings.camera)]
        self._overlay_proc = subprocess.Popen(args, cwd=PROJECT_DIR)
        sender.title = t("tray.menu.hide_overlay")

        def wait_and_cleanup():
            self._overlay_proc.wait()
            sender.title = t("tray.menu.show_overlay")
            self._overlay_proc = None

        threading.Thread(target=wait_and_cleanup, daemon=True).start()

    def _stop_overlay(self):
        if self._overlay_proc and self._overlay_proc.poll() is None:
            self._overlay_proc.terminate()
            try:
                self._overlay_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._overlay_proc.kill()
            self._overlay_proc = None

    # --- Snooze ---

    def _snooze(self, sender):
        if self.monitor:
            self.monitor.snooze_until = time.time() + 600  # 10 分钟
            rumps.notification("Sit Monitor", t("tray.notify.snooze_title"), t("tray.notify.snooze_msg"))
            sender.title = t("tray.menu.alerts_paused")
            # 10 分钟后恢复菜单文字
            def restore():
                time.sleep(600)
                sender.title = t("tray.menu.pause_alerts")
            threading.Thread(target=restore, daemon=True).start()

    # --- Stance ---

    def _cycle_stance(self, sender):
        """循环切换 stance_mode: auto → sitting → standing → auto"""
        cycle = {"auto": "sitting", "sitting": "standing", "standing": "auto"}
        self.settings.stance_mode = cycle.get(self.settings.stance_mode, "auto")
        self.settings.save()
        sender.title = self._stance_label()

    # --- Report ---

    def _view_report(self, _):
        text = weekly_report()
        rumps.alert(title=t("tray.alert.weekly_report_title"), message=text, ok=t("btn.ok"))

    def _check_daily_report(self, _):
        """每分钟检查一次，如果日期变了就发送昨日摘要"""
        from datetime import date, timedelta
        today = date.today()
        if self._last_daily_report_date is None:
            self._last_daily_report_date = today
            return
        if today != self._last_daily_report_date:
            self._last_daily_report_date = today
            yesterday = today - timedelta(days=1)
            text = daily_summary_text(yesterday)
            if t("tray.alert.no_data_keyword") not in text:
                rumps.notification("Sit Monitor", t("tray.alert.daily_report_title"), text)

    # --- Settings ---

    def _adjust(self, attr, delta):
        val = getattr(self.settings, attr)
        new_val = max(1.0, val + delta)
        if isinstance(val, int):
            new_val = int(new_val)
        else:
            new_val = round(new_val, 1)
        setattr(self.settings, attr, new_val)
        self.settings.save()
        if attr in self._mi_setting_labels:
            label_item, name_key, unit = self._mi_setting_labels[attr]
            label_item.title = f"{t(name_key)}: {new_val}{unit}"

    def _toggle_sound(self, sender):
        self.settings.sound = not self.settings.sound
        self.settings.save()
        sender.title = f"{'☑' if self.settings.sound else '☐'} {t('tray.menu.sound')}"

    def _toggle_auto_pause(self, sender):
        self.settings.auto_pause = not self.settings.auto_pause
        self.settings.save()
        sender.title = f"{'☑' if self.settings.auto_pause else '☐'} {t('tray.menu.auto_pause')}"

    def _toggle_call_mute(self, sender):
        self.settings.call_mute = not self.settings.call_mute
        self.settings.save()
        sender.title = f"{'☑' if self.settings.call_mute else '☐'} {t('tray.menu.call_mute')}"

    def _toggle_fatigue(self, sender):
        self.settings.fatigue_enabled = not self.settings.fatigue_enabled
        self.settings.save()
        sender.title = f"{'☑' if self.settings.fatigue_enabled else '☐'} {t('tray.menu.fatigue_detection')}"
        if self.settings.fatigue_enabled:
            rumps.notification("Sit Monitor", t("tray.notify.fatigue_on"), t("tray.notify.fatigue_on_msg"))
        else:
            rumps.notification("Sit Monitor", t("tray.notify.fatigue_off"), "")

    # --- Cloud / Social ---

    def _init_cloud(self):
        """初始化云端功能"""
        if not self.settings.cloud_enabled:
            return
        try:
            from sit_monitor.cloud import AchievementEngine, CloudClient, SyncManager
            self.settings.ensure_device_id()
            self._cloud_client = CloudClient()
            self._sync_manager = SyncManager(self.settings, self._cloud_client)
            self._achievement_engine = AchievementEngine()
            self._sync_manager.start()
            self._update_social_menu()
        except Exception as e:
            log.warning("Cloud init error: %s", e)

    def _stop_cloud(self):
        if self._sync_manager:
            self._sync_manager.stop()
            self._sync_manager = None
        if self._cloud_client:
            self._cloud_client.close()
            self._cloud_client = None

    def _toggle_cloud(self, sender):
        self.settings.cloud_enabled = not self.settings.cloud_enabled
        self.settings.save()
        sender.title = f"{'☑' if self.settings.cloud_enabled else '☐'} {t('tray.menu.enable_cloud')}"
        if self.settings.cloud_enabled:
            self._init_cloud()
        else:
            self._stop_cloud()

    def _update_social_menu(self):
        """更新 Social 菜单中的动态文字"""
        if self.settings.simple_mode:
            return
        try:
            if self._achievement_engine and self._mi_achievements:
                n = self._achievement_engine.unlocked_count
                total = self._achievement_engine.total_count
                self._mi_achievements.title = t("tray.menu.achievements", unlocked=n, total=total)
        except Exception:
            pass

    def _show_leaderboard_daily(self, _):
        if not self._cloud_client:
            rumps.alert("Social", t("tray.alert.cloud_required"))
            return
        try:
            today = str(date.today())
            entries = self._cloud_client.leaderboard_daily(today)
            if not entries:
                rumps.alert(t("tray.alert.leaderboard_today_title"), t("tray.alert.leaderboard_no_data"))
                return
            lines = [t("tray.alert.leaderboard_header")]
            lines.append("-" * 40)
            for e in entries[:20]:
                lines.append(
                    f"{e.rank:>2}  {e.nickname:<10}  {e.good_pct:>4}%  {e.total_minutes:>4.0f}m  {e.likes_count:>3}"
                )
            rumps.alert(title=t("tray.alert.leaderboard_today_title"), message="\n".join(lines), ok=t("btn.ok"))
        except Exception as e:
            rumps.alert(t("tray.alert.leaderboard_error"), str(e))

    def _show_leaderboard_weekly(self, _):
        if not self._cloud_client:
            rumps.alert("Social", t("tray.alert.cloud_required"))
            return
        try:
            today = date.today()
            week_start = str(today - timedelta(days=today.weekday()))
            entries = self._cloud_client.leaderboard_weekly(week_start)
            if not entries:
                rumps.alert(t("tray.alert.leaderboard_week_title"), t("tray.alert.leaderboard_no_data"))
                return
            lines = [t("tray.alert.leaderboard_header")]
            lines.append("-" * 40)
            for e in entries[:20]:
                lines.append(
                    f"{e.rank:>2}  {e.nickname:<10}  {e.good_pct:>4}%  {e.total_minutes:>4.0f}m  {e.likes_count:>3}"
                )
            rumps.alert(title=t("tray.alert.leaderboard_week_title"), message="\n".join(lines), ok=t("btn.ok"))
        except Exception as e:
            rumps.alert(t("tray.alert.leaderboard_error"), str(e))

    def _show_achievements(self, _):
        if not self._achievement_engine:
            from sit_monitor.cloud.achievements import AchievementEngine
            self._achievement_engine = AchievementEngine()
        achs = self._achievement_engine.get_all_achievements()
        lines = []
        for a in achs:
            status = "✅" if a["unlocked"] else "🔒"
            lines.append(f"{status} {a['icon']} {a['name']}: {a['description']}")
        rumps.alert(
            title=t("tray.alert.achievements_title",
                     unlocked=self._achievement_engine.unlocked_count,
                     total=self._achievement_engine.total_count),
            message="\n".join(lines),
            ok=t("btn.ok"),
        )

    def _show_challenges(self, _):
        if not self._cloud_client:
            rumps.alert("Social", t("tray.alert.cloud_required"))
            return
        try:
            challenges = self._cloud_client.list_my_challenges()
            if not challenges:
                rumps.alert(t("tray.alert.challenges_title"), t("tray.alert.no_challenges"))
                return
            lines = []
            for ch in challenges[:10]:
                status = {"pending": "⏳", "active": "⚔️", "completed": "✅"}.get(ch.get("status"), "?")
                lines.append(
                    f"{status} {ch.get('challenge_type','?')} "
                    f"{t('tray.alert.challenge_target', target=ch.get('target_value', 0))} "
                    f"{t('tray.alert.challenge_creator', score=ch.get('creator_score', 0))} vs "
                    f"{t('tray.alert.challenge_opponent', score=ch.get('opponent_score', 0))}"
                )
            rumps.alert(title=t("tray.alert.challenges_title"), message="\n".join(lines), ok=t("btn.ok"))
        except Exception as e:
            rumps.alert(t("tray.alert.challenge_error"), str(e))

    def _sync_now(self, _):
        if not self._sync_manager:
            rumps.alert("Social", t("tray.alert.cloud_required"))
            return
        def do_sync():
            self._sync_manager.sync_once()
            rumps.notification("Sit Monitor", t("tray.notify.sync_done"), t("tray.notify.sync_done_msg"))
        threading.Thread(target=do_sync, daemon=True).start()

    def _change_nickname(self, _):
        resp = rumps.Window(
            title=t("tray.alert.nickname_title"),
            message=t("tray.alert.nickname_msg"),
            default_text=self.settings.nickname,
            ok=t("btn.confirm"),
            cancel=t("btn.cancel"),
        ).run()
        if resp.clicked and resp.text.strip():
            new_name = resp.text.strip()[:20]
            self.settings.nickname = new_name
            self.settings.save()
            if self._mi_nickname:
                self._mi_nickname.title = t("tray.menu.nickname", name=new_name)
            if self._cloud_client:
                threading.Thread(
                    target=self._cloud_client.update_nickname,
                    args=(new_name,),
                    daemon=True,
                ).start()

    def _toggle_share(self, sender):
        self.settings.share_posture = not self.settings.share_posture
        self.settings.share_exercise = self.settings.share_posture
        self.settings.save()
        sender.title = f"{'☑' if self.settings.share_posture else '☐'} {t('tray.menu.share_data')}"

    # --- Battle ---

    def _quick_battle(self, _):
        """快速对战：从排行榜选择对手"""
        if not self._cloud_client:
            rumps.alert("Battle", t("tray.alert.cloud_required_short"))
            return
        try:
            today = str(date.today())
            entries = self._cloud_client.leaderboard_daily(today)
            others = [e for e in entries if e.user_id != self._cloud_client.user_id]
            if not others:
                rumps.alert(t("tray.alert.battle_title"), t("tray.alert.battle_no_opponents"))
                return
            lines = [t("tray.alert.battle_select_opponent")]
            for i, e in enumerate(others[:10], 1):
                lines.append(t("tray.alert.battle_opponent_entry", i=i, nickname=e.nickname, pct=e.good_pct))
            resp = rumps.Window(
                title=t("tray.alert.battle_title"),
                message="\n".join(lines),
                default_text="1",
                ok=t("btn.start_battle"),
                cancel=t("btn.cancel"),
            ).run()
            if resp.clicked and resp.text.strip():
                try:
                    idx = int(resp.text.strip()) - 1
                    if 0 <= idx < len(others):
                        opponent = others[idx]
                        result = self._cloud_client.create_battle(opponent.user_id)
                        if result:
                            rumps.notification("Sit Monitor", t("tray.notify.battle_created"),
                                               t("tray.notify.battle_created_msg", nickname=opponent.nickname))
                        else:
                            rumps.alert("Battle", t("tray.alert.battle_create_failed"))
                except (ValueError, IndexError):
                    rumps.alert("Battle", t("tray.alert.battle_invalid_choice"))
        except Exception as e:
            rumps.alert(t("tray.alert.battle_error"), str(e))

    def _show_battles(self, _):
        """显示我的对战列表"""
        if not self._cloud_client:
            rumps.alert("Battle", t("tray.alert.cloud_required_short"))
            return
        try:
            battles = self._cloud_client.list_my_battles()
            if not battles:
                rumps.alert(t("tray.alert.my_battles_title"), t("tray.alert.no_battles"))
                return
            lines = []
            uid = self._cloud_client.user_id
            for b in battles[:10]:
                status_icon = {
                    "invite": "📨", "accepted": "✅", "active": "🏃",
                    "finished": "🏁", "expired": "⏰", "cancelled": "❌",
                }.get(b.get("status"), "?")
                is_creator = b.get("creator_id") == uid
                role = t("tray.alert.battle_role_creator") if is_creator else t("tray.alert.battle_role_opponent")
                my_score = b.get("creator_score", 0) if is_creator else b.get("opponent_score", 0)
                opp_score = b.get("opponent_score", 0) if is_creator else b.get("creator_score", 0)
                winner = b.get("winner_id", "")
                win_text = ""
                if b.get("status") == "finished":
                    if winner == uid:
                        win_text = t("tray.alert.battle_win")
                    elif winner:
                        win_text = t("tray.alert.battle_lose")
                    else:
                        win_text = t("tray.alert.battle_draw")
                lines.append(
                    f"{status_icon} [{role}] {b.get('status')} | "
                    f"{t('tray.alert.battle_score', my_score=my_score, opp_score=opp_score)}{win_text}"
                )
            rumps.alert(title=t("tray.alert.my_battles_title"), message="\n".join(lines), ok=t("btn.ok"))
        except Exception as e:
            rumps.alert(t("tray.alert.battle_error"), str(e))

    # --- Account ---

    def _link_google(self, _):
        """绑定 Google 账号"""
        if not self._cloud_client:
            rumps.alert("Account", t("tray.alert.cloud_required_short"))
            return
        resp = rumps.alert(
            title=t("tray.alert.link_google_title"),
            message=t("tray.alert.link_google_msg"),
            ok=t("btn.continue_link"),
            cancel=t("btn.cancel"),
        )
        if resp != 1:
            return
        try:
            from sit_monitor.cloud.social_auth import start_google_oauth
            result = start_google_oauth(self._cloud_client)
            if result.get("success"):
                self.settings.auth_provider = "google"
                self.settings.save()
                if self._mi_auth:
                    self._mi_auth.title = t("tray.menu.auth_status", provider="google")
                rumps.notification("Sit Monitor", t("tray.notify.google_linked"), result.get("message", ""))
            elif result.get("url"):
                import webbrowser
                webbrowser.open(result["url"])
                rumps.notification("Sit Monitor", t("tray.notify.google_auth_pending"),
                                   t("tray.notify.google_auth_pending_msg"))
            else:
                rumps.alert(t("tray.alert.link_failed"),
                            result.get("error", t("tray.alert.link_unknown_error")))
        except Exception as e:
            rumps.alert(t("tray.alert.link_error"), str(e))

    def _unlink_provider(self, _):
        """解绑社交账号"""
        if self.settings.auth_provider == "device":
            rumps.alert("Account", t("tray.alert.already_anonymous"))
            return
        resp = rumps.alert(
            title=t("tray.alert.unlink_title"),
            message=t("tray.alert.unlink_msg", provider=self.settings.auth_provider),
            ok=t("btn.confirm_unlink"),
            cancel=t("btn.cancel"),
        )
        if resp == 1:
            self.settings.auth_provider = "device"
            self.settings.save()
            if self._mi_auth:
                self._mi_auth.title = t("tray.menu.auth_status", provider="device")
            rumps.notification("Sit Monitor", t("tray.notify.unlinked"), t("tray.notify.unlinked_msg"))

    def _check_achievements(self):
        """定时检查成就，解锁时发通知"""
        if not self._achievement_engine:
            return
        try:
            newly = self._achievement_engine.check_and_unlock()
            for a in newly:
                rumps.notification("Sit Monitor",
                                   t("tray.notify.achievement_unlocked", icon=a.icon, name=a.name),
                                   a.description)
                if self._cloud_client:
                    self._cloud_client.upload_achievement(a.id, self._achievement_engine._unlocked.get(a.id, ""))
            self._update_social_menu()
        except Exception as e:
            log.warning("Achievement check error: %s", e)

    # --- Auto Update ---

    def _start_auto_update_check(self):
        """启动后台定时检查更新线程"""
        def auto_check():
            while True:
                time.sleep(self._auto_update_hours * 3600)
                self._silent_check_update()

        _t = threading.Thread(target=auto_check, daemon=True)
        _t.start()

    def _silent_check_update(self):
        """静默检查更新，有新版本时通知用户"""
        if is_bundled():
            try:
                from sit_monitor.updater import check_for_update
                has_update, tag, _ = check_for_update(VERSION)
                if has_update:
                    rumps.notification("Sit Monitor", t("tray.notify.update_available"),
                                       t("tray.notify.update_new_version", version=tag))
            except Exception:
                pass
        else:
            try:
                subprocess.run(["git", "fetch", "origin"], cwd=PROJECT_DIR,
                               capture_output=True, timeout=15)
                local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR,
                                       capture_output=True, text=True).stdout.strip()
                remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=PROJECT_DIR,
                                        capture_output=True, text=True).stdout.strip()
                if local != remote:
                    git_log = subprocess.run(
                        ["git", "log", f"{local}..{remote}", "--oneline"],
                        cwd=PROJECT_DIR, capture_output=True, text=True,
                    ).stdout.strip()
                    rumps.notification("Sit Monitor", t("tray.notify.update_available"),
                                       t("tray.notify.update_available_msg", log=git_log))
            except Exception:
                pass

    # --- Update ---

    def _check_update(self, _):
        if is_bundled():
            self._check_update_bundled()
        else:
            self._check_update_git()

    def _check_update_bundled(self):
        """打包模式：通过 GitHub Releases 自动下载并替换更新"""
        def do_update():
            try:
                from sit_monitor.updater import (
                    check_for_update, get_dmg_url, download_update, install_and_restart,
                )
                has_update, tag, release = check_for_update(VERSION)
                if not has_update:
                    rumps.notification("Sit Monitor", t("tray.menu.check_updates"),
                                       t("tray.notify.up_to_date"))
                    return

                url = get_dmg_url(release)
                if not url:
                    rumps.notification("Sit Monitor", t("tray.notify.update_failed"),
                                       "No DMG found in release")
                    return

                rumps.notification("Sit Monitor", t("tray.notify.downloading_update"),
                                   tag)

                dmg_path = download_update(url)

                rumps.notification("Sit Monitor", t("tray.notify.update_done"), tag)

                if install_and_restart(dmg_path):
                    self._stop_preview()
                    self._stop_overlay()
                    self._stop_exercise()
                    self._stop_monitor()
                    self._stop_cloud()
                    rumps.quit_application()
                else:
                    rumps.notification("Sit Monitor", t("tray.notify.update_failed"),
                                       "Cannot determine app path")
            except Exception as e:
                rumps.notification("Sit Monitor", t("tray.notify.update_failed"), str(e))

        threading.Thread(target=do_update, daemon=True).start()

    def _check_update_git(self):
        """源码模式：通过 git pull 更新"""
        def do_update():
            try:
                subprocess.run(["git", "fetch", "origin"], cwd=PROJECT_DIR,
                               capture_output=True, timeout=15)
                local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR,
                                       capture_output=True, text=True).stdout.strip()
                remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=PROJECT_DIR,
                                        capture_output=True, text=True).stdout.strip()

                if local == remote:
                    rumps.notification("Sit Monitor", t("tray.menu.check_updates"), t("tray.notify.up_to_date"))
                    return

                subprocess.run(["git", "pull", "origin", "main"], cwd=PROJECT_DIR,
                               capture_output=True, timeout=30)

                diff = subprocess.run(
                    ["git", "diff", local, remote, "--name-only"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout
                if "requirements.txt" in diff:
                    python = python_executable()
                    req = os.path.join(PROJECT_DIR, "requirements.txt")
                    subprocess.run(["uv", "pip", "install", "--python", python, "-r", req],
                                   capture_output=True, timeout=60)

                git_log = subprocess.run(
                    ["git", "log", f"{local}..{remote}", "--oneline"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout.strip()

                rumps.notification("Sit Monitor", t("tray.notify.update_done"),
                                   git_log or "OK")

                # 自动重启：停止监控后 re-exec
                self._stop_monitor()
                time.sleep(1)
                python = python_executable()
                script = os.path.join(PROJECT_DIR, "sit_monitor.py")
                args = [python, script, "--tray"]
                if self.debug:
                    args.append("--debug")
                subprocess.Popen(args)
                rumps.quit_application()

            except Exception as e:
                rumps.notification("Sit Monitor", t("tray.notify.update_failed"), str(e))

        threading.Thread(target=do_update, daemon=True).start()

    # --- About ---

    def _show_about(self, _):
        try:
            commit = subprocess.run(
                ["git", "log", "--oneline", "-1"], cwd=PROJECT_DIR,
                capture_output=True, text=True,
            ).stdout.strip()
        except Exception:
            commit = "unknown"

        rumps.alert(
            title="Sit Monitor",
            message=t("tray.alert.about_msg", version=VERSION, commit=commit, repo=REPO_URL),
            ok=t("btn.ok"),
        )

    # --- Quit / Run ---

    @rumps.clicked("Quit")
    def quit_app(self, _):
        self._stop_preview()
        self._stop_overlay()
        self._stop_exercise()
        self._stop_monitor()
        self._stop_cloud()
        rumps.quit_application()

    def run(self):
        @rumps.timer(1)
        def auto_start(timer):
            timer.stop()
            self._start_monitor()
            self._mi_start.title = t("tray.menu.stop_monitoring")
            # 初始化云端功能
            self._init_cloud()

        # 每 0.5 秒在主线程更新 UI
        @rumps.timer(0.5)
        def ui_update(timer):
            self._poll_ui_update(timer)

        # 每 60 秒检查是否需要发送每日报告
        @rumps.timer(60)
        def daily_report_check(timer):
            self._check_daily_report(timer)

        # 每 30 分钟检查成就
        @rumps.timer(1800)
        def achievement_check(timer):
            self._check_achievements()

        super().run()
