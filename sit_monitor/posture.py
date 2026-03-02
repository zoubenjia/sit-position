"""角度计算与坐姿判定"""

import math

import mediapipe as mp
import numpy as np

# 关键点索引
PoseLandmark = mp.tasks.vision.PoseLandmark
LEFT_EAR = PoseLandmark.LEFT_EAR
RIGHT_EAR = PoseLandmark.RIGHT_EAR
LEFT_SHOULDER = PoseLandmark.LEFT_SHOULDER
RIGHT_SHOULDER = PoseLandmark.RIGHT_SHOULDER
LEFT_HIP = PoseLandmark.LEFT_HIP
RIGHT_HIP = PoseLandmark.RIGHT_HIP


def angle_deg(dx, dy):
    """计算向量 (dx, dy) 与垂直向上方向的夹角（度）"""
    return abs(math.degrees(math.atan2(dx, -dy)))


def shoulder_tilt(landmarks):
    """肩膀倾斜角：偏离水平的度数。

    正值=左肩高右肩低，负值=右肩高左肩低。
    （图像坐标 y 向下，ls.y < rs.y 表示左肩物理位置更高）
    """
    ls = landmarks[LEFT_SHOULDER]
    rs = landmarks[RIGHT_SHOULDER]
    if ls.visibility < 0.5 or rs.visibility < 0.5:
        return None
    dy = rs.y - ls.y  # 正值=左肩高
    dx = abs(rs.x - ls.x)  # 水平距离，取绝对值避免角度绕圈
    if dx < 0.001:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


def head_tilt(landmarks):
    """头部左右侧倾角：左右耳高度差。

    正值=左耳高（头向右歪），负值=右耳高（头向左歪）。
    """
    le = landmarks[LEFT_EAR]
    re = landmarks[RIGHT_EAR]
    if le.visibility < 0.5 or re.visibility < 0.5:
        return None
    dy = re.y - le.y  # 正值=左耳高
    dx = abs(re.x - le.x)
    if dx < 0.001:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


def head_forward_angle(landmarks):
    """头部前倾角：耳朵-肩膀连线与垂直线夹角，取左右平均"""
    le = landmarks[LEFT_EAR]
    re = landmarks[RIGHT_EAR]
    ls = landmarks[LEFT_SHOULDER]
    rs = landmarks[RIGHT_SHOULDER]

    angles = []
    if le.visibility >= 0.5 and ls.visibility >= 0.5:
        angles.append(angle_deg(le.x - ls.x, le.y - ls.y))
    if re.visibility >= 0.5 and rs.visibility >= 0.5:
        angles.append(angle_deg(re.x - rs.x, re.y - rs.y))

    return float(np.mean(angles)) if angles else None


def torso_forward_angle(landmarks):
    """躯干前倾角：肩膀-髋部连线与垂直线夹角，取左右平均"""
    ls = landmarks[LEFT_SHOULDER]
    rs = landmarks[RIGHT_SHOULDER]
    lh = landmarks[LEFT_HIP]
    rh = landmarks[RIGHT_HIP]

    angles = []
    if ls.visibility >= 0.5 and lh.visibility >= 0.5:
        angles.append(angle_deg(ls.x - lh.x, ls.y - lh.y))
    if rs.visibility >= 0.5 and rh.visibility >= 0.5:
        angles.append(angle_deg(rs.x - rh.x, rs.y - rh.y))

    return float(np.mean(angles)) if angles else None


def evaluate_posture(landmarks, thresholds):
    """综合判定坐姿，返回 (is_bad, details_dict, reasons)"""
    st = shoulder_tilt(landmarks)
    ht = head_tilt(landmarks)
    hf = head_forward_angle(landmarks)
    tf = torso_forward_angle(landmarks)

    details = {"shoulder": st, "head_tilt": ht, "neck": hf, "torso": tf}
    reasons = []

    if st is not None:
        tilt = abs(st)
        details["shoulder"] = tilt
        if tilt > thresholds["shoulder"]:
            side = "左肩高右肩低" if st > 0 else "右肩高左肩低"
            reasons.append(f"肩膀歪了（{side}），摆正肩膀 ({tilt:.1f}°)")

    if ht is not None:
        ht_abs = abs(ht)
        details["head_tilt"] = ht_abs
        if ht_abs > thresholds.get("head_tilt", 8.0):
            side = "头向右歪" if ht > 0 else "头向左歪"
            reasons.append(f"{side}，摆正头部 ({ht_abs:.1f}°)")

    if hf is not None and hf > thresholds["neck"]:
        reasons.append(f"头太靠前，往后收下巴 ({hf:.1f}°)")

    if tf is not None and tf > thresholds["torso"]:
        reasons.append(f"身体前倾，坐直挺胸 ({tf:.1f}°)")

    return len(reasons) > 0, details, reasons
