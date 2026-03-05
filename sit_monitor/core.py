"""PostureMonitor 核心引擎：摄像头循环、状态回调"""

import json
import logging
import os
import time
from datetime import datetime

import cv2
import mediapipe as mp

from sit_monitor.i18n import t
from sit_monitor.posture import evaluate_posture
from sit_monitor.stats import Stats
from sit_monitor.debug import draw_debug
from sit_monitor.platform import send_notification, media_play_pause, is_in_call
from sit_monitor.tts import speak

from sit_monitor.paths import model_path, face_model_path, log_dir

MODEL_PATH = model_path()
FACE_MODEL_PATH = face_model_path()
LOG_DIR = log_dir()


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

    @staticmethod
    def _detect_direction_hint(results):
        """根据部分可见的关键点分析人体偏移方向，返回方向提示文字或 None。

        当 MediaPipe 检测到了部分身体（pose_landmarks 非空）但肩膀可见度不够时，
        通过 NOSE 等高可见度关键点在画面中的归一化坐标判断偏移方向。
        """
        if not results.pose_landmarks:
            return None  # 完全没检测到，无法判断方向

        lm = results.pose_landmarks[0]
        # 选择可见度最高的关键点作为参考
        NOSE = mp.tasks.vision.PoseLandmark.NOSE
        LEFT_SHOULDER = mp.tasks.vision.PoseLandmark.LEFT_SHOULDER
        RIGHT_SHOULDER = mp.tasks.vision.PoseLandmark.RIGHT_SHOULDER

        ref = None
        best_vis = 0.3  # 最低可见度门槛
        for idx in [NOSE, LEFT_SHOULDER, RIGHT_SHOULDER]:
            pt = lm[idx]
            if pt.visibility > best_vis:
                best_vis = pt.visibility
                ref = pt

        if ref is None:
            return None

        hints = []
        # x: 0=画面左边, 1=画面右边  (镜像：画面左边对应人的右边)
        if ref.x < 0.2:
            hints.append(t("core.direction.right"))   # 人在画面左侧→请往右移
        elif ref.x > 0.8:
            hints.append(t("core.direction.left"))    # 人在画面右侧→请往左移

        # y: 0=画面上方, 1=画面下方
        if ref.y < 0.15:
            hints.append(t("core.direction.down"))    # 人在画面顶部→摄像头往下调
        elif ref.y > 0.85:
            hints.append(t("core.direction.up"))      # 人在画面底部→摄像头往上调

        if not hints:
            # 人在画面中央附近但肩膀可见度低→可能距离太远或角度不对
            hints.append(t("core.direction.closer"))

        sep = t("core.direction.sep")
        return sep.join(hints)

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

        # FaceLandmarker 初始化（疲劳检测）
        face_landmarker = None
        fatigue_tracker = None
        last_fatigue_notify_time = 0
        if s.fatigue_enabled and os.path.exists(FACE_MODEL_PATH):
            from sit_monitor.fatigue import FatigueTracker
            face_base = mp.tasks.BaseOptions(model_asset_path=FACE_MODEL_PATH)
            face_options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=face_base,
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                num_faces=1,
            )
            face_landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(face_options)
            fatigue_tracker = FatigueTracker(
                ear_threshold=s.ear_threshold,
                mar_threshold=s.mar_threshold,
            )

        bad_start_time = None
        good_streak = 0  # 连续 good 帧计数，用于防抖
        present_streak = 0  # 连续 person_present 帧计数，用于媒体恢复防抖
        last_notify_time = 0
        _say_proc = None  # 跟踪当前 say 进程，用于离开时停止语音
        last_check_time = 0
        away_start_time = None
        away_accum = 0  # 累计离开秒数（用于判断是否真正离开）
        last_away_check = None  # 上次处于 away 状态的时间
        no_person_adjust_notified = False   # 已发送"调整摄像头"提示
        no_person_preview_notified = False  # 已发送"打开显示摄像头"提示
        media_paused = False
        last_media_toggle_time = 0  # 媒体切换冷却
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
                        print(f"\r{t('core.camera_wait'):<80}", end="", flush=True)
                        time.sleep(camera_retry_interval)
                        continue
                    print(f"\r{t('core.camera_connected'):<80}", end="", flush=True)

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
                person_present = False
                if results.pose_landmarks:
                    _lm = results.pose_landmarks[0]
                    _ls_vis = _lm[mp.tasks.vision.PoseLandmark.LEFT_SHOULDER].visibility
                    _rs_vis = _lm[mp.tasks.vision.PoseLandmark.RIGHT_SHOULDER].visibility
                    person_present = _ls_vis >= 0.65 and _rs_vis >= 0.65

                # 是否使用 Notification Center（托盘模式下用横幅）
                use_nc = self.on_state_change is not None

                MEDIA_TOGGLE_COOLDOWN = 30  # 媒体切换至少间隔 30 秒
                PRESENT_STREAK_REQUIRED = 2  # 回来后连续检测到 2 次才恢复播放

                if not person_present:
                    # 区分：有部分身体检测到（摄像头角度问题） vs 完全没人
                    # 仅看 pose_landmarks 非空不够——人走后 MediaPipe 可能在背景上
                    # 产生低置信度的误检测，需要检查关键点的实际可见度
                    partial_detected = False
                    if results.pose_landmarks:
                        _lm = results.pose_landmarks[0]
                        _key_vis = max(
                            _lm[mp.tasks.vision.PoseLandmark.NOSE].visibility,
                            _lm[mp.tasks.vision.PoseLandmark.LEFT_SHOULDER].visibility,
                            _lm[mp.tasks.vision.PoseLandmark.RIGHT_SHOULDER].visibility,
                            _lm[mp.tasks.vision.PoseLandmark.LEFT_HIP].visibility,
                            _lm[mp.tasks.vision.PoseLandmark.RIGHT_HIP].visibility,
                        )
                        partial_detected = _key_vis >= 0.3

                    # 停止正在播放的提醒语音
                    if _say_proc and _say_proc.poll() is None:
                        _say_proc.terminate()
                        _say_proc = None
                    bad_start_time = None
                    present_streak = 0
                    self.stats.record("away", now)

                    if away_start_time is None:
                        away_start_time = now

                    # 累计离开时间（即使中间偶尔误检测到人也不会重置）
                    if last_away_check is not None:
                        away_accum += now - last_away_check
                    last_away_check = now

                    if (now - away_start_time) >= 60 or away_accum >= 60:
                        sit_start_time = None

                    away_duration = now - away_start_time

                    snoozed = now < self.snooze_until
                    if partial_detected:
                        # 摄像头角度不对：能看到部分身体但肩膀不够清晰
                        direction_hint = self._detect_direction_hint(results)

                        if not snoozed and not no_person_adjust_notified and away_duration >= 5:
                            if direction_hint:
                                msg = t("core.camera_adjust_direction_msg", direction=direction_hint)
                            else:
                                msg = t("core.camera_adjust_msg")
                            send_notification(
                                t("core.camera_adjust_title"),
                                msg,
                                sound=False,
                                use_notification_center=use_nc,
                                call_mute=False,
                            )
                            no_person_adjust_notified = True

                        status_line = t("core.camera_adjust_status", seconds=away_duration)
                        self._notify_state("camera_adjust", direction=direction_hint)
                    else:
                        # 真正没人：完全没有检测到任何身体
                        # 人走了不播语音——说了也听不到
                        if not snoozed and not no_person_preview_notified and away_duration >= 30:
                            send_notification(
                                t("core.no_person_preview_title"),
                                t("core.no_person_preview_msg"),
                                sound=False,
                                use_notification_center=use_nc,
                                call_mute=False,
                            )
                            no_person_preview_notified = True

                        if s.auto_pause:
                            if (not media_paused
                                    and away_duration >= s.away_seconds
                                    and (now - last_media_toggle_time) >= MEDIA_TOGGLE_COOLDOWN):
                                last_media_toggle_time = now
                                if media_play_pause(s.browser or None):
                                    media_paused = True
                            if media_paused:
                                status_line = t("core.media_paused", seconds=away_duration)
                            else:
                                status_line = t("core.no_person_away", seconds=away_duration)
                        else:
                            status_line = t("core.no_person_away", seconds=away_duration)

                        self._notify_state("away")
                else:
                    present_streak += 1
                    if (s.auto_pause and media_paused
                            and present_streak >= PRESENT_STREAK_REQUIRED
                            and (now - last_media_toggle_time) >= MEDIA_TOGGLE_COOLDOWN):
                        if media_play_pause(s.browser or None):
                            last_media_toggle_time = now
                        media_paused = False
                    # 从离开状态回来：重置 cooldown，让提醒立即生效
                    if away_start_time is not None and (now - away_start_time) >= s.away_seconds:
                        last_notify_time = 0
                        bad_start_time = None
                    # 只有连续在场超过 PRESENT_STREAK_REQUIRED 次才算真正回来
                    if present_streak >= PRESENT_STREAK_REQUIRED:
                        away_start_time = None
                        away_accum = 0
                        last_away_check = None
                        no_person_adjust_notified = False
                        no_person_preview_notified = False

                    if sit_start_time is None:
                        sit_start_time = now
                    sit_minutes = (now - sit_start_time) / 60

                    sit_max_seconds = s.sit_max_minutes * 60
                    snoozed = now < self.snooze_until
                    if not snoozed and (now - sit_start_time) >= sit_max_seconds and (now - last_sit_notify_time) >= sit_max_seconds:
                        _say_proc = send_notification(
                            t("core.sit_alert_title"),
                            t("core.sit_alert_msg", minutes=sit_minutes),
                            sound=s.sound,
                            use_notification_center=use_nc,
                            call_mute=s.call_mute,
                        )
                        log_event(self.logger, "sit_alert", sit_minutes=round(sit_minutes, 1))
                        self.stats.sit_notifications_sent += 1
                        last_sit_notify_time = now

                    lm = results.pose_landmarks[0]
                    is_bad, details, reasons = evaluate_posture(lm, thresholds)

                    # --- 疲劳检测 ---
                    fatigue_level = "normal"
                    if s.fatigue_enabled and face_landmarker and fatigue_tracker:
                        face_results = face_landmarker.detect(mp_image)
                        if face_results.face_landmarks:
                            fatigue_level = fatigue_tracker.update(
                                face_results.face_landmarks[0], now
                            )
                            # 疲劳提醒
                            if fatigue_level != "normal" and not snoozed and (now - last_fatigue_notify_time) >= s.fatigue_cooldown:
                                if fatigue_level == "very_tired":
                                    fatigue_msg = t("core.fatigue_very_tired")
                                else:
                                    fatigue_msg = t("core.fatigue_tired")
                                _say_proc = send_notification(
                                    t("core.fatigue_alert_title"),
                                    fatigue_msg,
                                    sound=s.sound,
                                    use_notification_center=use_nc,
                                    call_mute=s.call_mute,
                                )
                                log_event(self.logger, "fatigue_alert",
                                          level=fatigue_level,
                                          ear=round(fatigue_tracker.ear, 3),
                                          mar=round(fatigue_tracker.mar, 3),
                                          blink_rate=round(fatigue_tracker.blink_rate, 1),
                                          yawn_count=fatigue_tracker.yawn_count,
                                          pitch=round(fatigue_tracker.pitch, 1),
                                          sit_minutes=round(sit_minutes, 1))
                                last_fatigue_notify_time = now

                    log_data = {k: round(v, 1) if v is not None else None for k, v in details.items()}
                    log_data["sit_minutes"] = round(sit_minutes, 1)
                    if fatigue_level != "normal":
                        log_data["fatigue"] = fatigue_level
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
                                msg += t("core.sit_reminder_suffix", minutes=sit_minutes)
                            _say_proc = send_notification(
                                t("core.posture_alert_title"),
                                t("core.posture_alert_msg", msg=msg),
                                sound=s.sound,
                                use_notification_center=use_nc,
                                call_mute=s.call_mute,
                            )
                            log_event(self.logger, "posture_alert", reasons=[r for r in reasons],
                                      sit_minutes=round(sit_minutes, 1))
                            self.stats.notifications_sent += 1
                            last_notify_time = now
                            bad_start_time = now

                        status_line = (
                            t("core.bad_posture_status", duration=bad_duration, minutes=sit_minutes)
                            + " | ".join(f"{k}:{v:.1f}°" if v else f"{k}:N/A" for k, v in details.items())
                        )
                    else:
                        good_streak += 1
                        if good_streak >= GOOD_STREAK_REQUIRED and bad_start_time is not None:
                            # 真正恢复了，播报正向反馈（仅在坏姿势已触发过提醒后）
                            if s.sound and (now - bad_start_time) >= s.bad_seconds:
                                if not (s.call_mute and is_in_call()):
                                    speak(t("core.good_posture_tts"))
                            bad_start_time = None
                        status_line = (
                            t("core.good_posture_status", minutes=sit_minutes)
                            + " | ".join(f"{k}:{v:.1f}°" if v else f"{k}:N/A" for k, v in details.items())
                        )

                    state = "bad" if is_bad else "good"
                    fatigue_info = None
                    if fatigue_tracker and fatigue_level != "normal":
                        fatigue_info = {
                            "level": fatigue_level,
                            "ear": round(fatigue_tracker.ear, 3),
                            "mar": round(fatigue_tracker.mar, 3),
                            "blink_rate": round(fatigue_tracker.blink_rate, 1),
                            "yawn_count": fatigue_tracker.yawn_count,
                        }
                    self._notify_state(state, details=details, reasons=reasons,
                                       sit_minutes=sit_minutes, fatigue=fatigue_info)

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
            print(t("core.session_summary_title"))
            print("=" * 40)
            print(summary)
            print("=" * 40)

            landmarker.close()
            if face_landmarker:
                face_landmarker.close()
            if cap is not None:
                cap.release()
            if self.debug:
                cv2.destroyAllWindows()
            print(t("core.exited"))
            self._notify_state("stopped")
