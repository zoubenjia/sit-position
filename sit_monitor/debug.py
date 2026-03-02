"""Debug 模式下的 OpenCV 叠加绘制"""

import cv2
import mediapipe as mp


def draw_debug(frame, landmarks, is_bad, details):
    """在画面上绘制骨架和指标信息"""
    h, w = frame.shape[:2]
    connections = mp.tasks.vision.PoseLandmarksConnections.POSE_LANDMARKS

    for lm in landmarks:
        px = int(lm.x * w)
        py = int(lm.y * h)
        if lm.visibility >= 0.5:
            cv2.circle(frame, (px, py), 4, (0, 255, 0), -1)

    for conn in connections:
        start = landmarks[conn.start]
        end = landmarks[conn.end]
        if start.visibility >= 0.5 and end.visibility >= 0.5:
            pt1 = (int(start.x * w), int(start.y * h))
            pt2 = (int(end.x * w), int(end.y * h))
            cv2.line(frame, pt1, pt2, (0, 200, 0), 2)

    color = (0, 0, 255) if is_bad else (0, 255, 0)
    status = "BAD POSTURE" if is_bad else "GOOD"
    cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

    y = 70
    for name, val in details.items():
        text = f"{name}: {val:.1f}" if val is not None else f"{name}: N/A"
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        y += 25
