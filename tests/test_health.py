from sit_monitor.health import (
    camera_failure_action,
    watchdog_action,
    CAMERA_FAIL_ALERT_THRESHOLD,
    WATCHDOG_STALE_SECONDS,
    WATCHDOG_MAX_RESTARTS,
)


# ── 相机连续失败告警：只在达到阈值且未告警过时告警一次 ──
def test_camera_alert_at_threshold():
    assert camera_failure_action(CAMERA_FAIL_ALERT_THRESHOLD, False) == "alert"


def test_camera_no_alert_below_threshold():
    assert camera_failure_action(CAMERA_FAIL_ALERT_THRESHOLD - 1, False) == "none"


def test_camera_alert_only_once():
    # 已告警过就不再重复骚扰
    assert camera_failure_action(CAMERA_FAIL_ALERT_THRESHOLD + 99, True) == "none"


def test_camera_no_alert_when_healthy():
    assert camera_failure_action(0, False) == "none"


# ── 看门狗：监控在跑却长时间无检测事件 = 僵死，自愈重启 ──
def test_watchdog_ok_when_recent_event():
    assert watchdog_action(True, WATCHDOG_STALE_SECONDS - 1, 0) == "ok"


def test_watchdog_restart_when_stale():
    assert watchdog_action(True, WATCHDOG_STALE_SECONDS, 0) == "restart"


def test_watchdog_ok_when_monitor_stopped_by_user():
    # 用户主动停止监控时不得擅自重启
    assert watchdog_action(False, 99999.0, 0) == "ok"


def test_watchdog_ok_when_no_data_yet():
    # 刚启动还没有任何检测事件，不算僵死
    assert watchdog_action(True, None, 0) == "ok"


def test_watchdog_gives_up_after_max_restarts():
    # 反复重启仍不好转 → 停止重启，只告警，避免无限重启循环
    assert watchdog_action(True, WATCHDOG_STALE_SECONDS + 60, WATCHDOG_MAX_RESTARTS) == "give_up"


def test_watchdog_still_restarts_below_max():
    assert watchdog_action(True, WATCHDOG_STALE_SECONDS + 60, WATCHDOG_MAX_RESTARTS - 1) == "restart"


def test_watchdog_triggers_when_never_produced_events():
    """回归：监控从启动起就产不出事件时也必须触发。

    调用方须以"启动时刻"作为心跳基准（而非 None），否则最需要看门狗的
    场景（相机始终打不开、初始化卡死）反而永远不触发。
    """
    # 以启动时刻计时、已超过阈值 → 必须重启
    assert watchdog_action(True, WATCHDOG_STALE_SECONDS + 1, 0) == "restart"


# ── 黑帧防御：相机刚重开时自动曝光未启动，帧接近全黑 ──
from sit_monitor.health import is_frame_too_dark, DARK_FRAME_THRESHOLD


def test_dark_frame_detected():
    # 实测：反复开关相机、预热不足时亮度仅 1~3，MediaPipe 必然检测不到人
    assert is_frame_too_dark(2.0) is True


def test_normal_frame_not_dark():
    # 实测：预热充分时亮度约 30~40
    assert is_frame_too_dark(35.8) is False


def test_dark_frame_threshold_boundary():
    assert is_frame_too_dark(DARK_FRAME_THRESHOLD) is False
    assert is_frame_too_dark(DARK_FRAME_THRESHOLD - 0.1) is True
