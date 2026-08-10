"""健康自检：相机故障告警 + 监控僵死看门狗（纯逻辑，可单测）。

事故背景（2026-08-01 → 08-10，整整 9 天无监控无人察觉）：
摄像头权限被拒后，程序只往 stdout 打 OpenCV 报错并静默重试，最终监控停止；
菜单栏图标停在最后状态、看着正常；launchd 的 KeepAlive 只看进程是否存活，
进程在空转所以不重启。三重"静默"叠加 = 用户完全不知道自己没被监控。

这里提供两个判定：
- camera_failure_action：相机连续打不开时**主动告警一次**（不再静默）
- watchdog_action：监控在跑却长时间无检测事件时**自动重启**（自愈），
  反复无效则放弃重启改为告警，避免无限重启循环。
"""

CAMERA_FAIL_ALERT_THRESHOLD = 3    # 连续打不开几次才告警（避免瞬时抖动误报）
WATCHDOG_STALE_SECONDS = 180.0     # 监控在跑却这么久没有新检测事件 = 僵死
WATCHDOG_MAX_RESTARTS = 3          # 连续自动重启上限，超过只告警


def camera_failure_action(consecutive_failures, already_alerted):
    """相机连续打不开时的动作。

    consecutive_failures: 连续打开失败次数
    already_alerted:      本轮故障是否已经告警过（恢复后由调用方清零）

    返回 "alert"（该告警一次）或 "none"。
    """
    if already_alerted:
        return "none"
    if consecutive_failures >= CAMERA_FAIL_ALERT_THRESHOLD:
        return "alert"
    return "none"


def watchdog_action(monitor_running, seconds_since_last_event, restart_count):
    """监控僵死自愈决策。

    monitor_running:          监控是否**应当**在运行（用户没主动停止）
    seconds_since_last_event: 距上次检测事件的秒数；None＝还没有任何事件
    restart_count:            本轮已连续自动重启的次数

    返回 "ok"（正常）/ "restart"（自动重启监控）/ "give_up"（放弃重启，只告警）。
    """
    if not monitor_running:
        return "ok"   # 用户主动停止的，不得擅自重启
    if seconds_since_last_event is None:
        return "ok"   # 刚启动还没数据，不算僵死
    if seconds_since_last_event < WATCHDOG_STALE_SECONDS:
        return "ok"
    if restart_count >= WATCHDOG_MAX_RESTARTS:
        return "give_up"
    return "restart"


# 帧平均亮度低于此值视为"相机尚未就绪的黑帧"，不可用于姿势判定。
# 实测（M4 MacBook 内置摄像头，反复 open/release）：
#   预热 grab5 立即读 → 亮度 1.1~1.8（几乎全黑，MediaPipe 0/8 检测到人）
#   预热 grab10+等0.5s → 亮度 34~37（与相机常开时的 35.8 一致）
# 取 15 作门槛：明显高于黑帧、明显低于正常曝光，暗光环境也不至于误伤。
DARK_FRAME_THRESHOLD = 15.0


def is_frame_too_dark(mean_brightness):
    """帧是否因相机未就绪而过暗（此时不能判定"无人"，否则会误报 away）。"""
    return mean_brightness < DARK_FRAME_THRESHOLD
