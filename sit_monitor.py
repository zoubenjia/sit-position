#!/usr/bin/env python3
"""坐姿监控程序 - 使用 MacBook 摄像头检测不良坐姿并发送系统通知"""

import argparse
import math
import os
import signal
import subprocess
import sys
import time

import cv2
import mediapipe as mp
import numpy as np

# 模型文件路径（与脚本同目录）
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pose_landmarker_lite.task")

# 关键点索引（新 API 使用整数索引）
PoseLandmark = mp.tasks.vision.PoseLandmark
LEFT_EAR = PoseLandmark.LEFT_EAR
RIGHT_EAR = PoseLandmark.RIGHT_EAR
LEFT_SHOULDER = PoseLandmark.LEFT_SHOULDER
RIGHT_SHOULDER = PoseLandmark.RIGHT_SHOULDER
LEFT_HIP = PoseLandmark.LEFT_HIP
RIGHT_HIP = PoseLandmark.RIGHT_HIP


def parse_args():
    p = argparse.ArgumentParser(description="坐姿监控：检测不良坐姿并通知")
    p.add_argument("--camera", type=int, default=0, help="摄像头索引 (默认: 0)")
    p.add_argument("--interval", type=float, default=5.0, help="检测间隔/秒 (默认: 5.0)")
    p.add_argument("--bad-seconds", type=int, default=30, help="连续坏姿势多少秒后通知 (默认: 30)")
    p.add_argument("--cooldown", type=int, default=180, help="两次通知最小间隔/秒 (默认: 180)")
    p.add_argument("--debug", action="store_true", help="显示摄像头画面和骨架叠加")
    p.add_argument("--auto-pause", action="store_true", help="人离开时自动暂停视频，回来时恢复")
    p.add_argument("--away-seconds", type=float, default=3.0, help="离开多少秒后暂停 (默认: 3)")
    p.add_argument("--shoulder-threshold", type=float, default=10.0, help="肩膀倾斜角阈值/度 (默认: 10)")
    p.add_argument("--neck-threshold", type=float, default=15.0, help="头部前倾角阈值/度 (默认: 15)")
    p.add_argument("--torso-threshold", type=float, default=8.0, help="躯干前倾角阈值/度 (默认: 8)")
    return p.parse_args()


# --------------- 角度计算 ---------------

def angle_deg(dx, dy):
    """计算向量 (dx, dy) 与垂直向上方向的夹角（度）"""
    return abs(math.degrees(math.atan2(dx, -dy)))


def shoulder_tilt(landmarks):
    """肩膀倾斜角：左右肩高度差形成的角度"""
    ls = landmarks[LEFT_SHOULDER]
    rs = landmarks[RIGHT_SHOULDER]
    if ls.visibility < 0.5 or rs.visibility < 0.5:
        return None
    dx = rs.x - ls.x
    dy = rs.y - ls.y
    return abs(math.degrees(math.atan2(dy, dx)))


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


# --------------- 坐姿判定 ---------------

def evaluate_posture(landmarks, thresholds):
    """综合判定坐姿，返回 (is_bad, details_dict, reasons)"""
    st = shoulder_tilt(landmarks)
    hf = head_forward_angle(landmarks)
    tf = torso_forward_angle(landmarks)

    details = {"shoulder": st, "neck": hf, "torso": tf}
    reasons = []

    if st is not None:
        tilt = abs(st) if st <= 90 else abs(180 - st)
        details["shoulder"] = tilt
        if tilt > thresholds["shoulder"]:
            reasons.append(f"肩膀倾斜 {tilt:.1f}°")

    if hf is not None and hf > thresholds["neck"]:
        reasons.append(f"头部前倾 {hf:.1f}°")

    if tf is not None and tf > thresholds["torso"]:
        reasons.append(f"躯干前倾 {tf:.1f}°")

    return len(reasons) > 0, details, reasons


# --------------- macOS 通知 ---------------

def send_notification(title, message):
    """通过 osascript 弹窗提醒，10 秒后自动关闭"""
    script = (
        f'display dialog "{message}" with title "{title}" '
        f'buttons {{"好的"}} default button 1 giving up after 10'
    )
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------- 媒体播放控制 ---------------

def media_play_pause():
    """激活 Firefox 并发送空格键来暂停/恢复视频"""
    script = (
        'tell application "Firefox" to activate\n'
        'delay 0.3\n'
        'tell application "System Events" to key code 49'
    )
    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


# --------------- debug 绘制 ---------------

def draw_debug(frame, landmarks, is_bad, details):
    """在画面上绘制骨架和指标信息"""
    h, w = frame.shape[:2]
    drawing_utils = mp.tasks.vision.drawing_utils
    connections = mp.tasks.vision.PoseLandmarksConnections.POSE_LANDMARKS

    # 画骨架关键点和连接
    for lm in landmarks:
        px = int(lm.x * w)
        py = int(lm.y * h)
        if lm.visibility >= 0.5:
            cv2.circle(frame, (px, py), 4, (0, 255, 0), -1)

    # 画连接线
    for conn in connections:
        start = landmarks[conn.start]
        end = landmarks[conn.end]
        if start.visibility >= 0.5 and end.visibility >= 0.5:
            pt1 = (int(start.x * w), int(start.y * h))
            pt2 = (int(end.x * w), int(end.y * h))
            cv2.line(frame, pt1, pt2, (0, 200, 0), 2)

    # 状态文字
    color = (0, 0, 255) if is_bad else (0, 255, 0)
    status = "BAD POSTURE" if is_bad else "GOOD"
    cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

    y = 70
    for name, val in details.items():
        text = f"{name}: {val:.1f}" if val is not None else f"{name}: N/A"
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        y += 25


# --------------- 主循环 ---------------

def main():
    args = parse_args()
    thresholds = {
        "shoulder": args.shoulder_threshold,
        "neck": args.neck_threshold,
        "torso": args.torso_threshold,
    }

    # 检查模型文件
    if not os.path.exists(MODEL_PATH):
        print(f"错误: 未找到模型文件 {MODEL_PATH}")
        print("请运行 bash setup.sh 或手动下载:")
        print("  curl -sSL -o pose_landmarker_lite.task \\")
        print("    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")
        sys.exit(1)

    # 信号处理
    running = True

    def on_signal(sig, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    # MediaPipe PoseLandmarker 初始化（新 Tasks API）
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
    last_notify_time = 0
    last_check_time = 0
    away_start_time = None
    media_paused = False
    cap = None
    camera_retry_interval = 5  # 摄像头被占用时每隔几秒重试

    try:
        while running:
            now = time.time()

            # --- 摄像头管理：打开 / 重试 ---
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                cap = cv2.VideoCapture(args.camera)
                if not cap.isOpened():
                    cap.release()
                    cap = None
                    print(f"\r{'⏳ 摄像头被占用，等待释放...':<80}", end="", flush=True)
                    time.sleep(camera_retry_interval)
                    continue
                print(f"\r{'📷 摄像头已连接，开始监控...':<80}", end="", flush=True)

            if now - last_check_time < args.interval:
                if args.debug:
                    cap.grab()
                    ret, frame = cap.retrieve()
                    if ret:
                        cv2.imshow("Sit Monitor (debug)", frame)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break
                    time.sleep(0.03)
                else:
                    time.sleep(0.5)
                continue

            last_check_time = now

            ret, frame = cap.read()
            if not ret:
                # 读帧失败，可能摄像头被其他应用抢占
                cap.release()
                cap = None
                bad_start_time = None
                continue

            # 转换为 MediaPipe Image
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # 检测
            results = landmarker.detect(mp_image)

            person_present = bool(results.pose_landmarks)

            if not person_present:
                bad_start_time = None

                if args.auto_pause:
                    if away_start_time is None:
                        away_start_time = now
                    away_duration = now - away_start_time
                    if not media_paused and away_duration >= args.away_seconds:
                        media_play_pause()
                        media_paused = True
                        status_line = f"⏸ 已暂停播放（离开 {away_duration:.0f}s）"
                    else:
                        status_line = f"未检测到人体 ({away_duration:.0f}s)"
                else:
                    status_line = "未检测到人体"
            else:
                if args.auto_pause and media_paused:
                    media_play_pause()
                    media_paused = False
                away_start_time = None

                lm = results.pose_landmarks[0]
                is_bad, details, reasons = evaluate_posture(lm, thresholds)

                if is_bad:
                    if bad_start_time is None:
                        bad_start_time = now
                    bad_duration = now - bad_start_time

                    if bad_duration >= args.bad_seconds and (now - last_notify_time) >= args.cooldown:
                        msg = "、".join(reasons)
                        send_notification("坐姿提醒", f"请调整姿势：{msg}")
                        last_notify_time = now
                        bad_start_time = now

                    status_line = (
                        f"⚠ 坏姿势 {bad_duration:.0f}s | "
                        + " | ".join(f"{k}:{v:.1f}°" if v else f"{k}:N/A" for k, v in details.items())
                    )
                else:
                    bad_start_time = None
                    status_line = (
                        "✓ 姿势良好 | "
                        + " | ".join(f"{k}:{v:.1f}°" if v else f"{k}:N/A" for k, v in details.items())
                    )

                if args.debug:
                    draw_debug(frame, lm, is_bad, details)

            print(f"\r{status_line:<80}", end="", flush=True)

            if args.debug:
                cv2.imshow("Sit Monitor (debug)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    finally:
        print("\n正在退出...")
        landmarker.close()
        if cap is not None:
            cap.release()
        if args.debug:
            cv2.destroyAllWindows()
        print("已退出。")


if __name__ == "__main__":
    main()
