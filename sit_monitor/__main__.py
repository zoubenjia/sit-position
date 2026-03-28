"""python -m sit_monitor 入口"""

import argparse
import os
import signal
import sys

from sit_monitor.i18n import t


def parse_args():
    p = argparse.ArgumentParser(description="坐姿监控 & 运动指导")
    p.add_argument("mode", nargs="?", default="posture",
                   choices=["posture", "pushup", "preview", "overlay"],
                   help="运行模式: posture=坐姿监控(默认), pushup=俯卧撑训练, preview=摄像头预览, overlay=骨骼线叠加")
    p.add_argument("--camera", type=int, default=0, help="摄像头索引 (默认: 0)")
    p.add_argument("--interval", type=float, default=5.0, help="检测间隔/秒 (默认: 5.0)")
    p.add_argument("--bad-seconds", type=int, default=30, help="连续坏姿势多少秒后通知 (默认: 30)")
    p.add_argument("--cooldown", type=int, default=180, help="两次通知最小间隔/秒 (默认: 180)")
    p.add_argument("--debug", action="store_true", help="显示摄像头画面和骨架叠加")
    p.add_argument("--auto-pause", action="store_true", help="人离开时自动暂停视频，回来时恢复")
    p.add_argument("--away-seconds", type=float, default=3.0, help="离开多少秒后暂停 (默认: 3)")
    p.add_argument("--browser", type=str, default=None, help="浏览器名称 (默认: 自动检测)")
    p.add_argument("--shoulder-threshold", type=float, default=10.0, help="肩膀倾斜角阈值/度 (默认: 10)")
    p.add_argument("--neck-threshold", type=float, default=20.0, help="头部前倾角阈值/度 (默认: 20)")
    p.add_argument("--torso-threshold", type=float, default=8.0, help="躯干前倾角阈值/度 (默认: 8)")
    p.add_argument("--sit-max-minutes", type=int, default=45, help="连续就坐多少分钟后提醒休息 (默认: 45)")
    p.add_argument("--sound", action="store_true", help="启用语音播报提醒")
    p.add_argument("--tray", action="store_true",
                   default=(sys.platform in ("darwin", "win32")),
                   help="启用系统托盘模式 (macOS/Windows 默认开启)")
    p.add_argument("--no-tray", action="store_true", help="禁用系统托盘，使用纯 CLI 模式")
    # 俯卧撑参数
    p.add_argument("--elbow-down", type=float, default=130, help="肘角低于此进入下降阶段/度 (默认: 130)")
    p.add_argument("--elbow-up", type=float, default=145, help="肘角高于此计为一次/度 (默认: 145)")
    p.add_argument("--hip-threshold", type=float, default=0.06, help="臀部偏离阈值 (默认: 0.06)")
    p.add_argument("--depth-threshold", type=float, default=100, help="下降不够深警告阈值/度 (默认: 100)")
    return p.parse_args()


def _run_posture(args):
    """坐姿监控模式"""
    from sit_monitor.settings import Settings
    settings = Settings.load()
    settings.apply_args(args)

    if args.tray:
        if sys.platform == "darwin":
            from sit_monitor.tray import TrayApp
        elif sys.platform == "win32":
            from sit_monitor.tray_win import TrayApp
        else:
            print(t("main.unsupported_platform", platform=sys.platform))
            sys.exit(1)
        app = TrayApp(settings, debug=args.debug)
        app.run()
    else:
        from sit_monitor.core import PostureMonitor
        monitor = PostureMonitor(settings, debug=args.debug)

        if not monitor.check_model():
            print(t("main.model_not_found"))
            print(t("main.model_download_hint"))
            print("  curl -sSL -o pose_landmarker_lite.task \\")
            print("    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")
            sys.exit(1)

        def on_signal(sig, _frame):
            monitor.stop()

        signal.signal(signal.SIGINT, on_signal)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, on_signal)

        monitor.run()


def _run_exercise(args):
    """运动训练模式"""
    from sit_monitor.exercise import EXERCISE_REGISTRY, ExerciseMonitor

    analyzer_cls = EXERCISE_REGISTRY.get(args.mode)
    if analyzer_cls is None:
        print(t("main.unknown_exercise", mode=args.mode))
        sys.exit(1)

    # 传递可配置的阈值
    if args.mode == "pushup":
        analyzer = analyzer_cls(
            elbow_down=args.elbow_down,
            elbow_up=args.elbow_up,
            hip_threshold=args.hip_threshold,
            depth_threshold=args.depth_threshold,
        )
    else:
        analyzer = analyzer_cls()
    monitor = ExerciseMonitor(analyzer, camera=args.camera, debug=args.debug)

    if not monitor.check_model():
        print(t("main.model_not_found"))
        print(t("main.model_download_hint"))
        print("  curl -sSL -o pose_landmarker_lite.task \\")
        print("    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")
        sys.exit(1)

    def on_signal(sig, _frame):
        monitor.stop()

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)

    monitor.run()


def _run_preview(args):
    """摄像头预览模式：显示骨架叠加和姿势角度，不做监控提醒"""
    import cv2
    import mediapipe as mp_lib

    from sit_monitor.debug import draw_debug
    from sit_monitor.posture import evaluate_posture
    from sit_monitor.settings import Settings

    settings = Settings.load()
    from sit_monitor.paths import model_path as _model_path
    model_path = _model_path()

    base_options = mp_lib.tasks.BaseOptions(model_asset_path=model_path)
    options = mp_lib.tasks.vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_lib.tasks.vision.RunningMode.IMAGE,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        num_poses=1,
    )
    landmarker = mp_lib.tasks.vision.PoseLandmarker.create_from_options(options)
    cap = cv2.VideoCapture(args.camera)

    if not cap.isOpened():
        print(t("main.camera_error"))
        sys.exit(1)

    print(t("main.preview_started"))
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp_lib.Image(image_format=mp_lib.ImageFormat.SRGB, data=rgb)
        results = landmarker.detect(mp_image)

        if results.pose_landmarks:
            lm = results.pose_landmarks[0]
            # 显示肩膀可见度（方便调试离开检测）
            ls_vis = lm[mp_lib.tasks.vision.PoseLandmark.LEFT_SHOULDER].visibility
            rs_vis = lm[mp_lib.tasks.vision.PoseLandmark.RIGHT_SHOULDER].visibility
            is_bad, details, reasons, _ptypes = evaluate_posture(lm, settings.thresholds)
            draw_debug(frame, lm, is_bad, details)
            h = frame.shape[0]
            cv2.putText(frame, f"L_shoulder vis: {ls_vis:.2f}  R_shoulder vis: {rs_vis:.2f}",
                        (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 0), 1)
        else:
            cv2.putText(frame, "No person detected", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

        cv2.imshow("Sit Monitor - Preview (press q to quit)", frame)
        if cv2.waitKey(30) & 0xFF == ord("q"):
            break

    landmarker.close()
    cap.release()
    cv2.destroyAllWindows()


def _acquire_lock():
    """确保只有一个 sit_monitor 实例运行（posture 模式）。

    使用 fcntl 文件锁，进程退出后自动释放。
    """
    import fcntl
    import tempfile

    lock_path = os.path.join(tempfile.gettempdir(), "sit_monitor.lock")
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("sit_monitor 已在运行，退出。")
        sys.exit(0)
    # 保持 lock_file 打开，进程退出时自动释放
    return lock_file


def main():
    from sit_monitor.paths import is_bundled
    args = parse_args()
    if is_bundled():
        args.tray = True
    if args.no_tray:
        args.tray = False

    if args.mode == "posture":
        _lock = _acquire_lock()  # noqa: F841
        _run_posture(args)
    elif args.mode == "preview":
        _run_preview(args)
    elif args.mode == "overlay":
        from sit_monitor.overlay import run_overlay
        run_overlay(camera=args.camera)
    else:
        _run_exercise(args)


if __name__ == "__main__":
    main()
