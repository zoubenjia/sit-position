"""疲劳检测：基于 FaceMesh 的 EAR/MAR 计算 + 滑动窗口统计"""

import math
import time
from collections import deque

# FaceMesh 468 点中的关键索引
LEFT_EYE = [33, 160, 158, 133, 153, 144]   # 外角、上1、上2、内角、下2、下1
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
UPPER_LIP = 13
LOWER_LIP = 14
MOUTH_LEFT = 78
MOUTH_RIGHT = 308

# 头部姿态估算用的关键点
NOSE_TIP = 1
CHIN = 152
LEFT_EAR_TRAGION = 234
RIGHT_EAR_TRAGION = 454
FOREHEAD = 10


def _dist(a, b):
    """两个 landmark 之间的欧氏距离"""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def eye_aspect_ratio(landmarks, indices):
    """EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    indices: [外角, 上1, 上2, 内角, 下2, 下1]
    """
    p1 = landmarks[indices[0]]  # 外角
    p2 = landmarks[indices[1]]  # 上1
    p3 = landmarks[indices[2]]  # 上2
    p4 = landmarks[indices[3]]  # 内角
    p5 = landmarks[indices[4]]  # 下2
    p6 = landmarks[indices[5]]  # 下1

    v1 = _dist(p2, p6)  # 上1-下1 垂直距离
    v2 = _dist(p3, p5)  # 上2-下2 垂直距离
    h = _dist(p1, p4)   # 水平距离

    if h < 1e-6:
        return 0.3  # 避免除零，返回正常值
    return (v1 + v2) / (2.0 * h)


def mouth_aspect_ratio(landmarks):
    """MAR = |上唇-下唇| / |左嘴角-右嘴角|"""
    top = landmarks[UPPER_LIP]
    bottom = landmarks[LOWER_LIP]
    left = landmarks[MOUTH_LEFT]
    right = landmarks[MOUTH_RIGHT]

    vertical = _dist(top, bottom)
    horizontal = _dist(left, right)

    if horizontal < 1e-6:
        return 0.0
    return vertical / horizontal


def head_pitch(landmarks):
    """估算头部俯仰角（pitch）。
    用鼻尖到前额连线相对于鼻尖到下巴连线计算。
    返回角度（度）：负值 = 低头，正值 = 抬头。
    """
    nose = landmarks[NOSE_TIP]
    chin = landmarks[CHIN]
    forehead = landmarks[FOREHEAD]

    # 面部中线：前额 → 下巴
    face_dy = chin.y - forehead.y
    face_dz = chin.z - forehead.z

    if abs(face_dy) < 1e-6:
        return 0.0

    # pitch 角度：z 方向偏移 / y 方向长度
    # 头部下垂时下巴 z 更负（靠近摄像头），face_dz < 0，angle 为负
    angle_rad = math.atan2(face_dz, face_dy)
    return math.degrees(angle_rad)


class FatigueTracker:
    """滑动窗口统计 + 疲劳等级判定

    输出等级：
    - "normal": 正常
    - "tired": 疲劳（眨眼频率高 or 打哈欠多）
    - "very_tired": 非常疲劳（长时间闭眼 or 头部下垂）
    """

    def __init__(self, ear_threshold=0.2, mar_threshold=0.6):
        self.ear_threshold = ear_threshold
        self.mar_threshold = mar_threshold

        # 眨眼统计：60s 滑动窗口
        self._blink_times = deque()        # 每次眨眼的时间戳
        self._eye_closed = False           # 当前是否闭眼
        self._eye_closed_start = None      # 闭眼开始时间

        # 打哈欠统计：5min 滑动窗口
        self._yawn_times = deque()          # 每次哈欠的时间戳
        self._mouth_open = False            # 当前是否张嘴
        self._mouth_open_start = None       # 张嘴开始时间

        # 头部下垂
        self._head_droop_start = None       # 头部下垂开始时间

        # 当前状态
        self.level = "normal"
        self.blink_rate = 0.0     # 每分钟眨眼次数
        self.yawn_count = 0       # 5分钟内哈欠次数
        self.ear = 0.0            # 当前 EAR
        self.mar = 0.0            # 当前 MAR
        self.pitch = 0.0          # 当前 pitch

    def update(self, face_landmarks, now=None):
        """更新疲劳状态。

        face_landmarks: FaceMesh 结果中的 face_landmarks[0]（NormalizedLandmark 列表）
        now: 当前时间戳（秒），默认 time.time()
        返回: "normal" / "tired" / "very_tired"
        """
        if now is None:
            now = time.time()

        lm = face_landmarks

        # --- 计算指标 ---
        left_ear = eye_aspect_ratio(lm, LEFT_EYE)
        right_ear = eye_aspect_ratio(lm, RIGHT_EYE)
        self.ear = (left_ear + right_ear) / 2.0
        self.mar = mouth_aspect_ratio(lm)
        self.pitch = head_pitch(lm)

        is_very_tired = False
        is_tired = False

        # --- 眨眼检测 ---
        eye_closed = self.ear < self.ear_threshold

        if eye_closed:
            if not self._eye_closed:
                # 刚闭上眼
                self._eye_closed = True
                self._eye_closed_start = now
            else:
                # 持续闭眼：> 2s = very_tired
                if self._eye_closed_start and (now - self._eye_closed_start) > 2.0:
                    is_very_tired = True
        else:
            if self._eye_closed:
                # 睁开了，记录一次眨眼
                self._blink_times.append(now)
                self._eye_closed = False
                self._eye_closed_start = None

        # 清理 60s 窗口外的眨眼记录
        while self._blink_times and (now - self._blink_times[0]) > 60:
            self._blink_times.popleft()
        self.blink_rate = len(self._blink_times)  # 次/分钟

        if self.blink_rate > 25:
            is_tired = True

        # --- 打哈欠检测 ---
        mouth_open = self.mar > self.mar_threshold

        if mouth_open:
            if not self._mouth_open:
                self._mouth_open = True
                self._mouth_open_start = now
        else:
            if self._mouth_open:
                # 张嘴结束，检查是否持续 > 0.5s（算哈欠）
                if self._mouth_open_start and (now - self._mouth_open_start) >= 0.5:
                    self._yawn_times.append(now)
                self._mouth_open = False
                self._mouth_open_start = None

        # 清理 5min 窗口外的哈欠记录
        while self._yawn_times and (now - self._yawn_times[0]) > 300:
            self._yawn_times.popleft()
        self.yawn_count = len(self._yawn_times)

        if self.yawn_count >= 3:
            is_tired = True

        # --- 头部下垂检测 ---
        if self.pitch < -25:
            if self._head_droop_start is None:
                self._head_droop_start = now
            elif (now - self._head_droop_start) >= 3.0:
                is_very_tired = True
        else:
            self._head_droop_start = None

        # --- 综合判定 ---
        if is_very_tired:
            self.level = "very_tired"
        elif is_tired:
            self.level = "tired"
        else:
            self.level = "normal"

        return self.level

    def reset(self):
        """重置所有状态"""
        self._blink_times.clear()
        self._yawn_times.clear()
        self._eye_closed = False
        self._eye_closed_start = None
        self._mouth_open = False
        self._mouth_open_start = None
        self._head_droop_start = None
        self.level = "normal"
        self.blink_rate = 0.0
        self.yawn_count = 0
        self.ear = 0.0
        self.mar = 0.0
        self.pitch = 0.0
