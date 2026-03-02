"""系统托盘应用：rumps 菜单栏 + 状态更新"""

import os
import threading

import rumps

from sit_monitor.core import PostureMonitor
from sit_monitor.settings import Settings

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
            None,  # separator
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
        ]
        self._update_stats_menu()

    def _set_icon(self, state):
        path = _ICON_FILES.get(state, _ICON_FILES["stopped"])
        if os.path.exists(path):
            self.icon = path
            self.title = None  # 用图标，不显示文字

    def _on_state_change(self, state, details):
        """监控引擎的状态回调（从后台线程调用）"""
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

    @rumps.clicked("Quit")
    def quit_app(self, _):
        self._stop_monitor()
        rumps.quit_application()

    def run(self):
        """启动托盘应用，自动开始监控"""
        @rumps.timer(1)
        def auto_start(t):
            t.stop()
            self._start_monitor()
            try:
                self.menu["Start Monitoring"].title = "Stop Monitoring"
            except Exception:
                pass

        super().run()
