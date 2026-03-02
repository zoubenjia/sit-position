"""系统托盘应用：pystray 菜单、状态更新"""

import threading

import pystray
from pystray import MenuItem as Item

from sit_monitor import icons
from sit_monitor.core import PostureMonitor
from sit_monitor.settings import Settings


class TrayApp:
    def __init__(self, settings: Settings, debug=False):
        self.settings = settings
        self.debug = debug
        self.monitor = None
        self.monitor_thread = None
        self._state = "stopped"  # good / bad / away / camera_wait / stopped
        self._details = {}
        self.icon = None

    def _on_state_change(self, state, details):
        """监控引擎的状态回调（从后台线程调用）"""
        self._state = state
        self._details = details
        self._update_icon()

    def _update_icon(self):
        if self.icon is None:
            return
        state = self._state
        if state == "good":
            self.icon.icon = icons.green()
        elif state == "bad":
            self.icon.icon = icons.red()
        else:
            self.icon.icon = icons.gray()

    def _is_running(self):
        return self.monitor is not None and self.monitor.running

    def _start_monitor(self, icon=None, item=None):
        if self._is_running():
            return
        self.monitor = PostureMonitor(
            self.settings,
            debug=self.debug,
            on_state_change=self._on_state_change,
        )
        if not self.monitor.check_model():
            print("错误: 未找到模型文件，请运行 bash setup.sh")
            return
        self.monitor_thread = threading.Thread(target=self.monitor.run, daemon=True)
        self.monitor_thread.start()

    def _stop_monitor(self, icon=None, item=None):
        if self.monitor:
            self.monitor.stop()
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)
            self.monitor = None
            self.monitor_thread = None
        self._state = "stopped"
        self._update_icon()

    def _toggle_monitor(self, icon, item):
        if self._is_running():
            self._stop_monitor()
        else:
            self._start_monitor()

    def _quit(self, icon, item):
        self._stop_monitor()
        icon.stop()

    # --- Settings 菜单回调 ---

    def _make_threshold_adjust(self, attr, delta):
        def callback(icon, item):
            val = getattr(self.settings, attr)
            new_val = max(1.0, val + delta)
            setattr(self.settings, attr, round(new_val, 1))
            self.settings.save()
        return callback

    def _toggle_sound(self, icon, item):
        self.settings.sound = not self.settings.sound
        self.settings.save()

    def _toggle_auto_pause(self, icon, item):
        self.settings.auto_pause = not self.settings.auto_pause
        self.settings.save()

    # --- 菜单构建 ---

    def _build_menu(self):
        s = self.settings
        stats = self.monitor.stats if self.monitor else None

        good_min = f"{stats.good_seconds_total / 60:.0f}" if stats else "0"
        bad_min = f"{stats.bad_seconds_total / 60:.0f}" if stats else "0"
        notif_count = stats.notifications_sent if stats else 0

        return pystray.Menu(
            Item(
                lambda text: "Stop Monitoring" if self._is_running() else "Start Monitoring",
                self._toggle_monitor,
            ),
            Item("─────────", None, enabled=False),
            Item("Statistics", pystray.Menu(
                Item(f"姿势良好: {good_min} min", None, enabled=False),
                Item(f"姿势不良: {bad_min} min", None, enabled=False),
                Item(f"提醒次数: {notif_count}", None, enabled=False),
            )),
            Item("Settings", pystray.Menu(
                Item("Thresholds", pystray.Menu(
                    Item(f"Shoulder: {s.shoulder_threshold}°", None, enabled=False),
                    Item("  Shoulder +1", self._make_threshold_adjust("shoulder_threshold", 1.0)),
                    Item("  Shoulder -1", self._make_threshold_adjust("shoulder_threshold", -1.0)),
                    Item(f"Neck: {s.neck_threshold}°", None, enabled=False),
                    Item("  Neck +1", self._make_threshold_adjust("neck_threshold", 1.0)),
                    Item("  Neck -1", self._make_threshold_adjust("neck_threshold", -1.0)),
                    Item(f"Torso: {s.torso_threshold}°", None, enabled=False),
                    Item("  Torso +1", self._make_threshold_adjust("torso_threshold", 1.0)),
                    Item("  Torso -1", self._make_threshold_adjust("torso_threshold", -1.0)),
                )),
                Item(
                    lambda text: f"{'☑' if s.sound else '☐'} Sound",
                    self._toggle_sound,
                ),
                Item(
                    lambda text: f"{'☑' if s.auto_pause else '☐'} Auto-pause",
                    self._toggle_auto_pause,
                ),
            )),
            Item("─────────", None, enabled=False),
            Item("Quit", self._quit),
        )

    def run(self):
        """启动托盘应用（阻塞，必须在主线程调用）"""
        self.icon = pystray.Icon(
            "sit-monitor",
            icon=icons.gray(),
            title="Sit Monitor",
            menu=self._build_menu(),
        )
        # 自动启动监控
        self.icon.run(setup=lambda icon: self._start_monitor())
