"""系统输入空闲读取 + 深度休眠三态决策（纯逻辑，可单测）。

人真不在（摄像头 away 且键鼠长时间空闲）时进入深度休眠：关摄像头、
仅极低频轮询空闲秒数；碰键鼠即唤醒（不做摄像头兜底）。
"""

# 参数（本期为模块常量，未提为 Settings）。
ENTER_IDLE_SECONDS = 300.0       # 进入深度休眠的键鼠空闲门槛（且须同时 away）
WAKE_IDLE_SECONDS = 5.0          # 空闲秒数低于此值＝刚有键鼠输入＝唤醒
DEEP_SLEEP_POLL_SECONDS = 2.0    # 休眠期轻量轮询周期


def read_input_idle_seconds():
    """返回自上次任意键鼠输入以来的秒数；取不到（非 mac / Quartz 异常）返回 None。"""
    try:
        from Quartz import (
            CGEventSourceSecondsSinceLastEventType,
            kCGEventSourceStateHIDSystemState,
        )
        try:
            from Quartz import kCGAnyInputEventType
        except ImportError:
            kCGAnyInputEventType = 0xFFFFFFFF  # ~0：任意输入事件
        return float(CGEventSourceSecondsSinceLastEventType(
            kCGEventSourceStateHIDSystemState, kCGAnyInputEventType))
    except Exception:
        return None


def read_on_ac_power():
    """是否接通电源（AC）。True=插电, False=电池, None=读不到（非 mac / 异常）。"""
    try:
        import subprocess
        out = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3,
        ).stdout
        if "AC Power" in out:
            return True
        if "Battery Power" in out:
            return False
        return None
    except Exception:
        return None


def deep_sleep_decision(in_deep_sleep, is_away, idle_seconds, on_ac_power=None):
    """根据当前状态与信号决定动作。

    in_deep_sleep: 当前是否已处于深度休眠
    is_away:       最近一次摄像头检测是否判定无人（仅用于"进入"判定）
    idle_seconds:  键鼠空闲秒数；None＝取不到（feature 不可用）
    on_ac_power:   是否插电；True=AC（深度休眠是省电功能，插电不进入），
                   False=电池，None=读不到（当作电池，不禁用功能）

    返回 "enter" / "wake" / "stay_sleep" / "none"。
    """
    if not in_deep_sleep:
        if idle_seconds is None:
            return "none"  # 取不到空闲 → 永不进入，退回现有行为
        if on_ac_power is True:
            return "none"  # 插电：保持正常监控，不为省电牺牲姿势检测
        if is_away and idle_seconds >= ENTER_IDLE_SECONDS:
            return "enter"
        return "none"

    # 已在深度休眠：仅靠键鼠唤醒
    if idle_seconds is None:
        return "wake"  # failsafe：信号不可用就唤醒回正常检测
    if idle_seconds < WAKE_IDLE_SECONDS:
        return "wake"  # 刚有键鼠输入
    return "stay_sleep"
