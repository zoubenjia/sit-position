"""系统托盘应用：rumps 菜单栏 + 状态更新"""

import os
import subprocess
import sys
import threading
import time

import rumps

from sit_monitor.core import PostureMonitor
from sit_monitor.exercise import EXERCISE_REGISTRY, ExerciseMonitor
from sit_monitor.report import daily_summary_text, weekly_report
from sit_monitor.settings import Settings

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
        self._exercise_monitor = None
        self._exercise_thread = None
        self._state = "stopped"
        self._details = {}
        self._last_daily_report_date = None
        self._build_menu()

    def _build_menu(self):
        s = self.settings
        self.menu = [
            rumps.MenuItem("Start Monitoring", callback=self._toggle_monitor),
            rumps.MenuItem("Pause Alerts 10min", callback=self._snooze),
            None,
            rumps.MenuItem("🏋️ Pushup Training", callback=self._toggle_pushup),
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

    # --- Exercise ---

    def _is_exercising(self):
        return self._exercise_monitor is not None and self._exercise_monitor.running

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
        analyzer_cls = EXERCISE_REGISTRY.get(exercise_id)
        if analyzer_cls is None:
            rumps.notification("Sit Monitor", "错误", f"未知运动: {exercise_id}")
            return

        analyzer = analyzer_cls()
        self._exercise_monitor = ExerciseMonitor(
            analyzer, camera=self.settings.camera, debug=self.debug,
        )
        if not self._exercise_monitor.check_model():
            rumps.notification("Sit Monitor", "错误", "未找到模型文件")
            self._exercise_monitor = None
            return

        sender.title = "⏹ Stop Pushup"

        def run_and_cleanup():
            self._exercise_monitor.run()
            # 训练结束后恢复菜单
            sender.title = "🏋️ Pushup Training"
            self._exercise_monitor = None
            self._exercise_thread = None
            # 训练结束通知
            reps = getattr(analyzer, 'rep_count', 0)
            rumps.notification("Sit Monitor", "训练结束", f"完成 {reps} 个{analyzer.exercise_name}")
            # 恢复坐姿监控
            if resume_posture_after:
                self._start_monitor()
                try:
                    self.menu["Start Monitoring"].title = "Stop Monitoring"
                except Exception:
                    pass

        self._exercise_thread = threading.Thread(target=run_and_cleanup, daemon=True)
        self._exercise_thread.start()

    def _stop_exercise(self):
        if self._exercise_monitor:
            self._exercise_monitor.stop()
            if self._exercise_thread:
                self._exercise_thread.join(timeout=10)
            self._exercise_monitor = None
            self._exercise_thread = None

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
        self._stop_exercise()
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

        # 每 60 秒检查是否需要发送每日报告
        @rumps.timer(60)
        def daily_report_check(t):
            self._check_daily_report(t)

        super().run()
