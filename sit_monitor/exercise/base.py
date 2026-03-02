"""运动分析基类 + ExerciseMonitor 主循环"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import NamedTuple

import cv2
import mediapipe as mp

from sit_monitor.exercise.voice_coach import VoiceCoach
from sit_monitor.i18n import t

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(SCRIPT_DIR, "pose_landmarker_lite.task")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")


class RepPhase(Enum):
    IDLE = "idle"
    READY = "ready"
    UP = "up"
    DOWN = "down"


class RepResult(NamedTuple):
    phase: RepPhase
    rep_count: int
    form_feedbacks: list[tuple[str, str]]  # [(category, message), ...]
    metrics: dict[str, float]
    is_in_position: bool


class ExerciseAnalyzer(ABC):
    """运动分析器抽象基类"""

    @property
    @abstractmethod
    def exercise_name(self) -> str:
        """运动名称（用于语音和显示）"""

    @property
    @abstractmethod
    def exercise_id(self) -> str:
        """运动标识（用于日志）"""

    @abstractmethod
    def reset(self):
        """重置状态"""

    @abstractmethod
    def analyze_frame(self, landmarks, frame_time: float) -> RepResult:
        """分析一帧，返回 RepResult"""

    @abstractmethod
    def get_position_guidance(self, landmarks=None) -> str | None:
        """就位引导。landmarks=None 表示未检测到人体。返回引导文本，None 表示位置就绪。"""

    def on_position_ready(self):
        """位置就绪后调用，子类可覆盖以跳过初始检测阶段。"""
        pass


def _setup_exercise_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("exercise")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(
            os.path.join(LOG_DIR, "exercise.jsonl"), encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def _log_event(logger, event_type: str, **kwargs):
    record = {"ts": datetime.now().isoformat(), "event": event_type, **kwargs}
    logger.info(json.dumps(record, ensure_ascii=False))


class ExerciseMonitor:
    """摄像头 -> MediaPipe -> 分析器 -> 语音教练"""

    def __init__(self, analyzer: ExerciseAnalyzer, camera: int = 0, debug: bool = False):
        self.analyzer = analyzer
        self.camera = camera
        self.debug = debug
        self.running = False
        self.coach = VoiceCoach()
        self.logger = _setup_exercise_logging()

    def check_model(self) -> bool:
        return os.path.exists(MODEL_PATH)

    def stop(self):
        self.running = False

    def run(self):
        """主循环：就位引导 -> 训练 -> 结束总结"""
        analyzer = self.analyzer
        coach = self.coach

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

        cap = cv2.VideoCapture(self.camera)
        if not cap.isOpened():
            print(t("exercise.camera_error"))
            return

        self.running = True
        analyzer.reset()
        start_time = time.time()
        form_error_counts: dict[str, int] = {}
        last_rep_count = 0

        _log_event(self.logger, "exercise_start", exercise=analyzer.exercise_id)

        try:
            # === 阶段一：就位引导 ===
            print(t("exercise.position_guide"))
            positioned = False
            last_guidance_text = ""

            # 获取初始说明（第一次调用，analyzer 会返回摆摄像头等指令）
            initial = analyzer.get_position_guidance(None)
            if initial:
                coach.say(initial, priority=0)
                print(f"\r📍 {initial:<60}", end="", flush=True)
                last_guidance_text = initial
                # 给用户 8 秒消化初始指令（需要放电脑、调屏幕角度、站位）
                wait_end = time.time() + 8
                while self.running and time.time() < wait_end:
                    if self.debug:
                        ret, frame = cap.read()
                        if ret:
                            cv2.imshow("Exercise (debug)", frame)
                            if cv2.waitKey(1) & 0xFF == ord("q"):
                                self.running = False
                                break
                    time.sleep(0.1)

            # 就位检测循环 — 全部交给 analyzer.get_position_guidance 控制
            last_guidance_time = 0.0
            GUIDANCE_REPEAT_INTERVAL = 10  # 同一句引导超过 10 秒重复播报

            while self.running and not positioned:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.1)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                results = landmarker.detect(mp_image)

                lm = results.pose_landmarks[0] if results.pose_landmarks else None
                guidance = analyzer.get_position_guidance(lm)

                if guidance is None:
                    positioned = True
                    analyzer.on_position_ready()
                    coach.say(t("exercise.position_ready_tts"), priority=0, interrupt=True)
                    print("\r" + t("exercise.position_ready") + " " * 40)
                else:
                    now = time.time()
                    status = f"📍 {guidance}"
                    # 新引导立即播报并打断旧语音，同一句引导每 10 秒重复
                    if guidance != last_guidance_text:
                        coach.say(guidance, priority=0, category="position", interrupt=True)
                        last_guidance_text = guidance
                        last_guidance_time = now
                    elif (now - last_guidance_time) >= GUIDANCE_REPEAT_INTERVAL:
                        coach.say(guidance, priority=0, category="position")
                        last_guidance_time = now
                    print(f"\r{status:<60}", end="", flush=True)

                if self.debug:
                    if results.pose_landmarks:
                        from sit_monitor.debug import draw_debug
                        draw_debug(frame, results.pose_landmarks[0], False, {})
                    cv2.imshow("Exercise (debug)", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self.running = False
                        break

                time.sleep(0.03)

            if not self.running:
                return

            # === 阶段二：训练 ===
            coach.clear()  # 清空准备阶段残留的语音队列
            coach.say(t("exercise.start_tts"), priority=0)
            print(t("exercise.training"))
            last_phase = None
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.03)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                results = landmarker.detect(mp_image)

                if not results.pose_landmarks:
                    print(f"\r{t('exercise.no_person'):>40}", end="", flush=True)
                    time.sleep(0.03)
                    continue

                lm = results.pose_landmarks[0]
                frame_time = time.time()
                result = analyzer.analyze_frame(lm, frame_time)

                # 站起来 → 训练结束
                if result.phase == RepPhase.IDLE and last_phase is not None and last_phase != RepPhase.IDLE:
                    any_standing = any(cat == "standing" for cat, _ in result.form_feedbacks)
                    if any_standing:
                        break
                last_phase = result.phase

                # 新的一次完成
                if result.rep_count > last_rep_count:
                    count = result.rep_count
                    count_words = t("exercise.count_words").split(",")
                    word = count_words[count - 1] if count <= len(count_words) else str(count)

                    if count % 10 == 0:
                        coach.say(t("exercise.count_great", word=word), priority=0, category="count")
                    elif count % 5 == 0:
                        coach.say(t("exercise.count_good", word=word), priority=0, category="count")
                    else:
                        coach.say(word, priority=0, category="count")

                    _log_event(
                        self.logger, "rep",
                        exercise=analyzer.exercise_id,
                        count=count,
                        metrics={k: round(v, 2) for k, v in result.metrics.items()},
                    )
                    last_rep_count = count

                # 姿势纠正
                for category, message in result.form_feedbacks:
                    coach.say(message, priority=1, category=category)
                    form_error_counts[category] = form_error_counts.get(category, 0) + 1

                # 状态显示
                phase_icon = {
                    RepPhase.IDLE: "⚪",
                    RepPhase.READY: "🟢",
                    RepPhase.UP: "🔼",
                    RepPhase.DOWN: "🔽",
                }
                metrics_str = " | ".join(f"{k}:{v:.1f}" for k, v in result.metrics.items())
                status = f"{phase_icon.get(result.phase, '?')} {result.phase.value} | {t('exercise.rep_count', count=result.rep_count)} | {metrics_str}"
                print(f"\r{status:<80}", end="", flush=True)

                if self.debug:
                    from sit_monitor.debug import draw_debug
                    draw_debug(frame, lm, False, {})
                    cv2.imshow("Exercise (debug)", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                time.sleep(0.03)

        finally:
            # === 阶段三：结束总结 ===
            self.running = False
            duration = time.time() - start_time
            total_reps = getattr(analyzer, 'rep_count', last_rep_count)

            _log_event(
                self.logger, "exercise_stop",
                exercise=analyzer.exercise_id,
                total_reps=total_reps,
                duration_seconds=round(duration),
                form_errors=form_error_counts,
            )

            summary_text = t("exercise.summary_tts", count=total_reps, name=analyzer.exercise_name)
            coach.say(summary_text, priority=0)

            print(f"\n\n{'=' * 40}")
            print(t("exercise.summary_title", name=analyzer.exercise_name))
            print(f"{'=' * 40}")
            print(t("exercise.summary_reps", count=total_reps))
            print(t("exercise.summary_duration", seconds=duration))
            if form_error_counts:
                print(t("exercise.summary_form"))
                for cat, cnt in form_error_counts.items():
                    print(t("exercise.summary_form_item", category=cat, count=cnt))
            print(f"{'=' * 40}")

            # 等待最后的语音播完
            time.sleep(3)
            coach.stop()

            landmarker.close()
            cap.release()
            if self.debug:
                cv2.destroyAllWindows()
            print(t("exercise.exited"))
