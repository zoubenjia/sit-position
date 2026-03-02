"""PostureMonitor 核心引擎：摄像头循环、状态回调"""

import json
import logging
import os
import time
from datetime import datetime

import cv2
import mediapipe as mp

from sit_monitor.posture import evaluate_posture
from sit_monitor.stats import Stats
from sit_monitor.debug import draw_debug
from sit_monitor.platform import send_notification, media_play_pause
from sit_monitor.tts import speak

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(SCRIPT_DIR, "pose_landmarker_lite.task")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("posture")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join(LOG_DIR, "posture.jsonl"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def log_event(logger, event_type, **kwargs):
    record = {"ts": datetime.now().isoformat(), "event": event_type, **kwargs}
    logger.info(json.dumps(record, ensure_ascii=False))


class PostureMonitor:
    """核心监控引擎，可在主线程或后台线程运行。"""

    def __init__(self, settings, debug=False, on_state_change=None):
        """
        settings: Settings dataclass 实例
        debug: 是否显示 OpenCV 窗口
        on_state_change: 回调函数 (state, details) -> None
            state: "good" / "bad" / "away" / "camera_wait" / "stopped"
            details: dict with keys like shoulder, neck, torso, sit_minutes, reasons, etc.
        """
        self.settings = settings
        self.debug = debug
        self.on_state_change = on_state_change

        self.running = False
        self.snooze_until = 0  # 暂停提醒截止时间戳
        self.logger = setup_logging()
        self.stats = Stats()

    def _notify_state(self, state, **details):
        if self.on_state_change:
            try:
                self.on_state_change(state, details)
            except Exception:
                pass

    def check_model(self):
        if not os.path.exists(MODEL_PATH):
            return False
        return True

    def stop(self):
        self.running = False

    def run(self):
        """主监控循环。阻塞调用，直到 self.running = False。"""
        s = self.settings
        thresholds = s.thresholds
        log_event(self.logger, "start", thresholds=thresholds, sit_max_minutes=s.sit_max_minutes)

        # MediaPipe 初始化
        base_options = mp.tasks.BaseOptions(model_asset_path=MODEL_PATH)
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            num_poses=1,
        )
        landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)

        bad_start_time = None
        good_streak = 0  # 连续 good 帧计数，用于防抖
        last_notify_time = 0
        last_check_time = 0
        away_start_time = None
        media_paused = False
        sit_start_time = None
        last_sit_notify_time = 0
        cap = None
        camera_retry_interval = 5

        self.running = True

        try:
            while self.running:
                now = time.time()
                # 运行中实时读取设置（托盘可能已修改）
                thresholds = s.thresholds

                # --- 摄像头管理 ---
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    cap = cv2.VideoCapture(s.camera)
                    if not cap.isOpened():
                        cap.release()
                        cap = None
                        self._notify_state("camera_wait")
                        print(f"\r{'⏳ 摄像头被占用，等待释放...':<80}", end="", flush=True)
                        time.sleep(camera_retry_interval)
                        continue
                    print(f"\r{'📷 摄像头已连接，开始监控...':<80}", end="", flush=True)

                # 坏姿势时缩短检测间隔
                interval = 2.0 if bad_start_time is not None else s.interval
                wait = interval - (now - last_check_time)
                if wait > 0:
                    if self.debug:
                        cap.grab()
                        ret, frame = cap.retrieve()
                        if ret:
                            cv2.imshow("Sit Monitor (debug)", frame)
                            if cv2.waitKey(1) & 0xFF == ord("q"):
                                break
                        time.sleep(0.03)
                    else:
                        time.sleep(min(wait, 1.0))
                    continue

                last_check_time = now

                ret, frame = cap.read()
                if not ret:
                    cap.release()
                    cap = None
                    bad_start_time = None
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                results = landmarker.detect(mp_image)
                person_present = bool(results.pose_landmarks)

                # 是否使用 Notification Center（托盘模式下用横幅）
                use_nc = self.on_state_change is not None

                if not person_present:
                    bad_start_time = None
                    self.stats.record("away", now)

                    if away_start_time is not None and (now - away_start_time) >= 60:
                        sit_start_time = None

                    if s.auto_pause:
                        if away_start_time is None:
                            away_start_time = now
                        away_duration = now - away_start_time
                        if not media_paused and away_duration >= s.away_seconds:
                            media_play_pause(s.browser or None)
                            media_paused = True
                            status_line = f"⏸ 已暂停播放（离开 {away_duration:.0f}s）"
                        else:
                            status_line = f"未检测到人体 ({away_duration:.0f}s)"
                    else:
                        if away_start_time is None:
                            away_start_time = now
                        status_line = "未检测到人体"

                    self._notify_state("away")
                else:
                    if s.auto_pause and media_paused:
                        media_play_pause(s.browser or None)
                        media_paused = False
                    away_start_time = None

                    if sit_start_time is None:
                        sit_start_time = now
                    sit_minutes = (now - sit_start_time) / 60

                    sit_max_seconds = s.sit_max_minutes * 60
                    snoozed = now < self.snooze_until
                    if not snoozed and (now - sit_start_time) >= sit_max_seconds and (now - last_sit_notify_time) >= sit_max_seconds:
                        send_notification(
                            "久坐提醒",
                            f"你已经连续坐了 {sit_minutes:.0f} 分钟，起来活动一下、喝杯水吧！",
                            sound=s.sound,
                            use_notification_center=use_nc,
                        )
                        log_event(self.logger, "sit_alert", sit_minutes=round(sit_minutes, 1))
                        self.stats.sit_notifications_sent += 1
                        last_sit_notify_time = now

                    lm = results.pose_landmarks[0]
                    is_bad, details, reasons = evaluate_posture(lm, thresholds)

                    log_data = {k: round(v, 1) if v is not None else None for k, v in details.items()}
                    log_data["sit_minutes"] = round(sit_minutes, 1)
                    if is_bad:
                        self.stats.record("bad", now)
                        log_event(self.logger, "bad", reasons=[r for r in reasons], **log_data)
                    else:
                        self.stats.record("good", now)
                        log_event(self.logger, "good", **log_data)

                    # 防抖：需要连续 3 帧 good 才算真正恢复
                    GOOD_STREAK_REQUIRED = 3

                    if is_bad:
                        good_streak = 0
                        if bad_start_time is None:
                            bad_start_time = now
                        bad_duration = now - bad_start_time

                        if not snoozed and bad_duration >= s.bad_seconds and (now - last_notify_time) >= s.cooldown:
                            msg = "、".join(reasons)
                            if sit_minutes >= s.sit_max_minutes:
                                msg += f"\n（已连续就坐 {sit_minutes:.0f} 分钟，建议起来活动、喝杯水）"
                            send_notification(
                                "坐姿提醒",
                                f"请纠正姿势：{msg}",
                                sound=s.sound,
                                use_notification_center=use_nc,
                            )
                            log_event(self.logger, "posture_alert", reasons=[r for r in reasons],
                                      sit_minutes=round(sit_minutes, 1))
                            self.stats.notifications_sent += 1
                            last_notify_time = now
                            bad_start_time = now

                        status_line = (
                            f"⚠ 坏姿势 {bad_duration:.0f}s | 就坐 {sit_minutes:.0f}min | "
                            + " | ".join(f"{k}:{v:.1f}°" if v else f"{k}:N/A" for k, v in details.items())
                        )
                    else:
                        good_streak += 1
                        if good_streak >= GOOD_STREAK_REQUIRED and bad_start_time is not None:
                            # 真正恢复了，播报正向反馈（仅在坏姿势已触发过提醒后）
                            if s.sound and (now - bad_start_time) >= s.bad_seconds:
                                speak("坐姿很好，继续保持")
                            bad_start_time = None
                        status_line = (
                            f"✓ 姿势良好 | 就坐 {sit_minutes:.0f}min | "
                            + " | ".join(f"{k}:{v:.1f}°" if v else f"{k}:N/A" for k, v in details.items())
                        )

                    state = "bad" if is_bad else "good"
                    self._notify_state(state, details=details, reasons=reasons, sit_minutes=sit_minutes)

                    if self.debug:
                        draw_debug(frame, lm, is_bad, details)

                print(f"\r{status_line:<80}", end="", flush=True)

                if self.debug:
                    cv2.imshow("Sit Monitor (debug)", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

        finally:
            self.running = False
            self.stats.record(None, time.time())
            summary = self.stats.summary()
            log_event(self.logger, "stop",
                      total_checks=self.stats.total_checks,
                      good_count=self.stats.good_count,
                      bad_count=self.stats.bad_count,
                      good_minutes=round(self.stats.good_seconds_total / 60, 1),
                      bad_minutes=round(self.stats.bad_seconds_total / 60, 1),
                      notifications=self.stats.notifications_sent,
                      sit_notifications=self.stats.sit_notifications_sent)

            print("\n\n" + "=" * 40)
            print("📊 本次坐姿监控统计")
            print("=" * 40)
            print(summary)
            print("=" * 40)

            landmarker.close()
            if cap is not None:
                cap.release()
            if self.debug:
                cv2.destroyAllWindows()
            print("已退出。")
            self._notify_state("stopped")
