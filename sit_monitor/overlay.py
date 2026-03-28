"""Always-on-top skeleton overlay window."""

import sys
import cv2
import mediapipe as mp_lib

from sit_monitor.debug import draw_debug
from sit_monitor.i18n import t
from sit_monitor.paths import model_path as _model_path
from sit_monitor.posture import evaluate_posture
from sit_monitor.settings import Settings

# Default overlay size
_WIDTH = 240
_HEIGHT = 180


def _screen_size():
    """Return (width, height) of the primary display."""
    if sys.platform == "darwin":
        try:
            from AppKit import NSScreen
            frame = NSScreen.mainScreen().frame()
            return int(frame.size.width), int(frame.size.height)
        except Exception:
            pass
    elif sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except Exception:
            pass
    return 1920, 1080  # fallback


def run_overlay(camera: int = 0):
    """Launch the skeleton overlay window."""
    settings = Settings.load()
    model = _model_path()

    base_options = mp_lib.tasks.BaseOptions(model_asset_path=model)
    options = mp_lib.tasks.vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_lib.tasks.vision.RunningMode.IMAGE,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        num_poses=1,
    )
    landmarker = mp_lib.tasks.vision.PoseLandmarker.create_from_options(options)
    cap = cv2.VideoCapture(camera)

    if not cap.isOpened():
        print(t("main.camera_error"))
        sys.exit(1)

    win_name = "Sit Monitor - Overlay"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(win_name, _WIDTH, _HEIGHT)

    # Position: horizontally centered, near top
    sw, _sh = _screen_size()
    cv2.moveWindow(win_name, (sw - _WIDTH) // 2, 60)

    # Always on top
    cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1.0)

    print(t("main.overlay_started"))

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp_lib.Image(image_format=mp_lib.ImageFormat.SRGB, data=rgb)
            results = landmarker.detect(mp_image)

            if results.pose_landmarks:
                lm = results.pose_landmarks[0]
                is_bad, details, reasons, _ptypes = evaluate_posture(lm, settings.thresholds)
                draw_debug(frame, lm, is_bad, details)
            else:
                cv2.putText(frame, "No person", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

            cv2.imshow(win_name, frame)
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q") or key == 27:  # q or ESC
                break
    finally:
        landmarker.close()
        cap.release()
        cv2.destroyAllWindows()
