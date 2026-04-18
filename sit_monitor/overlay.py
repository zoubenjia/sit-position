"""Always-on-top skeleton overlay — transparent on macOS, black background fallback."""

import signal
import sys
import threading
import time

import cv2
import mediapipe as mp_lib
import numpy as np

from sit_monitor.i18n import t
from sit_monitor.paths import model_path as _model_path
from sit_monitor.posture import evaluate_posture
from sit_monitor.settings import Settings

_CONNECTIONS = mp_lib.tasks.vision.PoseLandmarksConnections.POSE_LANDMARKS


def _create_landmarker():
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
    return mp_lib.tasks.vision.PoseLandmarker.create_from_options(options)


def run_overlay(camera: int = 0):
    """Launch the skeleton overlay window."""
    if sys.platform == "darwin":
        _run_overlay_macos(camera)
    else:
        _run_overlay_cv(camera)


# ---------------------------------------------------------------------------
# macOS: transparent borderless overlay (PyObjC)
# ---------------------------------------------------------------------------

def _run_overlay_macos(camera_idx: int):
    """Transparent floating skeleton lines, no window chrome, click-through."""
    import objc
    from AppKit import (
        NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor,
        NSScreen, NSView, NSWindow, NSWindowStyleMaskBorderless,
    )
    from Foundation import (
        NSDefaultRunLoopMode, NSMakePoint, NSMakeRect, NSObject,
        NSRunLoop, NSTimer,
    )
    import Quartz

    settings = Settings.load()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # Accessory — no dock icon

    screen = NSScreen.mainScreen()
    sf = screen.frame()
    sw, sh = int(sf.size.width), int(sf.size.height)

    WIN_W, WIN_H = 240, 180
    win_x = (sw - WIN_W) // 2
    win_y = sh - WIN_H - 60  # Cocoa y from bottom

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(win_x, win_y, WIN_W, WIN_H),
        NSWindowStyleMaskBorderless,
        NSBackingStoreBuffered,
        False,
    )
    window.setBackgroundColor_(NSColor.clearColor())
    window.setOpaque_(False)
    window.setHasShadow_(False)
    window.setLevel_(Quartz.kCGOverlayWindowLevel)
    window.setIgnoresMouseEvents_(True)
    window.setCollectionBehavior_(1 << 4)  # canJoinAllSpaces

    # Shared state — show_bad is the debounced display flag
    _lock = threading.Lock()
    _state = {"landmarks": None, "is_bad": False, "show_bad": False,
              "problems": [], "running": True}

    # Landmark indices for reference lines
    _LS = mp_lib.tasks.vision.PoseLandmark.LEFT_SHOULDER
    _RS = mp_lib.tasks.vision.PoseLandmark.RIGHT_SHOULDER
    _LE = mp_lib.tasks.vision.PoseLandmark.LEFT_EAR
    _RE = mp_lib.tasks.vision.PoseLandmark.RIGHT_EAR
    _LH = mp_lib.tasks.vision.PoseLandmark.LEFT_HIP
    _RH = mp_lib.tasks.vision.PoseLandmark.RIGHT_HIP

    class SkeletonView(NSView):
        def drawRect_(self, dirty_rect):
            NSColor.clearColor().set()
            NSBezierPath.fillRect_(self.bounds())

            with _lock:
                lm = _state["landmarks"]
                show_bad = _state["show_bad"]
                problems = list(_state["problems"])

            if lm is None or not show_bad:
                return

            vw = self.bounds().size.width
            vh = self.bounds().size.height
            color = NSColor.redColor()

            # --- Reference guide lines (drawn first, behind skeleton) ---
            ref_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                1, 1, 1, 0.25)  # faint white

            ls = lm[_LS]
            rs = lm[_RS]
            le = lm[_LE]
            re = lm[_RE]
            lh = lm[_LH]
            rh = lm[_RH]

            # 1) Shoulder level guide — horizontal line at avg shoulder height
            if ls.visibility >= 0.5 and rs.visibility >= 0.5:
                avg_sy = (1 - (ls.y + rs.y) / 2) * vh
                guide_color = (NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1, 0.5, 0, 0.6) if "shoulder" in problems else ref_color)
                self._draw_hline(guide_color, avg_sy, vw)

            # 2) Ear level guide — horizontal line at avg ear height
            if le.visibility >= 0.5 and re.visibility >= 0.5:
                avg_ey = (1 - (le.y + re.y) / 2) * vh
                guide_color = (NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1, 0.5, 0, 0.6) if "head_tilt" in problems else ref_color)
                self._draw_hline(guide_color, avg_ey, vw)

            # 3) Neck vertical guide — plumb line from ear down to shoulder
            #    Shows ideal: ear should be directly above shoulder
            if le.visibility >= 0.5 and ls.visibility >= 0.5:
                sx = ls.x * vw
                sy_top = (1 - le.y) * vh
                sy_bot = (1 - ls.y) * vh
                guide_color = (NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1, 0.5, 0, 0.6) if "neck" in problems else ref_color)
                self._draw_vline(guide_color, sx, sy_bot, sy_top)
            if re.visibility >= 0.5 and rs.visibility >= 0.5:
                sx = rs.x * vw
                sy_top = (1 - re.y) * vh
                sy_bot = (1 - rs.y) * vh
                guide_color = (NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1, 0.5, 0, 0.6) if "neck" in problems else ref_color)
                self._draw_vline(guide_color, sx, sy_bot, sy_top)

            # 4) Torso vertical guide — plumb line from shoulder down to hip
            #    Shows ideal: shoulder should be directly above hip
            if ls.visibility >= 0.5 and lh.visibility >= 0.5:
                hx = lh.x * vw
                sy_top = (1 - ls.y) * vh
                sy_bot = (1 - lh.y) * vh
                guide_color = (NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1, 0.5, 0, 0.6) if "torso" in problems else ref_color)
                self._draw_vline(guide_color, hx, sy_bot, sy_top)
            if rs.visibility >= 0.5 and rh.visibility >= 0.5:
                hx = rh.x * vw
                sy_top = (1 - rs.y) * vh
                sy_bot = (1 - rh.y) * vh
                guide_color = (NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1, 0.5, 0, 0.6) if "torso" in problems else ref_color)
                self._draw_vline(guide_color, hx, sy_bot, sy_top)

            # --- Skeleton lines ---
            color.set()
            for conn in _CONNECTIONS:
                s = lm[conn.start]
                e = lm[conn.end]
                if s.visibility >= 0.5 and e.visibility >= 0.5:
                    path = NSBezierPath.bezierPath()
                    path.setLineWidth_(2.0)
                    path.moveToPoint_(NSMakePoint(s.x * vw, (1 - s.y) * vh))
                    path.lineToPoint_(NSMakePoint(e.x * vw, (1 - e.y) * vh))
                    path.stroke()

            for landmark in lm:
                if landmark.visibility >= 0.5:
                    px = landmark.x * vw
                    py = (1 - landmark.y) * vh
                    NSBezierPath.bezierPathWithOvalInRect_(
                        NSMakeRect(px - 3, py - 3, 6, 6)
                    ).fill()

        def _draw_hline(self, color, y, width):
            """Draw a dashed horizontal reference line."""
            color.set()
            path = NSBezierPath.bezierPath()
            path.setLineWidth_(1.0)
            path.setLineDash_count_phase_([4, 4], 2, 0)
            path.moveToPoint_(NSMakePoint(0, y))
            path.lineToPoint_(NSMakePoint(width, y))
            path.stroke()

        def _draw_vline(self, color, x, y_from, y_to):
            """Draw a dashed vertical reference line."""
            color.set()
            path = NSBezierPath.bezierPath()
            path.setLineWidth_(1.0)
            path.setLineDash_count_phase_([4, 4], 2, 0)
            path.moveToPoint_(NSMakePoint(x, y_from))
            path.lineToPoint_(NSMakePoint(x, y_to))
            path.stroke()

    view = SkeletonView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, WIN_H))
    window.setContentView_(view)
    window.orderFrontRegardless()

    # Camera thread
    def camera_loop():
        landmarker = _create_landmarker()
        cap = cv2.VideoCapture(camera_idx)
        if not cap.isOpened():
            _state["running"] = False
            return
        bad_streak = 0       # consecutive bad frames
        last_bad_time = 0.0  # timestamp of last bad frame
        BAD_THRESHOLD = 3    # show after N consecutive bad frames
        GOOD_DELAY = 3.0     # keep showing for N seconds after turning good

        try:
            while _state["running"]:
                ret, frame = cap.read()
                if not ret:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp_lib.Image(image_format=mp_lib.ImageFormat.SRGB, data=rgb)
                results = landmarker.detect(mp_image)

                now = time.time()
                with _lock:
                    if results.pose_landmarks:
                        lm = results.pose_landmarks[0]
                        is_bad, _, _, ptypes = evaluate_posture(lm, settings.thresholds)
                        _state["landmarks"] = lm
                        _state["is_bad"] = is_bad
                        _state["problems"] = ptypes

                        if is_bad:
                            bad_streak += 1
                            last_bad_time = now
                        else:
                            bad_streak = 0

                        # Debounce: show after BAD_THRESHOLD consecutive bad frames,
                        # hide GOOD_DELAY seconds after last bad frame
                        _state["show_bad"] = (
                            bad_streak >= BAD_THRESHOLD
                            or (now - last_bad_time < GOOD_DELAY and last_bad_time > 0)
                        )
                    else:
                        _state["landmarks"] = None
                        _state["problems"] = []
                        bad_streak = 0
                time.sleep(0.03)
        finally:
            landmarker.close()
            cap.release()
            _state["running"] = False

    thread = threading.Thread(target=camera_loop, daemon=True)
    thread.start()

    # Refresh timer
    class Refresher(NSObject):
        def refresh_(self, timer):
            if not _state["running"]:
                app.terminate_(None)
                return
            view.setNeedsDisplay_(True)

    refresher = Refresher.alloc().init()
    timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
        0.033, refresher, "refresh:", None, True,
    )
    NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSDefaultRunLoopMode)

    # Handle SIGTERM from tray
    def on_signal(sig, _frame):
        _state["running"] = False

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    print(t("main.overlay_started"))
    app.run()
    _state["running"] = False


# ---------------------------------------------------------------------------
# Fallback: OpenCV black-background overlay (Windows / Linux)
# ---------------------------------------------------------------------------

def _run_overlay_cv(camera_idx: int):
    """Black background with skeleton lines — for platforms without PyObjC."""
    settings = Settings.load()
    landmarker = _create_landmarker()
    cap = cv2.VideoCapture(camera_idx)

    if not cap.isOpened():
        print(t("main.camera_error"))
        sys.exit(1)

    win_name = "Sit Monitor - Overlay"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(win_name, 240, 180)

    # Screen center-top
    try:
        if sys.platform == "win32":
            import ctypes
            sw = ctypes.windll.user32.GetSystemMetrics(0)
        else:
            sw = 1920
    except Exception:
        sw = 1920
    cv2.moveWindow(win_name, (sw - 240) // 2, 60)
    cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1.0)

    print(t("main.overlay_started"))

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp_lib.Image(image_format=mp_lib.ImageFormat.SRGB, data=rgb)
            results = landmarker.detect(mp_image)

            canvas = np.zeros((h, w, 3), dtype=np.uint8)

            if results.pose_landmarks:
                lm = results.pose_landmarks[0]
                is_bad, details, reasons, ptypes = evaluate_posture(lm, settings.thresholds)
                if not is_bad:
                    cv2.imshow(win_name, canvas)
                    if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
                        break
                    continue
                color = (0, 0, 255)
                ref_normal = (60, 60, 60)  # faint grey
                ref_warn = (0, 140, 255)   # orange (BGR)

                _ls = lm[mp_lib.tasks.vision.PoseLandmark.LEFT_SHOULDER]
                _rs = lm[mp_lib.tasks.vision.PoseLandmark.RIGHT_SHOULDER]
                _le = lm[mp_lib.tasks.vision.PoseLandmark.LEFT_EAR]
                _re = lm[mp_lib.tasks.vision.PoseLandmark.RIGHT_EAR]
                _lh = lm[mp_lib.tasks.vision.PoseLandmark.LEFT_HIP]
                _rh = lm[mp_lib.tasks.vision.PoseLandmark.RIGHT_HIP]

                # Reference: shoulder level
                if _ls.visibility >= 0.5 and _rs.visibility >= 0.5:
                    sy = int((_ls.y + _rs.y) / 2 * h)
                    rc = ref_warn if "shoulder" in ptypes else ref_normal
                    cv2.line(canvas, (0, sy), (w, sy), rc, 1, cv2.LINE_AA)
                # Reference: ear level
                if _le.visibility >= 0.5 and _re.visibility >= 0.5:
                    ey = int((_le.y + _re.y) / 2 * h)
                    rc = ref_warn if "head_tilt" in ptypes else ref_normal
                    cv2.line(canvas, (0, ey), (w, ey), rc, 1, cv2.LINE_AA)
                # Reference: neck vertical (shoulder x → up to ear)
                for ear, shoulder, tag in [(_le, _ls, "neck"), (_re, _rs, "neck")]:
                    if ear.visibility >= 0.5 and shoulder.visibility >= 0.5:
                        sx = int(shoulder.x * w)
                        rc = ref_warn if tag in ptypes else ref_normal
                        cv2.line(canvas, (sx, int(shoulder.y * h)),
                                 (sx, int(ear.y * h)), rc, 1, cv2.LINE_AA)
                # Reference: torso vertical (hip x → up to shoulder)
                for shoulder, hip, tag in [(_ls, _lh, "torso"), (_rs, _rh, "torso")]:
                    if shoulder.visibility >= 0.5 and hip.visibility >= 0.5:
                        hx = int(hip.x * w)
                        rc = ref_warn if tag in ptypes else ref_normal
                        cv2.line(canvas, (hx, int(hip.y * h)),
                                 (hx, int(shoulder.y * h)), rc, 1, cv2.LINE_AA)

                # Skeleton
                for conn in _CONNECTIONS:
                    s = lm[conn.start]
                    e = lm[conn.end]
                    if s.visibility >= 0.5 and e.visibility >= 0.5:
                        pt1 = (int(s.x * w), int(s.y * h))
                        pt2 = (int(e.x * w), int(e.y * h))
                        cv2.line(canvas, pt1, pt2, color, 2)
                for landmark in lm:
                    if landmark.visibility >= 0.5:
                        px = int(landmark.x * w)
                        py = int(landmark.y * h)
                        cv2.circle(canvas, (px, py), 4, color, -1)

            cv2.imshow(win_name, canvas)
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q") or key == 27:
                break
    finally:
        landmarker.close()
        cap.release()
        cv2.destroyAllWindows()
