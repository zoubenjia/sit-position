"""python -m sit_monitor 入口"""

import argparse
import signal
import sys


def parse_args():
    p = argparse.ArgumentParser(description="坐姿监控：检测不良坐姿并通知")
    p.add_argument("--camera", type=int, default=0, help="摄像头索引 (默认: 0)")
    p.add_argument("--interval", type=float, default=5.0, help="检测间隔/秒 (默认: 5.0)")
    p.add_argument("--bad-seconds", type=int, default=30, help="连续坏姿势多少秒后通知 (默认: 30)")
    p.add_argument("--cooldown", type=int, default=180, help="两次通知最小间隔/秒 (默认: 180)")
    p.add_argument("--debug", action="store_true", help="显示摄像头画面和骨架叠加")
    p.add_argument("--auto-pause", action="store_true", help="人离开时自动暂停视频，回来时恢复")
    p.add_argument("--away-seconds", type=float, default=3.0, help="离开多少秒后暂停 (默认: 3)")
    p.add_argument("--browser", type=str, default=None, help="浏览器名称 (默认: 自动检测)")
    p.add_argument("--shoulder-threshold", type=float, default=7.0, help="肩膀倾斜角阈值/度 (默认: 7)")
    p.add_argument("--neck-threshold", type=float, default=10.0, help="头部前倾角阈值/度 (默认: 10)")
    p.add_argument("--torso-threshold", type=float, default=5.0, help="躯干前倾角阈值/度 (默认: 5)")
    p.add_argument("--sit-max-minutes", type=int, default=45, help="连续就坐多少分钟后提醒休息 (默认: 45)")
    p.add_argument("--sound", action="store_true", help="启用语音播报提醒")
    p.add_argument("--tray", action="store_true", help="启用系统托盘模式")
    return p.parse_args()


def main():
    args = parse_args()

    from sit_monitor.settings import Settings
    settings = Settings.load()
    settings.apply_args(args)

    if args.tray:
        from sit_monitor.tray import TrayApp
        app = TrayApp(settings, debug=args.debug)
        app.run()
    else:
        from sit_monitor.core import PostureMonitor
        monitor = PostureMonitor(settings, debug=args.debug)

        if not monitor.check_model():
            print("错误: 未找到模型文件")
            print("请运行 bash setup.sh 或手动下载:")
            print("  curl -sSL -o pose_landmarker_lite.task \\")
            print("    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")
            sys.exit(1)

        def on_signal(sig, _frame):
            monitor.stop()

        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)

        monitor.run()


if __name__ == "__main__":
    main()
