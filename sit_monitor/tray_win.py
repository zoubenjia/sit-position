"""Windows 系统托盘应用：pystray + Pillow，镜像 tray.py 全部功能"""

import logging
import os
import subprocess
import sys
import threading
import time
from datetime import date, timedelta

import pystray
from PIL import Image

from sit_monitor.core import PostureMonitor
from sit_monitor.report import daily_summary_text, weekly_report
from sit_monitor.settings import Settings

log = logging.getLogger(__name__)

VERSION = "1.3.0"
REPO_URL = "https://github.com/zoubenjia/sit-position"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 动态图标生成
try:
    from sit_monitor.icon_gen import icon_image as _gen_icon_image
    _HAS_ICON_GEN = True
except ImportError:
    _HAS_ICON_GEN = False

# 静态图标路径（回退用）
_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
_ICON_FILES = {
    "good": os.path.join(_ASSETS, "icon_good_color.png"),
    "bad": os.path.join(_ASSETS, "icon_bad_color.png"),
    "away": os.path.join(_ASSETS, "icon_idle.png"),
    "camera_wait": os.path.join(_ASSETS, "icon_idle.png"),
    "stopped": os.path.join(_ASSETS, "icon_idle.png"),
}


_WIN_ICON_SIZE = (64, 64)

def _load_icon(state, problems=None):
    if _HAS_ICON_GEN:
        return _gen_icon_image(state, problems or [], size=64)
    path = _ICON_FILES.get(state, _ICON_FILES["stopped"])
    if os.path.exists(path):
        img = Image.open(path).resize(_WIN_ICON_SIZE, Image.LANCZOS)
        return img
    # 回退：生成纯色图标
    color = {"good": "green", "bad": "red"}.get(state, "gray")
    img = Image.new("RGB", _WIN_ICON_SIZE, color)
    return img


def _msgbox(title, message):
    """用 tkinter 弹出消息框（Windows 原生风格）"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except Exception:
        print(f"[{title}] {message}")


class TrayApp:
    def __init__(self, settings: Settings, debug=False):
        self.settings = settings
        self.debug = debug
        self.monitor = None
        self.monitor_thread = None
        self._exercise_proc = None
        self._state = "stopped"
        self._details = {}
        self._posture_hint = "— 未启动"
        self._auto_update_hours = 12
        self._icon = None
        # Cloud
        self._cloud_client = None
        self._sync_manager = None
        self._achievement_engine = None

    def _build_menu(self):
        s = self.settings
        return pystray.Menu(
            pystray.MenuItem(lambda item: self._posture_hint, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "Stop Monitoring" if self._is_running() else "Start Monitoring",
                self._toggle_monitor,
            ),
            pystray.MenuItem("Pause Alerts 10min", self._snooze),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "⏹ Stop Pushup" if self._is_exercising() else "🏋️ Pushup Training",
                self._toggle_pushup,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: self._stats_text(),
                None,
                enabled=False,
            ),
            pystray.MenuItem("View Report", self._view_report),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", pystray.Menu(
                pystray.MenuItem(
                    lambda item: f"Shoulder: {s.shoulder_threshold}°",
                    None,
                    enabled=False,
                ),
                pystray.MenuItem("  Shoulder +1", lambda: self._adjust("shoulder_threshold", 1)),
                pystray.MenuItem("  Shoulder -1", lambda: self._adjust("shoulder_threshold", -1)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    lambda item: f"Neck: {s.neck_threshold}°",
                    None,
                    enabled=False,
                ),
                pystray.MenuItem("  Neck +1", lambda: self._adjust("neck_threshold", 1)),
                pystray.MenuItem("  Neck -1", lambda: self._adjust("neck_threshold", -1)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    lambda item: f"Torso: {s.torso_threshold}°",
                    None,
                    enabled=False,
                ),
                pystray.MenuItem("  Torso +1", lambda: self._adjust("torso_threshold", 1)),
                pystray.MenuItem("  Torso -1", lambda: self._adjust("torso_threshold", -1)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    lambda item: f"Bad Seconds: {s.bad_seconds}s",
                    None,
                    enabled=False,
                ),
                pystray.MenuItem("  Bad Seconds +5", lambda: self._adjust("bad_seconds", 5)),
                pystray.MenuItem("  Bad Seconds -5", lambda: self._adjust("bad_seconds", -5)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    lambda item: f"{'☑' if s.sound else '☐'} Sound",
                    self._toggle_sound,
                ),
                pystray.MenuItem(
                    lambda item: f"{'☑' if s.auto_pause else '☐'} Auto-pause",
                    self._toggle_auto_pause,
                ),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🌐 Social", pystray.Menu(
                pystray.MenuItem("📊 Leaderboard (Today)", self._show_leaderboard_daily),
                pystray.MenuItem("📊 Leaderboard (Week)", self._show_leaderboard_weekly),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    lambda item: f"🏅 My Achievements ({self._achievement_engine.unlocked_count}/{self._achievement_engine.total_count})" if self._achievement_engine else "🏅 My Achievements (0/7)",
                    self._show_achievements,
                ),
                pystray.MenuItem("⚔️ Challenges", self._show_challenges),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("🔄 Sync Now", self._sync_now),
                pystray.MenuItem(
                    lambda item: f"Nickname: {self.settings.nickname}",
                    self._change_nickname,
                ),
                pystray.MenuItem(
                    lambda item: f"{'☑' if self.settings.share_posture else '☐'} Share Data",
                    self._toggle_share,
                ),
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: f"{'☑' if self.settings.cloud_enabled else '☐'} Enable Cloud",
                self._toggle_cloud,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Check for Updates", self._check_update),
            pystray.MenuItem(f"About v{VERSION}", self._show_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    # --- 状态文字 ---

    def _stats_text(self):
        stats = self.monitor.stats if self.monitor else None
        if stats:
            good_min = f"{stats.good_seconds_total / 60:.0f}"
            bad_min = f"{stats.bad_seconds_total / 60:.0f}"
            notif = stats.notifications_sent
        else:
            good_min, bad_min, notif = "0", "0", 0
        return f"良好 {good_min}min | 不良 {bad_min}min | 提醒 {notif}次"

    # --- 状态回调 ---

    def _on_state_change(self, state, details):
        self._state = state
        self._details = details
        problems = details.get("problems", [])
        self._update_icon(state, problems)
        self._update_posture_hint(state, details)

    def _update_icon(self, state, problems=None):
        if self._icon:
            self._icon.icon = _load_icon(state, problems)

    def _update_posture_hint(self, state, details):
        if state == "good":
            self._posture_hint = "✓ 姿势良好"
        elif state == "bad":
            reasons = details.get("reasons", [])
            if reasons:
                self._posture_hint = "⚠ " + "；".join(reasons)
            else:
                self._posture_hint = "⚠ 请纠正坐姿"
        elif state == "away":
            self._posture_hint = "— 未检测到人"
        elif state == "camera_wait":
            self._posture_hint = "⏳ 等待摄像头"
        elif state == "stopped":
            self._posture_hint = "— 未启动"
        # 刷新菜单
        if self._icon:
            self._icon.update_menu()

    # --- 监控控制 ---

    def _is_running(self):
        return self.monitor is not None and self.monitor.running

    def _toggle_monitor(self):
        if self._is_running():
            self._stop_monitor()
        else:
            self._start_monitor()

    def _start_monitor(self):
        if self._is_running():
            return
        self.monitor = PostureMonitor(
            self.settings,
            debug=self.debug,
            on_state_change=self._on_state_change,
        )
        if not self.monitor.check_model():
            _msgbox("Sit Monitor", "错误：未找到模型文件，请运行 setup.ps1")
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
        self._posture_hint = "— 未启动"
        self._update_icon("stopped")

    # --- Exercise ---

    def _is_exercising(self):
        return self._exercise_proc is not None and self._exercise_proc.poll() is None

    def _toggle_pushup(self):
        if self._is_exercising():
            self._stop_exercise()
        else:
            was_monitoring = self._is_running()
            if was_monitoring:
                self._stop_monitor()
            self._start_exercise("pushup", was_monitoring)

    def _start_exercise(self, exercise_id, resume_posture_after=False):
        python = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
        if not os.path.exists(python):
            python = sys.executable
        args = [python, "-m", "sit_monitor", exercise_id,
                "--camera", str(self.settings.camera), "--debug"]
        self._exercise_proc = subprocess.Popen(args, cwd=PROJECT_DIR)
        self._update_icon("exercise")

        def wait_and_cleanup():
            self._exercise_proc.wait()
            self._exercise_proc = None
            self._update_icon("stopped")
            from sit_monitor.platform_win import send_notification
            send_notification("Sit Monitor", "俯卧撑训练已完成")
            if resume_posture_after:
                self._start_monitor()

        threading.Thread(target=wait_and_cleanup, daemon=True).start()

    def _stop_exercise(self):
        if self._exercise_proc and self._exercise_proc.poll() is None:
            self._exercise_proc.terminate()
            try:
                self._exercise_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._exercise_proc.kill()
            self._exercise_proc = None
            self._update_icon("stopped")

    # --- Snooze ---

    def _snooze(self):
        if self.monitor:
            self.monitor.snooze_until = time.time() + 600
            from sit_monitor.platform_win import send_notification
            send_notification("Sit Monitor", "已暂停提醒，10 分钟内不会发送提醒")

    # --- Report ---

    def _view_report(self):
        text = weekly_report()
        _msgbox("Sit Monitor — 周报", text)

    # --- Settings ---

    def _adjust(self, attr, delta):
        val = getattr(self.settings, attr)
        new_val = max(1.0, val + delta)
        setattr(self.settings, attr, round(new_val, 1))
        self.settings.save()

    def _toggle_sound(self):
        self.settings.sound = not self.settings.sound
        self.settings.save()

    def _toggle_auto_pause(self):
        self.settings.auto_pause = not self.settings.auto_pause
        self.settings.save()

    # --- Cloud / Social ---

    def _init_cloud(self):
        if not self.settings.cloud_enabled:
            return
        try:
            from sit_monitor.cloud import AchievementEngine, CloudClient, SyncManager
            self.settings.ensure_device_id()
            self._cloud_client = CloudClient()
            self._sync_manager = SyncManager(self.settings, self._cloud_client)
            self._achievement_engine = AchievementEngine()
            self._sync_manager.start()
        except Exception as e:
            log.warning("Cloud init error: %s", e)

    def _stop_cloud(self):
        if self._sync_manager:
            self._sync_manager.stop()
            self._sync_manager = None
        if self._cloud_client:
            self._cloud_client.close()
            self._cloud_client = None

    def _toggle_cloud(self):
        self.settings.cloud_enabled = not self.settings.cloud_enabled
        self.settings.save()
        if self.settings.cloud_enabled:
            self._init_cloud()
        else:
            self._stop_cloud()

    def _show_leaderboard_daily(self):
        if not self._cloud_client:
            _msgbox("Social", "请先开启 Enable Cloud")
            return
        try:
            today = str(date.today())
            entries = self._cloud_client.leaderboard_daily(today)
            if not entries:
                _msgbox("📊 今日排行榜", "暂无数据")
                return
            lines = [f"{'#':>2}  {'昵称':<10}  {'良好率':>5}  {'时长':>5}  {'👍':>3}"]
            lines.append("-" * 40)
            for e in entries[:20]:
                lines.append(f"{e.rank:>2}  {e.nickname:<10}  {e.good_pct:>4}%  {e.total_minutes:>4.0f}m  {e.likes_count:>3}")
            _msgbox("📊 今日排行榜", "\n".join(lines))
        except Exception as e:
            _msgbox("排行榜错误", str(e))

    def _show_leaderboard_weekly(self):
        if not self._cloud_client:
            _msgbox("Social", "请先开启 Enable Cloud")
            return
        try:
            today = date.today()
            week_start = str(today - timedelta(days=today.weekday()))
            entries = self._cloud_client.leaderboard_weekly(week_start)
            if not entries:
                _msgbox("📊 本周排行榜", "暂无数据")
                return
            lines = [f"{'#':>2}  {'昵称':<10}  {'良好率':>5}  {'时长':>5}  {'👍':>3}"]
            lines.append("-" * 40)
            for e in entries[:20]:
                lines.append(f"{e.rank:>2}  {e.nickname:<10}  {e.good_pct:>4}%  {e.total_minutes:>4.0f}m  {e.likes_count:>3}")
            _msgbox("📊 本周排行榜", "\n".join(lines))
        except Exception as e:
            _msgbox("排行榜错误", str(e))

    def _show_achievements(self):
        if not self._achievement_engine:
            from sit_monitor.cloud.achievements import AchievementEngine
            self._achievement_engine = AchievementEngine()
        achs = self._achievement_engine.get_all_achievements()
        lines = []
        for a in achs:
            status = "✅" if a["unlocked"] else "🔒"
            lines.append(f"{status} {a['icon']} {a['name']}: {a['description']}")
        _msgbox(
            f"🏅 成就 ({self._achievement_engine.unlocked_count}/{self._achievement_engine.total_count})",
            "\n".join(lines),
        )

    def _show_challenges(self):
        if not self._cloud_client:
            _msgbox("Social", "请先开启 Enable Cloud")
            return
        try:
            challenges = self._cloud_client.list_my_challenges()
            if not challenges:
                _msgbox("⚔️ 挑战", "暂无挑战\n\n通过 MCP 工具 social_create_challenge 发起挑战")
                return
            lines = []
            for ch in challenges[:10]:
                status_icon = {"pending": "⏳", "active": "⚔️", "completed": "✅"}.get(ch.get("status"), "?")
                lines.append(
                    f"{status_icon} {ch.get('challenge_type','?')} "
                    f"目标:{ch.get('target_value',0)} "
                    f"发起方:{ch.get('creator_score',0):.0f} vs 接受方:{ch.get('opponent_score',0):.0f}"
                )
            _msgbox("⚔️ 挑战", "\n".join(lines))
        except Exception as e:
            _msgbox("挑战错误", str(e))

    def _sync_now(self):
        if not self._sync_manager:
            _msgbox("Social", "请先开启 Enable Cloud")
            return
        def do_sync():
            self._sync_manager.sync_once()
            from sit_monitor.platform_win import send_notification
            send_notification("Sit Monitor", "数据已上传到云端")
        threading.Thread(target=do_sync, daemon=True).start()

    def _change_nickname(self):
        # Windows 上用 tkinter 简易输入框
        try:
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            new_name = simpledialog.askstring("修改昵称", "输入新昵称（2-20 个字符）",
                                              initialvalue=self.settings.nickname, parent=root)
            root.destroy()
            if new_name and new_name.strip():
                new_name = new_name.strip()[:20]
                self.settings.nickname = new_name
                self.settings.save()
                if self._cloud_client:
                    threading.Thread(target=self._cloud_client.update_nickname, args=(new_name,), daemon=True).start()
        except Exception:
            pass

    def _toggle_share(self):
        self.settings.share_posture = not self.settings.share_posture
        self.settings.share_exercise = self.settings.share_posture
        self.settings.save()

    def _check_achievements(self):
        if not self._achievement_engine:
            return
        try:
            newly = self._achievement_engine.check_and_unlock()
            for a in newly:
                from sit_monitor.platform_win import send_notification
                send_notification("Sit Monitor", f"🎉 成就解锁: {a.icon} {a.name} — {a.description}")
                if self._cloud_client:
                    self._cloud_client.upload_achievement(a.id, self._achievement_engine._unlocked.get(a.id, ""))
        except Exception as e:
            log.warning("Achievement check error: %s", e)

    # --- Update ---

    def _check_update(self):
        def do_update():
            try:
                subprocess.run(["git", "fetch", "origin"], cwd=PROJECT_DIR,
                               capture_output=True, timeout=15)
                local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR,
                                       capture_output=True, text=True).stdout.strip()
                remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=PROJECT_DIR,
                                        capture_output=True, text=True).stdout.strip()

                if local == remote:
                    from sit_monitor.platform_win import send_notification
                    send_notification("Sit Monitor", "已是最新版本")
                    return

                subprocess.run(["git", "pull", "origin", "main"], cwd=PROJECT_DIR,
                               capture_output=True, timeout=30)

                diff = subprocess.run(
                    ["git", "diff", local, remote, "--name-only"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout
                if "requirements.txt" in diff:
                    python = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
                    req = os.path.join(PROJECT_DIR, "requirements.txt")
                    subprocess.run(["uv", "pip", "install", "--python", python, "-r", req],
                                   capture_output=True, timeout=60)

                log = subprocess.run(
                    ["git", "log", f"{local}..{remote}", "--oneline"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout.strip()

                from sit_monitor.platform_win import send_notification
                send_notification("Sit Monitor", f"更新完成，正在重启...\n{log or '已拉取最新代码'}")

                # 重启
                self._stop_monitor()
                time.sleep(1)
                pythonw = os.path.join(PROJECT_DIR, ".venv", "Scripts", "pythonw.exe")
                if not os.path.exists(pythonw):
                    pythonw = sys.executable
                subprocess.Popen([pythonw, "-m", "sit_monitor", "--tray"], cwd=PROJECT_DIR)
                self._quit()

            except Exception as e:
                from sit_monitor.platform_win import send_notification
                send_notification("Sit Monitor", f"更新失败: {e}")

        threading.Thread(target=do_update, daemon=True).start()

    def _start_auto_update_check(self):
        def auto_check():
            while True:
                time.sleep(self._auto_update_hours * 3600)
                self._silent_check_update()

        t = threading.Thread(target=auto_check, daemon=True)
        t.start()

    def _silent_check_update(self):
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
                from sit_monitor.platform_win import send_notification
                send_notification("Sit Monitor", f"有新版本可用\n{log}\n请点击 Check for Updates 升级")
        except Exception:
            pass

    # --- About ---

    def _show_about(self):
        try:
            commit = subprocess.run(
                ["git", "log", "--oneline", "-1"], cwd=PROJECT_DIR,
                capture_output=True, text=True,
            ).stdout.strip()
        except Exception:
            commit = "unknown"

        _msgbox("Sit Monitor", (
            f"版本: v{VERSION}\n"
            f"提交: {commit}\n\n"
            "使用摄像头检测坐姿，\n"
            "通过 MediaPipe Pose 实时分析\n"
            "肩膀倾斜、头部前倾、躯干弯曲。\n\n"
            f"GitHub: {REPO_URL}\n"
            f"作者: Benjia Zou"
        ))

    # --- Quit / Run ---

    def _quit(self):
        self._stop_exercise()
        self._stop_monitor()
        self._stop_cloud()
        if self._icon:
            self._icon.stop()

    def run(self):
        menu = self._build_menu()
        self._icon = pystray.Icon("Sit Monitor", _load_icon("stopped"), "Sit Monitor", menu)

        # setup 在后台线程运行，必须先设 visible=True 让图标显示
        def on_setup(icon):
            icon.visible = True
            self._start_monitor()
            self._start_auto_update_check()
            self._init_cloud()
            # 成就定时检查（30 分钟）
            def achievement_loop():
                while True:
                    time.sleep(1800)
                    self._check_achievements()
            threading.Thread(target=achievement_loop, daemon=True).start()

        self._icon.run(setup=on_setup)
