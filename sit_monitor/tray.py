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
from sit_monitor.report import daily_summary_text, weekly_report
from sit_monitor.settings import Settings

log = logging.getLogger(__name__)

VERSION = "1.1.0"
REPO_URL = "https://github.com/zoubenjia/sit-position"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 图标路径
_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
_ICON_FILES = {
    "good": os.path.join(_ASSETS, "icon_good_color.png"),
    "bad": os.path.join(_ASSETS, "icon_bad_color.png"),
    "away": os.path.join(_ASSETS, "icon_idle.png"),
    "camera_wait": os.path.join(_ASSETS, "icon_idle.png"),
    "stopped": os.path.join(_ASSETS, "icon_idle.png"),
}


class TrayApp(rumps.App):
    def __init__(self, settings: Settings, debug=False):
        super().__init__("Sit Monitor", icon=_ICON_FILES["stopped"], quit_button=None)
        self.settings = settings
        self.debug = debug
        self.monitor = None
        self.monitor_thread = None
        self._exercise_proc = None
        self._preview_proc = None
        self._state = "stopped"
        self._details = {}
        self._ui_dirty = False
        self._last_daily_report_date = None
        self._auto_update_hours = 12  # 自动检查更新间隔（小时）
        # Cloud
        self._cloud_client = None
        self._sync_manager = None
        self._achievement_engine = None
        self._build_menu()
        self._start_auto_update_check()

    def _build_menu(self):
        s = self.settings
        self.menu = [
            rumps.MenuItem("✓ 姿势良好", callback=None),
            None,
            rumps.MenuItem("Start Monitoring", callback=self._toggle_monitor),
            rumps.MenuItem("📷 Show Camera", callback=self._toggle_preview),
            rumps.MenuItem("Pause Alerts 10min", callback=self._snooze),
            None,
            rumps.MenuItem("🏋️ Pushup Training", callback=self._toggle_pushup),
            [rumps.MenuItem("⚔️ Push-up Battle"), [
                rumps.MenuItem("⚡ Quick Battle", callback=self._quick_battle),
                rumps.MenuItem("📋 My Battles", callback=self._show_battles),
            ]],
            None,
            rumps.MenuItem("Statistics", callback=None),
            [rumps.MenuItem("Stats"), [
                rumps.MenuItem("姿势良好: 0 min", callback=None),
                rumps.MenuItem("姿势不良: 0 min", callback=None),
                rumps.MenuItem("提醒次数: 0", callback=None),
            ]],
            rumps.MenuItem("View Report", callback=self._view_report),
            None,
            [rumps.MenuItem("Settings"), [
                rumps.MenuItem(f"Shoulder: {s.shoulder_threshold}°", callback=None),
                rumps.MenuItem("  Shoulder +1", callback=lambda _: self._adjust("shoulder_threshold", 1)),
                rumps.MenuItem("  Shoulder -1", callback=lambda _: self._adjust("shoulder_threshold", -1)),
                None,
                rumps.MenuItem(f"Neck: {s.neck_threshold}°", callback=None),
                rumps.MenuItem("  Neck +1", callback=lambda _: self._adjust("neck_threshold", 1)),
                rumps.MenuItem("  Neck -1", callback=lambda _: self._adjust("neck_threshold", -1)),
                None,
                rumps.MenuItem(f"Torso: {s.torso_threshold}°", callback=None),
                rumps.MenuItem("  Torso +1", callback=lambda _: self._adjust("torso_threshold", 1)),
                rumps.MenuItem("  Torso -1", callback=lambda _: self._adjust("torso_threshold", -1)),
                None,
                rumps.MenuItem(f"Bad Seconds: {s.bad_seconds}s", callback=None),
                rumps.MenuItem("  Bad Seconds +5", callback=lambda _: self._adjust("bad_seconds", 5)),
                rumps.MenuItem("  Bad Seconds -5", callback=lambda _: self._adjust("bad_seconds", -5)),
                None,
                rumps.MenuItem(
                    f"{'☑' if s.sound else '☐'} Sound",
                    callback=self._toggle_sound,
                ),
                rumps.MenuItem(
                    f"{'☑' if s.auto_pause else '☐'} Auto-pause",
                    callback=self._toggle_auto_pause,
                ),
                None,
                rumps.MenuItem(
                    f"{'☑' if s.fatigue_enabled else '☐'} Fatigue Detection",
                    callback=self._toggle_fatigue,
                ),
            ]],
            None,
            [rumps.MenuItem("🌐 Social"), [
                rumps.MenuItem("📊 Leaderboard (Today)", callback=self._show_leaderboard_daily),
                rumps.MenuItem("📊 Leaderboard (Week)", callback=self._show_leaderboard_weekly),
                None,
                rumps.MenuItem("🏅 My Achievements (0/10)", callback=self._show_achievements),
                rumps.MenuItem("⚔️ Challenges", callback=self._show_challenges),
                None,
                rumps.MenuItem("🔄 Sync Now", callback=self._sync_now),
                rumps.MenuItem(f"Nickname: {s.nickname}", callback=self._change_nickname),
                rumps.MenuItem(
                    f"{'☑' if s.share_posture else '☐'} Share Data",
                    callback=self._toggle_share,
                ),
            ]],
            [rumps.MenuItem("🔐 Account"), [
                rumps.MenuItem(f"Auth: {s.auth_provider}", callback=None),
                rumps.MenuItem("🔗 Link Google", callback=self._link_google),
                rumps.MenuItem("🔓 Unlink", callback=self._unlink_provider),
            ]],
            None,
            rumps.MenuItem(
                f"{'☑' if s.cloud_enabled else '☐'} Enable Cloud",
                callback=self._toggle_cloud,
            ),
            None,
            rumps.MenuItem("Check for Updates", callback=self._check_update),
            rumps.MenuItem(f"About v{VERSION}", callback=self._show_about),
            None,
        ]
        self._update_stats_menu()

    # --- 图标 ---

    def _set_icon(self, state):
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
        self._set_icon(self._state)
        self._update_stats_menu()
        self._update_posture_hint(self._state, self._details)

    def _update_posture_hint(self, state, details):
        """实时更新菜单顶部的姿势提示"""
        try:
            hint_item = self.menu["✓ 姿势良好"]
        except KeyError:
            return

        fatigue = details.get("fatigue")
        fatigue_suffix = ""
        if fatigue:
            fl = fatigue.get("level", "")
            if fl == "very_tired":
                fatigue_suffix = " | 😴 非常疲劳"
            elif fl == "tired":
                fatigue_suffix = " | 🥱 疲劳"

        if state == "good":
            hint_item.title = "✓ 姿势良好" + fatigue_suffix
        elif state == "bad":
            reasons = details.get("reasons", [])
            if reasons:
                hint_item.title = "⚠ " + "；".join(reasons) + fatigue_suffix
            else:
                hint_item.title = "⚠ 请纠正坐姿" + fatigue_suffix
        elif state == "away":
            hint_item.title = "— 未检测到人"
        elif state == "camera_wait":
            hint_item.title = "⏳ 等待摄像头"
        elif state == "stopped":
            hint_item.title = "— 未启动"

    def _update_stats_menu(self):
        stats = self.monitor.stats if self.monitor else None
        if stats:
            good_min = f"{stats.good_seconds_total / 60:.0f}"
            bad_min = f"{stats.bad_seconds_total / 60:.0f}"
            notif = stats.notifications_sent
        else:
            good_min, bad_min, notif = "0", "0", 0
        try:
            self.menu["Statistics"].title = f"良好 {good_min}min | 不良 {bad_min}min | 提醒 {notif}次"
        except Exception:
            pass

    # --- 监控控制 ---

    def _is_running(self):
        return self.monitor is not None and self.monitor.running

    def _toggle_monitor(self, sender):
        if self._is_running():
            self._stop_monitor()
            sender.title = "Start Monitoring"
        else:
            self._start_monitor()
            sender.title = "Stop Monitoring"

    def _start_monitor(self):
        if self._is_running():
            return
        self.monitor = PostureMonitor(
            self.settings,
            debug=self.debug,
            on_state_change=self._on_state_change,
        )
        if not self.monitor.check_model():
            rumps.notification("Sit Monitor", "错误", "未找到模型文件，请运行 bash setup.sh")
            return
        self.monitor_thread = threading.Thread(target=self.monitor.run, daemon=True)
        self.monitor_thread.start()

    def _stop_monitor(self):
        if self.monitor:
            self.monitor.stop()
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)
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
            sender.title = "🏋️ Pushup Training"
        else:
            # 暂停坐姿监控，启动俯卧撑训练
            was_monitoring = self._is_running()
            if was_monitoring:
                self._stop_monitor()
                try:
                    self.menu["Start Monitoring"].title = "Start Monitoring"
                except Exception:
                    pass

            self._start_exercise("pushup", sender, was_monitoring)

    def _start_exercise(self, exercise_id, sender, resume_posture_after=False):
        # 以独立子进程启动（cv2.imshow 需要主线程）
        python = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
        args = [python, "-m", "sit_monitor", exercise_id,
                "--camera", str(self.settings.camera), "--debug"]
        self._exercise_proc = subprocess.Popen(args, cwd=PROJECT_DIR)
        sender.title = "⏹ Stop Pushup"

        def wait_and_cleanup():
            self._exercise_proc.wait()
            sender.title = "🏋️ Pushup Training"
            self._exercise_proc = None
            rumps.notification("Sit Monitor", "训练结束", "俯卧撑训练已完成")
            if resume_posture_after:
                self._start_monitor()
                try:
                    self.menu["Start Monitoring"].title = "Stop Monitoring"
                except Exception:
                    pass

        threading.Thread(target=wait_and_cleanup, daemon=True).start()

    def _stop_exercise(self):
        if self._exercise_proc and self._exercise_proc.poll() is None:
            self._exercise_proc.terminate()
            try:
                self._exercise_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._exercise_proc.kill()
            self._exercise_proc = None

    # --- Preview ---

    def _is_previewing(self):
        return self._preview_proc is not None and self._preview_proc.poll() is None

    def _toggle_preview(self, sender):
        if self._is_previewing():
            self._stop_preview()
            sender.title = "📷 Show Camera"
        else:
            self._start_preview(sender)

    def _start_preview(self, sender):
        python = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
        args = [python, "-m", "sit_monitor", "preview",
                "--camera", str(self.settings.camera)]
        self._preview_proc = subprocess.Popen(args, cwd=PROJECT_DIR)
        sender.title = "📷 Hide Camera"

        def wait_and_cleanup():
            self._preview_proc.wait()
            sender.title = "📷 Show Camera"
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

    # --- Snooze ---

    def _snooze(self, sender):
        if self.monitor:
            self.monitor.snooze_until = time.time() + 600  # 10 分钟
            rumps.notification("Sit Monitor", "已暂停提醒", "10 分钟内不会发送提醒")
            sender.title = "Alerts paused (10min)"
            # 10 分钟后恢复菜单文字
            def restore():
                time.sleep(600)
                sender.title = "Pause Alerts 10min"
            threading.Thread(target=restore, daemon=True).start()

    # --- Report ---

    def _view_report(self, _):
        text = weekly_report()
        rumps.alert(title="Sit Monitor — 周报", message=text, ok="好的")

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
            if "暂无" not in text:
                rumps.notification("Sit Monitor", "昨日坐姿日报", text)

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
        if attr == "bad_seconds":
            name, unit = "Bad Seconds", "s"
        else:
            name, unit = attr.replace("_threshold", "").capitalize(), "°"
        try:
            self.menu["Settings"][f"{name}: {val}{unit}"].title = f"{name}: {new_val}{unit}"
        except Exception:
            pass

    def _toggle_sound(self, sender):
        self.settings.sound = not self.settings.sound
        self.settings.save()
        sender.title = f"{'☑' if self.settings.sound else '☐'} Sound"

    def _toggle_auto_pause(self, sender):
        self.settings.auto_pause = not self.settings.auto_pause
        self.settings.save()
        sender.title = f"{'☑' if self.settings.auto_pause else '☐'} Auto-pause"

    def _toggle_fatigue(self, sender):
        self.settings.fatigue_enabled = not self.settings.fatigue_enabled
        self.settings.save()
        sender.title = f"{'☑' if self.settings.fatigue_enabled else '☐'} Fatigue Detection"
        if self.settings.fatigue_enabled:
            rumps.notification("Sit Monitor", "疲劳检测已开启", "将在下次启动监控时生效")
        else:
            rumps.notification("Sit Monitor", "疲劳检测已关闭", "")

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
        sender.title = f"{'☑' if self.settings.cloud_enabled else '☐'} Enable Cloud"
        if self.settings.cloud_enabled:
            self._init_cloud()
        else:
            self._stop_cloud()

    def _update_social_menu(self):
        """更新 Social 菜单中的动态文字"""
        try:
            if self._achievement_engine:
                n = self._achievement_engine.unlocked_count
                total = self._achievement_engine.total_count
                self.menu["🌐 Social"]["🏅 My Achievements (0/7)"].title = f"🏅 My Achievements ({n}/{total})"
        except Exception:
            pass

    def _show_leaderboard_daily(self, _):
        if not self._cloud_client:
            rumps.alert("Social", "请先在 Settings 中开启 Enable Cloud")
            return
        try:
            today = str(date.today())
            entries = self._cloud_client.leaderboard_daily(today)
            if not entries:
                rumps.alert("📊 今日排行榜", "暂无数据")
                return
            lines = [f"{'#':>2}  {'昵称':<10}  {'良好率':>5}  {'时长':>5}  {'👍':>3}"]
            lines.append("-" * 40)
            for e in entries[:20]:
                lines.append(
                    f"{e.rank:>2}  {e.nickname:<10}  {e.good_pct:>4}%  {e.total_minutes:>4.0f}m  {e.likes_count:>3}"
                )
            rumps.alert(title="📊 今日排行榜", message="\n".join(lines), ok="好的")
        except Exception as e:
            rumps.alert("排行榜错误", str(e))

    def _show_leaderboard_weekly(self, _):
        if not self._cloud_client:
            rumps.alert("Social", "请先在 Settings 中开启 Enable Cloud")
            return
        try:
            today = date.today()
            week_start = str(today - timedelta(days=today.weekday()))
            entries = self._cloud_client.leaderboard_weekly(week_start)
            if not entries:
                rumps.alert("📊 本周排行榜", "暂无数据")
                return
            lines = [f"{'#':>2}  {'昵称':<10}  {'良好率':>5}  {'时长':>5}  {'👍':>3}"]
            lines.append("-" * 40)
            for e in entries[:20]:
                lines.append(
                    f"{e.rank:>2}  {e.nickname:<10}  {e.good_pct:>4}%  {e.total_minutes:>4.0f}m  {e.likes_count:>3}"
                )
            rumps.alert(title="📊 本周排行榜", message="\n".join(lines), ok="好的")
        except Exception as e:
            rumps.alert("排行榜错误", str(e))

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
            title=f"🏅 成就 ({self._achievement_engine.unlocked_count}/{self._achievement_engine.total_count})",
            message="\n".join(lines),
            ok="好的",
        )

    def _show_challenges(self, _):
        if not self._cloud_client:
            rumps.alert("Social", "请先在 Settings 中开启 Enable Cloud")
            return
        try:
            challenges = self._cloud_client.list_my_challenges()
            if not challenges:
                rumps.alert("⚔️ 挑战", "暂无挑战\n\n通过 MCP 工具 social_create_challenge 发起挑战")
                return
            lines = []
            for ch in challenges[:10]:
                status = {"pending": "⏳", "active": "⚔️", "completed": "✅"}.get(ch.get("status"), "?")
                lines.append(
                    f"{status} {ch.get('challenge_type','?')} "
                    f"目标:{ch.get('target_value',0)} "
                    f"发起方:{ch.get('creator_score',0):.0f} vs 接受方:{ch.get('opponent_score',0):.0f}"
                )
            rumps.alert(title="⚔️ 挑战", message="\n".join(lines), ok="好的")
        except Exception as e:
            rumps.alert("挑战错误", str(e))

    def _sync_now(self, _):
        if not self._sync_manager:
            rumps.alert("Social", "请先在 Settings 中开启 Enable Cloud")
            return
        def do_sync():
            self._sync_manager.sync_once()
            rumps.notification("Sit Monitor", "同步完成", "数据已上传到云端")
        threading.Thread(target=do_sync, daemon=True).start()

    def _change_nickname(self, _):
        resp = rumps.Window(
            title="修改昵称",
            message="输入新昵称（2-20 个字符）",
            default_text=self.settings.nickname,
            ok="确定",
            cancel="取消",
        ).run()
        if resp.clicked and resp.text.strip():
            new_name = resp.text.strip()[:20]
            self.settings.nickname = new_name
            self.settings.save()
            try:
                self.menu["🌐 Social"][f"Nickname: {self.settings.nickname}"].title = f"Nickname: {new_name}"
            except Exception:
                pass
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
        sender.title = f"{'☑' if self.settings.share_posture else '☐'} Share Data"

    # --- Battle ---

    def _quick_battle(self, _):
        """快速对战：从排行榜选择对手"""
        if not self._cloud_client:
            rumps.alert("Battle", "请先开启 Enable Cloud")
            return
        try:
            today = str(date.today())
            entries = self._cloud_client.leaderboard_daily(today)
            others = [e for e in entries if e.user_id != self._cloud_client.user_id]
            if not others:
                rumps.alert("⚔️ 对战", "排行榜上没有其他用户，无法发起对战")
                return
            lines = ["选择对手（输入序号）："]
            for i, e in enumerate(others[:10], 1):
                lines.append(f"  {i}. {e.nickname} (良好率 {e.good_pct}%)")
            resp = rumps.Window(
                title="⚔️ Quick Battle",
                message="\n".join(lines),
                default_text="1",
                ok="发起对战",
                cancel="取消",
            ).run()
            if resp.clicked and resp.text.strip():
                try:
                    idx = int(resp.text.strip()) - 1
                    if 0 <= idx < len(others):
                        opponent = others[idx]
                        result = self._cloud_client.create_battle(opponent.user_id)
                        if result:
                            rumps.notification("Sit Monitor", "⚔️ 对战已发起",
                                               f"向 {opponent.nickname} 发起了俯卧撑对战")
                        else:
                            rumps.alert("对战", "创建对战失败")
                except (ValueError, IndexError):
                    rumps.alert("对战", "无效的选择")
        except Exception as e:
            rumps.alert("对战错误", str(e))

    def _show_battles(self, _):
        """显示我的对战列表"""
        if not self._cloud_client:
            rumps.alert("Battle", "请先开启 Enable Cloud")
            return
        try:
            battles = self._cloud_client.list_my_battles()
            if not battles:
                rumps.alert("⚔️ 对战", "暂无对战\n\n通过 Quick Battle 或 MCP 工具发起对战")
                return
            lines = []
            uid = self._cloud_client.user_id
            for b in battles[:10]:
                status_icon = {
                    "invite": "📨", "accepted": "✅", "active": "🏃",
                    "finished": "🏁", "expired": "⏰", "cancelled": "❌",
                }.get(b.get("status"), "?")
                # 显示对手
                is_creator = b.get("creator_id") == uid
                role = "发起" if is_creator else "收到"
                my_score = b.get("creator_score", 0) if is_creator else b.get("opponent_score", 0)
                opp_score = b.get("opponent_score", 0) if is_creator else b.get("creator_score", 0)
                winner = b.get("winner_id", "")
                win_text = ""
                if b.get("status") == "finished":
                    if winner == uid:
                        win_text = " 🏆 胜"
                    elif winner:
                        win_text = " 败"
                    else:
                        win_text = " 平"
                lines.append(
                    f"{status_icon} [{role}] {b.get('status')} | "
                    f"我:{my_score:.1f} vs 对手:{opp_score:.1f}{win_text}"
                )
            rumps.alert(title="⚔️ 我的对战", message="\n".join(lines), ok="好的")
        except Exception as e:
            rumps.alert("对战错误", str(e))

    # --- Account ---

    def _link_google(self, _):
        """绑定 Google 账号"""
        if not self._cloud_client:
            rumps.alert("Account", "请先开启 Enable Cloud")
            return
        # 提示用户绑定含义
        resp = rumps.alert(
            title="🔗 绑定 Google 账号",
            message=(
                "绑定后：\n"
                "• 您的坐姿和运动数据将与 Google 账号关联\n"
                "• 可在多设备间同步数据\n"
                "• 随时可以解绑恢复匿名\n\n"
                "是否继续？"
            ),
            ok="继续绑定",
            cancel="取消",
        )
        if resp != 1:
            return
        try:
            from sit_monitor.cloud.social_auth import start_google_oauth
            result = start_google_oauth(self._cloud_client)
            if result.get("success"):
                self.settings.auth_provider = "google"
                self.settings.save()
                try:
                    self.menu["🔐 Account"]["Auth: device"].title = "Auth: google"
                except Exception:
                    pass
                rumps.notification("Sit Monitor", "🔗 Google 账号已绑定", result.get("message", ""))
            elif result.get("url"):
                import webbrowser
                webbrowser.open(result["url"])
                rumps.notification("Sit Monitor", "🔗 请在浏览器中完成授权", "授权后将自动完成绑定")
            else:
                rumps.alert("绑定失败", result.get("error", "未知错误"))
        except Exception as e:
            rumps.alert("绑定错误", str(e))

    def _unlink_provider(self, _):
        """解绑社交账号"""
        if self.settings.auth_provider == "device":
            rumps.alert("Account", "当前已是匿名（设备）认证")
            return
        resp = rumps.alert(
            title="🔓 解绑社交账号",
            message=f"当前绑定: {self.settings.auth_provider}\n\n解绑后恢复匿名认证，历史数据保留。",
            ok="确认解绑",
            cancel="取消",
        )
        if resp == 1:
            self.settings.auth_provider = "device"
            self.settings.save()
            try:
                self.menu["🔐 Account"][f"Auth: google"].title = "Auth: device"
            except Exception:
                pass
            rumps.notification("Sit Monitor", "🔓 已解绑", "恢复匿名认证")

    def _check_achievements(self):
        """定时检查成就，解锁时发通知"""
        if not self._achievement_engine:
            return
        try:
            newly = self._achievement_engine.check_and_unlock()
            for a in newly:
                rumps.notification("Sit Monitor", f"🎉 成就解锁: {a.icon} {a.name}", a.description)
                # 上传到云端
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

        t = threading.Thread(target=auto_check, daemon=True)
        t.start()

    def _silent_check_update(self):
        """静默检查更新，有新版本时通知用户"""
        try:
            subprocess.run(["git", "fetch", "origin"], cwd=PROJECT_DIR,
                           capture_output=True, timeout=15)
            local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR,
                                   capture_output=True, text=True).stdout.strip()
            remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=PROJECT_DIR,
                                    capture_output=True, text=True).stdout.strip()
            if local != remote:
                log = subprocess.run(
                    ["git", "log", f"{local}..{remote}", "--oneline"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout.strip()
                rumps.notification("Sit Monitor", "有新版本可用",
                                   f"{log}\n点击菜单 Check for Updates 升级")
        except Exception:
            pass

    # --- Update ---

    def _check_update(self, _):
        def do_update():
            try:
                subprocess.run(["git", "fetch", "origin"], cwd=PROJECT_DIR,
                               capture_output=True, timeout=15)
                local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR,
                                       capture_output=True, text=True).stdout.strip()
                remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=PROJECT_DIR,
                                        capture_output=True, text=True).stdout.strip()

                if local == remote:
                    rumps.notification("Sit Monitor", "检查更新", "已是最新版本")
                    return

                subprocess.run(["git", "pull", "origin", "main"], cwd=PROJECT_DIR,
                               capture_output=True, timeout=30)

                diff = subprocess.run(
                    ["git", "diff", local, remote, "--name-only"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout
                if "requirements.txt" in diff:
                    python = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
                    req = os.path.join(PROJECT_DIR, "requirements.txt")
                    subprocess.run(["uv", "pip", "install", "--python", python, "-r", req],
                                   capture_output=True, timeout=60)

                log = subprocess.run(
                    ["git", "log", f"{local}..{remote}", "--oneline"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout.strip()

                rumps.notification("Sit Monitor", "更新完成，正在重启...",
                                   log or "已拉取最新代码")

                # 自动重启：停止监控后 re-exec
                self._stop_monitor()
                time.sleep(1)
                python = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
                script = os.path.join(PROJECT_DIR, "sit_monitor.py")
                args = [python, script, "--tray"]
                if self.debug:
                    args.append("--debug")
                # 启动新进程
                subprocess.Popen(args)
                # 退出当前进程
                rumps.quit_application()

            except Exception as e:
                rumps.notification("Sit Monitor", "更新失败", str(e))

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
            message=(
                f"版本: v{VERSION}\n"
                f"提交: {commit}\n\n"
                "使用 MacBook 摄像头检测坐姿，\n"
                "通过 MediaPipe Pose 实时分析\n"
                "肩膀倾斜、头部前倾、躯干弯曲。\n\n"
                f"GitHub: {REPO_URL}\n"
                f"作者: Benjia Zou"
            ),
            ok="好的",
        )

    # --- Quit / Run ---

    @rumps.clicked("Quit")
    def quit_app(self, _):
        self._stop_preview()
        self._stop_exercise()
        self._stop_monitor()
        self._stop_cloud()
        rumps.quit_application()

    def run(self):
        @rumps.timer(1)
        def auto_start(t):
            t.stop()
            self._start_monitor()
            try:
                self.menu["Start Monitoring"].title = "Stop Monitoring"
            except Exception:
                pass
            # 初始化云端功能
            self._init_cloud()

        # 每 0.5 秒在主线程更新 UI
        @rumps.timer(0.5)
        def ui_update(t):
            self._poll_ui_update(t)

        # 每 60 秒检查是否需要发送每日报告
        @rumps.timer(60)
        def daily_report_check(t):
            self._check_daily_report(t)

        # 每 30 分钟检查成就
        @rumps.timer(1800)
        def achievement_check(t):
            self._check_achievements()

        super().run()
