#!/usr/bin/env python3
"""坐姿监控程序 - 使用 MacBook 摄像头检测不良坐姿并发送系统通知"""

import argparse
import json
import logging
import math
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

import cv2
import mediapipe as mp
import numpy as np

# 模型文件路径（与脚本同目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "pose_landmarker_lite.task")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")


def setup_logging():
    """配置结构化日志，写入 logs/posture.jsonl"""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("posture")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(os.path.join(LOG_DIR, "posture.jsonl"), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def log_event(logger, event_type, **kwargs):
    """写入一条 JSON 日志"""
    record = {"ts": datetime.now().isoformat(), "event": event_type, **kwargs}
    logger.info(json.dumps(record, ensure_ascii=False))


class Stats:
    """运行期间的统计计数器"""
    def __init__(self):
        self.start_time = time.time()
        self.total_checks = 0
        self.good_count = 0
        self.bad_count = 0
        self.no_person_count = 0
        self.notifications_sent = 0
        self.sit_notifications_sent = 0
        self.bad_seconds_total = 0.0
        self.good_seconds_total = 0.0
        self._last_state = None  # "good" / "bad" / None
        self._last_state_time = None

    def record(self, state, now):
        """记录一次检测结果，state: 'good'/'bad'/'away'"""
        self.total_checks += 1
        if state == "good":
            self.good_count += 1
        elif state == "bad":
            self.bad_count += 1
        else:
            self.no_person_count += 1

        # 累计好/坏姿势持续时长
        if self._last_state in ("good", "bad") and self._last_state_time:
            dt = now - self._last_state_time
            if self._last_state == "good":
                self.good_seconds_total += dt
            else:
                self.bad_seconds_total += dt

        self._last_state = state
        self._last_state_time = now

    def summary(self):
        """返回统计摘要字符串"""
        elapsed = time.time() - self.start_time
        mins = elapsed / 60
        bad_pct = (self.bad_seconds_total / (self.good_seconds_total + self.bad_seconds_total) * 100
                   if (self.good_seconds_total + self.bad_seconds_total) > 0 else 0)
        lines = [
            f"运行时长: {mins:.1f} 分钟",
            f"总检测次数: {self.total_checks}",
            f"  姿势良好: {self.good_count} 次 ({self.good_seconds_total/60:.1f} 分钟)",
            f"  姿势不良: {self.bad_count} 次 ({self.bad_seconds_total/60:.1f} 分钟, {bad_pct:.0f}%)",
            f"  人不在位: {self.no_person_count} 次",
            f"坐姿提醒: {self.notifications_sent} 次",
            f"久坐提醒: {self.sit_notifications_sent} 次",
        ]
        return "\n".join(lines)

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
    p.add_argument("--browser", type=str, default=None, help="浏览器名称 (默认: 自动检测，支持 Firefox/Chrome/Safari/Arc)")
    p.add_argument("--shoulder-threshold", type=float, default=7.0, help="肩膀倾斜角阈值/度 (默认: 7)")
    p.add_argument("--neck-threshold", type=float, default=10.0, help="头部前倾角阈值/度 (默认: 10)")
    p.add_argument("--torso-threshold", type=float, default=5.0, help="躯干前倾角阈值/度 (默认: 5)")
    p.add_argument("--sit-max-minutes", type=int, default=45, help="连续就坐多少分钟后提醒休息 (默认: 45)")
    p.add_argument("--sound", action="store_true", help="启用语音播报提醒")
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

def send_notification(title, message, sound=False):
    """通过 osascript 弹窗提醒，10 秒后自动关闭。可选语音播报。"""
    safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
    safe_msg = message.replace('\\', '\\\\').replace('"', '\\"')
    script = (
        f'display dialog "{safe_msg}" with title "{safe_title}" '
        f'buttons {{"好的"}} default button 1 giving up after 10'
    )
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sound:
        # 先播系统提示音，再语音播报内容（去掉换行符）
        speech = message.replace("\n", "，")
        subprocess.Popen(["say", "-v", "Tingting", speech], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------- 媒体播放控制 ---------------

_BROWSERS = ["Firefox", "Google Chrome", "Safari", "Arc", "Brave Browser", "Microsoft Edge"]

# Chrome 系浏览器支持 AppleScript 执行 JS（可控制任意 tab 的视频）
_JS_BROWSERS = {"Google Chrome", "Arc", "Brave Browser", "Microsoft Edge"}

_VIDEO_JS = "document.querySelectorAll('video').forEach(v => v.paused ? v.play() : v.pause())"


def _detect_browser():
    """检测当前运行的浏览器"""
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of every process whose background only is false'],
        capture_output=True, text=True,
    )
    running = result.stdout.strip()
    for b in _BROWSERS:
        if b in running:
            return b
    return None


def media_play_pause(browser=None):
    """暂停/恢复浏览器视频。Chrome 系用 JS 直控，其他用空格键。"""
    target = browser or _detect_browser()
    if not target:
        return

    if target in _JS_BROWSERS:
        # Chrome 系：遍历所有 tab 找到有视频的，直接 JS 控制（不受前台 tab 限制）
        script = (
            f'tell application "{target}"\n'
            f'  repeat with w in windows\n'
            f'    repeat with t in tabs of w\n'
            f'      execute t javascript "{_VIDEO_JS}"\n'
            f'    end repeat\n'
            f'  end repeat\n'
            f'end tell'
        )
    elif target == "Safari":
        # Safari 用自己的 do JavaScript 语法
        script = (
            f'tell application "Safari"\n'
            f'  repeat with d in documents\n'
            f'    do JavaScript "{_VIDEO_JS}" in d\n'
            f'  end repeat\n'
            f'end tell'
        )
    else:
        # Firefox 等不支持 JS 注入的浏览器：激活窗口 + 空格键
        script = (
            f'tell application "{target}" to activate\n'
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

    # 初始化日志和统计
    logger = setup_logging()
    stats = Stats()
    log_event(logger, "start", thresholds=thresholds, sit_max_minutes=args.sit_max_minutes)

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
    sit_start_time = None       # 连续就坐开始时间
    last_sit_notify_time = 0    # 上次久坐提醒时间
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

            wait = args.interval - (now - last_check_time)
            if wait > 0:
                if args.debug:
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
                stats.record("away", now)
                # 离开超过 1 分钟视为真正休息，重置久坐计时
                if away_start_time is not None and (now - away_start_time) >= 60:
                    sit_start_time = None

                if args.auto_pause:
                    if away_start_time is None:
                        away_start_time = now
                    away_duration = now - away_start_time
                    if not media_paused and away_duration >= args.away_seconds:
                        media_play_pause(args.browser)
                        media_paused = True
                        status_line = f"⏸ 已暂停播放（离开 {away_duration:.0f}s）"
                    else:
                        status_line = f"未检测到人体 ({away_duration:.0f}s)"
                else:
                    if away_start_time is None:
                        away_start_time = now
                    status_line = "未检测到人体"
            else:
                if args.auto_pause and media_paused:
                    media_play_pause(args.browser)
                    media_paused = False
                away_start_time = None

                # 久坐计时
                if sit_start_time is None:
                    sit_start_time = now
                sit_minutes = (now - sit_start_time) / 60

                # 久坐提醒：每到一个周期提醒一次
                sit_max_seconds = args.sit_max_minutes * 60
                if (now - sit_start_time) >= sit_max_seconds and (now - last_sit_notify_time) >= sit_max_seconds:
                    send_notification("久坐提醒", f"你已经连续坐了 {sit_minutes:.0f} 分钟，起来活动一下吧！", sound=args.sound)
                    log_event(logger, "sit_alert", sit_minutes=round(sit_minutes, 1))
                    stats.sit_notifications_sent += 1
                    last_sit_notify_time = now

                lm = results.pose_landmarks[0]
                is_bad, details, reasons = evaluate_posture(lm, thresholds)

                # 记录日志和统计
                log_data = {k: round(v, 1) if v is not None else None for k, v in details.items()}
                log_data["sit_minutes"] = round(sit_minutes, 1)
                if is_bad:
                    stats.record("bad", now)
                    log_event(logger, "bad", reasons=[r for r in reasons], **log_data)
                else:
                    stats.record("good", now)
                    log_event(logger, "good", **log_data)

                # 坏姿势也可能是坐太久导致的，加入提示
                if is_bad:
                    if bad_start_time is None:
                        bad_start_time = now
                    bad_duration = now - bad_start_time

                    if bad_duration >= args.bad_seconds and (now - last_notify_time) >= args.cooldown:
                        msg = "、".join(reasons)
                        if sit_minutes >= args.sit_max_minutes:
                            msg += f"\n（已连续就坐 {sit_minutes:.0f} 分钟，建议起来休息）"
                        send_notification("坐姿提醒", f"请调整姿势：{msg}", sound=args.sound)
                        log_event(logger, "posture_alert", reasons=[r for r in reasons], sit_minutes=round(sit_minutes, 1))
                        stats.notifications_sent += 1
                        last_notify_time = now
                        bad_start_time = now

                    status_line = (
                        f"⚠ 坏姿势 {bad_duration:.0f}s | 就坐 {sit_minutes:.0f}min | "
                        + " | ".join(f"{k}:{v:.1f}°" if v else f"{k}:N/A" for k, v in details.items())
                    )
                else:
                    bad_start_time = None
                    status_line = (
                        f"✓ 姿势良好 | 就坐 {sit_minutes:.0f}min | "
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
        # 最后一次统计更新
        stats.record(None, time.time())
        summary = stats.summary()
        log_event(logger, "stop",
                  total_checks=stats.total_checks,
                  good_count=stats.good_count,
                  bad_count=stats.bad_count,
                  good_minutes=round(stats.good_seconds_total / 60, 1),
                  bad_minutes=round(stats.bad_seconds_total / 60, 1),
                  notifications=stats.notifications_sent,
                  sit_notifications=stats.sit_notifications_sent)

        print("\n\n" + "=" * 40)
        print("📊 本次坐姿监控统计")
        print("=" * 40)
        print(summary)
        print("=" * 40)

        landmarker.close()
        if cap is not None:
            cap.release()
        if args.debug:
            cv2.destroyAllWindows()
        print("已退出。")


if __name__ == "__main__":
    main()
