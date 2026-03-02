"""俯卧撑检测、计数、姿势纠正"""

import math
import time
from enum import Enum

import mediapipe as mp

from sit_monitor.exercise.base import ExerciseAnalyzer, RepPhase, RepResult

PoseLandmark = mp.tasks.vision.PoseLandmark

# 关键点索引
LEFT_SHOULDER = PoseLandmark.LEFT_SHOULDER
RIGHT_SHOULDER = PoseLandmark.RIGHT_SHOULDER
LEFT_ELBOW = PoseLandmark.LEFT_ELBOW
RIGHT_ELBOW = PoseLandmark.RIGHT_ELBOW
LEFT_WRIST = PoseLandmark.LEFT_WRIST
RIGHT_WRIST = PoseLandmark.RIGHT_WRIST
LEFT_HIP = PoseLandmark.LEFT_HIP
RIGHT_HIP = PoseLandmark.RIGHT_HIP
LEFT_KNEE = PoseLandmark.LEFT_KNEE
RIGHT_KNEE = PoseLandmark.RIGHT_KNEE
LEFT_ANKLE = PoseLandmark.LEFT_ANKLE
RIGHT_ANKLE = PoseLandmark.RIGHT_ANKLE
NOSE = PoseLandmark.NOSE

# 关键关节列表
_KEY_LANDMARKS = [
    LEFT_SHOULDER, RIGHT_SHOULDER,
    LEFT_ELBOW, RIGHT_ELBOW,
    LEFT_WRIST, RIGHT_WRIST,
    LEFT_HIP, RIGHT_HIP,
    LEFT_KNEE, RIGHT_KNEE,
    LEFT_ANKLE, RIGHT_ANKLE,
]

# 阈值（侧面地面摄像头，需要比理论值更宽松）
ELBOW_DOWN_THRESHOLD = 130  # 肘角低于此进入 DOWN（放宽，侧面检测不精确）
ELBOW_UP_THRESHOLD = 145    # 肘角高于此进入 UP（计数+1）
HIP_SAG_THRESHOLD = 0.06   # 臀部下沉阈值（放宽）
HIP_PIKE_THRESHOLD = -0.06  # 臀部翘起阈值（放宽）
ELBOW_SHALLOW_THRESHOLD = 100  # 下降不够深
HEAD_DROP_THRESHOLD = 0.15   # 头部下垂阈值（侧面拍容易误触发，放宽）
READY_BODY_ANGLE = 45       # 偏离水平面的角度阈值（0=水平，90=垂直）
READY_FRAMES_NEEDED = 5     # 就位确认需要连续帧数


class _PrepStep(Enum):
    """准备阶段"""
    SETUP = 0       # 初始摄像头/位置说明
    FIND = 1        # 寻找人体，确认全身可见
    STAND_OK = 2    # 站姿确认，提示趴下
    LIE_DOWN = 3    # 等待用户趴下
    FINAL = 4       # 最终位置检查（水平 + 手臂伸直）


def _angle_3p(a, b, c) -> float:
    """计算三点夹角（度），b 为顶点。"""
    ba = (a.x - b.x, a.y - b.y)
    bc = (c.x - b.x, c.y - b.y)
    dot = ba[0] * bc[0] + ba[1] * bc[1]
    mag_ba = math.sqrt(ba[0] ** 2 + ba[1] ** 2)
    mag_bc = math.sqrt(bc[0] ** 2 + bc[1] ** 2)
    if mag_ba * mag_bc < 1e-6:
        return 180.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_angle))


def _mid(p1, p2):
    """两点中点"""
    class _P:
        def __init__(self, x, y):
            self.x = x
            self.y = y
    return _P((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)


def _elbow_angle(landmarks) -> float:
    """计算肘关节角度，使用可见度更高的一侧。"""
    l_vis = min(landmarks[LEFT_SHOULDER].visibility,
                landmarks[LEFT_ELBOW].visibility,
                landmarks[LEFT_WRIST].visibility)
    r_vis = min(landmarks[RIGHT_SHOULDER].visibility,
                landmarks[RIGHT_ELBOW].visibility,
                landmarks[RIGHT_WRIST].visibility)
    if l_vis >= r_vis:
        return _angle_3p(landmarks[LEFT_SHOULDER], landmarks[LEFT_ELBOW], landmarks[LEFT_WRIST])
    return _angle_3p(landmarks[RIGHT_SHOULDER], landmarks[RIGHT_ELBOW], landmarks[RIGHT_WRIST])


def _hip_deviation(landmarks) -> float:
    """臀部偏离肩-踝连线的距离（正=下沉，负=翘起）。使用可见度更高的一侧。"""
    shoulder = _pick_side(landmarks, LEFT_SHOULDER, RIGHT_SHOULDER)
    hip = _pick_side(landmarks, LEFT_HIP, RIGHT_HIP)
    ankle = _pick_side(landmarks, LEFT_ANKLE, RIGHT_ANKLE)
    shoulder_mid = shoulder
    hip_mid = hip
    ankle_mid = ankle

    sa_x = ankle_mid.x - shoulder_mid.x
    sa_y = ankle_mid.y - shoulder_mid.y
    sa_len = math.sqrt(sa_x ** 2 + sa_y ** 2)
    if sa_len < 1e-6:
        return 0.0

    sh_x = hip_mid.x - shoulder_mid.x
    sh_y = hip_mid.y - shoulder_mid.y

    cross = sa_x * sh_y - sa_y * sh_x
    return cross / sa_len


def _pick_side(landmarks, idx_left, idx_right):
    """选择可见度更高的一侧关节（侧面拍摄时远侧不可靠）"""
    l, r = landmarks[idx_left], landmarks[idx_right]
    return l if l.visibility >= r.visibility else r


def _body_angle(landmarks) -> float:
    """身体偏离水平面的角度（度）。0=水平，90=垂直。

    使用可见度更高的一侧，避免侧面拍摄时远侧关节位置不准。
    """
    shoulder = _pick_side(landmarks, LEFT_SHOULDER, RIGHT_SHOULDER)
    ankle = _pick_side(landmarks, LEFT_ANKLE, RIGHT_ANKLE)
    dx = ankle.x - shoulder.x
    dy = ankle.y - shoulder.y
    raw = abs(math.degrees(math.atan2(dy, dx)))  # [0, 180]
    return raw if raw <= 90 else 180 - raw  # [0, 90]


class PushupAnalyzer(ExerciseAnalyzer):
    """俯卧撑分析器"""

    exercise_name = "俯卧撑"
    exercise_id = "pushup"

    def __init__(self, elbow_down=ELBOW_DOWN_THRESHOLD, elbow_up=ELBOW_UP_THRESHOLD,
                 hip_threshold=HIP_SAG_THRESHOLD, depth_threshold=ELBOW_SHALLOW_THRESHOLD):
        self.elbow_down = elbow_down
        self.elbow_up = elbow_up
        self.hip_sag = hip_threshold
        self.hip_pike = -hip_threshold
        self.depth_threshold = depth_threshold
        self.reset()

    def reset(self):
        self.phase = RepPhase.IDLE
        self.rep_count = 0
        self._ready_frames = 0
        self._min_elbow_in_rep = 180.0
        # 准备阶段状态
        self._prep_step = _PrepStep.SETUP
        self._prep_step_time = 0.0

    def on_position_ready(self):
        """准备阶段已确认位置，直接进入 READY 跳过 IDLE 检测。"""
        self.phase = RepPhase.READY
        self._min_elbow_in_rep = 180.0

    def _key_landmarks_visible(self, landmarks) -> bool:
        """检查关键关节是否可见（至少一侧完整可见即可，适配侧面拍摄）"""
        left_ok = all(
            landmarks[idx].visibility >= 0.5
            for idx in (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST, LEFT_HIP, LEFT_KNEE, LEFT_ANKLE)
        )
        right_ok = all(
            landmarks[idx].visibility >= 0.5
            for idx in (RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST, RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE)
        )
        return left_ok or right_ok

    def get_position_guidance(self, landmarks=None) -> str | None:
        """分步就位引导。landmarks=None 表示未检测到人体。

        场景：电脑放在地上，摄像头朝侧面。
        站着时摄像头只能看到下半身，趴下后才能看到全身。

        准备流程：
        SETUP    → 初始说明（电脑放地上、侧对、站好）
        FIND     → 检测到人体即可（站着只能看到腿）
        STAND_OK → 检测到人了，提示趴下
        LIE_DOWN → 等待用户趴下，观察身体逐渐变水平
        FINAL    → 全身可见 + 身体水平 + 手臂伸直 → 就绪
        """
        now = time.time()

        # Step 0: 初始说明
        if self._prep_step == _PrepStep.SETUP:
            self._prep_step = _PrepStep.FIND
            self._prep_step_time = now
            return (
                "请把电脑放在地上，打开屏幕，"
                "让摄像头对准你要趴下的位置。"
                "然后侧对摄像头，站在约两米远的地方"
            )

        # 未检测到人体
        if landmarks is None:
            return "请侧对摄像头，站到画面中"

        # Step 1: 只要检测到人体就行（站着时只看到腿很正常）
        if self._prep_step == _PrepStep.FIND:
            # 检测到人了，进入下一步
            self._prep_step = _PrepStep.STAND_OK
            self._prep_step_time = now
            return "检测到了！现在请趴下，双手撑地，准备俯卧撑"

        # Step 2: 提示趴下，给反应时间
        if self._prep_step == _PrepStep.STAND_OK:
            if now - self._prep_step_time > 3:
                self._prep_step = _PrepStep.LIE_DOWN
                self._prep_step_time = now
            return "请趴下，双手撑地，准备俯卧撑"

        body_ang = _body_angle(landmarks)  # 0=水平, 90=垂直
        visible = self._key_landmarks_visible(landmarks)

        # Step 3: 等待趴下 — 角度够低直接就绪
        if self._prep_step == _PrepStep.LIE_DOWN:
            if body_ang <= READY_BODY_ANGLE:
                return None  # 就绪！
            elif body_ang <= 60:
                return "快到了，身体再放平一些"
            else:
                return "请趴下，双手撑地，准备俯卧撑"

        return "请侧对摄像头站好"

    def analyze_frame(self, landmarks, frame_time: float) -> RepResult:
        """分析一帧，返回 RepResult"""
        feedbacks: list[tuple[str, str]] = []

        # 检查关键关节
        if not self._key_landmarks_visible(landmarks):
            self.phase = RepPhase.IDLE
            self._ready_frames = 0
            return RepResult(
                phase=self.phase,
                rep_count=self.rep_count,
                form_feedbacks=[],
                metrics={},
                is_in_position=False,
            )

        elbow = _elbow_angle(landmarks)
        hip_dev = _hip_deviation(landmarks)
        body_ang = _body_angle(landmarks)

        metrics = {
            "elbow": elbow,
            "hip_dev": hip_dev,
            "body_angle": body_ang,
        }

        # 站起来了 → 训练结束
        if body_ang > 60:
            self.phase = RepPhase.IDLE
            self._ready_frames = 0
            return RepResult(
                phase=self.phase,
                rep_count=self.rep_count,
                form_feedbacks=[("standing", "")],
                metrics=metrics,
                is_in_position=False,
            )

        # === 状态机 ===
        if self.phase == RepPhase.IDLE:
            if body_ang <= READY_BODY_ANGLE and elbow >= ELBOW_UP_THRESHOLD:
                self._ready_frames += 1
                if self._ready_frames >= READY_FRAMES_NEEDED:
                    self.phase = RepPhase.READY
                    self._min_elbow_in_rep = 180.0
            else:
                self._ready_frames = 0

        elif self.phase == RepPhase.READY or self.phase == RepPhase.UP:
            self._min_elbow_in_rep = min(self._min_elbow_in_rep, elbow)
            if elbow < self.elbow_down:
                self.phase = RepPhase.DOWN
                self._min_elbow_in_rep = min(self._min_elbow_in_rep, elbow)

        elif self.phase == RepPhase.DOWN:
            self._min_elbow_in_rep = min(self._min_elbow_in_rep, elbow)
            if elbow > self.elbow_up:
                self.rep_count += 1

                if self._min_elbow_in_rep > self.depth_threshold:
                    feedbacks.append(("shallow", "再低一点，手臂弯到九十度"))

                self.phase = RepPhase.UP
                self._min_elbow_in_rep = 180.0

        # === 姿势纠正（仅在 READY/UP/DOWN 阶段） ===
        if self.phase in (RepPhase.READY, RepPhase.UP, RepPhase.DOWN):
            if hip_dev > self.hip_sag:
                feedbacks.append(("hip_sag", "臀部太低了，收紧核心抬起来"))
            elif hip_dev < self.hip_pike:
                feedbacks.append(("hip_pike", "臀部太高了，身体保持一条直线"))

            nose = landmarks[NOSE]
            shoulder_mid = _mid(landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER])
            if nose.y - shoulder_mid.y > HEAD_DROP_THRESHOLD:
                feedbacks.append(("head_drop", "头不要低，眼睛看前方地面"))

        return RepResult(
            phase=self.phase,
            rep_count=self.rep_count,
            form_feedbacks=feedbacks,
            metrics=metrics,
            is_in_position=self.phase != RepPhase.IDLE,
        )
