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
WATCHDOG_MAX_RESTARTS = 3          # 快速重启上限，超过转入冷却期
WATCHDOG_COOLDOWN_SECONDS = 900.0  # 冷却期：放弃快速重启后每 15 分钟再试一次


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
        # 不能永久躺平：故障（如相机被占）往往几分钟后自行恢复。
        # 实测 2026-08-15：快速重启 3 次后放弃，相机 10 分钟后就好了，
        # 监控却一直停到 3 小时后人工干预。改为冷却期后继续低频重试。
        if seconds_since_last_event >= WATCHDOG_COOLDOWN_SECONDS:
            return "restart"
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


# ── 电量分级策略 ──────────────────────────────────────────────
# 实测（2026-09-08，M4 MacBook）：常驻监控平均占用 17.8% CPU，
# 每 5.8s 开一次摄像头跑一轮推理，坏姿势时加密到 2s 一轮——对电池是实打实的负担。
# 低电量时按级降频，把电留给用户干活。
#
# 进入/退出用不同阈值（滞回）：否则电量在阈值附近浮动会反复切换模式。
POWER_SAVER_ENTER = 20      # ≤此电量进入省电
POWER_SAVER_EXIT = 25       # 回升到此电量才退出省电
POWER_CRITICAL_ENTER = 10   # ≤此电量进入极低频
POWER_CRITICAL_EXIT = 15    # 回升到此电量才退出极低频

CRITICAL_INTERVAL_SECONDS = 60.0  # 极低频模式的固定检测间隔
SAVER_BAD_INTERVAL = 5.0          # 省电模式下坏姿势的加密间隔（正常是 2s）


def power_mode(battery_percent, on_ac_power, current_mode="normal"):
    """按电量决定运行模式："normal" / "saver" / "critical"。

    battery_percent: 电量百分比；None＝读不到
    on_ac_power:     是否插电（True 立即回正常，省电功能对插电无意义）
    current_mode:    当前所处模式，用于滞回判定

    低电量不完全停止监控——恰恰是赶工时最容易含胸驼背，
    故降到极低频兜底而非彻底让路。
    """
    if on_ac_power is True:
        return "normal"
    if battery_percent is None:
        return "normal"   # 读不到电量不擅自降级行为

    p = battery_percent
    # critical 判定（已在其中则用退出阈值）
    if current_mode == "critical":
        if p < POWER_CRITICAL_EXIT:
            return "critical"
    elif p <= POWER_CRITICAL_ENTER:
        return "critical"

    # saver 判定（从 critical 回升也先降到 saver，逐级恢复）
    if current_mode in ("saver", "critical"):
        if p < POWER_SAVER_EXIT:
            return "saver"
    elif p <= POWER_SAVER_ENTER:
        return "saver"

    return "normal"


def power_adjusted_interval(mode, normal_interval, bad_active):
    """按电源模式调整检测间隔。

    mode:            power_mode() 的结果
    normal_interval: 正常模式下算出的间隔（含动态退避）
    bad_active:      当前是否处于坏姿势加密状态
    """
    if mode == "critical":
        return CRITICAL_INTERVAL_SECONDS
    if mode == "saver":
        return SAVER_BAD_INTERVAL if bad_active else normal_interval * 2
    return normal_interval
