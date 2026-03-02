"""系统托盘应用：rumps 菜单栏 + 状态更新"""

import os
import subprocess
import sys
import threading

import rumps

from sit_monitor.core import PostureMonitor
from sit_monitor.settings import Settings

VERSION = "1.0.0"
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
        self._state = "stopped"
        self._details = {}
        self._build_menu()

    def _build_menu(self):
        s = self.settings
        self.menu = [
            rumps.MenuItem("Start Monitoring", callback=self._toggle_monitor),
            None,
            rumps.MenuItem("Statistics", callback=None),
            [rumps.MenuItem("Stats"), [
                rumps.MenuItem("姿势良好: 0 min", callback=None),
                rumps.MenuItem("姿势不良: 0 min", callback=None),
                rumps.MenuItem("提醒次数: 0", callback=None),
            ]],
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
                rumps.MenuItem(
                    f"{'☑' if s.sound else '☐'} Sound",
                    callback=self._toggle_sound,
                ),
                rumps.MenuItem(
                    f"{'☑' if s.auto_pause else '☐'} Auto-pause",
                    callback=self._toggle_auto_pause,
                ),
            ]],
            None,
            rumps.MenuItem("Check for Updates", callback=self._check_update),
            rumps.MenuItem(f"About Sit Monitor v{VERSION}", callback=self._show_about),
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
        self._state = state
        self._details = details
        self._set_icon(state)
        self._update_stats_menu()

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

    # --- Settings ---

    def _adjust(self, attr, delta):
        val = getattr(self.settings, attr)
        new_val = max(1.0, val + delta)
        setattr(self.settings, attr, round(new_val, 1))
        self.settings.save()
        name = attr.replace("_threshold", "").capitalize()
        try:
            self.menu["Settings"][f"{name}: {val}°"].title = f"{name}: {new_val}°"
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

                # 拉取更新
                subprocess.run(["git", "pull", "origin", "main"], cwd=PROJECT_DIR,
                               capture_output=True, timeout=30)

                # 检查依赖变化
                diff = subprocess.run(
                    ["git", "diff", local, remote, "--name-only"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout
                if "requirements.txt" in diff:
                    python = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
                    req = os.path.join(PROJECT_DIR, "requirements.txt")
                    subprocess.run(["uv", "pip", "install", "--python", python, "-r", req],
                                   capture_output=True, timeout=60)

                # 获取更新说明
                log = subprocess.run(
                    ["git", "log", f"{local}..{remote}", "--oneline"],
                    cwd=PROJECT_DIR, capture_output=True, text=True,
                ).stdout.strip()

                rumps.notification("Sit Monitor", "更新完成，请重启",
                                   log or "已拉取最新代码")
            except Exception as e:
                rumps.notification("Sit Monitor", "更新失败", str(e))

        threading.Thread(target=do_update, daemon=True).start()

    # --- About ---

    def _show_about(self, _):
        # 获取当前 commit
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
        self._stop_monitor()
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

        super().run()
